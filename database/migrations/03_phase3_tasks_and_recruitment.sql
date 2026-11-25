-- ==============================================================================
-- AT BiZ: Phase 3 & 4 Database Migration
-- Subsystems: Work Tasks & Operational Assignment Engine + Recruitment Pipeline
-- Seed Data: Real-world roles for RIL and JLL (Airtel MSC)
-- ==============================================================================

-- ==============================================================================
-- 1. WORK TASKS & OPERATIONAL ASSIGNMENT ENGINE (Tables 14 to 16)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 14: work_tasks
-- Granular operational work items (e.g. Ingest resume, verify candidate, issue offer).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.work_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    module_id VARCHAR(32) NOT NULL REFERENCES public.modules(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    related_entity_type VARCHAR(32) NOT NULL, -- 'candidate', 'application', 'offer', 'onboarding_case'
    related_entity_id UUID NOT NULL,
    priority VARCHAR(16) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    status VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    due_date TIMESTAMPTZ,
    created_by UUID REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_work_tasks_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_work_tasks_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_work_tasks_lookup 
    ON public.work_tasks(tenant_id, site_id, status);
CREATE INDEX IF NOT EXISTS idx_work_tasks_entity 
    ON public.work_tasks(tenant_id, related_entity_type, related_entity_id);

-- ------------------------------------------------------------------------------
-- Table 15: work_task_assignments
-- Assigns work items to one or multiple users.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.work_task_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    task_id UUID NOT NULL,
    assigned_user_id UUID NOT NULL,
    assigned_by UUID REFERENCES public.profiles(id),
    assignment_status VARCHAR(24) NOT NULL DEFAULT 'assigned' 
        CHECK (assignment_status IN ('assigned', 'acknowledged', 'completed', 'reassigned')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_work_task_assignment UNIQUE (tenant_id, task_id, assigned_user_id),
    CONSTRAINT fk_work_task_assignments_task FOREIGN KEY (tenant_id, task_id) 
        REFERENCES public.work_tasks(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_work_task_assignments_user FOREIGN KEY (tenant_id, assigned_user_id) 
        REFERENCES public.profiles(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_assignments_user 
    ON public.work_task_assignments(tenant_id, assigned_user_id, assignment_status);

-- ------------------------------------------------------------------------------
-- Table 16: work_task_assignment_history
-- Full audit trail of reassignment and completion of tasks.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.work_task_assignment_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    task_id UUID NOT NULL,
    previous_user_id UUID REFERENCES public.profiles(id),
    new_user_id UUID REFERENCES public.profiles(id),
    action VARCHAR(32) NOT NULL,
    changed_by UUID REFERENCES public.profiles(id),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==============================================================================
-- 2. RECRUITMENT & RESUME INGESTION SUBSYSTEM (Tables 17 to 24)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 17: designations
-- Job roles specific to a client or tenant.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.designations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    client_id UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    title VARCHAR(150) NOT NULL,
    department VARCHAR(100),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_designations_tenant_client_title UNIQUE (tenant_id, client_id, title)
);

CREATE INDEX IF NOT EXISTS idx_designations_tenant ON public.designations(tenant_id, client_id);

-- ------------------------------------------------------------------------------
-- Table 18: vacancies
-- Job requisitions raised for a specific client.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.vacancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL,
    designation_id UUID NOT NULL REFERENCES public.designations(id) ON DELETE CASCADE,
    headcount INT NOT NULL DEFAULT 1,
    min_qualification VARCHAR(150),
    salary_range_min NUMERIC(10, 2),
    salary_range_max NUMERIC(10, 2),
    status VARCHAR(24) NOT NULL DEFAULT 'open' CHECK (status IN ('draft', 'open', 'on_hold', 'fulfilled', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_vacancies_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_vacancies_client FOREIGN KEY (tenant_id, client_id) 
        REFERENCES public.clients(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vacancies_client ON public.vacancies(tenant_id, client_id, status);

-- ------------------------------------------------------------------------------
-- Table 19: vacancy_sites
-- Distributes vacancy headcounts across specific client sites / circles.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.vacancy_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    vacancy_id UUID NOT NULL,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    allocated_count INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_vacancy_sites UNIQUE (tenant_id, vacancy_id, site_id),
    CONSTRAINT fk_vacancy_sites_vacancy FOREIGN KEY (tenant_id, vacancy_id) 
        REFERENCES public.vacancies(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_vacancy_sites_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

-- ------------------------------------------------------------------------------
-- Table 20: candidates
-- Central candidate repository with Google Drive ingestion fields.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100),
    email VARCHAR(255),
    phone VARCHAR(24) NOT NULL,
    dob DATE,
    gender VARCHAR(16),
    location TEXT,
    last_qualification VARCHAR(150),
    experience_years NUMERIC(4, 1),
    -- Google Drive Ingestion Metadata
    drive_file_id VARCHAR(255),
    drive_folder_path TEXT, -- e.g. '/RIL/Delhi/Lobby Assistant/Rahul_Resume.pdf'
    raw_resume_text TEXT,
    extracted_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidates_tenant_id UNIQUE (tenant_id, id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_search 
    ON public.candidates(tenant_id, phone, email);
CREATE INDEX IF NOT EXISTS idx_candidates_drive_file 
    ON public.candidates(tenant_id, drive_file_id);

-- ------------------------------------------------------------------------------
-- Table 21: applications
-- Candidate application tied to a specific vacancy and specific client site.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    candidate_id UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    vacancy_id UUID REFERENCES public.vacancies(id) ON DELETE SET NULL,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    stage VARCHAR(32) NOT NULL DEFAULT 'applied' 
        CHECK (stage IN ('applied', 'screened', 'interview_scheduled', 'interviewed', 'offered', 'onboarding', 'joined', 'rejected')),
    status VARCHAR(32) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'withdrawn', 'rejected', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_applications_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT fk_applications_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_applications_lookup 
    ON public.applications(tenant_id, site_id, stage, status);

-- ------------------------------------------------------------------------------
-- Table 22: application_status_history
-- Audit log of recruitment stage transitions.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.application_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    from_stage VARCHAR(32),
    to_stage VARCHAR(32) NOT NULL,
    changed_by UUID REFERENCES public.profiles(id),
    remarks TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 23: screening_results
-- AI match scores, recruiter evaluation, and screening criteria.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.screening_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    application_id UUID NOT NULL REFERENCES public.applications(id) ON DELETE CASCADE,
    screener_user_id UUID REFERENCES public.profiles(id),
    match_score NUMERIC(5, 2), -- e.g. 87.50%
    recommendation VARCHAR(32) CHECK (recommendation IN ('shortlist', 'hold', 'reject')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------------------------
-- Table 24: voice_recordings
-- Telephonic screening audio, call recordings, and transcriptions.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.voice_recordings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    candidate_id UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    application_id UUID REFERENCES public.applications(id) ON DELETE SET NULL,
    storage_url TEXT NOT NULL,
    duration_seconds INT,
    transcription TEXT,
    sentiment VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ==============================================================================
-- 3. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================
ALTER TABLE public.work_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.work_task_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.work_task_assignment_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.designations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vacancies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vacancy_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.application_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.screening_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_recordings ENABLE ROW LEVEL SECURITY;

-- Work Tasks Policies (Site & Assignment Scoped)
CREATE POLICY work_tasks_select_policy ON public.work_tasks
FOR SELECT USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND public.has_site_access(site_id)
        AND (
            public.is_tenant_admin()
            OR EXISTS (
                SELECT 1 FROM public.work_task_assignments wta 
                WHERE wta.task_id = work_tasks.id AND wta.assigned_user_id = auth.uid()
            )
        )
    )
);

CREATE POLICY work_tasks_write_policy ON public.work_tasks
FOR ALL USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id() 
        AND public.has_site_access(site_id)
    )
);

-- Work Task Assignments Policies
CREATE POLICY task_assignments_policy ON public.work_task_assignments
FOR ALL USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id()
        AND (assigned_user_id = auth.uid() OR public.is_tenant_admin())
    )
);

-- Designations Policies
CREATE POLICY designations_select_policy ON public.designations
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY designations_write_policy ON public.designations
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Vacancies Policies
CREATE POLICY vacancies_select_policy ON public.vacancies
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY vacancies_write_policy ON public.vacancies
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Vacancy Sites Policies (Site-scoped)
CREATE POLICY vacancy_sites_select_policy ON public.vacancy_sites
FOR SELECT USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.has_site_access(site_id))
);

