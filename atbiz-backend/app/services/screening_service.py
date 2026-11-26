import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from fastapi import HTTPException, status
from supabase import Client

from app.config import settings
from app.database import get_supabase
from app.dependencies.auth import AuthUser
from app.services.sarvam_service import sarvam_client, SarvamClient, SarvamAPIError

logger = logging.getLogger("screening_service")
logger.setLevel(logging.INFO)

# Strict Indian mobile phone regex: E.164 format (+91 followed by 10 digits starting with 6-9)
INDIAN_PHONE_REGEX = re.compile(r"^\+91[6-9]\d{9}$")


def normalize_indian_phone(phone: Optional[str]) -> str:
    """
    Validates and normalizes phone numbers into E.164 Indian mobile format (+91XXXXXXXXXX).
    Rejects any non-Indian or invalid mobile numbers.
    
    Accepts:
        - 9876543210
        - +919876543210
        - 919876543210
        - 09876543210
        - Formats with whitespace/hyphens: "+91 98765-43210"
        
    Raises:
        ValueError("INVALID_INDIAN_MOBILE_NUMBER") if invalid.
    """
    if not phone or not isinstance(phone, str):
        raise ValueError("INVALID_INDIAN_MOBILE_NUMBER: Phone number is missing or empty")

    # Remove all whitespace, hyphens, dots, parentheses
    cleaned = re.sub(r"[\s\-\.\(\)]+", "", phone.strip())

    # Strip prefixes
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]

    # Must be exactly 10 digits starting with 6, 7, 8, or 9
    if not re.match(r"^[6-9]\d{9}$", cleaned):
        raise ValueError(
            f"INVALID_INDIAN_MOBILE_NUMBER: '{phone}' is not a valid 10-digit Indian mobile number starting with 6-9"
        )

    return f"+91{cleaned}"


