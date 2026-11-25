import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.dependencies.auth import (
    AuthUser,
    get_current_user,
    require_admin,
    require_developer
)
from app.database import get_supabase
from app.config import settings
from app.services.email_service import EmailService

router = APIRouter(prefix="/api/users", tags=["User Management & Auth"])


class InviteUserRequest(BaseModel):
    email: str
    full_name: str
    phone: Optional[str] = None
    account_tier: str = "tenant_user"  # 'tenant_admin' or 'tenant_user'
    role_name: Optional[str] = "Team Member"
    client_ids: List[str] = []
    site_ids: List[str] = []
    modules: List[str] = ["resume_desk"]
    target_tenant_id: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    new_password: str


def generate_temp_password(length: int = 12) -> str:
    """Generates a secure, human-readable temporary password with symbols and digits."""
    upper = secrets.choice(string.ascii_uppercase)
    lower = secrets.choice(string.ascii_lowercase)
    digit = secrets.choice(string.digits)
    symbol = secrets.choice("@#$%!*")
    all_chars = string.ascii_letters + string.digits + "@#$%!*"
    rest = "".join(secrets.choice(all_chars) for _ in range(length - 4))
    combined = list(upper + lower + digit + symbol + rest)
    secrets.SystemRandom().shuffle(combined)
    return "".join(combined)


@router.get("/me")
def get_current_user_profile(user: AuthUser = Depends(get_current_user)):
    """Returns the authenticated user's profile, role, tenant, and allowed scopes."""
    return {
        "status": "success",
        "user": user.model_dump()
    }


@router.get("")
def list_tenant_users(
    tenant_id: Optional[str] = None,
    user: AuthUser = Depends(require_admin)
):
    """
    Lists users under the current tenant.
    Developer accounts can query any tenant; Tenant Admins can only query their own.
    """
    supabase = get_supabase()
    target_tenant = user.tenant_id

    if user.is_developer and tenant_id:
        target_tenant = tenant_id

    query = supabase.table("profiles").select(
        "id, email, full_name, phone, account_tier, tenant_id, primary_role_id, status, must_change_password, created_at, roles(name), tenants(name)"
    )
    if target_tenant:
        query = query.eq("tenant_id", target_tenant)

    profiles = query.order("created_at", desc=True).execute().data or []

    # Enrich each profile with assigned clients, modules, role_name, tenant_name
    user_ids = [p["id"] for p in profiles]
    client_assigns = {}
    module_assigns = {}

    if user_ids:
        # Fetch client assignments
        ca_data = supabase.table("user_client_assignments").select(
            "user_id, client_id, clients(name)"
        ).in_("user_id", user_ids).eq("status", "active").execute().data or []
        for r in ca_data:
            uid = r["user_id"]
            cname = (r.get("clients") or {}).get("name") or r["client_id"]
            client_assigns.setdefault(uid, []).append({"id": r["client_id"], "name": cname})

        # Fetch module assignments
        ma_data = supabase.table("user_module_assignments").select(
            "user_id, module_id"
        ).in_("user_id", user_ids).execute().data or []
        for r in ma_data:
            uid = r["user_id"]
            module_assigns.setdefault(uid, []).append(r["module_id"])

    for p in profiles:
        uid = p["id"]
        role_obj = p.get("roles") or {}
        tenant_obj = p.get("tenants") or {}
        p["role_name"] = role_obj.get("name") or None
        p["tenant_name"] = tenant_obj.get("name") or None
        p["assigned_clients"] = client_assigns.get(uid, [])
        p["assigned_modules"] = module_assigns.get(uid, [])

    return {
        "status": "success",
        "total": len(profiles),
        "users": profiles
    }