-- Candidates Policies
CREATE POLICY candidates_select_policy ON public.candidates
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY candidates_write_policy ON public.candidates
FOR ALL USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

-- Applications Policies (Site-scoped)
CREATE POLICY applications_select_policy ON public.applications
FOR SELECT USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id() 
        AND public.has_site_access(site_id)
    )
);

CREATE POLICY applications_write_policy ON public.applications
FOR ALL USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id() 
        AND public.has_site_access(site_id)
    )
);

-- Screening Results Policies
CREATE POLICY screening_results_policy ON public.screening_results
FOR ALL USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

-- Voice Recordings Policies
CREATE POLICY voice_recordings_policy ON public.voice_recordings
FOR ALL USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

-- ==============================================================================
-- 4. REAL-WORLD SEED DATA (Client Specific Job Roles / Designations)
-- ==============================================================================
DO $$
DECLARE
    v_tenant_id UUID := 'a0000000-0000-0000-0000-000000000001'::UUID;
    v_ril_id UUID := 'c0000000-0000-0000-0000-000000000001'::UUID;
    v_jll_id UUID := 'c0000000-0000-0000-0000-000000000002'::UUID;
BEGIN
    -- 1. Insert RIL Roles (Lobby Assistant, Team Leader, Supervisor)
    INSERT INTO public.designations (tenant_id, client_id, title, department) VALUES
    (v_tenant_id, v_ril_id, 'Lobby Assistant', 'Operations / Retail Front Desk'),
    (v_tenant_id, v_ril_id, 'Team Leader', 'Operations / Store Management'),
    (v_tenant_id, v_ril_id, 'Supervisor', 'Operations / Shift Supervision')
    ON CONFLICT (tenant_id, client_id, title) DO NOTHING;

    -- 2. Insert JLL (Airtel MSC) Roles (Technician, Supervisor, Engineer, Sr. Engineer)
    INSERT INTO public.designations (tenant_id, client_id, title, department) VALUES
    (v_tenant_id, v_jll_id, 'Technician', 'Telecom Infrastructure / Technical'),
    (v_tenant_id, v_jll_id, 'Supervisor', 'Facilities & Site Operations'),
    (v_tenant_id, v_jll_id, 'Engineer', 'Telecom MSC Systems Engineering'),
    (v_tenant_id, v_jll_id, 'Sr. Engineer', 'Core Telecom Infrastructure')
    ON CONFLICT (tenant_id, client_id, title) DO NOTHING;
END $$;
