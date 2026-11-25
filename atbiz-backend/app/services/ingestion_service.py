from typing import Dict, Any, List, Optional
from app.database import get_supabase
from app.config import settings
from app.services.resume_parser import ResumeParser
from app.services.gdrive_service import GoogleDriveService

class IngestionService:
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT_ID
        self.supabase = get_supabase()

    def _normalize(self, s: str) -> str:
        import re
        return re.sub(r'[^a-zA-Z0-9]', '', s or '').lower()

    def _resolve_client_and_site(self, client_name: str, site_name: str) -> tuple[Optional[str], Optional[str]]:
        """Resolve client_id and site_id from folder names with fuzzy normalization."""
        if not hasattr(self, '_clients_cache') or not self._clients_cache:
            self._clients_cache = self.supabase.table("clients").select("id, code, name").eq("tenant_id", self.tenant_id).execute().data or []
        if not hasattr(self, '_sites_cache') or not self._sites_cache:
            self._sites_cache = self.supabase.table("client_sites").select("id, client_id, state, site_name, site_code").eq("tenant_id", self.tenant_id).execute().data or []

        c_norm = self._normalize(client_name)
        matched_client_id = None
        for c in self._clients_cache:
            c_name_norm = self._normalize(c["name"])
            c_code_norm = self._normalize(c["code"])
            if c_norm in c_name_norm or c_name_norm in c_norm or c_norm in c_code_norm:
                matched_client_id = c["id"]
                break

        matched_site_id = None
        if matched_client_id:
            s_norm = self._normalize(site_name)
            for s in self._sites_cache:
                if s["client_id"] == matched_client_id:
                    if (
                        s_norm == self._normalize(s["state"]) or
                        s_norm in self._normalize(s["site_name"]) or
                        s_norm in self._normalize(s["site_code"])
                    ):
                        matched_site_id = s["id"]
                        break

        return matched_client_id, matched_site_id

    def _record_candidate_location(self, candidate_id: str, file_data: Dict[str, Any], existing_attrs: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """
        Record location / folder where candidate was found.
        Keeps 1 candidate row in candidates table while ensuring application exists
        for (client_id, site_id) and locations_present is updated.
        """
        client_id, site_id = self._resolve_client_and_site(
            client_name=file_data["client_name"],
            site_name=file_data["site_name"]
        )

        locations = existing_attrs.get("locations_present") or []
        folder_path = file_data.get("folder_path")
        file_id = file_data.get("file_id")
        client_name = file_data.get("client_name")
        site_name = file_data.get("site_name")
        role_name = file_data.get("role_name")

        # Check if this exact path is already recorded
        existing_loc = next((l for l in locations if l.get("path") == folder_path), None)
        if not existing_loc:
            locations.append({
                "client_id": client_id,
                "site_id": site_id,
                "client_name": client_name,
                "site_name": site_name,
                "role_name": role_name,
                "path": folder_path,
                "file_id": file_id
            })
            existing_attrs["locations_present"] = locations

        if len(locations) > 1:
            flags = list(set(existing_attrs.get("flags", []) + ["multiple_locations", "already_present"]))
            existing_attrs["flags"] = flags

        # Ensure application exists in applications table for this site
        if client_id and site_id:
            existing_app = self.supabase.table("applications")\
                .select("id")\
                .eq("tenant_id", self.tenant_id)\
                .eq("candidate_id", candidate_id)\
                .eq("site_id", site_id)\
                .execute()

            if not existing_app.data:
                self.supabase.table("applications").insert({
                    "tenant_id": self.tenant_id,
                    "candidate_id": candidate_id,
                    "client_id": client_id,
                    "site_id": site_id,
                    "stage": "applied",
                    "status": "active"
                }).execute()

        # Update candidate extracted_attributes in Supabase
        self.supabase.table("candidates").update({
            "extracted_attributes": existing_attrs
        }).eq("id", candidate_id).execute()

        return client_id, site_id

    def ingest_single_file(self, file_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and save one resume using atomic RPC or safe fallback with rename tracking."""
        import hashlib
        from datetime import datetime

        drive_file_id = file_data["file_id"]
        file_bytes = file_data.get("file_bytes")
        if file_bytes is None:
            return {
                "status": "error",
                "message": file_data.get("error") or "No file bytes downloaded",
                "file_name": file_data.get("file_name")
            }

        file_hash = hashlib.sha256(file_bytes).hexdigest()

        # Resolve client and site
        client_id, site_id = self._resolve_client_and_site(
            client_name=file_data["client_name"],
            site_name=file_data["site_name"]
        )

        # -------------------------------------------------------------
        # STEP 1: Fast Check for Known Drive File (Rename / Move detection)
        # -------------------------------------------------------------
        # If this exact Drive File ID is already registered, check if its folder path
        # or location in Google Drive changed.
        existing_cf = None
        try:
            cf_res = self.supabase.table("candidate_files")\
                .select("id, candidate_id, folder_path, file_hash, client_id, site_id, role_name")\
                .eq("tenant_id", self.tenant_id)\
                .eq("drive_file_id", drive_file_id)\
                .execute()
            if cf_res.data:
                existing_cf = cf_res.data[0]
        except Exception:
            pass

        existing_cand = None
        if not existing_cf:
            try:
                c_res = self.supabase.table("candidates")\
                    .select("id, drive_folder_path, extracted_attributes")\
                    .eq("tenant_id", self.tenant_id)\
                    .eq("drive_file_id", drive_file_id)\
                    .execute()
                if c_res.data:
                    existing_cand = c_res.data[0]
            except Exception:
                pass

        if existing_cf or existing_cand:
            candidate_id = existing_cf["candidate_id"] if existing_cf else existing_cand["id"]
            old_path = (existing_cf.get("folder_path") if existing_cf else existing_cand.get("drive_folder_path")) or ""
            current_path = file_data["folder_path"]

            norm_old = (old_path or "").strip().strip("/").replace("//", "/")
            norm_curr = (current_path or "").strip().strip("/").replace("//", "/")

            # Has the folder path changed in Google Drive?
            if norm_old and norm_curr and norm_old != norm_curr:
                old_site_id = existing_cf.get("site_id") if existing_cf else None
                new_role = file_data.get("role_name")

                # 1. Update or upsert candidate_files
                try:
                    self.supabase.table("candidate_files").upsert({
                        "tenant_id": self.tenant_id,
                        "candidate_id": candidate_id,
                        "drive_file_id": drive_file_id,
                        "file_hash": file_hash,
                        "file_name": file_data["file_name"],
                        "folder_path": current_path,
                        "client_id": client_id,
                        "site_id": site_id,
                        "role_name": new_role,
                        "file_size_bytes": file_data.get("file_size_bytes") or len(file_bytes),
                        "is_unresolved": (site_id is None),
                        "updated_at": datetime.utcnow().isoformat()
                    }, on_conflict="tenant_id, drive_file_id").execute()
                except Exception as cf_err:
                    print(f"Error updating candidate_files on move: {cf_err}")

                # 2. Update candidates record & locations_present
                try:
                    cand_res = self.supabase.table("candidates").select("id, extracted_attributes").eq("id", candidate_id).execute()
                    attrs = (cand_res.data[0].get("extracted_attributes") if cand_res.data else {}) or {}
                    attrs["is_renamed"] = True
                    attrs["renamed_at"] = datetime.utcnow().isoformat()
                    attrs["previous_path"] = old_path
                    flags = list(set(attrs.get("flags", []) + ["renamed_in_drive", "already_present"]))
                    attrs["flags"] = flags

                    locs = attrs.get("locations_present") or []
                    updated_loc = False
                    for loc in locs:
                        loc_path_norm = (loc.get("path") or "").strip().strip("/").replace("//", "/")
                        if loc.get("file_id") == drive_file_id or (loc_path_norm and loc_path_norm == norm_old):
                            loc["client_id"] = client_id
                            loc["site_id"] = site_id
                            loc["client_name"] = file_data["client_name"]
                            loc["site_name"] = file_data["site_name"]
                            loc["role_name"] = new_role
                            loc["path"] = current_path
                            loc["file_id"] = drive_file_id
                            updated_loc = True
                            break
                    if not updated_loc:
                        locs.append({
                            "client_id": client_id,
                            "site_id": site_id,
                            "client_name": file_data["client_name"],
                            "site_name": file_data["site_name"],
                            "role_name": new_role,
                            "path": current_path,
                            "file_id": drive_file_id
                        })
                    attrs["locations_present"] = locs

                    self.supabase.table("candidates").update({
                        "drive_folder_path": current_path,
                        "extracted_attributes": attrs,
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("id", candidate_id).execute()
                except Exception as c_err:
                    print(f"Error updating candidate on move: {c_err}")

                # 3. Migrate application: clean up orphaned old site application if candidate has no other files there
                try:
                    if old_site_id and site_id and old_site_id != site_id:
                        other_files = self.supabase.table("candidate_files")\
                            .select("id")\
                            .eq("tenant_id", self.tenant_id)\
                            .eq("candidate_id", candidate_id)\
                            .eq("site_id", old_site_id)\
                            .neq("drive_file_id", drive_file_id)\
                            .execute().data or []
                        if not other_files:
                            self.supabase.table("applications")\
                                .delete()\
                                .eq("tenant_id", self.tenant_id)\
                                .eq("candidate_id", candidate_id)\
                                .eq("site_id", old_site_id)\
                                .execute()

                    if client_id and site_id:
                        self.supabase.table("applications").upsert({
                            "tenant_id": self.tenant_id,
                            "candidate_id": candidate_id,
                            "client_id": client_id,
                            "site_id": site_id,
                            "stage": "applied",
                            "status": "active"
                        }, on_conflict="tenant_id, candidate_id, client_id, site_id").execute()
                except Exception as app_err:
                    print(f"Error migrating application on move: {app_err}")

                return {
                    "status": "renamed",
                    "flag": "already_present_renamed",
                    "message": f"Resume moved in Drive from '{old_path}' to '{current_path}'.",
                    "candidate_id": candidate_id
                }

            # If folder path is identical and file hash is identical, skip immediately
            existing_hash = existing_cf.get("file_hash") if existing_cf else None
            if not existing_hash or existing_hash == file_hash:
                return {
                    "status": "skipped",
                    "flag": "already_present",
                    "message": "Already ingested (unchanged in Drive)",
                    "candidate_id": candidate_id
                }

        # -------------------------------------------------------------
        # STEP 2: Parse Resume Content (Only for new or content-modified files)
        # -------------------------------------------------------------
        parsed = ResumeParser.parse(
            file_bytes=file_bytes,
            file_name=file_data["file_name"],
            fallback_site=file_data["site_name"]
        )

        # Try atomic Postgres RPC first (Migration 05)
        try:
            cand_attrs = parsed.extracted_attributes or {}
            cand_attrs["file_hash"] = file_hash
            cand_attrs["ingested_at"] = datetime.utcnow().isoformat()
            if not site_id:
                cand_attrs.setdefault("flags", []).append("unresolved_site_folder")
                cand_attrs["unresolved_folder_path"] = file_data["folder_path"]

            candidate_payload = {
                "first_name": parsed.first_name,
                "last_name": parsed.last_name,
                "email": parsed.email,
                "phone": parsed.phone,
                "dob": parsed.dob if parsed.dob and len(parsed.dob) <= 10 else None,
                "location": parsed.location,
                "last_qualification": parsed.last_qualification,
                "experience_years": parsed.experience_years,
                "raw_resume_text": parsed.raw_text[:5000],
                "extracted_attributes": cand_attrs
            }

            file_payload = {
                "drive_file_id": drive_file_id,
                "file_hash": file_hash,
                "file_name": file_data["file_name"],
                "folder_path": file_data["folder_path"],
                "client_id": client_id,
                "site_id": site_id,
                "role_name": file_data["role_name"],
                "file_size_bytes": file_data.get("file_size_bytes") or len(file_bytes),
                "mime_type": cand_attrs.get("mime_type")
            }

            app_payload = {"stage": "applied", "status": "active"} if (client_id and site_id) else None
            task_payload = {
                "module_id": "screening",
                "title": f"Screen Candidate: {parsed.first_name} {parsed.last_name or ''} ({file_data['role_name']})",
                "description": f"Extracted from Google Drive folder: {file_data['folder_path']}",
                "priority": "medium"
            } if (client_id and site_id) else None

            rpc_res = self.supabase.rpc("ingest_candidate_atomic", {
                "p_tenant_id": self.tenant_id,
                "p_candidate": candidate_payload,
                "p_file": file_payload,
                "p_application": app_payload,
                "p_task": task_payload
            }).execute()

            data = rpc_res.data or {}
            if data.get("file_already_known") and not data.get("application_created"):
                return {
                    "status": "skipped",
                    "flag": "already_present",
                    "message": "Already ingested (Google Drive File ID match)",
                    "candidate_id": data.get("candidate_id")
                }
            elif data.get("is_existing_candidate"):
                return {
                    "status": "duplicate_identity",
                    "flag": "person_already_present",
                    "message": f"Candidate with phone/email matched existing candidate. Recorded application and file.",
                    "candidate_id": data.get("candidate_id")
                }
            else:
                return {
                    "status": "success",
                    "candidate_id": data.get("candidate_id"),
                    "application_id": data.get("application_id"),
                    "name": f"{parsed.first_name} {parsed.last_name or ''}".strip(),
                    "client_resolved": client_id is not None,
                    "site_resolved": site_id is not None
                }
        except Exception as rpc_err:
            # Fallback to direct table queries if RPC is not yet registered in schema cache
            pass

        # -------------------------------------------------------------
        # FALLBACK: Direct table operations (Pre-Migration 05)
        # -------------------------------------------------------------
        # CHECK 1: File ID match (Rename in Google Drive check)
        existing_by_drive_id = self.supabase.table("candidates")\
            .select("id, first_name, last_name, drive_folder_path, extracted_attributes")\
            .eq("tenant_id", self.tenant_id)\
            .eq("drive_file_id", drive_file_id)\
            .execute()

        if existing_by_drive_id.data:
            existing = existing_by_drive_id.data[0]
            old_path = existing.get("drive_folder_path")
            current_path = file_data["folder_path"]

            norm_old = (old_path or "").strip().strip("/").replace("//", "/")
            norm_curr = (current_path or "").strip().strip("/").replace("//", "/")

            if norm_old and norm_curr and norm_old != norm_curr:
                attrs = existing.get("extracted_attributes") or {}
                attrs["is_renamed"] = True
                attrs["renamed_at"] = datetime.utcnow().isoformat()
                attrs["previous_path"] = old_path
                flags = list(set(attrs.get("flags", []) + ["renamed_in_drive", "already_present"]))
                attrs["flags"] = flags

                self.supabase.table("candidates").update({
                    "drive_folder_path": current_path,
                    "extracted_attributes": attrs
                }).eq("id", existing["id"]).execute()

                return {
                    "status": "renamed",
                    "flag": "already_present_renamed",
                    "message": f"Resume was renamed in Google Drive from '{old_path}' to '{current_path}'.",
                    "candidate_id": existing["id"],
                    "candidate_name": f"{existing['first_name']} {existing.get('last_name') or ''}".strip()
                }

            return {
                "status": "skipped",
                "flag": "already_present",
                "message": "Already ingested (Google Drive File ID match)",
                "candidate_id": existing["id"]
            }

        # -------------------------------------------------------------
        # CHECK 2: File Content Hash (Exact duplicate PDF file uploaded)
        # -------------------------------------------------------------
        existing_by_hash = self.supabase.table("candidates")\
            .select("id, first_name, last_name, drive_folder_path, extracted_attributes")\
            .eq("tenant_id", self.tenant_id)\
            .contains("extracted_attributes", {"file_hash": file_hash})\
            .execute()

        if existing_by_hash.data:
            existing = existing_by_hash.data[0]
            attrs = existing.get("extracted_attributes") or {}
            flags = list(set(attrs.get("flags", []) + ["duplicate_resume_uploaded", "already_present"]))
            attrs["flags"] = flags
            dup_files = attrs.get("duplicate_files") or []
            curr_path = file_data["folder_path"]
            if curr_path not in dup_files and curr_path != existing.get("drive_folder_path"):
                dup_files.append(curr_path)
            attrs["duplicate_files"] = dup_files
            
            # Record location & ensure application exists for this site
            self._record_candidate_location(existing["id"], file_data, attrs)

            return {
                "status": "duplicate_content",
                "flag": "duplicate_file_already_present",
                "message": f"Exact duplicate resume file already exists for {existing['first_name']} {existing.get('last_name') or ''} (Path: {existing.get('drive_folder_path')}). Recorded location and application.",
                "candidate_id": existing["id"]
            }

        # -------------------------------------------------------------
        # Parse Resume Content
        # -------------------------------------------------------------
        parsed = ResumeParser.parse(
            file_bytes=file_bytes,
            file_name=file_data["file_name"],
            fallback_site=file_data["site_name"]
        )

        # -------------------------------------------------------------
        # CHECK 3: Candidate Identity Match (Phone / Email duplicate check)
        # -------------------------------------------------------------
        if parsed.phone and parsed.phone != "+91-0000000000":
            existing_by_phone = self.supabase.table("candidates")\
                .select("id, first_name, last_name, drive_folder_path, extracted_attributes")\
                .eq("tenant_id", self.tenant_id)\
                .eq("phone", parsed.phone)\
                .execute()
            if existing_by_phone.data:
                existing = existing_by_phone.data[0]
                attrs = existing.get("extracted_attributes") or {}
                flags = list(set(attrs.get("flags", []) + ["duplicate_resume_uploaded", "already_present"]))
                attrs["flags"] = flags
                dup_files = attrs.get("duplicate_files") or []
                curr_path = file_data["folder_path"]
                if curr_path not in dup_files and curr_path != existing.get("drive_folder_path"):
                    dup_files.append(curr_path)
                attrs["duplicate_files"] = dup_files
                
                # Record location & ensure application exists for this site
                self._record_candidate_location(existing["id"], file_data, attrs)

                return {
                    "status": "duplicate_identity",
                    "flag": "person_already_present",
                    "message": f"Candidate with phone {parsed.phone} is already present as {existing['first_name']} {existing.get('last_name') or ''}. Recorded location and application.",
                    "candidate_id": existing["id"]
                }

        if parsed.email:
            existing_by_email = self.supabase.table("candidates")\
                .select("id, first_name, last_name, drive_folder_path, extracted_attributes")\
                .eq("tenant_id", self.tenant_id)\
                .eq("email", parsed.email)\
                .execute()
            if existing_by_email.data:
                existing = existing_by_email.data[0]
                attrs = existing.get("extracted_attributes") or {}
                flags = list(set(attrs.get("flags", []) + ["duplicate_resume_uploaded", "already_present"]))
                attrs["flags"] = flags
                dup_files = attrs.get("duplicate_files") or []
                curr_path = file_data["folder_path"]
                if curr_path not in dup_files and curr_path != existing.get("drive_folder_path"):
                    dup_files.append(curr_path)
                attrs["duplicate_files"] = dup_files
                
                # Record location & ensure application exists for this site
                self._record_candidate_location(existing["id"], file_data, attrs)

                return {
                    "status": "duplicate_identity",
                    "flag": "person_already_present",
                    "message": f"Candidate with email {parsed.email} is already present as {existing['first_name']} {existing.get('last_name') or ''}. Recorded location and application.",
                    "candidate_id": existing["id"]
                }

        # -------------------------------------------------------------
        # NEW CANDIDATE: Insert into Database
        # -------------------------------------------------------------
        client_id, site_id = self._resolve_client_and_site(
            client_name=file_data["client_name"],
            site_name=file_data["site_name"]
        )

        attrs = parsed.extracted_attributes or {}
        attrs["file_hash"] = file_hash
        attrs["ingested_at"] = datetime.utcnow().isoformat()

        candidate_payload = {
            "tenant_id": self.tenant_id,
            "first_name": parsed.first_name,
            "last_name": parsed.last_name,
            "email": parsed.email,
            "phone": parsed.phone,
            "dob": parsed.dob if parsed.dob and len(parsed.dob) <= 10 else None,
            "location": parsed.location,
            "last_qualification": parsed.last_qualification,
            "experience_years": parsed.experience_years,
            "drive_file_id": drive_file_id,
            "drive_folder_path": file_data["folder_path"],
            "raw_resume_text": parsed.raw_text[:5000],
            "extracted_attributes": attrs
        }

        cand_res = self.supabase.table("candidates").insert(candidate_payload).execute()
        if not cand_res.data:
            raise RuntimeError("Failed to insert candidate record")

        candidate_id = cand_res.data[0]["id"]

        # Insert Application
        application_id = None
        if client_id and site_id:
            app_payload = {
                "tenant_id": self.tenant_id,
                "candidate_id": candidate_id,
                "client_id": client_id,
                "site_id": site_id,
                "stage": "applied",
                "status": "active"
            }
            app_res = self.supabase.table("applications").insert(app_payload).execute()
            if app_res.data:
                application_id = app_res.data[0]["id"]

            task_payload = {
                "tenant_id": self.tenant_id,
                "client_id": client_id,
                "site_id": site_id,
                "module_id": "screening",
                "title": f"Screen Candidate: {parsed.first_name} {parsed.last_name or ''} ({file_data['role_name']})",
                "description": f"Extracted from Google Drive folder: {file_data['folder_path']}",
                "related_entity_type": "candidate",
                "related_entity_id": candidate_id,
                "priority": "medium",
                "status": "pending"
            }
            self.supabase.table("work_tasks").insert(task_payload).execute()

        return {
            "status": "success",
            "candidate_id": candidate_id,
            "application_id": application_id,
            "name": f"{parsed.first_name} {parsed.last_name or ''}".strip(),
            "client_resolved": client_id is not None,
            "site_resolved": site_id is not None
        }

    def reconcile_unresolved_candidates(self) -> int:
        """
        Re-attempts resolution for previously unmapped folders (site_id IS NULL).
        Creates the application and screening task if client and site can now be resolved.
        """
        reconciled_count = 0
        try:
            res = self.supabase.table("candidate_files")\
                .select("id, candidate_id, folder_path, file_name, role_name")\
                .eq("tenant_id", self.tenant_id)\
                .eq("is_unresolved", True)\
                .execute()
            unresolved = res.data or []
            for item in unresolved:
                folder_path = item.get("folder_path") or ""
                parts = [p.strip() for p in folder_path.strip("/").split("/") if p.strip()]
                if len(parts) >= 2:
                    client_name = parts[0]
                    site_name = parts[1]
                    role_name = parts[2] if len(parts) >= 3 else item.get("role_name", "General")
                    c_id, s_id = self._resolve_client_and_site(client_name, site_name)
                    if c_id and s_id:
                        self.supabase.table("candidate_files").update({
                            "client_id": c_id,
                            "site_id": s_id,
                            "role_name": role_name,
                            "is_unresolved": False
                        }).eq("id", item["id"]).execute()

                        # Ensure application exists
                        self.supabase.table("applications").upsert({
                            "tenant_id": self.tenant_id,
                            "candidate_id": item["candidate_id"],
                            "client_id": c_id,
                            "site_id": s_id,
                            "stage": "applied",
                            "status": "active"
                        }, on_conflict="tenant_id, candidate_id, client_id, site_id").execute()

                        reconciled_count += 1
        except Exception:
            pass
        return reconciled_count

    def run_gdrive_sync(self, root_folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Crawl Google Drive and ingest all resumes with duplicate tracking."""
        from datetime import datetime

        # 1. Run auto-reconciliation on any unmapped files from previous runs
        reconciled = self.reconcile_unresolved_candidates()

        gdrive = GoogleDriveService()
        stats = {
            "total_scanned": 0,
            "newly_ingested": 0,
            "skipped_duplicates": 0,
            "renamed_in_drive": 0,
            "reconciled_files": reconciled,
            "synced_at": datetime.utcnow().isoformat() + "Z",
            "errors": []
        }

        for file_item in gdrive.crawl_resumes(root_folder_id):
            stats["total_scanned"] += 1
            try:
                res = self.ingest_single_file(file_item)
                if res["status"] == "success":
                    stats["newly_ingested"] += 1
                elif res["status"] == "renamed":
                    stats["renamed_in_drive"] += 1
                elif res["status"] in ("duplicate_content", "duplicate_identity"):
                    stats["skipped_duplicates"] += 1
                elif res["status"] == "skipped":
                    stats["unchanged_files"] = stats.get("unchanged_files", 0) + 1
            except Exception as e:
                stats["errors"].append({
                    "file": file_item["file_name"],
                    "path": file_item["folder_path"],
                    "error": str(e)
                })

        return stats

        return stats

    def run_local_sync(self, local_path: str) -> Dict[str, Any]:
        """Test crawler using a local directory with the same folder hierarchy."""
        stats = {
            "total_scanned": 0,
            "newly_ingested": 0,
            "skipped_duplicates": 0,
            "errors": []
        }

        for file_item in GoogleDriveService.crawl_local_directory(local_path):
            stats["total_scanned"] += 1
            try:
                res = self.ingest_single_file(file_item)
                if res["status"] == "success":
                    stats["newly_ingested"] += 1
                elif res["status"] == "skipped":
                    stats["skipped_duplicates"] += 1
            except Exception as e:
                stats["errors"].append({
                    "file": file_item["file_name"],
                    "path": file_item["folder_path"],
                    "error": str(e)
                })

        return stats

    def provision_drive_folders(self, root_folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates or verifies the complete folder structure in Google Drive based on the database:
        [Atbiz Root] -> [Client] -> [Site / State] -> [Role]
        """
        gdrive = GoogleDriveService()
        root_id = root_folder_id or settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        if not root_id:
            raise ValueError("GOOGLE_DRIVE_ROOT_FOLDER_ID is required in .env or request body.")

        clients_res = self.supabase.table("clients")\
            .select("id, code, name")\
            .eq("tenant_id", self.tenant_id)\
            .execute()
        clients = clients_res.data or []

        total_roles_created = 0
        tree = {}

        for client in clients:
            client_folder_name = client["code"] or client["name"]
            client_folder_id = gdrive.get_or_create_folder(client_folder_name, root_id)
            tree[client_folder_name] = {}

            # Sites under client
            sites_res = self.supabase.table("client_sites")\
                .select("id, state, site_name, site_code")\
                .eq("tenant_id", self.tenant_id)\
                .eq("client_id", client["id"])\
                .execute()
            sites = sites_res.data or []

            # Roles/Designations under client
            desig_res = self.supabase.table("designations")\
                .select("id, title")\
                .eq("tenant_id", self.tenant_id)\
                .eq("client_id", client["id"])\
                .execute()
            roles = desig_res.data or []

            for site in sites:
                site_folder_name = site["state"] or site["site_name"]
                site_folder_id = gdrive.get_or_create_folder(site_folder_name, client_folder_id)
                tree[client_folder_name][site_folder_name] = []

                for role in roles:
                    role_folder_name = role["title"]
                    gdrive.get_or_create_folder(role_folder_name, site_folder_id)
                    tree[client_folder_name][site_folder_name].append(role_folder_name)
                    total_roles_created += 1

        return {
            "status": "success",
            "message": "Google Drive folder hierarchy verified/provisioned successfully.",
            "total_role_folders": total_roles_created,
            "hierarchy": tree
        }
