from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.database import get_supabase
from app.config import settings

router = APIRouter(prefix="/api/candidates", tags=["Candidates"])

# Stage to Display Status mapping
STAGE_TO_DISPLAY = {
    "applied": "New",
    "screened": "Ready for AI Call",
    "interview_scheduled": "AI Call Initiated",
    "interviewed": "AI Call Completed",
    "offered": "Offer Sent",
    "onboarding": "Accepted",
    "joined": "Accepted",
    "rejected": "Rejected",
}

DISPLAY_TO_STAGE = {
    "New": ("applied", "active"),
    "Ready for AI Call": ("screened", "active"),
    "AI Call Initiated": ("interview_scheduled", "active"),
    "AI Call Completed": ("interviewed", "active"),
    "Offer Sent": ("offered", "active"),
    "Accepted": ("joined", "active"),
    "Rejected": ("rejected", "rejected"),
}


@router.get("/meta/tree")
def get_clients_and_sites_tree(tenant_id: Optional[str] = None):
    """
    Returns the Clients -> Sites -> Roles/Positions hierarchy with real-time candidate counts
    for the Resume Desk sidebar.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    # 1. Fetch clients
    clients = supabase.table("clients").select("id, code, name").eq("tenant_id", t_id).execute().data or []

    # 2. Fetch sites
    sites = supabase.table("client_sites").select("id, client_id, state, site_name, site_code").eq("tenant_id", t_id).execute().data or []

    # 3. Fetch applications and candidates to compute candidate counts and positions
    apps = supabase.table("applications").select("client_id, site_id, candidate_id").eq("tenant_id", t_id).execute().data or []
    cands = supabase.table("candidates").select("id, drive_folder_path, extracted_attributes").eq("tenant_id", t_id).execute().data or []
    cands_map = {c["id"]: c for c in cands}

    site_counts = {}
    client_counts = {}
    site_roles = {}  # { site_id: { role_name: count } }

    for a in apps:
        c_id = a.get("client_id")
        s_id = a.get("site_id")
        cand_id = a.get("candidate_id")
        cand = cands_map.get(cand_id)
        if not cand:
            continue
        if c_id:
            client_counts[c_id] = client_counts.get(c_id, 0) + 1
        if s_id:
            site_counts[s_id] = site_counts.get(s_id, 0) + 1
            attrs = cand.get("extracted_attributes") or {}
            locs = attrs.get("locations_present") or []
            matched_loc = next((l for l in locs if l.get("site_id") == s_id), None)
            if matched_loc and matched_loc.get("role_name"):
                role = matched_loc["role_name"]
            else:
                parts = [p.strip() for p in (cand.get("drive_folder_path") or "").strip("/").split("/") if p.strip()]
                role = parts[2] if len(parts) >= 3 else "General"
            site_roles.setdefault(s_id, {})
            site_roles[s_id][role] = site_roles[s_id].get(role, 0) + 1

    # 4. Fetch active drive_tree from tenant settings
    drive_tree = None
    try:
        t_res = supabase.table("tenants").select("settings").eq("id", t_id).execute()
        if t_res.data:
            drive_tree = (t_res.data[0].get("settings") or {}).get("drive_tree")
    except Exception:
        pass

    def _normalize(s: str) -> str:
        import re
        return re.sub(r'[^a-zA-Z0-9]', '', s or '').lower()

    tree = []
    for c in clients:
        c_id = c["id"]
        c_count = client_counts.get(c_id, 0)
        c_sites = [s for s in sites if s["client_id"] == c_id]

        matched_drive_client_sites = None
        if drive_tree:
            c_name_norm = _normalize(c.get("name"))
            c_code_norm = _normalize(c.get("code"))
            for drive_c_name, drive_c_sites in drive_tree.items():
                dc_norm = _normalize(drive_c_name)
                if dc_norm in c_name_norm or c_name_norm in dc_norm or dc_norm == c_code_norm:
                    matched_drive_client_sites = drive_c_sites
                    break

        # If drive_tree is active and this client folder was deleted/not in Drive, and has 0 candidates, omit it
        if drive_tree is not None and matched_drive_client_sites is None and c_count == 0:
            continue

        site_items = []
        for s in c_sites:
            s_id = s["id"]
            s_count = site_counts.get(s_id, 0)

            matched_drive_roles = None
            if matched_drive_client_sites is not None:
                s_state_norm = _normalize(s.get("state"))
                s_name_norm = _normalize(s.get("site_name"))
                s_code_norm = _normalize(s.get("site_code"))
                for drive_s_name, drive_roles in matched_drive_client_sites.items():
                    ds_norm = _normalize(drive_s_name)
                    if ds_norm == s_state_norm or ds_norm in s_name_norm or s_state_norm in ds_norm or ds_norm == s_code_norm:
                        matched_drive_roles = drive_roles
                        break

            # If drive_tree is active and this site folder was deleted/not in Drive, and has 0 candidates, omit it
            if matched_drive_client_sites is not None and matched_drive_roles is None and s_count == 0:
                continue

            # Roles under site: active in Drive or having active candidates
            roles_set = set()
            if matched_drive_roles is not None:
                roles_set.update(matched_drive_roles)
            roles_set.update(site_roles.get(s_id, {}).keys())

            role_items = [
                {"name": role_name, "count": site_roles.get(s_id, {}).get(role_name, 0)}
                for role_name in roles_set
            ]
            role_items.sort(key=lambda x: (-x["count"], x["name"]))

            site_items.append({
                "id": s["id"],
                "state": s["state"],
                "name": s["site_name"] or s["state"],
                "count": s_count,
                "roles": role_items
            })

        tree.append({
            "id": c["id"],
            "code": c["code"],
            "name": c["name"],
            "count": c_count,
            "sites": site_items
        })

    return {
        "total_count": len(cands),
        "tree": tree
    }


@router.get("")
def list_candidates(
    client_id: Optional[str] = None,
    site_id: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
    sort_by: Optional[str] = "created_at",
    sort_order: Optional[str] = "desc",
    tenant_id: Optional[str] = None
):
    """
    Fast query endpoint for Dashboard with site, client, role/position filters, status, search,
    sorting, and pagination.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    start = (page - 1) * limit
    end = start + limit - 1

    query = supabase.table("candidates")\
        .select("id, first_name, last_name, email, phone, dob, location, last_qualification, drive_file_id, drive_folder_path, extracted_attributes, created_at", count="exact")\
        .eq("tenant_id", t_id)

    if search:
        query = query.or_(f"first_name.ilike.%{search}%,phone.ilike.%{search}%,email.ilike.%{search}%,location.ilike.%{search}%")

    # Candidate ID filters from role, site, client, or status
    filtered_candidate_ids = None

    if role:
        if site_id:
            # Candidate must have this role specifically at this site
            # 1. Via multi-location entry
            m1 = supabase.table("candidates").select("id").eq("tenant_id", t_id).contains(
                "extracted_attributes", {"locations_present": [{"site_id": site_id, "role_name": role}]}
            ).execute().data or []
            # 2. Or via drive folder path
            m2 = supabase.table("candidates").select("id").eq("tenant_id", t_id).ilike("drive_folder_path", f"%/{role}/%").execute().data or []
            role_cand_ids = set(c["id"] for c in m1).union(c["id"] for c in m2)
            filtered_candidate_ids = role_cand_ids
        elif client_id:
            # Candidate must have this role at this client
            m1 = supabase.table("candidates").select("id").eq("tenant_id", t_id).contains(
                "extracted_attributes", {"locations_present": [{"client_id": client_id, "role_name": role}]}
            ).execute().data or []
            m2 = supabase.table("candidates").select("id").eq("tenant_id", t_id).ilike("drive_folder_path", f"%/{role}/%").execute().data or []
            role_cand_ids = set(c["id"] for c in m1).union(c["id"] for c in m2)
            filtered_candidate_ids = role_cand_ids
        else:
            # Global role filter
            m1 = supabase.table("candidates").select("id").eq("tenant_id", t_id).ilike("drive_folder_path", f"%/{role}/%").execute().data or []
            m2 = supabase.table("candidates").select("id").eq("tenant_id", t_id).contains(
                "extracted_attributes", {"locations_present": [{"role_name": role}]}
            ).execute().data or []
            filtered_candidate_ids = set([c["id"] for c in m1] + [c["id"] for c in m2])

    # If site_id, client_id, or status is filtered, join through applications
    if site_id or client_id or status:
        app_query = supabase.table("applications").select("candidate_id, stage, status").eq("tenant_id", t_id)
        if site_id:
            app_query = app_query.eq("site_id", site_id)
        if client_id:
            app_query = app_query.eq("client_id", client_id)
        if status and status.lower() != "all":
            mapped_stage, _ = DISPLAY_TO_STAGE.get(status, (status.lower(), "active"))
            app_query = app_query.eq("stage", mapped_stage)

        app_res = app_query.execute()
        app_cand_ids = set(row["candidate_id"] for row in (app_res.data or []))
        if filtered_candidate_ids is not None:
            filtered_candidate_ids = filtered_candidate_ids.intersection(app_cand_ids)
        else:
            filtered_candidate_ids = app_cand_ids

    # When both role and site_id/client_id are filtered, ensure exact alignment with meta/tree role resolution
    if role and (site_id or client_id) and filtered_candidate_ids:
        c_rows = supabase.table("candidates").select("id, drive_folder_path, extracted_attributes").in_("id", list(filtered_candidate_ids)).execute().data or []
        verified_ids = set()
        for cand in c_rows:
            attrs = cand.get("extracted_attributes") or {}
            locs = attrs.get("locations_present") or []
            cand_role = None
            if site_id:
                matched_loc = next((l for l in locs if l.get("site_id") == site_id), None)
                if matched_loc and matched_loc.get("role_name"):
                    cand_role = matched_loc["role_name"]
            elif client_id:
                matched_loc = next((l for l in locs if l.get("client_id") == client_id), None)
                if matched_loc and matched_loc.get("role_name"):
                    cand_role = matched_loc["role_name"]

            if not cand_role:
                parts = [p.strip() for p in (cand.get("drive_folder_path") or "").strip("/").split("/") if p.strip()]
                cand_role = parts[2] if len(parts) >= 3 else "General"

            if cand_role and cand_role.strip().lower() == role.strip().lower():
                verified_ids.add(cand["id"])

        filtered_candidate_ids = verified_ids

    if filtered_candidate_ids is not None:
        if not filtered_candidate_ids:
            return {"data": [], "count": 0, "page": page, "limit": limit}
        query = query.in_("id", list(filtered_candidate_ids))

    valid_sort_columns = {
        "name": "first_name",
        "first_name": "first_name",
        "phone": "phone",
        "location": "location",
        "email": "email",
        "created_at": "created_at",
        "date": "created_at",
    }
    col = valid_sort_columns.get((sort_by or "").lower(), "created_at")
    desc = ((sort_order or "").lower() == "desc")

    query = query.order(col, desc=desc).range(start, end)
    res = query.execute()
    candidate_list = res.data or []

    # Attach application info, contextual location, and notes to candidate objects
    if candidate_list:
        c_ids = [c["id"] for c in candidate_list]
        apps_res = supabase.table("applications")\
            .select("id, candidate_id, client_id, site_id, stage, status")\
            .eq("tenant_id", t_id)\
            .in_("candidate_id", c_ids)\
            .execute()
        apps_map = {a["candidate_id"]: a for a in (apps_res.data or [])}

        for c in candidate_list:
            app = apps_map.get(c["id"])
            attrs = c.get("extracted_attributes") or {}
            c["application_id"] = app["id"] if app else None
            stage = app["stage"] if app else "applied"
            c["stage"] = stage
            c["app_status"] = app["status"] if app else "active"
            c["display_status"] = STAGE_TO_DISPLAY.get(stage, "New")
            c["flags"] = attrs.get("flags", [])
            c["is_renamed"] = bool(attrs.get("is_renamed", False))
            c["notes"] = attrs.get("notes", [])
            c["comments_count"] = len(c["notes"])
            c["ai_call_badge"] = attrs.get("ai_call_badge", "AI Call")
            file_id = c.get("drive_file_id")
            c["resume_url"] = f"https://drive.google.com/file/d/{file_id}/view" if file_id else None
            
            # Locations Present support
            locs = attrs.get("locations_present") or []
            c["locations_present"] = locs
            c["is_multi_location"] = len(locs) > 1

            # If user filtered by site_id, set contextual display for that site
            if site_id and locs:
                matched_loc = next((l for l in locs if l.get("site_id") == site_id), None)
                if matched_loc:
                    c["contextual_role"] = matched_loc.get("role_name")
                    c["contextual_path"] = matched_loc.get("path")
                    c["contextual_site"] = matched_loc.get("site_name")
                    c["other_locations"] = [l for l in locs if l.get("site_id") != site_id]
                else:
                    c["other_locations"] = locs
            else:
                c["other_locations"] = locs

            if not c.get("contextual_role"):
                parts = [p.strip() for p in (c.get("drive_folder_path") or "").strip("/").split("/") if p.strip()]
                if len(parts) >= 3:
                    c["contextual_role"] = parts[2]

        if (sort_by or "").lower() == "status":
            candidate_list.sort(key=lambda x: (x.get("display_status") or "").lower(), reverse=desc)
        elif (sort_by or "").lower() == "comments":
            candidate_list.sort(key=lambda x: x.get("comments_count", 0), reverse=desc)

    return {
        "data": candidate_list,
        "count": res.count or len(candidate_list),
        "page": page,
        "limit": limit
    }


