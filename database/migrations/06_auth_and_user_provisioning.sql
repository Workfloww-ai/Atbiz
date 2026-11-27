-- ==============================================================================
-- Migration 06: Authentication, User Provisioning & Module Scoping
-- Subsystems:
--   1. must_change_password flag on public.profiles
--   2. user_module_assignments (granular module access per user)
--   3. Helper function for verifying caller permission to provision users
-- ==============================================================================

BEGIN;

-- ------------------------------------------------------------------------------
-- 1. Add must_change_password flag to profiles (defaults to FALSE for existing)
-- ------------------------------------------------------------------------------
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE;

-- ------------------------------------------------------------------------------
-- 2. Create user_module_assignments table
-- Allows Admins/SuperAdmins to restrict users to specific modules (e.g. Resume Desk, Attendance)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_module_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    module_id VARCHAR(32) NOT NULL REFERENCES public.modules(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_module_assignment UNIQUE (tenant_id, user_id, module_id),
    CONSTRAINT fk_user_module_assignment_user FOREIGN KEY (tenant_id, user_id) 
        REFERENCES public.profiles(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_modules_lookup 
    ON public.user_module_assignments(tenant_id, user_id, module_id);

-- Enable RLS
ALTER TABLE public.user_module_assignments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_module_assignments_select_policy ON public.user_module_assignments;
CREATE POLICY user_module_assignments_select_policy ON public.user_module_assignments
FOR SELECT USING (
    public.is_developer() 
    OR tenant_id = public.get_current_tenant_id()
    OR user_id = auth.uid()
);

DROP POLICY IF EXISTS user_module_assignments_write_policy ON public.user_module_assignments;
CREATE POLICY user_module_assignments_write_policy ON public.user_module_assignments
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Ensure module IDs for resume_desk and pipeline are present
INSERT INTO public.modules (id, name, description, sort_order)
VALUES 
  ('resume_desk', 'Resume Desk', 'Resume intake, search & digital filters', 6),
  ('pipeline', 'Recruitment Pipeline', 'Application stages, interviews, and status', 7)
ON CONFLICT (id) DO NOTHING;

COMMIT;