@router.post("/invite")
def invite_user(
    req: InviteUserRequest,
    user: AuthUser = Depends(require_admin)
):
    """
    Super Admin / Admin provisions a new team member.
    - Generates temporary password.
    - Sets must_change_password = TRUE.
    - Binds user to specified clients, sites, and modules.
    - Sends Welcome Email with credentials via Resend.
    """
    supabase = get_supabase()

    # Determine tenant
    if req.account_tier == "developer":
        target_tenant_id = None
    elif user.is_developer:
        target_tenant_id = req.target_tenant_id or settings.DEFAULT_TENANT_ID
    else:
        target_tenant_id = user.tenant_id or settings.DEFAULT_TENANT_ID

    if req.account_tier != "developer" and not target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid tenant_id is required to provision a user."
        )

    # Permission check: Tenant Admins cannot create Super Admins or Developers
    if not user.is_super_admin and req.account_tier in ("tenant_super_admin", "developer"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant Admins can only invite Standard Users or fellow Admins."
        )

    # 1. Generate secure temporary password
    temp_password = generate_temp_password(12)

    # 2. Create user in Supabase Auth via Admin API
    try:
        auth_resp = supabase.auth.admin.create_user({
            "email": req.email,
            "password": temp_password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": req.full_name,
                "phone": req.phone or "",
                "tenant_id": target_tenant_id,
                "account_tier": req.account_tier
            }
        })
        new_auth_user = auth_resp.user
        new_user_id = str(new_auth_user.id)
    except Exception as e:
        err_msg = str(e)
        if "already registered" in err_msg.lower() or "unique" in err_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email '{req.email}' is already registered."
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user account: {err_msg}"
        )

    # 3. Lookup or create primary_role_id if role_name provided
    role_id = None
    if req.role_name and target_tenant_id:
        try:
            r_res = supabase.table("roles").select("id").eq("tenant_id", target_tenant_id).eq("name", req.role_name).execute()
            if r_res.data:
                role_id = r_res.data[0]["id"]
            else:
                ins = supabase.table("roles").insert({
                    "tenant_id": target_tenant_id,
                    "name": req.role_name,
                    "description": f"Role for {req.role_name}"
                }).execute()
                if ins.data:
                    role_id = ins.data[0]["id"]
        except Exception as e:
            print(f"Role lookup warning: {e}")

    # 4. Ensure profile in public.profiles with must_change_password = True
    try:
        supabase.table("profiles").upsert({
            "id": new_user_id,
            "tenant_id": target_tenant_id,
            "email": req.email,
            "full_name": req.full_name,
            "phone": req.phone or "",
            "account_tier": req.account_tier,
            "primary_role_id": role_id,
            "must_change_password": True,
            "status": "active"
        }).execute()
    except Exception as e:
        print(f"Warning: Failed to update profile attributes: {e}")

    # 4. Save Client Assignments
    if req.client_ids:
        client_records = [
            {
                "tenant_id": target_tenant_id,
                "user_id": new_user_id,
                "client_id": cid,
                "assigned_by": user.id,
                "status": "active"
            }
            for cid in req.client_ids
        ]
        try:
            supabase.table("user_client_assignments").upsert(
                client_records, on_conflict="tenant_id, user_id, client_id"
            ).execute()
        except Exception as e:
            print(f"Warning: Failed to insert client assignments: {e}")

    # 5. Save Site Assignments (if provided)
    if req.site_ids:
        # Resolve client_id for each site
        site_data = supabase.table("client_sites").select("id, client_id").in_("id", req.site_ids).execute().data or []
        site_map = {s["id"]: s["client_id"] for s in site_data}
        site_records = [
            {
                "tenant_id": target_tenant_id,
                "user_id": new_user_id,
                "client_id": site_map.get(sid, req.client_ids[0] if req.client_ids else None),
                "site_id": sid,
                "assigned_by": user.id,
                "status": "active"
            }
            for sid in req.site_ids if site_map.get(sid) or req.client_ids
        ]
        if site_records:
            try:
                supabase.table("user_site_assignments").upsert(
                    site_records, on_conflict="tenant_id, user_id, site_id"
                ).execute()
            except Exception as e:
                print(f"Warning: Failed to insert site assignments: {e}")

    # 6. Save Module Assignments
    if req.modules:
        module_records = [
            {
                "tenant_id": target_tenant_id,
                "user_id": new_user_id,
                "module_id": mid,
                "assigned_by": user.id
            }
            for mid in req.modules
        ]
        try:
            supabase.table("user_module_assignments").upsert(
                module_records, on_conflict="tenant_id, user_id, module_id"
            ).execute()
        except Exception as e:
            print(f"Warning: Failed to insert module assignments: {e}")

    # 7. Fetch tenant organization name for the welcome email
    tenant_name = "AT BiZ Workforce Solutions"
    try:
        t_resp = supabase.table("tenants").select("name").eq("id", target_tenant_id).execute()
        if t_resp.data:
            tenant_name = t_resp.data[0].get("name", tenant_name)
    except Exception:
        pass

    # 8. Send Welcome Email
    EmailService.send_welcome_email(
        to_email=req.email,
        full_name=req.full_name,
        temporary_password=temp_password,
        organization_name=tenant_name,
        role_name=req.role_name or ("Admin" if req.account_tier == "tenant_admin" else "Team Member"),
        assigned_modules=req.modules
    )

    return {
        "status": "success",
        "message": f"User {req.email} successfully provisioned.",
        "user_id": new_user_id,
        "email": req.email,
        "temporary_password": temp_password,  # Returned so Admin can view/copy directly
        "must_change_password": True,
        "modules": req.modules
    }


@router.post("/change-password")
def change_user_password(
    req: ChangePasswordRequest,
    user: AuthUser = Depends(get_current_user)
):
    """
    Updates the authenticated user's password and removes the must_change_password requirement.
    """
    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )

    supabase = get_supabase()

    # Update password in Supabase Auth via Admin API
    try:
        supabase.auth.admin.update_user_by_id(
            user.id,
            {"password": req.new_password}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update password: {str(e)}"
        )

    # Clear must_change_password flag
    try:
        supabase.table("profiles").update({
            "must_change_password": False
        }).eq("id", user.id).execute()
    except Exception as e:
        print(f"Warning: Failed to reset must_change_password flag: {e}")

    return {
        "status": "success",
        "message": "Password changed successfully. Your account is now fully active."
    }


@router.get("/tenants")
def list_all_tenants(user: AuthUser = Depends(get_current_user)):
    """Lists available tenants. Developers see all tenants; standard users see their assigned tenant."""
    supabase = get_supabase()
    if user.is_developer:
        try:
            tenants = supabase.table("tenants").select("id, name, slug, billing_tier, status").execute().data or []
        except Exception:
            tenants = []
        if not tenants:
            tenants = [
                {
                    "id": settings.DEFAULT_TENANT_ID,
                    "name": "AT BiZ Workforce Solutions Ltd.",
                    "slug": "atbiz-workforce",
                    "billing_tier": "enterprise",
                    "status": "active"
                }
            ]
        return {"status": "success", "tenants": tenants}
    else:
        return {
            "status": "success",
            "tenants": [
                {
                    "id": user.tenant_id or settings.DEFAULT_TENANT_ID,
                    "name": user.tenant_name or "AT BiZ Workforce Solutions Ltd."
                }
            ]
        }
