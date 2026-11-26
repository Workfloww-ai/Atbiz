import re
import time
import base64
import requests
from typing import Dict, Any, Optional, Tuple
from app.config import settings
from app.services.gdrive_service import GoogleDriveService
from app.services.ingestion_service import IngestionService

GRAPH_API_URL = "https://graph.facebook.com/v21.0"

# In-memory deduplication cache: stores processed msg_ids for 24 hours
_PROCESSED_MESSAGES: Dict[str, float] = {}

class WhatsAppService:
    def __init__(self):
        self.api_token = settings.WHATSAPP_API_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.dovesoft_key = settings.DOVESOFT_API_KEY
        self.dovesoft_waba = settings.DOVESOFT_WABA_NUMBER
        self.gdrive = GoogleDriveService()
        self.ingestion = IngestionService()

    def send_text_message(self, to_phone: str, message: str) -> Dict[str, Any]:
        """Send a WhatsApp text message to a sender (Meta Cloud API or Dovesoft)."""
        clean_phone = re.sub(r'\D', '', to_phone)

        # 1. If Dovesoft is configured, send via Dovesoft REST API
        if self.dovesoft_key and self.dovesoft_waba:
            headers = {
                "key": self.dovesoft_key,
                "wabaNumber": self.dovesoft_waba,
                "Content-Type": "application/json"
            }
            payload = {
                "to": clean_phone,
                "type": "text",
                "text": {"body": message}
            }
            try:
                print(f"[WhatsApp] Sending reply to {clean_phone} via Dovesoft ({settings.DOVESOFT_SEND_URL})...")
                resp = requests.post(settings.DOVESOFT_SEND_URL, headers=headers, json=payload, timeout=10)
                print(f"[WhatsApp] Send response: HTTP {resp.status_code} - {resp.text}")
                try:
                    return resp.json()
                except Exception:
                    return {"status": resp.status_code, "text": resp.text}
            except Exception as e:
                print(f"[Dovesoft] Error sending reply to {to_phone}: {e}")
                return {"error": str(e)}

        # 2. Otherwise send via Meta Cloud API
        if not self.api_token or not self.phone_number_id:
            print("[WhatsApp] Neither Dovesoft nor Meta API credentials configured. Skipping reply.")
            return {"status": "skipped_no_config"}

        url = f"{GRAPH_API_URL}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {"body": message}
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            print(f"[WhatsApp] Error sending message to {to_phone}: {e}")
            return {"error": str(e)}

    def download_dovesoft_media(self, media_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download media file from Dovesoft WhatsApp REST API.
        Endpoint: https://api.dovesoft.io//REST/directApi/downloadAttachmentFile
        Headers: key, wabaNumber
        Params: mediaId
        Decodes base64 string or byte array with retry on 429/5xx.
        """
        if not self.dovesoft_key or not self.dovesoft_waba:
            return None, "Dovesoft API Key or WABA Number not configured"

        url = settings.DOVESOFT_DOWNLOAD_URL
        headers = {
            "key": self.dovesoft_key,
            "wabaNumber": self.dovesoft_waba,
        }
        params = {"mediaId": media_id}
        print(f"[Dovesoft] Requesting media download from {url} (mediaId={media_id})...")

        for attempt in range(1, 4):
            try:
                resp = requests.post(url, headers=headers, params=params, timeout=30)
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(attempt * 2)
                    continue

                if resp.status_code != 200:
                    return None, f"Dovesoft download failed HTTP {resp.status_code}: {resp.text}"

                data = resp.json()
                if isinstance(data, dict):
                    print(f"[Dovesoft] Download response received keys: {list(data.keys())}")
                    raw_file = (
                        data.get("file")
                        or data.get("data")
                        or data.get("fileContent")
                        or data.get("base64")
                        or data.get("attachment")
                        or data.get("content")
                    )
                else:
                    raw_file = data

                if isinstance(raw_file, str):
                    try:
                        file_bytes = base64.b64decode(raw_file)
                    except Exception:
                        file_bytes = raw_file.encode("latin-1")
                elif isinstance(raw_file, (list, tuple)):
                    # Handle signed byte array from Java backend (-128 to 127) -> convert to 0..255
                    file_bytes = bytes([b & 0xFF for b in raw_file])
                elif isinstance(raw_file, bytes):
                    file_bytes = raw_file
                else:
                    return None, f"Unexpected Dovesoft 'file' payload format: {type(raw_file)}"

                # Determine MIME type from magic bytes
                mime_type = "application/pdf"
                if file_bytes.startswith(b"%PDF"):
                    mime_type = "application/pdf"
                elif file_bytes.startswith(b"PK\x03\x04"):
                    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif file_bytes.startswith(b"\xd0\xcf\x11\xe0"):
                    mime_type = "application/msword"

                print(f"✅ [Dovesoft] Successfully decoded file: {len(file_bytes)} bytes (MIME: {mime_type})")
                return file_bytes, mime_type
            except Exception as e:
                if attempt == 3:
                    return None, str(e)
                time.sleep(attempt * 2)

        return None, "Dovesoft download retries exhausted"

    def download_media_bytes(self, media_id: str, direct_url: Optional[str] = None) -> Tuple[Optional[bytes], Optional[str]]:
        """
        Download media bytes:
        - If direct URL is present or media_id is an HTTP URL, download directly.
        - Otherwise uses Dovesoft if configured, else Meta Cloud API.
        """
        target_url = direct_url if (direct_url and direct_url.startswith("http")) else (media_id if (media_id and media_id.startswith("http")) else None)
        if target_url:
            try:
                print(f"[WhatsApp] Downloading media from direct URL: {target_url}")
                res = requests.get(target_url, timeout=30)
                if res.status_code == 200:
                    mime_type = res.headers.get("Content-Type", "application/pdf")
                    return res.content, mime_type
                print(f"[WhatsApp] Direct download returned HTTP {res.status_code}")
            except Exception as e:
                print(f"[WhatsApp] Direct download error: {e}")

        if self.dovesoft_key and self.dovesoft_waba:
            return self.download_dovesoft_media(media_id)

        if not self.api_token:
            return None, "WhatsApp API Token not configured"

        headers = {"Authorization": f"Bearer {self.api_token}"}
        try:
            # 1. Get media URL
            media_info_url = f"{GRAPH_API_URL}/{media_id}"
            res = requests.get(media_info_url, headers=headers, timeout=10)
            if res.status_code != 200:
                return None, f"Failed to get media info: {res.text}"

            download_url = res.json().get("url")
            mime_type = res.json().get("mime_type", "application/pdf")
            if not download_url:
                return None, "No download URL returned by Meta"

            # 2. Download binary bytes
            media_res = requests.get(download_url, headers=headers, timeout=30)
            if media_res.status_code != 200:
                return None, f"Failed to download media bytes: {media_res.status_code}"

            return media_res.content, mime_type
        except Exception as e:
            return None, str(e)

    def process_incoming_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes standard incoming WhatsApp webhook payload (compatible with Dovesoft & Meta).
        Handles forwarded documents (resumes) and text queries.
        Saves files directly into Google Drive 'WhatsApp' folder without touching Supabase.
        """
        now = time.time()
        # Clean up deduplication cache older than 24 hours
        stale_keys = [k for k, t in _PROCESSED_MESSAGES.items() if now - t > 86400]
        for k in stale_keys:
            _PROCESSED_MESSAGES.pop(k, None)

        entries = event_data.get("entry") or []
        results = []

        # Case 1: Unwrapped Meta format where event_data directly contains "messages"
        if not entries and "messages" in event_data:
            entries = [{"changes": [{"value": event_data}]}]

        # Case 2: Nested under "data"
        if not entries and isinstance(event_data.get("data"), dict):
            nested_data = event_data["data"]
            if "messages" in nested_data:
                entries = [{"changes": [{"value": nested_data}]}]
            elif "entry" in nested_data:
                entries = nested_data["entry"]
            else:
                event_data = {**event_data, **nested_data}

        # Case 3: Flat Dovesoft webhook payloads
        if not entries and any(k in event_data for k in ("mediaId", "from", "mobileNo", "media_id", "phone", "sender")):
            sender = (
                event_data.get("from")
                or event_data.get("mobileNo")
                or event_data.get("sender")
                or event_data.get("phone")
                or ""
            )
            media_id = (
                event_data.get("mediaId")
                or event_data.get("media_id")
                or (event_data.get("document") or {}).get("id")
                or event_data.get("id")
            )
            filename = (
                event_data.get("filename")
                or event_data.get("fileName")
                or (event_data.get("document") or {}).get("filename")
                or f"Resume_{sender}.pdf"
            )
            msg_type = (
                event_data.get("type")
                or ("document" if (media_id or event_data.get("caption") or "pdf" in str(filename).lower()) else "text")
            )
            normalized_msg = {
                "id": event_data.get("id") or f"dovesoft_{int(now)}_{sender}",
                "from": str(sender),
                "type": msg_type,
                "document": {"id": media_id, "filename": filename} if media_id else {},
                "text": {"body": event_data.get("text", "")} if msg_type == "text" else {}
            }
            entries = [{
                "changes": [{
                    "value": {
                        "messages": [normalized_msg],
                        "contacts": [{"wa_id": str(sender), "profile": {"name": event_data.get("name", "Team Member")}}]
                    }
                }]
            }]

        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}

                for msg in messages:
                    msg_id = msg.get("id")
                    # Deduplication: ignore if message ID was already processed
                    if msg_id:
                        if msg_id in _PROCESSED_MESSAGES:
                            print(f"[WhatsApp Webhook] Skipping duplicate message {msg_id}")
                            continue
                        _PROCESSED_MESSAGES[msg_id] = now

                    sender_wa_id = msg.get("from")
                    sender_name = contacts.get(sender_wa_id) or "Team Member"
                    msg_type = msg.get("type")
                    formatted_phone = f"+{sender_wa_id}" if sender_wa_id else "+91-0000000000"

                    # 1. Document / Resume uploaded (or forwarded)
                    if msg_type == "document":
                        doc = msg.get("document", {})
                        media_id = doc.get("id")
                        doc_url = doc.get("url") or doc.get("link") or doc.get("attachmentUrl") or doc.get("fileUrl")
                        orig_filename = doc.get("filename") or f"Resume_{sender_wa_id}.pdf"
                        clean_filename = re.sub(r'[^\w\.\-]', '_', orig_filename)
                        safe_file_name = f"{sender_wa_id}_{clean_filename}"

                        print(f"[WhatsApp] Processing incoming document: {clean_filename} (media_id: {media_id}, url: {doc_url}) from {sender_wa_id}")
                        file_bytes, mime_or_err = self.download_media_bytes(media_id, direct_url=doc_url)
                        if not file_bytes:
                            print(f"❌ [WhatsApp] Media download failed: {mime_or_err}")
                            self.send_text_message(
                                sender_wa_id,
                                f"⚠️ Could not download {clean_filename}. Please try forwarding it again."
                            )
                            results.append({"status": "download_failed", "error": mime_or_err})
                            continue

                        # Save to Google Drive 'WhatsApp' folder
                        drive_file_id = None
                        try:
                            whatsapp_folder_id = self.gdrive.get_whatsapp_folder_id()
                            print(f"[WhatsApp] Uploading to Google Drive folder '{whatsapp_folder_id}' as '{safe_file_name}'...")
                            drive_file = self.gdrive.upload_file(
                                folder_id=whatsapp_folder_id,
                                file_name=safe_file_name,
                                file_bytes=file_bytes,
                                mime_type=mime_or_err or "application/pdf"
                            )
                            drive_file_id = drive_file.get("id")
                            print(f"✅ [WhatsApp] Resume successfully saved to Drive 'WhatsApp' folder: {safe_file_name} (ID: {drive_file_id})")
                        except Exception as drive_err:
                            print(f"❌ [WhatsApp] Failed to save to Drive: {drive_err}")
                            results.append({"status": "drive_upload_failed", "error": str(drive_err)})
                            continue

                        # Auto-reply confirmation to the team member who forwarded it
                        reply_text = (
                            f"✅ Uploaded successfully in your Drive!\n\n"
                            f"📄 File: {clean_filename}\n"
                            f"📁 Folder: Google Drive > WhatsApp"
                        )
                        self.send_text_message(sender_wa_id, reply_text)

                        results.append({
                            "status": "saved_to_drive",
                            "sender": sender_wa_id,
                            "file_name": safe_file_name,
                            "drive_file_id": drive_file_id,
                            "drive_folder": "WhatsApp"
                        })

                    # 2. Text message
                    elif msg_type == "text":
                        reply_text = (
                            f"Hi {sender_name}! 👋\n\n"
                            f"To submit a referral resume, simply **forward the PDF or Word document** here. "
                            f"It will be automatically saved to Google Drive."
                        )
                        self.send_text_message(sender_wa_id, reply_text)
                        results.append({"status": "text_reply_sent", "sender": sender_wa_id})

                    # 3. Image received
                    elif msg_type == "image":
                        reply_text = (
                            f"Hi {sender_name}! We received your photo/image. "
                            f"For best results, please send your resume in **PDF** or **Word document** format."
                        )
                        self.send_text_message(sender_wa_id, reply_text)
                        results.append({"status": "image_notified", "sender": sender_wa_id})

        return {"processed": len(results), "results": results}