def resolve_job_context(supabase: Client, application_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Resolves authoritative job context (title, description) from applications -> vacancies -> designations.
    If title is missing, raises ValueError("MISSING_JOB_CONTEXT").
    Never silently assigns a generic placeholder title.
    """
    # 1. Fetch application details
    app_res = (
        supabase.table("applications")
        .select("id, tenant_id, vacancy_id, candidate_id, client_id, site_id, job_title")
        .eq("id", application_id)
        .eq("tenant_id", tenant_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    application = app_res.data
    if not application:
        raise ValueError(f"APPLICATION_NOT_FOUND: Application '{application_id}' does not exist or is deleted")

    job_title: Optional[str] = application.get("job_title")
    job_description: str = ""
    vacancy_id = application.get("vacancy_id")

    # 2. Query Vacancy if linked
    if vacancy_id:
        try:
            vac_res = (
                supabase.table("vacancies")
                .select("id, title, job_description, designation_id")
                .eq("id", vacancy_id)
                .single()
                .execute()
            )
            vacancy = vac_res.data
            if vacancy:
                if vacancy.get("title") and not job_title:
                    job_title = vacancy.get("title")
                if vacancy.get("job_description"):
                    job_description = vacancy.get("job_description")

                # 3. Query Designation if linked to Vacancy
                designation_id = vacancy.get("designation_id")
                if designation_id and not job_title:
                    des_res = (
                        supabase.table("designations")
                        .select("id, name, description")
                        .eq("id", designation_id)
                        .single()
                        .execute()
                    )
                    designation = des_res.data
                    if designation and designation.get("name"):
                        job_title = designation.get("name")
                        if not job_description and designation.get("description"):
                            job_description = designation.get("description")
        except Exception as e:
            logger.warning(f"Error resolving vacancy/designation for application {application_id}: {e}")

    # Enforce authoritative job context
    if not job_title or not job_title.strip():
        raise ValueError(f"MISSING_JOB_CONTEXT: No job title found for application '{application_id}'")

    return {
        "application_id": application_id,
        "tenant_id": tenant_id,
        "candidate_id": application["candidate_id"],
        "client_id": application.get("client_id"),
        "site_id": application.get("site_id"),
        "job_title": job_title.strip(),
        "job_description": (job_description or "").strip()
    }


class ScreeningService:
    def __init__(self, client: Optional[SarvamClient] = None, db_client: Optional[Client] = None):
        self.sarvam = client or sarvam_client
        self.supabase = db_client or get_supabase()

    def _get_active_screening_cycle(self, application_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Checks for existing active screening cycle (QUEUED, IN_PROGRESS, RECONCILIATION_PENDING)."""
        res = (
            self.supabase.table("screening_cycles")
            .select("id, cycle_number, status, created_at")
            .eq("tenant_id", tenant_id)
            .eq("application_id", application_id)
            .in_("status", ["QUEUED", "IN_PROGRESS", "RECONCILIATION_PENDING"])
            .is_("deleted_at", "null")
            .execute()
        )
        return res.data[0] if res.data else None

    def _get_screening_cycles_history(self, application_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Returns all cycles for an application ordered by cycle_number descending."""
        res = (
            self.supabase.table("screening_cycles")
            .select("id, cycle_number, status, created_at, completed_at, is_rescreen")
            .eq("tenant_id", tenant_id)
            .eq("application_id", application_id)
            .is_("deleted_at", "null")
            .order("cycle_number", desc=True)
            .execute()
        )
        return res.data or []

    async def trigger_screening_batch(
        self,
        application_ids: List[str],
        force_rescreen: bool,
        auth_user: AuthUser
    ) -> Dict[str, Any]:
        """
        Validates applications, ensures tenant/site scoping, checks duplicate screening locks,
        creates cohorts and cycles, and streams the batch to Sarvam Voice Agent.
        """
        tenant_id = auth_user.tenant_id or settings.DEFAULT_TENANT_ID
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        logger.info(
            f"Screening batch initiated by {auth_user.email} (tenant: {tenant_id}) "
            f"for {len(application_ids)} application(s). force_rescreen={force_rescreen}"
        )

        for app_id in application_ids:
            try:
                # 1. Authoritative Job Context & Application Verification
                context = resolve_job_context(self.supabase, app_id, tenant_id)

                # Site access check for non-admin users
                if context.get("site_id") and not auth_user.is_admin:
                    if context["site_id"] not in auth_user.assigned_site_ids:
                        rejected.append({
                            "application_id": app_id,
                            "reason_code": "SITE_ACCESS_DENIED",
                            "message": "User does not have access to this application's site"
                        })
                        continue

                # 2. Candidate Phone and Details
                cand_res = (
                    self.supabase.table("candidates")
                    .select("id, full_name, phone, qualification, experience_years, extracted_attributes")
                    .eq("id", context["candidate_id"])
                    .eq("tenant_id", tenant_id)
                    .single()
                    .execute()
                )
                candidate = cand_res.data
                if not candidate:
                    rejected.append({
                        "application_id": app_id,
                        "reason_code": "CANDIDATE_NOT_FOUND",
                        "message": "Candidate record not found"
                    })
                    continue

                # Validate Indian Mobile Phone Number
                try:
                    normalized_phone = normalize_indian_phone(candidate.get("phone"))
                except ValueError as ve:
                    rejected.append({
                        "application_id": app_id,
                        "reason_code": "INVALID_INDIAN_MOBILE_NUMBER",
                        "message": str(ve)
                    })
                    continue

                # 3. Check Active Duplicate Screening Lock
                active_cycle = self._get_active_screening_cycle(app_id, tenant_id)
                if active_cycle:
                    rejected.append({
                        "application_id": app_id,
                        "reason_code": "ALREADY_IN_PROGRESS",
                        "message": f"An active screening cycle (#{active_cycle['cycle_number']}) is currently {active_cycle['status']}",
                        "active_cycle_id": active_cycle["id"]
                    })
                    continue

                # 4. Check Historical Cycles & Max Attempts Ceiling
                history = self._get_screening_cycles_history(app_id, tenant_id)
                total_previous_cycles = len(history)

                if total_previous_cycles > 0:
                    latest = history[0]
                    if not force_rescreen and latest.get("status") in ("COMPLETED", "FAILED"):
                        rejected.append({
                            "application_id": app_id,
                            "reason_code": "ALREADY_SCREENED",
                            "message": f"Application was already screened in cycle #{latest['cycle_number']}. Set force_rescreen=true to re-screen.",
                            "latest_cycle_id": latest["id"]
                        })
                        continue

                    if total_previous_cycles >= settings.MAX_SCREENING_ATTEMPTS:
                        rejected.append({
                            "application_id": app_id,
                            "reason_code": "MAX_ATTEMPTS_EXCEEDED",
                            "message": f"Maximum screening attempts ({settings.MAX_SCREENING_ATTEMPTS}) reached for this application",
                            "cycle_count": total_previous_cycles
                        })
                        continue

                    next_cycle_number = total_previous_cycles + 1
                else:
                    next_cycle_number = 1

                # 5. Prepare Sarvam Input Variables
                cycle_id = str(uuid.uuid4())
                sarvam_inputs = {
                    "candidate_name": candidate.get("full_name") or "Candidate",
                    "job_title": context["job_title"],
                    "job_description": context["job_description"],
                    "qualification": candidate.get("qualification") or "",
                    "experience": str(candidate.get("experience_years") or ""),
                    "application_id": app_id
                }

                accepted.append({
                    "application_id": app_id,
                    "cycle_id": cycle_id,
                    "cycle_number": next_cycle_number,
                    "candidate_id": candidate["id"],
                    "candidate_name": sarvam_inputs["candidate_name"],
                    "normalized_phone": normalized_phone,
                    "job_title": context["job_title"],
                    "inputs": sarvam_inputs
                })

            except ValueError as ve:
                err_msg = str(ve)
                reason_code = err_msg.split(":")[0] if ":" in err_msg else "VALIDATION_ERROR"
                rejected.append({
                    "application_id": app_id,
                    "reason_code": reason_code,
                    "message": err_msg
                })
            except Exception as exc:
                logger.error(f"Unexpected error validating application {app_id}: {exc}")
                rejected.append({
                    "application_id": app_id,
                    "reason_code": "INTERNAL_ERROR",
                    "message": "Failed to evaluate application eligibility"
                })

        # If no applications qualified, return response immediately
        if not accepted:
            return {
                "cohort_id": None,
                "cohort_name": None,
                "total_requested": len(application_ids),
                "accepted_count": 0,
                "rejected_count": len(rejected),
                "accepted": [],
                "rejected": rejected
            }

        # 6. Create Screening Cohort Record
        tenant_prefix = str(tenant_id).replace("-", "")[:8]
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        cohort_name = f"atbiz_{tenant_prefix}_{timestamp_str}_{uuid.uuid4().hex[:6]}"
        cohort_id = str(uuid.uuid4())

        cohort_record = {
            "id": cohort_id,
            "tenant_id": tenant_id,
            "cohort_name": cohort_name,
            "status": "processing",
            "total_applications": len(accepted),
            "successful_count": 0,
            "failed_count": 0,
            "triggered_by_user_id": auth_user.id,
            "triggered_by_email": auth_user.email
        }
        self.supabase.table("screening_cohorts").insert(cohort_record).execute()

        # 7. Insert Screening Cycle Records
        cycle_records = []
        sarvam_users_payload = []

        for item in accepted:
            cycle_records.append({
                "id": item["cycle_id"],
                "tenant_id": tenant_id,
                "cohort_id": cohort_id,
                "application_id": item["application_id"],
                "cycle_number": item["cycle_number"],
                "status": "QUEUED",
                "normalized_phone": item["normalized_phone"],
                "is_rescreen": (item["cycle_number"] > 1),
                "rescreen_reason": "Recruiter requested re-screening" if (item["cycle_number"] > 1) else None,
                "sarvam_inputs": item["inputs"],
                "triggered_by_user_id": auth_user.id,
                "triggered_by_email": auth_user.email
            })

            sarvam_users_payload.append({
                "phone_number": item["normalized_phone"],
                "user_id": item["cycle_id"],
                "inputs": item["inputs"]
            })

        self.supabase.table("screening_cycles").insert(cycle_records).execute()

        # 8. Submit Stream Cohort to Sarvam Voice Agent
        try:
            sarvam_resp = await self.sarvam.stream_cohort(
                cohort_name=cohort_name,
                users=sarvam_users_payload
            )
            sarvam_cohort_id = sarvam_resp.get("cohort_id")

            # Update cohort to submitted
            self.supabase.table("screening_cohorts").update({
                "status": "submitted",
                "sarvam_cohort_id": sarvam_cohort_id
            }).eq("id", cohort_id).execute()

            # Update cycles to IN_PROGRESS
            self.supabase.table("screening_cycles").update({
                "status": "IN_PROGRESS"
            }).eq("cohort_id", cohort_id).execute()

        except SarvamAPIError as api_err:
            if api_err.status_code == 504:
                logger.warning(f"Sarvam stream cohort timed out for {cohort_name}. Entering reconciliation state.")
                self.supabase.table("screening_cohorts").update({
                    "status": "reconciliation_pending",
                    "error_message": "Stream cohort timed out; reconciliation pending"
                }).eq("id", cohort_id).execute()

                self.supabase.table("screening_cycles").update({
                    "status": "RECONCILIATION_PENDING"
                }).eq("cohort_id", cohort_id).execute()
            else:
                logger.error(f"Sarvam stream cohort API error for {cohort_name}: {api_err}")
                self.supabase.table("screening_cohorts").update({
                    "status": "failed",
                    "error_message": str(api_err)
                }).eq("id", cohort_id).execute()

                self.supabase.table("screening_cycles").update({
                    "status": "FAILED",
                    "error_details": {"error": str(api_err), "status_code": api_err.status_code}
                }).eq("cohort_id", cohort_id).execute()

        except Exception as exc:
            logger.error(f"Unexpected error submitting to Sarvam: {exc}")
            self.supabase.table("screening_cohorts").update({
                "status": "failed",
                "error_message": str(exc)
            }).eq("id", cohort_id).execute()

            self.supabase.table("screening_cycles").update({
                "status": "FAILED",
                "error_details": {"error": str(exc)}
            }).eq("cohort_id", cohort_id).execute()

        return {
            "cohort_id": cohort_id,
            "cohort_name": cohort_name,
            "total_requested": len(application_ids),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "accepted": accepted,
            "rejected": rejected
        }

    async def process_sarvam_webhook(
        self,
        raw_body: bytes,
        signature: Optional[str],
        timestamp: Optional[str]
    ) -> Dict[str, Any]:
        """
        Validates Sarvam webhook HMAC signature, deduplicates deliveries, logs call interactions,
        updates cycle progress, and saves final AI evaluation & voice recording.
        """
        # 1. HMAC-SHA256 Signature Verification & Replay Protection
        if not self.sarvam.verify_webhook_signature(raw_body, signature, timestamp):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired Sarvam webhook signature"
            )

        # 2. Parse JSON Payload
        import json
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Malformed JSON payload: {str(exc)}"
            )

        # Extract identifiers from top-level or nested 'data'/'event_data' dictionary
        data_dict = payload.get("data") if isinstance(payload.get("data"), dict) else (payload.get("event_data") if isinstance(payload.get("event_data"), dict) else {})
        event_id = payload.get("event_id") or payload.get("id") or data_dict.get("event_id") or str(uuid.uuid4())
        sarvam_interaction_id = payload.get("call_id") or payload.get("interaction_id") or data_dict.get("call_id") or data_dict.get("interaction_id")
        event_type = payload.get("event_type") or payload.get("type") or data_dict.get("event_type") or data_dict.get("type") or "call_event"
        cycle_id = payload.get("user_id") or data_dict.get("user_id")  # In our stream cohort, user_id is the cycle_id

        # 3. Locate the screening cycle
        if not cycle_id:
            logger.warning(f"Webhook received without user_id / cycle_id: {payload}")
            return {"status": "ignored", "reason": "missing_user_id"}

        cycle_res = (
            self.supabase.table("screening_cycles")
            .select("id, tenant_id, application_id, cycle_number, status")
            .eq("id", cycle_id)
            .single()
            .execute()
        )
        cycle = cycle_res.data
        if not cycle:
            logger.warning(f"Webhook received for non-existent cycle_id: {cycle_id}")
            return {"status": "ignored", "reason": "cycle_not_found"}

        tenant_id = cycle["tenant_id"]
        ts_val = int(timestamp) if timestamp and timestamp.isdigit() else int(datetime.now(timezone.utc).timestamp())

        # 4. Webhook Event Deduplication
        if sarvam_interaction_id:
            existing_event = (
                self.supabase.table("screening_webhook_events")
                .select("id, processed")
                .eq("tenant_id", tenant_id)
                .eq("sarvam_interaction_id", sarvam_interaction_id)
                .eq("event_type", event_type)
                .eq("sarvam_timestamp", ts_val)
                .execute()
            )
            if existing_event.data:
                logger.info(f"Duplicate webhook event detected for interaction '{sarvam_interaction_id}'. Ignoring.")
                return {"status": "ignored", "reason": "duplicate_event"}

        # Record incoming event in screening_webhook_events
        webhook_event_record = {
            "tenant_id": tenant_id,
            "event_id": event_id,
            "sarvam_interaction_id": sarvam_interaction_id,
            "event_type": event_type,
            "sarvam_timestamp": ts_val,
            "signature_header": signature,
            "payload": payload,
            "processed": False
        }
        self.supabase.table("screening_webhook_events").insert(webhook_event_record).execute()

        # 5. Record Call Interaction Attempt
        call_status = (
            payload.get("call_status")
            or payload.get("status")
            or ("COMPLETED" if event_type in ("call_completed", "call_evaluated") else "IN_PROGRESS")
        ).upper()

        # Determine interaction_number within this cycle
        existing_interactions = (
            self.supabase.table("screening_call_interactions")
            .select("id, interaction_number")
            .eq("tenant_id", tenant_id)
            .eq("cycle_id", cycle_id)
            .execute()
        )
        interaction_num = len(existing_interactions.data or []) + 1

        interaction_record = {
            "tenant_id": tenant_id,
            "cycle_id": cycle_id,
            "sarvam_interaction_id": sarvam_interaction_id,
            "interaction_number": interaction_num,
            "status": call_status if call_status in ('INITIATED', 'RINGING', 'IN_PROGRESS', 'COMPLETED', 'BUSY', 'NO_ANSWER', 'FAILED') else 'IN_PROGRESS',
            "connectivity_status": payload.get("connectivity_status") or payload.get("telephony_status"),
            "call_duration_seconds": payload.get("duration") or payload.get("call_duration_seconds"),
            "failure_reason": payload.get("failure_reason") or payload.get("error"),
            "raw_payload": payload,
            "initiated_at": payload.get("started_at") or payload.get("initiated_at"),
            "completed_at": payload.get("completed_at") or payload.get("ended_at")
        }

        self.supabase.table("screening_call_interactions").insert(interaction_record).execute()

        # 6. Evaluate Terminal State & Screening Results
        is_completed = event_type in ("call_completed", "call_evaluated") or call_status == "COMPLETED"
        is_failed = call_status in ("FAILED", "UNREACHABLE", "NO_ANSWER", "BUSY") and payload.get("terminal", False)

        now_iso = datetime.now(timezone.utc).isoformat()

        if is_completed:
            if cycle.get("status") != "COMPLETED":
                # Update screening cycle to COMPLETED
                self.supabase.table("screening_cycles").update({
                    "status": "COMPLETED",
                    "completed_at": now_iso
                }).eq("id", cycle_id).execute()

            # Save Final Screening Result (match_score, recommendation, notes)
            eval_data = payload.get("evaluation") or payload.get("metrics") or data_dict.get("evaluation") or data_dict.get("metrics") or {}
            match_score = eval_data.get("match_score") or eval_data.get("score")
            recommendation = (eval_data.get("recommendation") or "hold").lower()
            if recommendation not in ("shortlist", "hold", "reject"):
                recommendation = "hold"

            notes = eval_data.get("summary") or eval_data.get("notes") or payload.get("summary") or ""

            # Check if result already exists for this cycle (idempotent write)
            existing_res = (
                self.supabase.table("screening_results")
                .select("id")
                .eq("cycle_id", cycle_id)
                .execute()
            )
            if not existing_res.data:
                self.supabase.table("screening_results").insert({
                    "tenant_id": tenant_id,
                    "application_id": cycle["application_id"],
                    "cycle_id": cycle_id,
                    "match_score": match_score,
                    "recommendation": recommendation,
                    "notes": notes
                }).execute()

            # Save Voice Recording if audio/storage url provided
            storage_url = payload.get("recording_url") or payload.get("audio_url") or data_dict.get("recording_url") or data_dict.get("audio_url")
            if storage_url:
                # Query candidate_id from application
                app_data = (
                    self.supabase.table("applications")
                    .select("candidate_id")
                    .eq("id", cycle["application_id"])
                    .single()
                    .execute()
                ).data
                candidate_id = app_data.get("candidate_id") if app_data else None

                if candidate_id:
                    self.supabase.table("voice_recordings").insert({
                        "tenant_id": tenant_id,
                        "candidate_id": candidate_id,
                        "application_id": cycle["application_id"],
                        "cycle_id": cycle_id,
                        "storage_url": storage_url,
                        "duration_seconds": payload.get("duration") or payload.get("call_duration_seconds"),
                        "transcription": payload.get("transcript") or payload.get("transcription"),
                        "sentiment": payload.get("sentiment")
                    }).execute()

        elif is_failed and cycle.get("status") not in ("COMPLETED", "FAILED"):
            self.supabase.table("screening_cycles").update({
                "status": "FAILED",
                "completed_at": now_iso,
                "error_details": {"failure_reason": interaction_record["failure_reason"] or call_status}
            }).eq("id", cycle_id).execute()

        # Mark webhook event as processed
        self.supabase.table("screening_webhook_events").update({
            "processed": True
        }).eq("event_id", event_id).execute()

        return {
            "status": "success",
            "event_id": event_id,
            "cycle_id": cycle_id,
            "call_status": call_status
        }

    def get_application_screening_summary(self, application_id: str, tenant_id: str) -> Dict[str, Any]:
        """Returns the full screening lifecycle and history for an application."""
        cycles = (
            self.supabase.table("screening_cycles")
            .select("id, cycle_number, status, normalized_phone, is_rescreen, rescreen_reason, sarvam_inputs, created_at, completed_at")
            .eq("tenant_id", tenant_id)
            .eq("application_id", application_id)
            .is_("deleted_at", "null")
            .order("cycle_number", desc=True)
            .execute()
        ).data or []

        latest_cycle = cycles[0] if cycles else None
        latest_result = None
        recordings = []

        if latest_cycle:
            # Query screening results for latest cycle
            res = (
                self.supabase.table("screening_results")
                .select("id, match_score, recommendation, notes, created_at")
                .eq("cycle_id", latest_cycle["id"])
                .execute()
            )
            latest_result = res.data[0] if res.data else None

            # Query voice recordings
            recs = (
                self.supabase.table("voice_recordings")
                .select("id, storage_url, duration_seconds, transcription, sentiment, created_at")
                .eq("cycle_id", latest_cycle["id"])
                .execute()
            )
            recordings = recs.data or []

        return {
            "application_id": application_id,
            "active_cycle": latest_cycle if (latest_cycle and latest_cycle["status"] in ("QUEUED", "IN_PROGRESS", "RECONCILIATION_PENDING")) else None,
            "latest_cycle": latest_cycle,
            "total_cycles": len(cycles),
            "screening_result": latest_result,
            "recordings": recordings,
            "history": cycles
        }

    def get_application_call_interactions(self, application_id: str, tenant_id: str) -> List[Dict[str, Any]]:
        """Returns all individual telephony attempts and interactions for an application's screening cycles."""
        cycles = (
            self.supabase.table("screening_cycles")
            .select("id, cycle_number")
            .eq("tenant_id", tenant_id)
            .eq("application_id", application_id)
            .is_("deleted_at", "null")
            .execute()
        ).data or []

        if not cycles:
            return []

        cycle_ids = [c["id"] for c in cycles]
        interactions = (
            self.supabase.table("screening_call_interactions")
            .select("id, cycle_id, sarvam_interaction_id, interaction_number, status, connectivity_status, call_duration_seconds, failure_reason, initiated_at, completed_at, created_at")
            .eq("tenant_id", tenant_id)
            .in_("cycle_id", cycle_ids)
            .is_("deleted_at", "null")
            .order("created_at", desc=True)
            .execute()
        ).data or []

        return interactions


screening_service = ScreeningService()
