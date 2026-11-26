from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File, Form
from typing import Optional
from datetime import datetime
from app.services.ingestion_service import IngestionService
from app.services.scheduler import scheduler
from app.database import get_supabase
from app.config import settings

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])

@router.get("/status")
def get_sync_status(tenant_id: Optional[str] = None):
    """
    Returns sync status, last updated timestamp, countdown to next 6-hour sync,
    and total candidates in database.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    status = scheduler.get_status()

    # Query live candidate count, duplicates count, and latest ingestion time
    try:
        sb = get_supabase()
        res = sb.table("candidates").select("id, created_at, extracted_attributes", count="exact").eq("tenant_id", t_id).order("created_at", desc=True).execute()
        cands_data = res.data or []
        total_unique = len(cands_data)

        # Count duplicate resume files and candidates with duplicates
        duplicate_files_count = 0
        candidates_with_duplicates = 0
        for c in cands_data:
            attrs = c.get("extracted_attributes") or {}
            dup_files = attrs.get("duplicate_files") or []
            flags = attrs.get("flags") or []
            if dup_files:
                duplicate_files_count += len(dup_files)
                candidates_with_duplicates += 1
            elif "duplicate_resume_uploaded" in flags:
                duplicate_files_count += 1
                candidates_with_duplicates += 1

        total_scanned = scheduler.last_stats.get("total_scanned") or (total_unique + duplicate_files_count)
        # Duplicate resumes are the extra copies uploaded beyond unique candidate identities
        duplicates_count = duplicate_files_count if duplicate_files_count > 0 else max(0, total_scanned - total_unique)

        status["total_candidates"] = total_unique
        status["total_scanned"] = total_scanned
        status["total_duplicates"] = duplicates_count
        status["candidates_with_duplicates"] = candidates_with_duplicates
        status["last_synced_resumes_count"] = total_scanned

        if not status["last_synced_at"] and cands_data:
            latest_cand_time = cands_data[0].get("created_at")
            if latest_cand_time:
                status["last_synced_at"] = latest_cand_time
                # Estimate next sync based on last candidate creation + 6 hours
                try:
                    from datetime import datetime, timedelta
                    dt = datetime.fromisoformat(latest_cand_time.replace("Z", "+00:00"))
                    next_dt = dt + timedelta(hours=6)
                    status["next_scheduled_sync"] = next_dt.isoformat()
                    now = datetime.now(dt.tzinfo)
                    status["seconds_until_next_sync"] = max(0, int((next_dt - now).total_seconds()))
                except Exception:
                    pass
    except Exception as e:
        print(f"Error fetching sync status: {e}")
        status["total_candidates"] = 0
        status["total_scanned"] = 0
        status["total_duplicates"] = 0
        status["candidates_with_duplicates"] = 0
        status["last_synced_resumes_count"] = 0

    return status

@router.post("/sync")
def trigger_sync(
    background_tasks: BackgroundTasks,
    root_folder_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    force: bool = False
):
    """
    Manually trigger Google Drive resume sync in the background.
    Returns HTTP 409 Conflict if another sync is already active for this tenant.
    Pass force=True to unlock/expire any stuck sync run.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    stale_mins = 0 if force else 10
    run_id = scheduler._acquire_db_lock(triggered_by="manual", stale_minutes=stale_mins)
    if not run_id:
        raise HTTPException(
            status_code=409,
            detail="A sync is already active for this tenant. Please wait for it to complete."
        )

    def run_worker():
        service = IngestionService(tenant_id=t_id)
        scheduler.current_run_id = run_id
        stats = {}
        sync_status = "completed"
        try:
            stats = service.run_gdrive_sync(root_folder_id=root_folder_id)
            scheduler.last_synced_at = datetime.utcnow()
            scheduler.last_stats = stats
        except Exception as e:
            sync_status = "failed"
            stats = {"errors": [{"error": str(e), "at": datetime.utcnow().isoformat()}]}
        finally:
            scheduler._finish_db_run(run_id, sync_status, stats, stats.get("errors", []))
            scheduler.current_run_id = None

    background_tasks.add_task(run_worker)
    return {
        "status": "started",
        "run_id": run_id,
        "message": "Google Drive resume ingestion has started in the background."
    }

@router.get("/runs")
def list_sync_runs(limit: int = 10, tenant_id: Optional[str] = None):
    """Observability endpoint: Returns recent sync run records and their stats/errors."""
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()
    try:
        res = supabase.table("sync_runs").select("*").eq("tenant_id", t_id).order("started_at", desc=True).limit(limit).execute()
        return {"runs": res.data or []}
    except Exception as e:
        return {"runs": [], "error": str(e)}

@router.post("/sync-local")
def trigger_local_sync(
    local_path: str,
    tenant_id: Optional[str] = None
):
    """
    Test resume ingestion from a local folder structured as:
    local_path / Client / Site / Role / resume.pdf
    """
    service = IngestionService(tenant_id=tenant_id)
    try:
        stats = service.run_local_sync(local_path)
        return {
            "status": "completed",
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/upload")
async def upload_single_resume(
    file: UploadFile = File(...),
    client_name: str = Form(...),
    site_name: str = Form(...),
    role_name: str = Form(...),
    tenant_id: Optional[str] = None
):
    """
    Directly upload a resume for instant parsing and DB ingestion.
    """
    service = IngestionService(tenant_id=tenant_id)
    content = await file.read()
    
    file_data = {
        "file_id": f"upload_{file.filename}",
        "file_name": file.filename,
        "client_name": client_name,
        "site_name": site_name,
        "role_name": role_name,
        "folder_path": f"/{client_name}/{site_name}/{role_name}/{file.filename}",
        "file_bytes": content,
        "web_link": None
    }
    
    try:
        result = service.ingest_single_file(file_data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/init-drive-folders")
def initialize_drive_folders(
    root_folder_id: Optional[str] = None,
    tenant_id: Optional[str] = None
):
    """
    Checks your Google Drive and automatically creates the full folder hierarchy 
    (Client -> Site -> Role) for all records in the database if they don't already exist.
    """
    service = IngestionService(tenant_id=tenant_id)
    try:
        result = service.provision_drive_folders(root_folder_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

