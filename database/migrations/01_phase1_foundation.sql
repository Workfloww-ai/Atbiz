-- ==============================================================================
-- AT BiZ: Phase 1 Database Migration (Foundation & Security Subsystem)
-- Technology: PostgreSQL 15+ / Supabase
-- Security Model: Multi-Tenant Isolation with Developer God-Mode & Tenant RLS
-- ==============================================================================

-- 1. EXTENSIONS
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. TABLE DEFINITIONS (Tables 1 to 6)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 1: tenants
-- Master organization table. Every operational record is isolated by tenant_id.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    billing_tier VARCHAR(32) NOT NULL DEFAULT 'standard',
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenants_slug ON public.tenants(slug);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON public.tenants(status);

-- ------------------------------------------------------------------------------
-- Table 2: roles
-- Tenant-specific roles (e.g. Tenant Super Admin, HR Manager, Recruiter).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES public.tenants(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    description TEXT,
    is_system_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_roles_tenant_name UNIQUE (tenant_id, name)
);

CREATE INDEX IF NOT EXISTS idx_roles_tenant_id ON public.roles(tenant_id);

-- ------------------------------------------------------------------------------
-- Table 3: modules
-- Global catalog of all operational subsystems in AT BiZ (immutable by tenants).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.modules (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0
);

-- ------------------------------------------------------------------------------
-- Table 4: permissions
-- Specific granular actions linked to modules.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.permissions (
    id VARCHAR(64) PRIMARY KEY,
    module_id VARCHAR(32) NOT NULL REFERENCES public.modules(id) ON DELETE CASCADE,
    action VARCHAR(32) NOT NULL,
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_permissions_module ON public.permissions(module_id);

-- ------------------------------------------------------------------------------
-- Table 5: role_permissions
-- Mapping between roles and allowed permissions.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES public.tenants(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
    permission_id VARCHAR(64) NOT NULL REFERENCES public.permissions(id) ON DELETE CASCADE,
    CONSTRAINT uq_role_permissions UNIQUE (tenant_id, role_id, permission_id)
);

CREATE INDEX IF NOT EXISTS idx_role_permissions_lookup ON public.role_permissions(tenant_id, role_id);

-- ------------------------------------------------------------------------------
-- Table 6: profiles
-- Extends Supabase auth.users. 
-- Enforces: 1 EMAIL = 1 USER = 1 TENANT ONLY (unless Developer Account).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID REFERENCES public.tenants(id) ON DELETE RESTRICT,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(24),
    account_tier VARCHAR(32) NOT NULL DEFAULT 'tenant_user' 
        CHECK (account_tier IN ('developer', 'tenant_super_admin', 'tenant_admin', 'tenant_user')),
    primary_role_id UUID REFERENCES public.roles(id) ON DELETE SET NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'invited')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Invariance: Developer has tenant_id = NULL. All other tiers MUST have a tenant_id.
    CONSTRAINT chk_developer_tenant_null CHECK (
        (account_tier = 'developer' AND tenant_id IS NULL) OR 
        (account_tier != 'developer' AND tenant_id IS NOT NULL)
    ),
    -- Required for composite foreign keys from child tables
    CONSTRAINT uq_profiles_tenant_user UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON public.profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(email);
CREATE INDEX IF NOT EXISTS idx_profiles_tier_status ON public.profiles(account_tier, status);

-- ==============================================================================
-- 3. SECURITY & AUTHENTICATION HELPER FUNCTIONS (SECURITY DEFINER)
-- ==============================================================================

-- Extract active user's tenant_id
CREATE OR REPLACE FUNCTION public.get_current_tenant_id()
RETURNS UUID AS $$
  SELECT tenant_id FROM public.profiles WHERE id = auth.uid() AND status = 'active';
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Check if active user is a Developer (Cross-Tenant God-Mode)
CREATE OR REPLACE FUNCTION public.is_developer()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE id = auth.uid() AND account_tier = 'developer' AND status = 'active'
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Check if active user is a Tenant Super Admin (Organization Owner)
CREATE OR REPLACE FUNCTION public.is_tenant_super_admin()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE id = auth.uid() AND account_tier = 'tenant_super_admin' AND status = 'active'
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- Check if active user is a Tenant Admin or higher
CREATE OR REPLACE FUNCTION public.is_tenant_admin()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE id = auth.uid() 
      AND account_tier IN ('tenant_super_admin', 'tenant_admin') 
      AND status = 'active'
  );
$$ LANGUAGE sql STABLE SECURITY DEFINER;

-- ==============================================================================
-- 4. AUTOMATIC PROFILE PROVISIONING TRIGGER (auth.users -> public.profiles)
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER AS $$
DECLARE
    v_tier VARCHAR(32);
    v_tenant_id UUID;