@router.patch("/{candidate_id}/status")
def update_candidate_status(
    candidate_id: str,
    payload: Dict[str, Any] = Body(...),
    tenant_id: Optional[str] = None
):
    """
    Update a candidate's status from the Resume Desk dropdown.
    Updates applications.stage and records history.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    new_display_status = payload.get("status")
    if not new_display_status:
        raise HTTPException(status_code=400, detail="Status is required")

    mapped_stage, mapped_status = DISPLAY_TO_STAGE.get(new_display_status, ("applied", "active"))

    # Fetch active application for candidate
    app_res = supabase.table("applications")\
        .select("id, stage, status")\
        .eq("tenant_id", t_id)\
        .eq("candidate_id", candidate_id)\
        .execute()

    if not app_res.data:
        raise HTTPException(status_code=404, detail="Application not found for candidate")

    app = app_res.data[0]
    old_stage = app["stage"]

    # Update application
    supabase.table("applications").update({
        "stage": mapped_stage,
        "status": mapped_status,
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }).eq("id", app["id"]).execute()

    # Insert status history
    try:
        supabase.table("application_status_history").insert({
            "tenant_id": t_id,
            "application_id": app["id"],
            "from_stage": old_stage,
            "to_stage": mapped_stage,
            "remarks": f"Updated via Resume Desk to '{new_display_status}'",
            "changed_by": None
        }).execute()
    except Exception as e:
        print(f"Warning logging status history: {e}")

    return {
        "status": "success",
        "display_status": new_display_status,
        "stage": mapped_stage,
        "app_status": mapped_status
    }


@router.post("/{candidate_id}/notes")
def add_candidate_note(
    candidate_id: str,
    payload: Dict[str, Any] = Body(...),
    tenant_id: Optional[str] = None
):
    """
    Add an audio or text comment/note to a candidate profile.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    note_text = payload.get("note") or payload.get("text")
    if not note_text:
        raise HTTPException(status_code=400, detail="Note text is required")

    cand_res = supabase.table("candidates")\
        .select("id, extracted_attributes")\
        .eq("tenant_id", t_id)\
        .eq("id", candidate_id)\
        .execute()

    if not cand_res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cand = cand_res.data[0]
    attrs = cand.get("extracted_attributes") or {}
    notes = attrs.get("notes") or []

    new_note = {
        "id": len(notes) + 1,
        "text": note_text,
        "author": payload.get("author", "Recruiter"),
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    notes.append(new_note)
    attrs["notes"] = notes

    supabase.table("candidates").update({
        "extracted_attributes": attrs
    }).eq("id", candidate_id).execute()

    return {
        "status": "success",
        "notes": notes,
        "comments_count": len(notes)
    }


@router.get("/{candidate_id}")
def get_candidate(candidate_id: str, tenant_id: Optional[str] = None):
    """Fetch complete candidate profile and applications."""
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    res = supabase.table("candidates")\
        .select("*")\
        .eq("tenant_id", t_id)\
        .eq("id", candidate_id)\
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate = res.data[0]

    # Fetch applications
    apps_res = supabase.table("applications")\
        .select("id, client_id, site_id, stage, status, created_at")\
        .eq("candidate_id", candidate_id)\
        .execute()
    candidate["applications"] = apps_res.data or []

    attrs = candidate.get("extracted_attributes") or {}
    candidate["notes"] = attrs.get("notes", [])
    candidate["flags"] = attrs.get("flags", [])
    candidate["is_renamed"] = bool(attrs.get("is_renamed", False))
    file_id = candidate.get("drive_file_id")
    candidate["resume_url"] = f"https://drive.google.com/file/d/{file_id}/view" if file_id else None

    return candidate


@router.get("/{candidate_id}/resume")
def open_candidate_resume(candidate_id: str, tenant_id: Optional[str] = None):
    """
    Returns the direct Google Drive URL and metadata for opening the candidate resume.
    """
    t_id = tenant_id or settings.DEFAULT_TENANT_ID
    supabase = get_supabase()

    res = supabase.table("candidates")\
        .select("id, first_name, last_name, drive_file_id, drive_folder_path")\
        .eq("tenant_id", t_id)\
        .eq("id", candidate_id)\
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cand = res.data[0]
    file_id = cand.get("drive_file_id")
    if not file_id:
        raise HTTPException(status_code=404, detail="No resume file associated with candidate")

    drive_url = f"https://drive.google.com/file/d/{file_id}/view"
    return {
        "status": "success",
        "resume_url": drive_url,
        "drive_file_id": file_id,
        "drive_folder_path": cand.get("drive_folder_path")
    }
