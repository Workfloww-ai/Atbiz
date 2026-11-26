from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from typing import List, Optional
from pydantic import BaseModel, Field

from app.dependencies.auth import AuthUser, get_current_user
from app.config import settings
from app.services.screening_service import screening_service

router = APIRouter(prefix="/api/screening", tags=["AI Screening"])


class TriggerScreeningRequest(BaseModel):
    application_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of application UUIDs to trigger screening for"
    )
    force_rescreen: bool = Field(
        default=False,
        description="Whether to allow re-screening of previously completed applications"
    )


@router.post("/trigger", status_code=status.HTTP_200_OK)
async def trigger_screening(
    request: TriggerScreeningRequest,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Triggers outbound AI screening for selected candidate applications.
    Accepts application_ids only. Validates tenant access, Indian phone numbers,
    and authoritative job context before streaming to Sarvam.
    """
    if not request.application_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="application_ids list cannot be empty"
        )

    result = await screening_service.trigger_screening_batch(
        application_ids=request.application_ids,
        force_rescreen=request.force_rescreen,
        auth_user=current_user
    )
    return result


@router.get("/applications/{application_id}/status")
def get_application_screening_status(
    application_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Returns the real-time AI screening status, latest assessment, and cycle history
    for a given recruitment application.
    """
    tenant_id = current_user.tenant_id or settings.DEFAULT_TENANT_ID
    return screening_service.get_application_screening_summary(
        application_id=application_id,
        tenant_id=tenant_id
    )


@router.get("/applications/{application_id}/interactions")
def get_application_call_interactions(
    application_id: str,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Returns all telephony attempts and interaction events across all screening cycles
    for a given recruitment application.
    """
    tenant_id = current_user.tenant_id or settings.DEFAULT_TENANT_ID
    interactions = screening_service.get_application_call_interactions(
        application_id=application_id,
        tenant_id=tenant_id
    )
    return {"application_id": application_id, "interactions": interactions}


@router.post("/webhooks/sarvam")
async def sarvam_webhook(
    request: Request,
    sarvam_signature: Optional[str] = Header(None, alias="Sarvam-Signature"),
    sarvam_timestamp: Optional[str] = Header(None, alias="Sarvam-Timestamp")
):
    """
    Inbound webhook receiver for Sarvam AI Voice Agent call events.
    Verifies HMAC-SHA256 signature, validates 300-second replay window,
    deduplicates events, and stores call results/recordings.
    """
    raw_body = await request.body()
    return await screening_service.process_sarvam_webhook(
        raw_body=raw_body,
        signature=sarvam_signature,
        timestamp=sarvam_timestamp
    )