BEGIN
    -- Extract account_tier from auth signup metadata (default to 'tenant_user')
    v_tier := COALESCE(new.raw_user_meta_data->>'account_tier', 'tenant_user');
    
    -- If developer, tenant_id is explicitly null
    IF v_tier = 'developer' THEN
        v_tenant_id := NULL;
    ELSE
        v_tenant_id := (new.raw_user_meta_data->>'tenant_id')::UUID;
        IF v_tenant_id IS NULL THEN
            RAISE EXCEPTION 'A valid tenant_id is required to register a non-developer user account.';
        END IF;
    END IF;

    INSERT INTO public.profiles (
        id,
        tenant_id,
        email,
        full_name,
        phone,
        account_tier,
        status
    ) VALUES (
        new.id,
        v_tenant_id,
        new.email,
        COALESCE(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1)),
        new.raw_user_meta_data->>'phone',
        v_tier,
        'active'
    );
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();

-- ==============================================================================
-- 5. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

-- Enable RLS on all Phase 1 tables
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_permissions ENABLE ROW LEVEL SECURITY;

-- Tenants Policies
CREATE POLICY tenants_select_policy ON public.tenants
FOR SELECT USING (
    public.is_developer() OR id = public.get_current_tenant_id()
);

CREATE POLICY tenants_write_policy ON public.tenants
FOR ALL USING (
    public.is_developer()
);

-- Profiles Policies
CREATE POLICY profiles_select_policy ON public.profiles
FOR SELECT USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id())
    OR (id = auth.uid())
);

CREATE POLICY profiles_update_policy ON public.profiles
FOR UPDATE USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id() 
        AND public.is_tenant_admin()
    )
    OR (id = auth.uid()) -- User updating their own profile
);

-- Roles Policies
CREATE POLICY roles_select_policy ON public.roles
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY roles_write_policy ON public.roles
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Modules Policies (Read-only for all authenticated users, editable only by Developer)
CREATE POLICY modules_select_policy ON public.modules
FOR SELECT TO authenticated USING (TRUE);

CREATE POLICY modules_write_policy ON public.modules
FOR ALL USING (public.is_developer());

-- Permissions Policies (Read-only for authenticated users, editable only by Developer)
CREATE POLICY permissions_select_policy ON public.permissions
FOR SELECT TO authenticated USING (TRUE);

CREATE POLICY permissions_write_policy ON public.permissions
FOR ALL USING (public.is_developer());

-- Role Permissions Policies
CREATE POLICY role_permissions_select_policy ON public.role_permissions
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY role_permissions_write_policy ON public.role_permissions
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- ==============================================================================
-- 6. SYSTEM SEED DATA (Modules, Core Permissions & Initial Setup)
-- ==============================================================================

-- Seed 15 Standard Operational Modules
INSERT INTO public.modules (id, name, description, sort_order) VALUES
('dashboard', 'Dashboard', 'Executive summaries and metrics overview', 1),
('clients', 'Client Management', 'Corporate clients and agreement settings', 2),
('sites', 'Site Management', 'Operational state circles, hubs, and sites', 3),
('vacancies', 'Vacancy Management', 'Job requisitions and headcount requirements', 4),
('candidates', 'Candidate Management', 'Candidate profiles and resume records', 5),
('screening', 'Resume Screening', 'Automated parsing, AI matching and reviews', 6),
('recruitment', 'Recruitment Pipeline', 'Application stages, interviews, and status', 7),
('voice_recordings', 'Voice Recordings', 'Telephonic pre-screening and audio logs', 8),
('offers', 'Offer Management', 'Offer letter generation, dispatch, and tracking', 9),
('onboarding', 'Onboarding Operations', 'Document verification, compliance, and KYC', 10),
('employees', 'Employee Management', 'Permanent master records and deployments', 11),
('attendance', 'Attendance Tracking', 'Clock-in logs, biometric/geo records, overtime', 12),
('mis', 'MIS Reports', 'Analytical dashboards and custom reports', 13),
('users', 'User Management', 'User accounts, roles, and site permissions', 14),
('settings', 'Tenant Settings', 'System configurations and operational presets', 15)
ON CONFLICT (id) DO UPDATE SET 
    name = EXCLUDED.name, 
    description = EXCLUDED.description, 
    sort_order = EXCLUDED.sort_order;

