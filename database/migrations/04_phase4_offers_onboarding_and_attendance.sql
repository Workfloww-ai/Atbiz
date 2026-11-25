-- ==============================================================================
-- AT BiZ: Phase 4 Final Database Migration
-- Subsystems: 
--   1. Offer Management (Tables 25 to 28)
--   2. Onboarding Operations (Tables 29 to 32)
--   3. Employee Management & Deployments (Tables 33 to 34)
--   4. Attendance Tracking & MIS Reports (Tables 35 to 38)
--   5. System Governance, Audit Ledger & Background Workers (Tables 39 to 41)
-- ==============================================================================

-- ==============================================================================
-- 1. OFFER MANAGEMENT SUBSYSTEM (Tables 25 to 28)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 25: offer_templates
-- Client-specific or tenant-wide offer letter templates.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.offer_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    client_id UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    template_name VARCHAR(150) NOT NULL,
    content TEXT NOT NULL,
    variables_schema JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 26: offers
-- Formal commercial offer extended to a candidate for a specific client site.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.offers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    template_id UUID REFERENCES public.offer_templates(id) ON DELETE SET NULL,
    designation VARCHAR(150) NOT NULL,
    gross_salary_monthly NUMERIC(12, 2) NOT NULL,
    ctc_annual NUMERIC(12, 2) NOT NULL,
    salary_breakup JSONB NOT NULL DEFAULT '{}'::jsonb,
    joining_date DATE NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    offer_status VARCHAR(24) NOT NULL DEFAULT 'draft' 
        CHECK (offer_status IN ('draft', 'generated', 'sent', 'accepted', 'rejected', 'expired', 'cancelled')),
    created_by UUID REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_offers_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_offers_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_offers_lookup ON public.offers(tenant_id, site_id, offer_status);

-- ------------------------------------------------------------------------------
-- Table 27: offer_documents
-- Stored PDF artifacts and signed offer copies.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.offer_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    offer_id UUID NOT NULL REFERENCES public.offers(id) ON DELETE CASCADE,
    file_type VARCHAR(32) NOT NULL CHECK (file_type IN ('generated_pdf', 'signed_copy', 'supporting_doc')),
    storage_path TEXT NOT NULL,
    hash_md5 VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 28: offer_status_history
-- Full audit log of offer generation, dispatch, acceptance, or rejection.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.offer_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    offer_id UUID NOT NULL REFERENCES public.offers(id) ON DELETE CASCADE,
    from_status VARCHAR(24),
    to_status VARCHAR(24) NOT NULL,
    reason TEXT,
    changed_by UUID REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==============================================================================
-- 2. ONBOARDING OPERATIONS SUBSYSTEM (Tables 29 to 32)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 29: onboarding_cases
-- Master onboarding tracking record for candidates whose offers are accepted.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.onboarding_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    candidate_id UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    overall_status VARCHAR(32) NOT NULL DEFAULT 'documents_pending' 
        CHECK (overall_status IN ('documents_pending', 'under_review', 'verified', 'approved', 'rejected')),
    target_joining_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_onboarding_cases_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_onboarding_cases_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_onboarding_lookup ON public.onboarding_cases(tenant_id, site_id, overall_status);

-- ------------------------------------------------------------------------------
-- Table 30: onboarding_requirements
-- Checklist of mandatory compliance documents per client site.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.onboarding_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    client_id UUID REFERENCES public.clients(id) ON DELETE CASCADE,
    site_id UUID,
    document_type VARCHAR(64) NOT NULL, -- e.g. 'aadhaar', 'pan', 'bank_passbook', 'educational'
    is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    validation_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 31: onboarding_submissions
-- Actual candidate document files uploaded for verification.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.onboarding_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    case_id UUID NOT NULL REFERENCES public.onboarding_cases(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES public.onboarding_requirements(id) ON DELETE SET NULL,
    document_type VARCHAR(64) NOT NULL,
    file_storage_url TEXT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected')),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 32: onboarding_reviews
-- Sign-off ledger by Onboarding Executives.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.onboarding_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    submission_id UUID NOT NULL REFERENCES public.onboarding_submissions(id) ON DELETE CASCADE,
    reviewer_user_id UUID REFERENCES public.profiles(id),
    decision VARCHAR(24) NOT NULL CHECK (decision IN ('approved', 'rejected')),
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==============================================================================
-- 3. EMPLOYEE MANAGEMENT SUBSYSTEM (Tables 33 to 34)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 33: employees
-- Permanent employee master created once onboarding completes successfully.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    candidate_id UUID UNIQUE REFERENCES public.candidates(id) ON DELETE SET NULL,
    employee_code VARCHAR(32) NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(24) NOT NULL,
    date_of_birth DATE NOT NULL,
    date_of_joining DATE NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'terminated', 'resigned')),
    bank_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    statutory_details JSONB NOT NULL DEFAULT '{}'::jsonb, -- PF, ESI, UAN
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_employees_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_employees_code UNIQUE (tenant_id, employee_code)
);

CREATE INDEX IF NOT EXISTS idx_employees_lookup ON public.employees(tenant_id, employee_code, status);

-- ------------------------------------------------------------------------------
-- Table 34: employee_assignments
-- Current and historical deployments of employees at client operational sites.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.employee_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    employee_id UUID NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    designation VARCHAR(150) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE, -- NULL indicates active ongoing deployment
    shift_timing VARCHAR(32),
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'transferred')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_employee_assignments_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_emp_assignments_site ON public.employee_assignments(tenant_id, site_id, status);

