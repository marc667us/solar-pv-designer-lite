-- 007_rls_boq_hierarchy.sql
-- =====================================================================
-- SOC 2 M1.6 extension — RLS for the BOQ-project hierarchy.
--
-- Closes the 2026-06-25 Codex review's HIGH finding: the BOQ project
-- hierarchy tables (boq_projects, boq_buildings, boq_floors,
-- boq_floor_items, boq_floor_rate_buildup, boq_audit_log) carried no
-- tenant_id column and were excluded from the Phase 4 RLS migration
-- (003_rls_tenant.sql).
--
-- Mirrors 003's structure exactly:
--   PART 1 — Reuses current_tenant_id() + _phase4_user_to_tenant() from 003.
--   PART 2 — ADD COLUMN tenant_id UUID (nullable) on the 6 BOQ tables.
--   PART 3 — Deterministic backfill from the owning user / parent project.
--   PART 4 — ENABLE ROW LEVEL SECURITY + parallel-run policy per table.
--
-- Parallel-run safety: the policy is intentionally permissive when the
-- GUC is unset OR when the row's tenant_id is NULL. The Phase 7 cutover
-- (separate migration, post Phase B) tightens to FORCE ROW LEVEL SECURITY
-- + drops both NULL escapes.
--
-- Idempotent: every statement uses IF NOT EXISTS / IF EXISTS, so the file
-- can be applied twice without error.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 — Reuse helpers from 003. Re-CREATE OR REPLACE so this migration
--          can be applied to a fresh DB that hasn't seen 003 yet.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION current_tenant_id() RETURNS UUID
    LANGUAGE plpgsql STABLE AS $$
DECLARE
    raw_value TEXT;
BEGIN
    raw_value := current_setting('app.current_tenant', true);
    IF raw_value IS NULL OR raw_value = '' THEN
        RETURN NULL;
    END IF;
    BEGIN
        RETURN raw_value::uuid;
    EXCEPTION WHEN invalid_text_representation THEN
        RETURN NULL;
    END;
END;
$$;

CREATE OR REPLACE FUNCTION _phase4_user_to_tenant(uid BIGINT) RETURNS UUID
    LANGUAGE sql IMMUTABLE AS $$
    SELECT md5('solarpro-tenant-v1:' || uid::text)::uuid
$$;


-- ---------------------------------------------------------------------
-- PART 2 — tenant_id UUID column on each BOQ-hierarchy table.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    boq_tables TEXT[] := ARRAY[
        'boq_projects',
        'boq_buildings',
        'boq_floors',
        'boq_floor_items',
        'boq_floor_rate_buildup',
        'boq_audit_log'
    ];
BEGIN
    FOREACH t IN ARRAY boq_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id UUID',
                t
            );
            EXECUTE format(
                'CREATE INDEX IF NOT EXISTS %I ON %I (tenant_id)',
                'idx_' || t || '_tenant_id', t
            );
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 3 — Backfill.
--
-- Hierarchy:
--   boq_projects         <- user_id          (creator)
--   boq_buildings        <- project_id chain -> boq_projects.tenant_id
--   boq_floors           <- project_id chain -> boq_projects.tenant_id
--   boq_floor_items      <- project_id chain -> boq_projects.tenant_id
--   boq_floor_rate_buildup <- project_id chain -> boq_projects.tenant_id
--   boq_audit_log        <- user_id          (actor's tenant — matches 003)
--
-- Order matters: boq_projects must be backfilled first, then the chain.
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. boq_projects (root) -- from user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_projects' AND column_name='user_id') THEN
        UPDATE boq_projects
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 2. boq_buildings -- from parent project
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_buildings' AND column_name='project_id') THEN
        UPDATE boq_buildings b
           SET tenant_id = p.tenant_id
          FROM boq_projects p
         WHERE b.project_id = p.id
           AND b.tenant_id IS NULL
           AND p.tenant_id IS NOT NULL;
    END IF;

    -- 3. boq_floors -- from parent project
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_floors' AND column_name='project_id') THEN
        UPDATE boq_floors f
           SET tenant_id = p.tenant_id
          FROM boq_projects p
         WHERE f.project_id = p.id
           AND f.tenant_id IS NULL
           AND p.tenant_id IS NOT NULL;
    END IF;

    -- 4. boq_floor_items -- from parent project (project_id is NOT NULL)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_floor_items' AND column_name='project_id') THEN
        UPDATE boq_floor_items i
           SET tenant_id = p.tenant_id
          FROM boq_projects p
         WHERE i.project_id = p.id
           AND i.tenant_id IS NULL
           AND p.tenant_id IS NOT NULL;
    END IF;

    -- 5. boq_floor_rate_buildup -- from parent project
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_floor_rate_buildup' AND column_name='project_id') THEN
        UPDATE boq_floor_rate_buildup r
           SET tenant_id = p.tenant_id
          FROM boq_projects p
         WHERE r.project_id = p.id
           AND r.tenant_id IS NULL
           AND p.tenant_id IS NOT NULL;
    END IF;

    -- 6. boq_audit_log -- from actor user_id (matches 003's convention
    --    that audit rows carry the actor's tenant; cross-tenant admin
    --    actions stay visible to the tenant being acted on via JOIN on
    --    target_id when querying).
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_audit_log' AND column_name='user_id') THEN
        UPDATE boq_audit_log
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 — RLS policies (parallel-run flavour, identical pattern to 003).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    boq_tables TEXT[] := ARRAY[
        'boq_projects',
        'boq_buildings',
        'boq_floors',
        'boq_floor_items',
        'boq_floor_rate_buildup',
        'boq_audit_log'
    ];
BEGIN
    FOREACH t IN ARRAY boq_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
            pol_name := t || '_tenant_isolation';
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol_name, t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    USING (
                        current_tenant_id() IS NULL
                        OR tenant_id IS NULL
                        OR tenant_id = current_tenant_id()
                    )
                    WITH CHECK (
                        current_tenant_id() IS NULL
                        OR tenant_id IS NULL
                        OR tenant_id = current_tenant_id()
                    )
                $pol$,
                pol_name, t
            );
        END IF;
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
-- All 6 must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id'
--      AND table_schema='public'
--      AND table_name IN (
--        'boq_projects','boq_buildings','boq_floors',
--        'boq_floor_items','boq_floor_rate_buildup','boq_audit_log');
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname LIKE 'boq_%_tenant_isolation';
--
-- Coverage check (should match row count before migration):
--
--   SELECT
--     (SELECT COUNT(*) FROM boq_projects WHERE tenant_id IS NULL) AS unbackfilled_projects,
--     (SELECT COUNT(*) FROM boq_buildings WHERE tenant_id IS NULL) AS unbackfilled_buildings,
--     (SELECT COUNT(*) FROM boq_floors WHERE tenant_id IS NULL) AS unbackfilled_floors,
--     (SELECT COUNT(*) FROM boq_floor_items WHERE tenant_id IS NULL) AS unbackfilled_items,
--     (SELECT COUNT(*) FROM boq_floor_rate_buildup WHERE tenant_id IS NULL) AS unbackfilled_rates,
--     (SELECT COUNT(*) FROM boq_audit_log WHERE tenant_id IS NULL) AS unbackfilled_audit;
--
-- Expected: zero unbackfilled rows on tables that have a non-NULL parent.
-- =====================================================================
