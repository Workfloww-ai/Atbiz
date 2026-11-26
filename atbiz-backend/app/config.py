import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

class Settings:
    # Supabase Configuration
    _raw_url = os.getenv("SUPABASE_URL", "")
    if _raw_url.startswith("http"):
        SUPABASE_URL = _raw_url
    else:
        SUPABASE_URL = "https://lhmcqiwjdgtszxyjvtuj.supabase.co"
    
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

    # Default Organization Tenant (from Phase 1 seed data)
    DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "a0000000-0000-0000-0000-000000000001")

    # Google Drive Configuration (Absolute Paths)
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(BASE_DIR, "service_account.json"))
    GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
    TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
    OAUTH_CLIENT_FILE = os.path.join(BASE_DIR, "credentials.json")
    MAX_RESUME_SIZE_MB = int(os.getenv("MAX_RESUME_SIZE_MB", "15"))

    # WhatsApp Configuration (Meta Cloud API & Dovesoft)
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "atbiz_whatsapp_verify_token_2026")
    WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    DOVESOFT_API_KEY = os.getenv("DOVESOFT_API_KEY", "")
    DOVESOFT_WABA_NUMBER = os.getenv("DOVESOFT_WABA_NUMBER", os.getenv("WABA_NUMBER", ""))
    DOVESOFT_DOWNLOAD_URL = os.getenv("DOVESOFT_DOWNLOAD_URL", "https://api.dovesoft.io/REST/directApi/downloadAttachmentFile")
    DOVESOFT_SEND_URL = os.getenv("DOVESOFT_SEND_URL") or os.getenv("DOVESOFT_WHATSAPP_URL") or "https://api.dovesoft.io/REST/directApi/message"

    # Email / Resend Configuration
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "AT BiZ <notifications@atbiz.in>")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

settings = Settings()
