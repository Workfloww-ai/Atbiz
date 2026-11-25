-- ==============================================================================
-- Migration 05: candidate_files, sync_runs (heartbeat lock), real unique
-- constraints, and atomic idempotent ingest RPC
--
-- Requires PostgreSQL 15+ (uses ON DELETE SET NULL (column list)).
-- Tables are small, so a single transaction with plain CREATE INDEX is fine.
-- ==============================================================================
BEGIN;

-- ------------------------------------------------------------------------------
-- 0. Preflight: report what will be touched
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    v_app_dupes  INT;
    v_task_dupes INT;
BEGIN
    SELECT COUNT(*) INTO v_app_dupes FROM (
        SELECT 1 FROM public.applications
        GROUP BY tenant_id, candidate_id, client_id, site_id
        HAVING COUNT(*) > 1
    ) x;

    SELECT COUNT(*) INTO v_task_dupes FROM (
        SELECT 1 FROM public.work_tasks
        GROUP BY tenant_id, client_id, site_id, module_id,
                 related_entity_type, related_entity_id
        HAVING COUNT(*) > 1
    ) x;

    RAISE NOTICE 'Duplicate application groups: %, duplicate work_task groups: %',
        v_app_dupes, v_task_dupes;
END $$;

-- ------------------------------------------------------------------------------
-- 1. Safe deduplication of applications (never touches candidates)
--    Keeps the oldest row per (tenant, candidate, client, site), repoints any
--    child rows that reference a duplicate, then deletes only the duplicates.
-- ------------------------------------------------------------------------------
DO $$
DECLARE
    fk            RECORD;
    v_dupe_count  INT;
    v_composite   INT;
BEGIN
    CREATE TEMP TABLE _app_dupes ON COMMIT DROP AS
    SELECT id AS dup_id, keep_id
    FROM (
        SELECT id,
               first_value(id) OVER w AS keep_id,
               row_number()    OVER w AS rn
        FROM public.applications
        WINDOW w AS (PARTITION BY tenant_id, candidate_id, client_id, site_id
                     ORDER BY created_at, id)
    ) s
    WHERE rn > 1;

    SELECT COUNT(*) INTO v_dupe_count FROM _app_dupes;
    IF v_dupe_count = 0 THEN
        RETURN;
    END IF;

    -- Composite FKs pointing at applications cannot be repointed generically.
    SELECT COUNT(*) INTO v_composite
    FROM pg_constraint
    WHERE contype = 'f'
      AND confrelid = 'public.applications'::regclass
      AND array_length(conkey, 1) > 1;
    IF v_composite > 0 THEN
        RAISE EXCEPTION
          'Composite FKs reference applications; dedupe duplicates manually first';
    END IF;

    -- Repoint single-column FKs (screenings, interviews, etc.) to the survivor.
    FOR fk IN
        SELECT c.conrelid::regclass AS tbl, a.attname AS col
        FROM pg_constraint c
        JOIN pg_attribute a
          ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f'
          AND c.confrelid = 'public.applications'::regclass
          AND array_length(c.conkey, 1) = 1
    LOOP
        EXECUTE format(
            'UPDATE %s t SET %I = d.keep_id FROM _app_dupes d WHERE t.%I = d.dup_id',
            fk.tbl, fk.col, fk.col);
    END LOOP;

    DELETE FROM public.applications a
    USING _app_dupes d
    WHERE a.id = d.dup_id;

    RAISE NOTICE 'Removed % duplicate application rows', v_dupe_count;
END $$;

-- Same for work_tasks (no known children; keep the oldest).
DELETE FROM public.work_tasks t
USING (
    SELECT id,
           row_number() OVER (
               PARTITION BY tenant_id, client_id, site_id, module_id,
                            related_entity_type, related_entity_id
               ORDER BY created_at, id) AS rn
    FROM public.work_tasks
) d
WHERE t.id = d.id AND d.rn > 1;

