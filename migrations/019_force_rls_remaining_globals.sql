-- 019_force_rls_remaining_globals.sql
-- =====================================================================
-- SOC 2 Phase 7 close-out -- FORCE ROW LEVEL SECURITY on the last 3
-- global tables (monitor_alerts, monitor_state, login_failures), now
-- that their writer-side caveats are resolved.
--
-- RESOLUTIONS:
--
-- monitor_alerts, monitor_state
--   The `_run_monitor_scan()` cron in web_app.py writes to a phantom
--   LOCAL SQLite file (solar.db in app dir), NEVER to live Postgres.
--   On Render the live PG tables are populated/read exclusively by the
--   @admin_required route handlers (monitor_status, monitor_settings,
--   monitor_alerts_list, monitor_dismiss). Those handlers run inside
--   a Flask request context, so M3.4 `apply_tenant_guc` has already
--   written `app.current_role='admin'` to the connection by the time
--   the query fires. The existing admin_all strict policy is the
--   correct semantic -- no policy change needed.
--
-- login_failures
--   Written by the legacy /login POST failed branch, which runs in
--   an anonymous request (auth has NOT succeeded). With the admin_all
--   policy in place, FORCE would reject the INSERT. Reclassify the
--   policy from admin_only to anon_insert (matches the leads /
--   beta_signups / assessment_requests pattern):
--     * SELECT      admin
--     * INSERT      anon (anyone)
--     * UPDATE/DEL  admin
--   Reads still require admin (only admins see brute-force logs).
--   Writes admitted from anon context.
--
-- Idempotent: DROP POLICY IF EXISTS + CREATE POLICY each step.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Reclassify login_failures: drop admin_all, install the
--           anon_insert quadruplet (admin SEL + anon INS + admin
--           UPD/DEL).
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
         WHERE table_schema='public' AND table_name='login_failures'
    ) THEN
        RAISE NOTICE 'login_failures table absent; skipping policy reclassification.';
        RETURN;
    END IF;

    -- Drop the existing admin_all (catches the new policy name) +
    -- any older form. IF EXISTS keeps re-runs clean.
    EXECUTE 'DROP POLICY IF EXISTS login_failures_global_admin_all     ON login_failures';
    EXECUTE 'DROP POLICY IF EXISTS login_failures_global_admin_select  ON login_failures';
    EXECUTE 'DROP POLICY IF EXISTS login_failures_global_anon_insert   ON login_failures';
    EXECUTE 'DROP POLICY IF EXISTS login_failures_global_admin_update  ON login_failures';
    EXECUTE 'DROP POLICY IF EXISTS login_failures_global_admin_delete  ON login_failures';

    EXECUTE $pol$
        CREATE POLICY login_failures_global_admin_select ON login_failures
            FOR SELECT
            USING (current_user_is_admin())
    $pol$;

    EXECUTE $pol$
        CREATE POLICY login_failures_global_anon_insert ON login_failures
            FOR INSERT
            WITH CHECK (true)
    $pol$;

    EXECUTE $pol$
        CREATE POLICY login_failures_global_admin_update ON login_failures
            FOR UPDATE
            USING (current_user_is_admin())
            WITH CHECK (current_user_is_admin())
    $pol$;

    EXECUTE $pol$
        CREATE POLICY login_failures_global_admin_delete ON login_failures
            FOR DELETE
            USING (current_user_is_admin())
    $pol$;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- Hard pre-condition for FORCE: each table must carry at
--           least one *_global_* strict policy. Without that, FORCE
--           turns into a hard deny.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    n INT;
    targets TEXT[] := ARRAY[
        'monitor_alerts', 'monitor_state', 'login_failures'
    ];
BEGIN
    FOREACH t IN ARRAY targets LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name=t
        ) THEN
            CONTINUE;
        END IF;
        SELECT COUNT(*) INTO n
          FROM pg_policies
         WHERE schemaname='public'
           AND tablename = t
           AND policyname LIKE '%_global_%';
        IF n < 1 THEN
            RAISE EXCEPTION
                'Pre-condition failed: table % carries no _global_* '
                'strict policy. FORCE would deny all access.', t;
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 3 -- FORCE on the 3 remaining global tables.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    targets TEXT[] := ARRAY[
        'monitor_alerts', 'monitor_state', 'login_failures'
    ];
BEGIN
    FOREACH t IN ARRAY targets LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
             WHERE table_schema='public' AND table_name=t
        ) THEN
            CONTINUE;
        END IF;
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   -- All 3 now report rls_on=t AND force_on=t:
--   SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
--     FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
--    WHERE n.nspname='public'
--      AND c.relname IN ('monitor_alerts','monitor_state','login_failures')
--    ORDER BY c.relname;
--
--   -- login_failures policy shape (4 policies after reclassification):
--   SELECT policyname, cmd
--     FROM pg_policies
--    WHERE tablename='login_failures'
--    ORDER BY policyname;
--   -- expect: 4 rows
--   --   login_failures_global_admin_delete  | DELETE
--   --   login_failures_global_admin_select  | SELECT
--   --   login_failures_global_admin_update  | UPDATE
--   --   login_failures_global_anon_insert   | INSERT
--
--   -- Anon INSERT must succeed (BEGIN/COMMIT-wrapped):
--   BEGIN;
--     SELECT set_config('app.current_role', '', true);
--     INSERT INTO login_failures (username, ip_address) VALUES ('smoke','127.0.0.1');
--     DELETE FROM login_failures WHERE username='smoke';
--   COMMIT;  -- second DELETE would normally need admin; allowed here only
--             because we're running as the DB superuser bypassing the policy
--             for the cleanup. In real anon code paths the DELETE isn't fired.
-- =====================================================================

-- =====================================================================
-- ROLLBACK SKETCH (ship as migration 020 if needed)
-- ---------------------------------------------------------------------
-- DO $$ DECLARE t TEXT; targets TEXT[] :=
--   ARRAY['monitor_alerts','monitor_state','login_failures'];
-- BEGIN
--   FOREACH t IN ARRAY targets LOOP
--     EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
--   END LOOP;
-- END; $$;
--
-- DROP POLICY IF EXISTS login_failures_global_admin_select ON login_failures;
-- DROP POLICY IF EXISTS login_failures_global_anon_insert  ON login_failures;
-- DROP POLICY IF EXISTS login_failures_global_admin_update ON login_failures;
-- DROP POLICY IF EXISTS login_failures_global_admin_delete ON login_failures;
-- CREATE POLICY login_failures_global_admin_all ON login_failures
--     FOR ALL USING (current_user_is_admin())
--             WITH CHECK (current_user_is_admin());
-- =====================================================================
