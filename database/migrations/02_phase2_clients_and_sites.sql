-- ==============================================================================
-- AT BiZ: Phase 2 Database Migration (Client, Site & User Spatial Scoping)
-- Features: Composite Foreign Keys (tenant_id, client_id, site_id)
-- Seed Data: Real-world tenant setup for RIL and JLL (Airtel MSC)
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- Table 7: clients
-- Corporate clients serviced by a tenant.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    code VARCHAR(32) NOT NULL,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(64),
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_clients_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_clients_tenant_code UNIQUE (tenant_id, code)
);

CREATE INDEX IF NOT EXISTS idx_clients_tenant_status ON public.clients(tenant_id, status);

-- ------------------------------------------------------------------------------
-- Table 8: client_sites
-- Physical operational locations / state circles belonging to a client.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.client_sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL,
    site_code VARCHAR(32) NOT NULL,
    site_name VARCHAR(150) NOT NULL,
    state VARCHAR(64) NOT NULL,
    city VARCHAR(64),
    pincode VARCHAR(12),
    address TEXT,
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_sites_tenant_id UNIQUE (tenant_id, id),
    CONSTRAINT uq_client_sites_tenant_client_id UNIQUE (tenant_id, client_id, id),
    CONSTRAINT uq_client_sites_code UNIQUE (tenant_id, client_id, site_code),
    CONSTRAINT fk_client_sites_client FOREIGN KEY (tenant_id, client_id) 
        REFERENCES public.clients(tenant_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_client_sites_lookup ON public.client_sites(tenant_id, client_id, status);

-- ------------------------------------------------------------------------------
-- Table 9: client_contacts
-- Point of contacts at client organizations.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.client_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL,
    site_id UUID,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(24),
    designation VARCHAR(100),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_client_contacts_client FOREIGN KEY (tenant_id, client_id) 
        REFERENCES public.clients(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_client_contacts_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE SET NULL
);

-- ------------------------------------------------------------------------------
-- Table 10: client_settings
-- SLA, compliance presets, and offer letter configuration per client.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.client_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    client_id UUID NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_settings_client UNIQUE (tenant_id, client_id),
    CONSTRAINT fk_client_settings_client FOREIGN KEY (tenant_id, client_id) 
        REFERENCES public.clients(tenant_id, id) ON DELETE CASCADE
);

-- ------------------------------------------------------------------------------
-- Table 11: user_module_permissions
-- User-specific granular module permission overrides.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_module_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    permission_id VARCHAR(64) NOT NULL REFERENCES public.permissions(id) ON DELETE CASCADE,
    is_granted BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by UUID NOT NULL REFERENCES public.profiles(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_module_permission UNIQUE (tenant_id, user_id, permission_id),
    CONSTRAINT fk_user_module_permissions_user FOREIGN KEY (tenant_id, user_id) 
        REFERENCES public.profiles(tenant_id, id) ON DELETE CASCADE
);

-- ------------------------------------------------------------------------------
-- Table 12: user_client_assignments
-- Grants a user visibility across all sites under a client (e.g. Account Manager).
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_client_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    client_id UUID NOT NULL,
    assigned_by UUID NOT NULL REFERENCES public.profiles(id),
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_client_assignment UNIQUE (tenant_id, user_id, client_id),
    CONSTRAINT fk_user_client_assignment_user FOREIGN KEY (tenant_id, user_id) 
        REFERENCES public.profiles(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_user_client_assignment_client FOREIGN KEY (tenant_id, client_id) 
        REFERENCES public.clients(tenant_id, id) ON DELETE CASCADE
);

