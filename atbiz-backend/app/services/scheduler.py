import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.services.ingestion_service import IngestionService
from app.database import get_supabase
from app.config import settings

class SyncScheduler:
    INTERVAL_SECONDS = 6 * 3600  # 6 hours

    def __init__(self):
        self.last_synced_at: Optional[datetime] = None
        self.last_stats: Dict[str, Any] = {}
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self.current_run_id: Optional[str] = None

    def get_status(self) -> Dict[str, Any]:
        """Returns the current scheduler state, last updated time, and next sync countdown."""
        next_sync = None
        seconds_remaining = None
        if self.last_synced_at:
            next_dt = self.last_synced_at + timedelta(seconds=self.INTERVAL_SECONDS)
            next_sync = next_dt.isoformat() + "Z"
            seconds_remaining = max(0, int((next_dt - datetime.utcnow()).total_seconds()))

        return {
            "is_scheduler_active": self.is_running,
            "sync_interval_hours": 6,
            "last_synced_at": (self.last_synced_at.isoformat() + "Z") if self.last_synced_at else None,
            "next_scheduled_sync": next_sync,
            "seconds_until_next_sync": seconds_remaining,
            "last_sync_stats": self.last_stats,
            "is_syncing": self.current_run_id is not None
        }

    def _acquire_db_lock(self, triggered_by: str = "scheduler", stale_minutes: int = 10) -> Optional[str]:
        """Attempt to acquire distributed sync lock via Postgres start_sync_run function."""
        supabase = get_supabase()
        try:
            res = supabase.rpc("start_sync_run", {
                "p_tenant_id": settings.DEFAULT_TENANT_ID,
                "p_triggered_by": triggered_by,
                "p_stale_minutes": stale_minutes
            }).execute()
            return res.data
        except Exception:
            # Fallback if migration not yet applied
            return f"local_{datetime.utcnow().timestamp()}"

    def _send_heartbeat(self, run_id: str) -> bool:
        """Update heartbeat_at in Postgres. Returns False if cancelled or expired."""
        if str(run_id).startswith("local_"):
            return True
        supabase = get_supabase()
        try:
            res = supabase.rpc("heartbeat_sync_run", {"p_run_id": run_id}).execute()
            return bool(res.data)
        except Exception:
            return True

    def _finish_db_run(self, run_id: str, status: str, stats: Dict[str, Any], errors: list):
        """Record completion in sync_runs table."""
        if str(run_id).startswith("local_"):
            return
        supabase = get_supabase()
        try:
            supabase.rpc("finish_sync_run", {
                "p_run_id": run_id,
                "p_status": status,
                "p_stats": stats,
                "p_errors": errors
            }).execute()
        except Exception:
            pass

    async def _heartbeat_loop(self, run_id: str, stop_event: asyncio.Event):
        """Background task sending heartbeat every 45 seconds."""
        while not stop_event.is_set():
            try:
                await asyncio.sleep(45)
                if stop_event.is_set():
                    break
                is_alive = await asyncio.to_thread(self._send_heartbeat, run_id)
                if not is_alive:
                    print(f"[Scheduler] Run {run_id} was expired or cancelled by another process.")
                    break
            except Exception as e:
                print(f"[Scheduler] Heartbeat error: {e}")

    def run_sync_sync(self, triggered_by: str = "scheduler") -> Dict[str, Any]:
        """Synchronous sync runner with heartbeat lock."""
        run_id = self._acquire_db_lock(triggered_by=triggered_by)
        if not run_id:
            return {
                "status": "already_running",
                "message": "A sync is already active for this tenant. Please wait."
            }

        self.current_run_id = run_id
        service = IngestionService()
        stats = {
            "total_scanned": 0,
            "newly_ingested": 0,
            "skipped_duplicates": 0,
            "renamed_in_drive": 0,
            "unchanged_files": 0,
            "errors": []
        }
        sync_status = "completed"

        try:
            stats = service.run_gdrive_sync()
            if stats.get("errors"):
                sync_status = "completed" if (stats.get("newly_ingested", 0) + stats.get("unchanged_files", 0)) > 0 else "failed"
            self.last_synced_at = datetime.utcnow()
            self.last_stats = stats
            return stats
        except Exception as e:
            sync_status = "failed"
            stats["errors"].append({"error": str(e), "at": datetime.utcnow().isoformat()})
            raise e
        finally:
            self._finish_db_run(run_id, sync_status, stats, stats.get("errors", []))
            self.current_run_id = None

    async def run_sync_once(self, triggered_by: str = "scheduler") -> Dict[str, Any]:
        """Asynchronously trigger sync without blocking event loop."""
        run_id = await asyncio.to_thread(self._acquire_db_lock, triggered_by)
        if not run_id:
            return {
                "status": "already_running",
                "message": "A sync is already active for this tenant."
            }

        self.current_run_id = run_id
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(run_id, stop_event))

        service = IngestionService()
        sync_status = "completed"
        stats = {}
        try:
            stats = await asyncio.to_thread(service.run_gdrive_sync)
            self.last_synced_at = datetime.utcnow()
            self.last_stats = stats
            return stats
        except Exception as e:
            sync_status = "failed"
            stats = {"errors": [{"error": str(e)}]}
            raise e
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            await asyncio.to_thread(self._finish_db_run, run_id, sync_status, stats, stats.get("errors", []))
            self.current_run_id = None

    async def _loop(self):
        self.is_running = True
        # Run first sync on startup after 5 seconds
        await asyncio.sleep(5)
        while self.is_running:
            try:
                print(f"[{datetime.utcnow().isoformat()}] Starting scheduled 6-hour Google Drive sync...")
                await self.run_sync_once(triggered_by="scheduler")
                print(f"[{datetime.utcnow().isoformat()}] 6-hour sync complete. Next sync in 6 hours.")
            except Exception as e:
                print(f"Error during scheduled sync: {e}")
            await asyncio.sleep(self.INTERVAL_SECONDS)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()

scheduler = SyncScheduler()