-- Seed Standard Granular Permissions
INSERT INTO public.permissions (id, module_id, action, description) VALUES
-- Dashboard
('dashboard:view', 'dashboard', 'view', 'View dashboard metrics and analytics'),
-- Clients
('clients:view', 'clients', 'view', 'View client accounts'),
('clients:create', 'clients', 'create', 'Create new client accounts'),
('clients:edit', 'clients', 'edit', 'Update client account details'),
-- Sites
('sites:view', 'sites', 'view', 'View client sites'),
('sites:create', 'sites', 'create', 'Create new sites/circles'),
('sites:assign', 'sites', 'assign', 'Assign users to sites'),
-- Vacancies
('vacancies:view', 'vacancies', 'view', 'View job vacancies'),
('vacancies:create', 'vacancies', 'create', 'Create job vacancies'),
('vacancies:edit', 'vacancies', 'edit', 'Edit job vacancies'),
-- Candidates
('candidates:view', 'candidates', 'view', 'View candidate details and resumes'),
('candidates:create', 'candidates', 'create', 'Create/ingest candidate resumes'),
('candidates:edit', 'candidates', 'edit', 'Edit candidate information'),
-- Screening
('screening:view', 'screening', 'view', 'View screening scores and notes'),
('screening:evaluate', 'screening', 'evaluate', 'Evaluate and screen candidates'),
-- Voice Recordings
('voice_recordings:view', 'voice_recordings', 'view', 'Listen to and view voice recordings'),
('voice_recordings:upload', 'voice_recordings', 'upload', 'Upload telephonic screening audio'),
-- Offers
('offers:view', 'offers', 'view', 'View offer letter records'),
('offers:create', 'offers', 'create', 'Generate offer letters'),
('offers:approve', 'offers', 'approve', 'Approve generated offer letters'),
('offers:send', 'offers', 'send', 'Dispatch offers to candidates'),
-- Onboarding
('onboarding:view', 'onboarding', 'view', 'View onboarding cases and checklists'),
('onboarding:verify', 'onboarding', 'verify', 'Verify submitted candidate documents'),
('onboarding:approve', 'onboarding', 'approve', 'Give final onboarding approval'),
-- Employees
('employees:view', 'employees', 'view', 'View deployed employee master records'),
('employees:manage', 'employees', 'manage', 'Create and modify employee deployments'),
-- Attendance
('attendance:view', 'attendance', 'view', 'View attendance and shift records'),
('attendance:log', 'attendance', 'log', 'Log check-in/check-out and overtime'),
('attendance:edit', 'attendance', 'edit', 'Modify/override attendance records'),
-- MIS
('mis:view', 'mis', 'view', 'View MIS analytical reports'),
('mis:export', 'mis', 'export', 'Export Excel/CSV/PDF MIS reports'),
-- Users
('users:view', 'users', 'view', 'View organisation users'),
('users:manage', 'users', 'manage', 'Create users, assign roles and sites'),
-- Settings
('settings:manage', 'settings', 'manage', 'Manage organization settings')
ON CONFLICT (id) DO NOTHING;

-- Seed Default Demo Tenant
INSERT INTO public.tenants (id, slug, name, billing_tier, status)
VALUES (
    'a0000000-0000-0000-0000-000000000001'::UUID,
    'atbiz-workforce',
    'AT BiZ Workforce Solutions Ltd.',
    'enterprise',
    'active'
) ON CONFLICT (id) DO NOTHING;

-- Seed Standard Roles for the Demo Tenant
INSERT INTO public.roles (id, tenant_id, name, description, is_system_default) VALUES
('b0000000-0000-0000-0000-000000000001'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Tenant Super Admin', 'Full control over the tenant organization and billing', TRUE),
('b0000000-0000-0000-0000-000000000002'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Tenant Admin', 'Operational management of users, clients, sites, and roles', TRUE),
('b0000000-0000-0000-0000-000000000003'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'HR Manager', 'Supervises recruitment, onboarding, and client site operations', TRUE),
('b0000000-0000-0000-0000-000000000004'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Recruitment Executive', 'Candidate intake, screening, and vacancy pipeline management', TRUE),
('b0000000-0000-0000-0000-000000000005'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Offer Management Executive', 'Prepares, generates, and issues candidate offer letters', TRUE),
('b0000000-0000-0000-0000-000000000006'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Onboarding Executive', 'Collects, verifies KYC/educational documents, and processes joining', TRUE),
('b0000000-0000-0000-0000-000000000007'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Attendance Executive', 'Reviews daily attendance, leaves, and overtime submissions', TRUE),
('b0000000-0000-0000-0000-000000000008'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'MIS Executive', 'Generates workforce analytics and compliance summaries', TRUE),
('b0000000-0000-0000-0000-000000000009'::UUID, 'a0000000-0000-0000-0000-000000000001'::UUID, 'Site Supervisor', 'Local on-site supervision of daily shifts, check-ins, and intake', TRUE)
ON CONFLICT (id) DO NOTHING;
