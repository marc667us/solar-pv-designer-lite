-- 022_soc_rls.sql
-- =====================================================================
-- AI-SOC (Slice 0) -- Row Level Security for the ten support/security
-- operational tables created by new_soc_slice0.py::_ensure_soc_schema().
--
-- Classification: ADMIN ONLY. These tables hold platform-operational
-- data (incidents, events, agent runs, runbooks, security evidence,
-- knowledge articles, deployment links). No customer/tenant reads them
-- and no anonymous path writes them -- they are the same intent class
-- as monitor_alerts / admin_settings / login_failures in
-- 015_global_table_policies.sql PART 4.
--
-- Pattern (identical to 015 PART 4, plus a parallel-run escape):
--   * ENABLE ROW LEVEL SECURITY on each table.
--   * One strict admin-all policy gated on current_user_is_admin()
--     (reads the app.current_role GUC written by apply_tenant_guc()).
--   * One parallel-run permissive policy admitting access when NO role
--     context is set (KEYCLOAK_ENABLED off / legacy path) so applying
--     this migration cannot lock the app out before cutover. PG ORs
--     permissive policies, so the escape widens access today and is
--     dropped at Phase-7 cutover (like the other parallel-run policies).
--
-- NOT force-enabled: uses ENABLE (not FORCE) so the bootstrap/superuser
-- seed path is unaffected, matching how 015 shipped globals before the
-- deliberate FORCE pass (018/019/020). A later migration may FORCE these
-- once the admin GUC is proven set on every SOC request path.
--
-- Depends on: current_user_is_admin() from 015_global_table_policies.sql.
-- Re-declared here CREATE OR REPLACE so this file applies standalone.
--
-- Idempotent: guarded by information_schema existence checks;
-- DROP POLICY IF EXISTS + CREATE POLICY per policy.
--
-- Apply deliberately via the gated workflow (dry-run first), NEVER auto:
--   irreversible-ish DDL on live Postgres. Seeding/reads on these tables
--   must run with set_config('app.current_role','admin',true) in the txn
--   (see feedback_solar_rls_seed_admin_role) or the admin policy rejects.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- current_user_is_admin() helper (idempotent re-declaration).
-- Considered admin iff app.current_role GUC is exactly 'admin'.
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
-- PART 2 -- ENABLE RLS + admin-all + parallel-run escape on all ten.
-- ---------------------------------------------------------------------
DO $$
DECLARE
    t TEXT;
    soc_tables TEXT[] := ARRAY[
        'support_incidents',
        'support_events',
        'support_actions',
        'support_approvals',
        'support_agent_runs',
        'support_runbooks',
        'security_incidents',
        'security_evidence',
        'knowledge_articles',
        'deployment_changes'
    ];
    role_ctx TEXT;
BEGIN
    -- Reusable SQL fragment: TRUE when no role GUC is set on the session
    -- (legacy / parallel-run / KEYCLOAK off). Written inline per policy.
    role_ctx := $frag$
        current_setting('app.current_role', true) IS NULL
        OR current_setting('app.current_role', true) = ''
    $frag$;

    FOREACH t IN ARRAY soc_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);

            -- Strict admin-all policy.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_soc_admin_all', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR ALL
                    USING (current_user_is_admin())
                    WITH CHECK (current_user_is_admin())
                $pol$, t || '_soc_admin_all', t);

            -- Parallel-run escape: admit when no role context is set, so
            -- applying this migration before Keycloak cutover does not
            -- lock the app out. Dropped at Phase-7 cutover.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_soc_parallel_run', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR ALL
                    USING ( %s )
                    WITH CHECK ( %s )
                $pol$, t || '_soc_parallel_run', t, role_ctx, role_ctx);
        END IF;
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   SELECT tablename, COUNT(*) AS policy_count
--     FROM pg_policies
--    WHERE tablename IN (
--      'support_incidents','support_events','support_actions',
--      'support_approvals','support_agent_runs','support_runbooks',
--      'security_incidents','security_evidence','knowledge_articles',
--      'deployment_changes')
--    GROUP BY tablename ORDER BY tablename;
--   Expected: 2 per table (soc_admin_all + soc_parallel_run).
--
--   -- Admin context sees rows; a set non-admin role does not:
--   SELECT set_config('app.current_role','admin',true);
--   SELECT COUNT(*) FROM support_incidents;      -- admitted
--   SELECT set_config('app.current_role','user',true);
--   SELECT COUNT(*) FROM support_incidents;      -- 0 (both policies reject)
-- =====================================================================