-- ==============================================================================
-- 4. ATTENDANCE & MIS SUBSYSTEM (Tables 35 to 38)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 35: attendance_records
-- Daily clock-in/out and shift records for deployed employees.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.attendance_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    employee_id UUID NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    attendance_date DATE NOT NULL,
    check_in_time TIMESTAMPTZ,
    check_out_time TIMESTAMPTZ,
    hours_worked NUMERIC(5, 2),
    overtime_hours NUMERIC(4, 2) NOT NULL DEFAULT 0,
    verification_mode VARCHAR(32) DEFAULT 'manual', -- 'biometric', 'geo_tag', 'manual'
    status VARCHAR(24) NOT NULL DEFAULT 'present' CHECK (status IN ('present', 'absent', 'half_day', 'leave', 'holiday')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_attendance_daily UNIQUE (tenant_id, employee_id, attendance_date),
    CONSTRAINT fk_attendance_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_attendance_site_date 
    ON public.attendance_records(tenant_id, site_id, attendance_date);

-- ------------------------------------------------------------------------------
-- Table 36: attendance_status_history
-- Supervisor overrides and manual correction audit log.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.attendance_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    attendance_id UUID NOT NULL REFERENCES public.attendance_records(id) ON DELETE CASCADE,
    modified_by UUID REFERENCES public.profiles(id),
    old_status VARCHAR(24),
    new_status VARCHAR(24) NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 37: mis_reports
-- Saved configurations for analytical reports.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.mis_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    report_type VARCHAR(48) NOT NULL, -- 'headcount', 'attrition', 'attendance_summary', 'offer_tat'
    filter_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 38: mis_report_logs
-- Log of generated/exported reports with site scopes.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.mis_report_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    report_id UUID REFERENCES public.mis_reports(id) ON DELETE CASCADE,
    generated_by UUID REFERENCES public.profiles(id),
    site_id_scope UUID[],
    file_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==============================================================================
-- 5. SYSTEM GOVERNANCE, AUDIT & ASYNC WORKERS (Tables 39 to 41)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 39: audit_logs
-- Immutable ledger for sensitive operational events and data mutations.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID REFERENCES public.profiles(id),
    event_type VARCHAR(64) NOT NULL, -- 'OFFER_ISSUED', 'ATTENDANCE_OVERRIDE', 'USER_ROLE_CHANGED'
    entity_type VARCHAR(32) NOT NULL,
    entity_id UUID NOT NULL,
    old_data JSONB,
    new_data JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event 
    ON public.audit_logs(tenant_id, event_type, created_at);

-- ------------------------------------------------------------------------------
-- Table 40: notifications
-- In-app notifications for task assignments and review requests.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    link_url TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user 
    ON public.notifications(tenant_id, user_id, is_read);

-- ------------------------------------------------------------------------------
-- Table 41: background_jobs
-- Async task execution queue (Google Drive crawler, resume parser, PDF generator).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.background_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    job_type VARCHAR(48) NOT NULL, -- 'gdrive_sync', 'resume_parse', 'offer_pdf_render'
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
    error_message TEXT,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_queue 
    ON public.background_jobs(status, created_at);

-- ==============================================================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================
ALTER TABLE public.offer_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.offers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.offer_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.offer_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.onboarding_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employees ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.employee_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attendance_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attendance_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mis_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mis_report_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.background_jobs ENABLE ROW LEVEL SECURITY;

-- Offer Templates
CREATE POLICY offer_templates_policy ON public.offer_templates
FOR ALL USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

-- Offers (Site + Task Scoped)
CREATE POLICY offers_select_policy ON public.offers
FOR SELECT USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND public.has_site_access(site_id)
        AND (
            public.is_tenant_admin()
            OR EXISTS (
                SELECT 1 FROM public.work_task_assignments wta
                JOIN public.work_tasks wt ON wt.id = wta.task_id
                WHERE wt.related_entity_id = offers.id AND wta.assigned_user_id = auth.uid()
            )
        )
    )
);

CREATE POLICY offers_write_policy ON public.offers
FOR ALL USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND public.has_site_access(site_id)
    )
);

-- Onboarding Cases (Site + Task Scoped)
CREATE POLICY onboarding_select_policy ON public.onboarding_cases
FOR SELECT USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND public.has_site_access(site_id)
        AND (
            public.is_tenant_admin()
            OR EXISTS (
                SELECT 1 FROM public.work_task_assignments wta
                JOIN public.work_tasks wt ON wt.id = wta.task_id
                WHERE wt.related_entity_id = onboarding_cases.id AND wta.assigned_user_id = auth.uid()
            )
        )
    )
);

CREATE POLICY onboarding_write_policy ON public.onboarding_cases
FOR ALL USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND public.has_site_access(site_id)
    )
);

-- Employees Policies
CREATE POLICY employees_select_policy ON public.employees
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY employees_write_policy ON public.employees
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Employee Assignments (Site-scoped)
CREATE POLICY employee_assignments_policy ON public.employee_assignments
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.has_site_access(site_id))
);

-- Attendance Records (Site-scoped)
CREATE POLICY attendance_records_policy ON public.attendance_records
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.has_site_access(site_id))
);

-- Notifications (Self-scoped)
CREATE POLICY notifications_policy ON public.notifications
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND user_id = auth.uid())
);

-- Audit Logs (Read-only for Admins & Developers)
CREATE POLICY audit_logs_policy ON public.audit_logs
FOR SELECT USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Background Jobs (Admins & Developers)
CREATE POLICY background_jobs_policy ON public.background_jobs
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);
