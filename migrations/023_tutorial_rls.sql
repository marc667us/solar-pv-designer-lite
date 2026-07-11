-- 023_tutorial_rls.sql
-- =====================================================================
-- Tutorial & Demo Framework -- Row Level Security for tutorial_events,
-- the telemetry table created by new_tutorial_admin.py::_ensure_tutorial_schema().
--
-- Classification: WRITE-ANY, ADMIN-READ. Unlike the ten admin-only SOC
-- tables (022), tutorial_events is written by ANY visitor -- including
-- anonymous users playing a public demo (spec "video tutorial.txt":
-- "Public users can play public demos only"; ANALYTICS section records
-- their started/completed/skipped). So the policy set differs from 022:
--
--   * INSERT is permitted to everyone (telemetry sink). A row carries no
--     secret; the app clamps/allowlists every field before insert.
--   * SELECT is admin-only (the /admin/tutorials/analytics dashboard is
--     already @admin_required at the app layer; this is the DB backstop).
--   * UPDATE/DELETE are admin-only.
--   * A parallel-run escape admits access when NO role context is set
--     (KEYCLOAK_ENABLED off / legacy path) so applying this migration
--     cannot lock the app out before cutover -- identical intent to 022.
--
-- NOT force-enabled: ENABLE (not FORCE), so the bootstrap/superuser path
-- is unaffected (matches 015/022). A later migration may FORCE once the
-- admin GUC is proven set on every admin-read request path.
--
-- Depends on: current_user_is_admin() from 015_global_table_policies.sql
-- (re-declared CREATE OR REPLACE so this file applies standalone).
--
-- Idempotent: existence-guarded; DROP POLICY IF EXISTS + CREATE POLICY.
--
-- Apply deliberately via the gated workflow (dry-run first), NEVER auto.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- current_user_is_admin() helper (idempotent re-declaration).
-- Considered admin iff the app.current_role GUC is exactly 'admin'.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION current_user_is_admin() RETURNS BOOLEAN
    LANGUAGE plpgsql STABLE AS $$
DECLARE
    raw_value TEXT;
BEGIN
    raw_value := current_setting('app.current_role', true);
    IF raw_value IS NULL THEN
        RETURN FALSE;
    END IF;
    RETURN raw_value = 'admin';
END;
$$;

-- ---------------------------------------------------------------------
-- PART 2 -- ENABLE RLS + policies on tutorial_events (guarded on the
-- table existing, since _ensure_tutorial_schema creates it lazily).
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'tutorial_events'
    ) THEN
        EXECUTE 'ALTER TABLE tutorial_events ENABLE ROW LEVEL SECURITY';

        -- INSERT: anyone may write telemetry (anonymous public demos included).
        EXECUTE 'DROP POLICY IF EXISTS tutorial_events_insert_any ON tutorial_events';
        EXECUTE 'CREATE POLICY tutorial_events_insert_any ON tutorial_events
                 FOR INSERT WITH CHECK (true)';

        -- SELECT: admin only (DB backstop behind the @admin_required dashboard).
        EXECUTE 'DROP POLICY IF EXISTS tutorial_events_admin_read ON tutorial_events';
        EXECUTE 'CREATE POLICY tutorial_events_admin_read ON tutorial_events
                 FOR SELECT USING (current_user_is_admin())';

        -- UPDATE/DELETE: admin only.
        EXECUTE 'DROP POLICY IF EXISTS tutorial_events_admin_write ON tutorial_events';
        EXECUTE 'CREATE POLICY tutorial_events_admin_write ON tutorial_events
                 FOR UPDATE USING (current_user_is_admin())';
        EXECUTE 'DROP POLICY IF EXISTS tutorial_events_admin_delete ON tutorial_events';
        EXECUTE 'CREATE POLICY tutorial_events_admin_delete ON tutorial_events
                 FOR DELETE USING (current_user_is_admin())';

        -- Parallel-run escape: when NO role context is set (KC off / legacy),
        -- admit all access so this migration cannot lock out the live path
        -- before cutover. PG ORs permissive policies; drop at Phase-7 FORCE.
        EXECUTE 'DROP POLICY IF EXISTS tutorial_events_parallel_run ON tutorial_events';
        EXECUTE 'CREATE POLICY tutorial_events_parallel_run ON tutorial_events
                 FOR ALL USING (current_setting(''app.current_role'', true) IS NULL)
                 WITH CHECK (current_setting(''app.current_role'', true) IS NULL)';
    END IF;
END $$;

COMMIT;