-- ------------------------------------------------------------------------------
-- 2. Real uniqueness for idempotent upserts
-- ------------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_candidate_site
    ON public.applications (tenant_id, candidate_id, client_id, site_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_work_tasks_entity_dedupe
    ON public.work_tasks (tenant_id, client_id, site_id, module_id,
                          related_entity_type, related_entity_id);

-- Identity matching indexes (Tier 3). Not unique: two people can legitimately
-- share a phone or email, so concurrency is handled by advisory locks in the RPC.
CREATE INDEX IF NOT EXISTS idx_candidates_phone_norm
    ON public.candidates (tenant_id,
        (right(regexp_replace(phone, '\D', '', 'g'), 10)));

CREATE INDEX IF NOT EXISTS idx_candidates_email_lower
    ON public.candidates (tenant_id, (lower(email)))
    WHERE email IS NOT NULL;

-- ------------------------------------------------------------------------------
-- 3. candidate_files: one row per Drive file, many files per candidate
--    drive_file_id is unique; file_hash is a plain index (same PDF may legitimately
--    live in several folders). file_hash is nullable for legacy rows with no hash.
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.candidate_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    candidate_id    UUID NOT NULL,
    drive_file_id   VARCHAR(255) NOT NULL,
    file_hash       VARCHAR(64),
    file_name       VARCHAR(255) NOT NULL,
    folder_path     TEXT NOT NULL DEFAULT '',
    client_id       UUID REFERENCES public.clients(id) ON DELETE SET NULL,
    site_id         UUID,
    role_name       VARCHAR(150),
    file_size_bytes BIGINT,
    mime_type       VARCHAR(100),
    is_unresolved   BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidate_files_drive_file UNIQUE (tenant_id, drive_file_id),
    CONSTRAINT fk_candidate_files_candidate
        FOREIGN KEY (tenant_id, candidate_id)
        REFERENCES public.candidates (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_files_site
        FOREIGN KEY (tenant_id, client_id, site_id)
        REFERENCES public.client_sites (tenant_id, client_id, id)
        ON DELETE SET NULL (client_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_candidate_files_hash
    ON public.candidate_files (tenant_id, file_hash)
    WHERE file_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_candidate_files_candidate
    ON public.candidate_files (tenant_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_candidate_files_unresolved
    ON public.candidate_files (tenant_id)
    WHERE is_unresolved = true;

-- ------------------------------------------------------------------------------
-- 4. Backfill from existing candidates and applications (real data only)
--    - file_hash: only when a real hash is stored, otherwise NULL (no fake md5)
--    - client/site: taken from the candidate's earliest application, if any
--      (a candidate with several applications gets the first; the exact
--      file-to-site mapping for older multi-site candidates is not recoverable)
--    - is_unresolved: true when the candidate has no application at all
-- ------------------------------------------------------------------------------
WITH first_app AS (
    SELECT DISTINCT ON (candidate_id)
           candidate_id, client_id, site_id
    FROM public.applications
    ORDER BY candidate_id, created_at, id
),
ins AS (
    INSERT INTO public.candidate_files (
        tenant_id, candidate_id, drive_file_id, file_hash, file_name,
        folder_path, client_id, site_id, is_unresolved
    )
    SELECT c.tenant_id,
           c.id,
           c.drive_file_id,
           NULLIF(c.extracted_attributes->>'file_hash', ''),
           COALESCE(NULLIF(c.extracted_attributes->>'file_name', ''),
                    NULLIF(c.extracted_attributes->>'parsed_from', ''),
                    c.drive_file_id),
           COALESCE(c.drive_folder_path, ''),
           fa.client_id,
           fa.site_id,
           (fa.site_id IS NULL)
    FROM public.candidates c
    LEFT JOIN first_app fa ON fa.candidate_id = c.id
    WHERE c.drive_file_id IS NOT NULL
    ON CONFLICT (tenant_id, drive_file_id) DO NOTHING
    RETURNING 1
)
SELECT COUNT(*) AS backfilled_files FROM ins;

DO $$
DECLARE v_missing INT;
BEGIN
    SELECT COUNT(*) INTO v_missing
    FROM public.candidates c
    WHERE c.drive_file_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM public.candidate_files f
          WHERE f.tenant_id = c.tenant_id AND f.drive_file_id = c.drive_file_id);
    RAISE NOTICE 'Candidates with a drive_file_id but no candidate_files row: %', v_missing;
END $$;

-- ------------------------------------------------------------------------------
-- 5. sync_runs: history + heartbeat-based distributed lock
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.sync_runs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
    status             VARCHAR(16) NOT NULL DEFAULT 'running'
                       CONSTRAINT chk_sync_runs_status
                       CHECK (status IN ('running', 'completed', 'failed')),
    triggered_by       VARCHAR(32) NOT NULL DEFAULT 'scheduler',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    heartbeat_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ,
    total_scanned      INT NOT NULL DEFAULT 0,
    newly_ingested     INT NOT NULL DEFAULT 0,
    skipped_duplicates INT NOT NULL DEFAULT 0,
    renamed_in_drive   INT NOT NULL DEFAULT 0,
    unchanged_files    INT NOT NULL DEFAULT 0,
    error_count        INT NOT NULL DEFAULT 0,
    errors             JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- Exactly one running sync per tenant.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_runs_active_per_tenant
    ON public.sync_runs (tenant_id) WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_sync_runs_tenant_started
    ON public.sync_runs (tenant_id, started_at DESC);

-- Acquire the lock. Expires a stale run first (no heartbeat for p_stale_minutes),
-- then tries to insert. Returns the new run id, or NULL if another sync is live.
CREATE OR REPLACE FUNCTION public.start_sync_run(
    p_tenant_id     UUID,
    p_triggered_by  TEXT DEFAULT 'scheduler',
    p_stale_minutes INT  DEFAULT 10
) RETURNS UUID
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_run_id UUID;
BEGIN
    UPDATE public.sync_runs
    SET status = 'failed',
        completed_at = now(),
        error_count = error_count + 1,
        errors = errors || jsonb_build_array(jsonb_build_object(
            'error', 'lock expired: no heartbeat for ' || p_stale_minutes || ' minutes',
            'at', now()))
    WHERE tenant_id = p_tenant_id
      AND status = 'running'
      AND heartbeat_at < now() - make_interval(mins => p_stale_minutes);

    INSERT INTO public.sync_runs (tenant_id, triggered_by)
    VALUES (p_tenant_id, p_triggered_by)
    ON CONFLICT (tenant_id) WHERE status = 'running' DO NOTHING
    RETURNING id INTO v_run_id;

    RETURN v_run_id;  -- NULL => another sync is running (return HTTP 409)
END;
$$;

-- Returns false if the run was expired or finished by someone else: the worker
-- should stop when it sees false.
CREATE OR REPLACE FUNCTION public.heartbeat_sync_run(p_run_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    UPDATE public.sync_runs
    SET heartbeat_at = now()
    WHERE id = p_run_id AND status = 'running';
    RETURN FOUND;
END;
$$;

-- p_stats keys: total_scanned, newly_ingested, skipped_duplicates,
-- renamed_in_drive, unchanged_files. p_errors is a JSON array.
CREATE OR REPLACE FUNCTION public.finish_sync_run(
    p_run_id UUID,
    p_status TEXT,
    p_stats  JSONB DEFAULT '{}'::jsonb,
    p_errors JSONB DEFAULT '[]'::jsonb
) RETURNS VOID
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF p_status NOT IN ('completed', 'failed') THEN
        RAISE EXCEPTION 'invalid status %', p_status;
    END IF;

    UPDATE public.sync_runs
    SET status             = p_status,
        completed_at       = now(),
        heartbeat_at       = now(),
        total_scanned      = COALESCE((p_stats->>'total_scanned')::int, total_scanned),
        newly_ingested     = COALESCE((p_stats->>'newly_ingested')::int, newly_ingested),
        skipped_duplicates = COALESCE((p_stats->>'skipped_duplicates')::int, skipped_duplicates),
        renamed_in_drive   = COALESCE((p_stats->>'renamed_in_drive')::int, renamed_in_drive),
        unchanged_files    = COALESCE((p_stats->>'unchanged_files')::int, unchanged_files),
        errors             = errors || COALESCE(p_errors, '[]'::jsonb),
        error_count        = error_count + jsonb_array_length(COALESCE(p_errors, '[]'::jsonb))
    WHERE id = p_run_id AND status = 'running';
END;
$$;

-- ------------------------------------------------------------------------------
-- 6. Atomic, idempotent ingest RPC
--
-- One call = one transaction. Safe to call again for the same file (re-sync,
-- rename, or reconciliation after HR fixes a folder): it never creates a second
-- candidate, file row, application, or task.
--
-- p_candidate  : first_name, last_name, email, phone, dob, gender, location,
--                last_qualification, experience_years, raw_resume_text,
--                extracted_attributes
-- p_file       : drive_file_id (required), file_hash, file_name, folder_path,
--                client_id, site_id, role_name, file_size_bytes, mime_type
-- p_application: stage, status  (created only if client_id AND site_id are set)
-- p_task       : module_id (required), title (required), description, priority
--
-- SECURITY INVOKER on purpose: the backend uses service_role (bypasses RLS), so
-- DEFINER is unnecessary and would only add risk.
-- ------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.ingest_candidate_atomic(
    p_tenant_id   UUID,
    p_candidate   JSONB,
    p_file        JSONB,
    p_application JSONB DEFAULT NULL,
    p_task        JSONB DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_drive_file_id  TEXT := p_file->>'drive_file_id';
    v_email_raw      TEXT := NULLIF(btrim(p_candidate->>'email'), '');
    v_email          TEXT := lower(NULLIF(btrim(p_candidate->>'email'), ''));
    v_phone_norm     TEXT;
    v_client_id      UUID := NULLIF(p_file->>'client_id', '')::uuid;
    v_site_id        UUID := NULLIF(p_file->>'site_id', '')::uuid;
    v_candidate_id   UUID;
    v_file_existed   BOOLEAN := false;
    v_matched        BOOLEAN := false;
    v_app_id         UUID;
    v_app_created    BOOLEAN := false;
    v_task_id        UUID;
    v_task_module    TEXT := NULLIF(p_task->>'module_id', '');
    v_task_title     TEXT := NULLIF(p_task->>'title', '');
BEGIN
    IF v_drive_file_id IS NULL THEN
        RAISE EXCEPTION 'p_file.drive_file_id is required';
    END IF;

    -- Normalize phone to last 10 digits; treat all-zero / short numbers as absent.
    v_phone_norm := right(regexp_replace(
        COALESCE(p_candidate->>'phone', ''), '\D', '', 'g'), 10);
    IF v_phone_norm !~ '^\d{10}$' OR v_phone_norm ~ '^0+$' THEN
        v_phone_norm := NULL;
    END IF;

    -- Serialize concurrent ingests of the same file / identity (lock order is
    -- always file, phone, email, so no deadlocks). Released at commit.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(p_tenant_id::text || ':file:' || v_drive_file_id, 0));
    IF v_phone_norm IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(p_tenant_id::text || ':phone:' || v_phone_norm, 0));
    END IF;
    IF v_email IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(
            hashtextextended(p_tenant_id::text || ':email:' || v_email, 0));
    END IF;

    -- Tier 1: file already known? Reuse its candidate.
    SELECT candidate_id INTO v_candidate_id
    FROM public.candidate_files
    WHERE tenant_id = p_tenant_id AND drive_file_id = v_drive_file_id;
    v_file_existed := FOUND;

    -- Tier 3: identity match by phone, then email.
    IF v_candidate_id IS NULL AND v_phone_norm IS NOT NULL THEN
        SELECT id INTO v_candidate_id
        FROM public.candidates
        WHERE tenant_id = p_tenant_id
          AND right(regexp_replace(phone, '\D', '', 'g'), 10) = v_phone_norm
        ORDER BY created_at LIMIT 1;
    END IF;
    IF v_candidate_id IS NULL AND v_email IS NOT NULL THEN
        SELECT id INTO v_candidate_id
        FROM public.candidates
        WHERE tenant_id = p_tenant_id AND lower(email) = v_email
        ORDER BY created_at LIMIT 1;
    END IF;
    v_matched := (v_candidate_id IS NOT NULL) AND NOT v_file_existed;

    IF v_candidate_id IS NULL THEN
        INSERT INTO public.candidates (
            tenant_id, first_name, last_name, email, phone, dob, gender,
            location, last_qualification, experience_years, raw_resume_text,
            drive_file_id, drive_folder_path, extracted_attributes
        ) VALUES (
            p_tenant_id,
            COALESCE(NULLIF(btrim(p_candidate->>'first_name'), ''), 'Candidate'),
            NULLIF(btrim(p_candidate->>'last_name'), ''),
            v_email_raw,
            COALESCE(NULLIF(btrim(p_candidate->>'phone'), ''), '+91-0000000000'),
            NULLIF(p_candidate->>'dob', '')::date,
            NULLIF(p_candidate->>'gender', ''),
            NULLIF(p_candidate->>'location', ''),
            NULLIF(p_candidate->>'last_qualification', ''),
            NULLIF(p_candidate->>'experience_years', '')::numeric,
            left(p_candidate->>'raw_resume_text', 5000),
            v_drive_file_id,
            p_file->>'folder_path',
            COALESCE(p_candidate->'extracted_attributes', '{}'::jsonb)
        ) RETURNING id INTO v_candidate_id;
    ELSIF v_matched THEN
        -- Existing person, new file: existing values win, gaps get filled.
        UPDATE public.candidates
        SET email = COALESCE(email, v_email_raw),
            extracted_attributes =
                COALESCE(p_candidate->'extracted_attributes', '{}'::jsonb)
                || extracted_attributes,
            updated_at = now()
        WHERE id = v_candidate_id;
    END IF;

    -- File row: upsert on drive_file_id. Handles rename/move, and reconciliation
    -- (a later call with a now-resolved client/site fills in the blanks).
    INSERT INTO public.candidate_files (
        tenant_id, candidate_id, drive_file_id, file_hash, file_name, folder_path,
        client_id, site_id, role_name, file_size_bytes, mime_type, is_unresolved
    ) VALUES (
        p_tenant_id, v_candidate_id, v_drive_file_id,
        NULLIF(p_file->>'file_hash', ''),
        COALESCE(NULLIF(p_file->>'file_name', ''), v_drive_file_id),
        COALESCE(p_file->>'folder_path', ''),
        v_client_id, v_site_id,
        NULLIF(p_file->>'role_name', ''),
        NULLIF(p_file->>'file_size_bytes', '')::bigint,
        NULLIF(p_file->>'mime_type', ''),
        (v_site_id IS NULL)
    )
    ON CONFLICT (tenant_id, drive_file_id) DO UPDATE
    SET file_name     = EXCLUDED.file_name,
        folder_path   = EXCLUDED.folder_path,
        file_hash     = COALESCE(EXCLUDED.file_hash, public.candidate_files.file_hash),
        client_id     = COALESCE(EXCLUDED.client_id, public.candidate_files.client_id),
        site_id       = COALESCE(EXCLUDED.site_id, public.candidate_files.site_id),
        role_name     = COALESCE(EXCLUDED.role_name, public.candidate_files.role_name),
        is_unresolved = (COALESCE(EXCLUDED.site_id, public.candidate_files.site_id) IS NULL),
        updated_at    = now();

    -- Application (idempotent via uq_applications_candidate_site).
    IF p_application IS NOT NULL AND v_client_id IS NOT NULL AND v_site_id IS NOT NULL THEN
        INSERT INTO public.applications (
            tenant_id, candidate_id, client_id, site_id, stage, status
        ) VALUES (
            p_tenant_id, v_candidate_id, v_client_id, v_site_id,
            COALESCE(p_application->>'stage', 'applied'),
            COALESCE(p_application->>'status', 'active')
        )
        ON CONFLICT (tenant_id, candidate_id, client_id, site_id) DO NOTHING
        RETURNING id INTO v_app_id;

        IF v_app_id IS NOT NULL THEN
            v_app_created := true;
        ELSE
            SELECT id INTO v_app_id
            FROM public.applications
            WHERE tenant_id = p_tenant_id AND candidate_id = v_candidate_id
              AND client_id = v_client_id AND site_id = v_site_id;
        END IF;

        -- Task (idempotent via uq_work_tasks_entity_dedupe). Skipped unless the
        -- caller supplies a valid module_id and title.
        IF p_task IS NOT NULL AND v_task_module IS NOT NULL AND v_task_title IS NOT NULL THEN
            INSERT INTO public.work_tasks (
                tenant_id, client_id, site_id, module_id, title, description,
                related_entity_type, related_entity_id, priority, status
            ) VALUES (
                p_tenant_id, v_client_id, v_site_id, v_task_module, v_task_title,
                p_task->>'description',
                'candidate', v_candidate_id,
                COALESCE(p_task->>'priority', 'medium'), 'pending'
            )
            ON CONFLICT (tenant_id, client_id, site_id, module_id,
                         related_entity_type, related_entity_id) DO NOTHING
            RETURNING id INTO v_task_id;
        END IF;
    END IF;

    RETURN jsonb_build_object(
        'success',               true,
        'candidate_id',          v_candidate_id,
        'is_existing_candidate', (v_file_existed OR v_matched),
        'file_already_known',    v_file_existed,
        'is_unresolved',         (v_site_id IS NULL),
        'application_id',        v_app_id,
        'application_created',   v_app_created,
        'task_id',               v_task_id,
        'task_created',          (v_task_id IS NOT NULL)
    );
END;
$$;

-- ------------------------------------------------------------------------------
-- 7. Lock everything down: RLS on, no anon/authenticated access, RPCs for
--    service_role only. (service_role bypasses RLS, so the backend still works.
--    Add SELECT policies later if the frontend must read these tables directly.)
-- ------------------------------------------------------------------------------
ALTER TABLE public.candidate_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_runs       ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.candidate_files FROM anon, authenticated;
REVOKE ALL ON public.sync_runs       FROM anon, authenticated;

REVOKE ALL ON FUNCTION public.ingest_candidate_atomic(UUID, JSONB, JSONB, JSONB, JSONB)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.start_sync_run(UUID, TEXT, INT)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.heartbeat_sync_run(UUID)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finish_sync_run(UUID, TEXT, JSONB, JSONB)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.ingest_candidate_atomic(UUID, JSONB, JSONB, JSONB, JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.start_sync_run(UUID, TEXT, INT)   TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_sync_run(UUID)          TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_sync_run(UUID, TEXT, JSONB, JSONB) TO service_role;

COMMIT;
