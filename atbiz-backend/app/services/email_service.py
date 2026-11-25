import httpx
from typing import Optional
from app.config import settings

class EmailService:
    """
    Handles transactional emails for AT BiZ.
    Sends via Resend API when RESEND_API_KEY is configured.
    Falls back to structured console logging during local development.
    """

    @staticmethod
    def send_welcome_email(
        to_email: str,
        full_name: str,
        temporary_password: str,
        organization_name: str = "AT BiZ Workforce Solutions",
        role_name: str = "Team Member",
        assigned_modules: Optional[list] = None
    ) -> bool:
        login_url = f"{settings.FRONTEND_URL}/login"
        modules_str = ", ".join(assigned_modules) if assigned_modules else "Standard Access"

        html_content = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px;">
            <div style="border-bottom: 2px solid #0f172a; padding-bottom: 12px; margin-bottom: 20px;">
                <h2 style="color: #0f172a; margin: 0; font-size: 20px; font-weight: 700;">AT BiZ Workforce Platform</h2>
                <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">Enterprise Recruitment & Operations</p>
            </div>
            <p style="color: #334155; font-size: 15px;">Hello <strong>{full_name}</strong>,</p>
            <p style="color: #334155; font-size: 14px; line-height: 1.5;">
                You have been invited to join <strong>{organization_name}</strong> on the AT BiZ Platform as <strong>{role_name}</strong>.
            </p>
            
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0; font-size: 13px; color: #475569;"><strong>Your Account Credentials:</strong></p>
                <p style="margin: 4px 0; font-size: 14px; color: #1e293b;"><strong>Email:</strong> {to_email}</p>
                <p style="margin: 4px 0; font-size: 14px; color: #1e293b;"><strong>Temporary Password:</strong> <code style="background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-size: 15px; font-weight: 600;">{temporary_password}</code></p>
                <p style="margin: 8px 0 0 0; font-size: 12px; color: #b45309;">⚠️ You will be prompted to choose a permanent password upon your first sign in.</p>
            </div>

            <p style="font-size: 13px; color: #64748b; margin: 12px 0;">
                <strong>Assigned Modules:</strong> {modules_str}
            </p>

            <div style="margin: 24px 0;">
                <a href="{login_url}" style="background-color: #0f172a; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 600; display: inline-block;">
                    Log In to AT BiZ &rarr;
                </a>
            </div>

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;" />
            <p style="font-size: 11px; color: #94a3b8; margin: 0;">
                This is an automated system notification. Please do not reply directly to this email.
            </p>
        </div>
        """

        if settings.RESEND_API_KEY:
            try:
                res = httpx.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": settings.RESEND_FROM_EMAIL,
                        "to": [to_email],
                        "subject": f"Welcome to {organization_name} - Your AT BiZ Credentials",
                        "html": html_content
                    },
                    timeout=10.0
                )
                if res.status_code in (200, 201):
                    print(f"✅ Welcome email sent via Resend to: {to_email}")
                    return True
                else:
                    print(f"❌ Resend API error ({res.status_code}): {res.text}")
            except Exception as e:
                print(f"❌ Failed to dispatch email via Resend: {e}")

        # Development Fallback: Structured Console Output
        print("\n" + "=" * 65)
        print("📧 [AT BiZ EMAIL SERVICE - DEVELOPMENT MODE]")
        print(f"To:                 {to_email} ({full_name})")
        print(f"Organization:       {organization_name}")
        print(f"Role:               {role_name}")
        print(f"Assigned Modules:   {modules_str}")
        print(f"Temporary Password: {temporary_password}")
        print(f"Login URL:          {login_url}")
        print("=" * 65 + "\n")
        return True