-- ------------------------------------------------------------------------------
-- Table 13: user_site_assignments
-- CORE SPATIAL SECURITY TABLE: Maps users to the exact sites they can view.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.user_site_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    client_id UUID NOT NULL,
    site_id UUID NOT NULL,
    assigned_by UUID NOT NULL REFERENCES public.profiles(id),
    status VARCHAR(24) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ, -- For temporary/shift assignments
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_site_assignment UNIQUE (tenant_id, user_id, site_id),
    CONSTRAINT fk_user_site_assignment_user FOREIGN KEY (tenant_id, user_id) 
        REFERENCES public.profiles(tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_user_site_assignment_site FOREIGN KEY (tenant_id, client_id, site_id) 
        REFERENCES public.client_sites(tenant_id, client_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_sites_lookup 
    ON public.user_site_assignments(tenant_id, user_id, site_id, status);

-- ==============================================================================
-- 3. SITE-LEVEL SECURITY EVALUATOR FUNCTION
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.has_site_access(p_site_id UUID)
RETURNS BOOLEAN AS $$
DECLARE
    v_user_id UUID := auth.uid();
    v_tenant_id UUID := public.get_current_tenant_id();
    v_tier VARCHAR(32);
    v_role_name VARCHAR(64);
BEGIN
    -- Developer Account has global platform access
    IF public.is_developer() THEN
        RETURN TRUE;
    END IF;

    -- Extract caller tier and role
    SELECT p.account_tier, r.name INTO v_tier, v_role_name
    FROM public.profiles p
    LEFT JOIN public.roles r ON r.id = p.primary_role_id
    WHERE p.id = v_user_id AND p.status = 'active';

    -- Tenant Super Admin & Tenant Admin get organization-wide site visibility
    IF v_tier IN ('tenant_super_admin', 'tenant_admin') OR v_role_name IN ('Tenant Super Admin', 'Tenant Admin', 'HR Manager') THEN
        RETURN EXISTS (SELECT 1 FROM public.client_sites WHERE id = p_site_id AND tenant_id = v_tenant_id);
    END IF;

    -- Direct site assignment check
    IF EXISTS (
        SELECT 1 FROM public.user_site_assignments usa
        WHERE usa.user_id = v_user_id 
          AND usa.site_id = p_site_id 
          AND usa.tenant_id = v_tenant_id 
          AND usa.status = 'active'
          AND (usa.expires_at IS NULL OR usa.expires_at > now())
    ) THEN
        RETURN TRUE;
    END IF;

    -- Client-wide inheritance check
    RETURN EXISTS (
        SELECT 1 FROM public.user_client_assignments uca
        JOIN public.client_sites cs ON cs.client_id = uca.client_id
        WHERE uca.user_id = v_user_id 
          AND cs.id = p_site_id 
          AND uca.tenant_id = v_tenant_id 
          AND uca.status = 'active'
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ==============================================================================
-- 4. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================
ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_module_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_client_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_site_assignments ENABLE ROW LEVEL SECURITY;

-- Clients Policies
CREATE POLICY clients_select_policy ON public.clients
FOR SELECT USING (
    public.is_developer() OR tenant_id = public.get_current_tenant_id()
);

CREATE POLICY clients_write_policy ON public.clients
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- Client Sites Policies
CREATE POLICY client_sites_select_policy ON public.client_sites
FOR SELECT USING (
    public.is_developer() 
    OR (
        tenant_id = public.get_current_tenant_id() 
        AND public.has_site_access(id)
    )
);

CREATE POLICY client_sites_write_policy ON public.client_sites
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- User Site Assignments Policies
CREATE POLICY user_site_assignments_select_policy ON public.user_site_assignments
FOR SELECT USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND (user_id = auth.uid() OR public.is_tenant_admin()))
);

CREATE POLICY user_site_assignments_write_policy ON public.user_site_assignments
FOR ALL USING (
    public.is_developer() 
    OR (tenant_id = public.get_current_tenant_id() AND public.is_tenant_admin())
);

-- ==============================================================================
-- 5. REAL-WORLD SEED DATA (RIL & JLL from Tenant Specifications)
-- ==============================================================================
DO $$
DECLARE
    v_tenant_id UUID := 'a0000000-0000-0000-0000-000000000001'::UUID;
    v_ril_id UUID := 'c0000000-0000-0000-0000-000000000001'::UUID;
    v_jll_id UUID := 'c0000000-0000-0000-0000-000000000002'::UUID;
BEGIN
    -- 1. Insert Client: RIL
    INSERT INTO public.clients (id, tenant_id, code, name, industry, status)
    VALUES (v_ril_id, v_tenant_id, 'RIL', 'Reliance Industries Limited (RIL)', 'Retail & Logistics', 'active')
    ON CONFLICT (tenant_id, code) DO NOTHING;

    -- 2. Insert Client: JLL (Airtel MSC)
    INSERT INTO public.clients (id, tenant_id, code, name, industry, status)
    VALUES (v_jll_id, v_tenant_id, 'JLL-AIRTEL', 'JLL (Airtel MSC)', 'Telecom Facilities Management', 'active')
    ON CONFLICT (tenant_id, code) DO NOTHING;

    -- 3. Insert RIL Sites (8 States)
    INSERT INTO public.client_sites (tenant_id, client_id, site_code, site_name, state) VALUES
    (v_tenant_id, v_ril_id, 'RIL-BIH', 'RIL Bihar Circle', 'Bihar'),
    (v_tenant_id, v_ril_id, 'RIL-CHD', 'RIL Chandigarh Circle', 'Chandigarh'),
    (v_tenant_id, v_ril_id, 'RIL-DEL', 'RIL Delhi Circle', 'Delhi'),
    (v_tenant_id, v_ril_id, 'RIL-JHK', 'RIL Jharkhand Circle', 'Jharkhand'),
    (v_tenant_id, v_ril_id, 'RIL-ORI', 'RIL Orissa Circle', 'Orissa'),
    (v_tenant_id, v_ril_id, 'RIL-PUN', 'RIL Punjab Circle', 'Punjab'),
    (v_tenant_id, v_ril_id, 'RIL-UP',  'RIL Uttar Pradesh Circle', 'Uttar Pradesh'),
    (v_tenant_id, v_ril_id, 'RIL-WB',  'RIL West Bengal Circle', 'West Bengal')
    ON CONFLICT (tenant_id, client_id, site_code) DO NOTHING;

    -- 4. Insert JLL (Airtel MSC) Sites (10 Circles/States)
    INSERT INTO public.client_sites (tenant_id, client_id, site_code, site_name, state) VALUES
    (v_tenant_id, v_jll_id, 'JLL-AP',   'JLL Airtel MSC Andhra Pradesh', 'AP'),
    (v_tenant_id, v_jll_id, 'JLL-DEL',  'JLL Airtel MSC Delhi', 'DEL'),
    (v_tenant_id, v_jll_id, 'JLL-HPHP', 'JLL Airtel MSC Himachal & Punjab', 'HPHP'),
    (v_tenant_id, v_jll_id, 'JLL-JK',   'JLL Airtel MSC Jammu & Kashmir', 'JK'),
    (v_tenant_id, v_jll_id, 'JLL-KER',  'JLL Airtel MSC Kerala', 'KER'),
    (v_tenant_id, v_jll_id, 'JLL-KK',   'JLL Airtel MSC Karnataka', 'KK'),
    (v_tenant_id, v_jll_id, 'JLL-RAJ',  'JLL Airtel MSC Rajasthan', 'RAJ'),
    (v_tenant_id, v_jll_id, 'JLL-TN',   'JLL Airtel MSC Tamil Nadu', 'TN'),
    (v_tenant_id, v_jll_id, 'JLL-UPE',  'JLL Airtel MSC UP East', 'UPE'),
    (v_tenant_id, v_jll_id, 'JLL-UPW',  'JLL Airtel MSC UP West', 'UPW')
    ON CONFLICT (tenant_id, client_id, site_code) DO NOTHING;
END $$;
