import json
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException, Query
from typing import Optional, Dict, Any
from app.config import settings
from app.services.whatsapp_service import WhatsAppService

# Router that responds to /api/webhooks/whatsapp AND /api/whatsapp
router = APIRouter(tags=["WhatsApp"])

@router.get("/api/webhooks/whatsapp")
@router.get("/api/whatsapp")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
):
    """
    Verification endpoint called by Meta / Dovesoft when setting up or checking callback URL.
    """
    print(f"📡 [WhatsApp Webhook GET] Verification check: mode={hub_mode}, token={hub_verify_token}")
    expected_token = settings.WHATSAPP_VERIFY_TOKEN

    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        print("✅ [WhatsApp Webhook] Verification successful.")
        return Response(content=hub_challenge, media_type="text/plain", status_code=200)

    # Some providers like Dovesoft simply do a GET request to verify URL is reachable
    if not hub_mode and not hub_verify_token:
        print("ℹ️ [WhatsApp Webhook GET] Ping check received, returning 200 OK.")
        return {"status": "ok", "message": "WhatsApp webhook endpoint is active and listening"}

    print(f"⚠️ [WhatsApp Webhook] Verification token mismatch. Received: '{hub_verify_token}', Expected: '{expected_token}'")
    raise HTTPException(status_code=403, detail="Verification token mismatch")

@router.post("/api/webhooks/whatsapp")
@router.post("/api/whatsapp")
async def handle_whatsapp_message(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receives incoming WhatsApp message notifications from Dovesoft or Meta.
    Accepts both JSON and form payloads. Returns immediate 200 OK.
    """
    body: Dict[str, Any] = {}
    content_type = request.headers.get("content-type", "")

    try:
        if "application/json" in content_type:
            body = await request.json()
        elif "form" in content_type:
            form = await request.form()
            body = dict(form)
        else:
            raw = await request.body()
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {"raw_payload": raw.decode("utf-8", errors="ignore")}
    except Exception as e:
        print(f"❌ [WhatsApp Webhook] Failed to parse request body: {e}")
        body = {}

    print("\n" + "="*50)
    print(f"📥 [WhatsApp Webhook POST] New message notification received!")
    print(f"Headers: Content-Type={content_type}")
    print(f"Body: {json.dumps(body, indent=2, default=str)}")
    print("="*50 + "\n")

    wa_service = WhatsAppService()
    # Process in background task to never block caller timeout
    background_tasks.add_task(wa_service.process_incoming_event, body)

    return {"status": "received", "success": True}

@router.get("/api/webhooks/whatsapp/status")
@router.get("/api/whatsapp/status")
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
