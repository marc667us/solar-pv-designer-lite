-- 004_audit_log_tenant.sql
-- =====================================================================
-- Phase 6 of docs/SECURITY_MIGRATION_KEYCLOAK.md
--
-- Extends `audit_logs` (created by web_app.py:init_db, mirrored on
-- Postgres by migration 001) with two columns the unified audit
-- writer needs:
--
--   tenant_id UUID  -- which tenant the actor belonged to. Carried
--                      forward by app.security.audit.write_audit_event.
--   agent_id  TEXT  -- the Keycloak `azp` for service-account actions
--                      and the OIDC `userId` for human Keycloak events.
--
-- Adds indexes for the most common audit queries (per-tenant time
-- window + per-agent time window) and a parallel-run-safe RLS policy
-- matching the template from migration 003.
--
-- Idempotent. Safe to re-run.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- ADD COLUMN IF NOT EXISTS
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'audit_logs'
    ) THEN
        EXECUTE 'ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tenant_id UUID';
        EXECUTE 'ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS agent_id  TEXT';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_created '
                'ON audit_logs (tenant_id, created_at DESC)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_audit_logs_agent_created '
                'ON audit_logs (agent_id, created_at DESC)';
        EXECUTE 'CREATE INDEX IF NOT EXISTS idx_audit_logs_action_created '
                'ON audit_logs (action, created_at DESC)';
    END IF;
END;
$$;

-- ---------------------------------------------------------------------
-- PART 2 -- RLS using the migration 003 helper
--
-- audit_logs is intentionally append-only: the policy allows INSERT
-- always (so an actor can record their own action) but SELECT is
-- gated on tenant match. Phase 7 cutover may tighten further.
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'audit_logs'
    ) AND EXISTS (
        SELECT 1 FROM pg_proc WHERE proname = 'current_tenant_id'
    ) THEN
        EXECUTE 'ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs';
        EXECUTE $pol$
            CREATE POLICY audit_logs_tenant_isolation ON audit_logs
                FOR SELECT
                USING (
                    current_tenant_id() IS NULL
                    OR tenant_id IS NULL
                    OR tenant_id = current_tenant_id()
                )
        $pol$;
        EXECUTE 'DROP POLICY IF EXISTS audit_logs_append_only ON audit_logs';
        EXECUTE $pol$
            CREATE POLICY audit_logs_append_only ON audit_logs
                FOR INSERT
                WITH CHECK (true)
        $pol$;
        -- No UPDATE / DELETE policy -> nobody can mutate audit rows.
    END IF;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name = 'audit_logs' AND column_name IN ('tenant_id','agent_id');
--   SELECT indexname FROM pg_indexes
--    WHERE tablename = 'audit_logs' AND indexname LIKE 'idx_audit_logs_%';
--   SELECT policyname FROM pg_policies WHERE tablename = 'audit_logs';
-- =====================================================================
