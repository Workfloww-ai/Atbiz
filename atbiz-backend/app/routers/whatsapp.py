from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException, Query
from typing import Optional, Dict, Any
from app.config import settings
from app.services.whatsapp_service import WhatsAppService

router = APIRouter(prefix="/api/webhooks/whatsapp", tags=["WhatsApp"])

@router.get("")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """
    Verification endpoint called by Meta when setting up the webhook in Meta App Dashboard.
    Responds with hub.challenge if hub.verify_token matches settings.WHATSAPP_VERIFY_TOKEN.
    """
    expected_token = settings.WHATSAPP_VERIFY_TOKEN

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        print("[WhatsApp Webhook] Verification successful.")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)

    print(f"[WhatsApp Webhook] Verification failed. Received token: '{hub_verify_token}', Expected: '{expected_token}'")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receives incoming WhatsApp message notifications from Meta.
    Returns immediate 200 OK to satisfy Meta's 3-second timeout requirement,
    and processes media downloading + Google Drive upload asynchronously.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    wa_service = WhatsAppService()
    # Process in background task to never block Meta's webhook runner
    background_tasks.add_task(wa_service.process_incoming_event, body)

    return {"status": "received"}

@router.get("/status")
def get_whatsapp_config_status():
    """Returns the current WhatsApp integration status (Meta & Dovesoft)."""
    has_dovesoft = bool(settings.DOVESOFT_API_KEY and settings.DOVESOFT_WABA_NUMBER)
    has_meta = bool(settings.WHATSAPP_API_TOKEN and settings.WHATSAPP_PHONE_NUMBER_ID)

    return {
        "is_configured": has_dovesoft or has_meta,
        "provider": "dovesoft" if has_dovesoft else ("meta" if has_meta else "none"),
        "has_dovesoft_configured": has_dovesoft,
        "has_meta_configured": has_meta,
        "dovesoft_waba_number": settings.DOVESOFT_WABA_NUMBER,
        "webhook_url": "/api/webhooks/whatsapp",
        "verify_token": settings.WHATSAPP_VERIFY_TOKEN
    }
