-- 018_force_rls_globals.sql
-- =====================================================================
-- SOC 2 Phase 7 close-out -- ALTER TABLE FORCE ROW LEVEL SECURITY
-- on 12 of the 15 global tables.
--
-- WHY THIS EXISTS
-- ---------------
-- The SolarPro app's Render connection runs as the database OWNER.
-- PostgreSQL bypasses RLS for owners by default unless the table
-- carries FORCE ROW LEVEL SECURITY. Without that flag every policy
-- on the owner's connection is a no-op -- including the strict
-- policies installed by migration 015 and the parallel-run drops
-- from migration 017.
--
-- Surfaced during the 017 apply behaviour smoke: both the
-- "with admin GUC" and "without admin GUC" queries returned identical
-- counts because owner role bypassed RLS in both. The smoke didn't
-- regress, but it also didn't prove enforcement -- this migration
-- closes that gap for the 12 tables whose writers all run inside a
-- Flask request context (so the M3.4-wired apply_tenant_guc has
-- already published the role GUC by the time the query runs).
--
-- INTENTIONALLY SKIPPED (writers run OUTSIDE a request context, so
-- the role GUC is absent and the strict admin_all policy would deny
-- the write):
--   * monitor_alerts  -- background monitor cron INSERTs new alerts.
--                       Needs a writer-side `SET LOCAL
--                       app.current_role='admin'` (or session-level
--                       SET on the cron's connection) before FORCE.
--   * monitor_state   -- background monitor cron UPDATEs scan state.
--                       Same fix.
--   * login_failures  -- legacy /login POST writes a row before any
--                       auth context exists. The KC migration retired
--                       the legacy POST path (M1.1) but the route
--                       still falls back when KC is unreachable, so
--                       it stays callable and would 500 on FORCE.
--                       Resolve by either retiring the legacy path
--                       entirely OR widening the policy to admit
--                       INSERT WITH CHECK (true).
--
-- Those three are documented in the session memory as the remaining
-- Phase 7 close-out items.
--
-- ROLLBACK: ALTER TABLE %I NO FORCE ROW LEVEL SECURITY; per table.
-- Sketch at the bottom of this file. Strict policies stay in place
-- when rollback runs, so behaviour returns to "owner bypasses RLS".
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Hard pre-condition: every table about to be FORCED must
--           carry at least one *_global_* strict policy. Without that
--           the FORCE turns into a hard deny (no policy admits the
--           row), bricking access.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    n INT;
    forced_tables TEXT[] := ARRAY[
        'installers', 'news_posts', 'helpline_learned_kb',
        'product_brands', 'product_categories', 'appliances',
        'assessment_requests', 'leads', 'beta_signups', 'newsletter_subscribers',
        'upgrade_codes', 'admin_settings'
    ];
BEGIN
    FOREACH t IN ARRAY forced_tables LOOP
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
                'strict policy. FORCE would deny all access. Migration '
                '015 must be fully applied first.', t;
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- Enable FORCE on the 12 tables.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    forced_tables TEXT[] := ARRAY[
        'installers', 'news_posts', 'helpline_learned_kb',
        'product_brands', 'product_categories', 'appliances',
        'assessment_requests', 'leads', 'beta_signups', 'newsletter_subscribers',
        'upgrade_codes', 'admin_settings'
    ];
BEGIN
    FOREACH t IN ARRAY forced_tables LOOP
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
--   -- All 12 tables must report rowsecurity AND forcerowsecurity true:
--   SELECT c.relname,
--          c.relrowsecurity      AS rls_on,
--          c.relforcerowsecurity AS force_on
--     FROM pg_class c
--     JOIN pg_namespace n ON n.oid = c.relnamespace
--    WHERE n.nspname = 'public'
--      AND c.relname IN (
--        'installers','news_posts','helpline_learned_kb',
--        'product_brands','product_categories','appliances',
--        'assessment_requests','leads','beta_signups','newsletter_subscribers',
--        'upgrade_codes','admin_settings')
--    ORDER BY c.relname;
--   -- expect: 12 rows, both flags true on every row.
--
--   -- Behaviour smoke (MUST use BEGIN/COMMIT around SET LOCAL because
--   -- psql autocommits each statement and is_local would expire):
--   BEGIN;
--     SELECT set_config('app.current_role', '', true);
--     SELECT COUNT(*) AS no_guc FROM admin_settings;   -- expect 0
--   COMMIT;
--   BEGIN;
--     SELECT set_config('app.current_role', 'admin', true);
--     SELECT COUNT(*) AS with_guc FROM admin_settings; -- expect actual count
--   COMMIT;
-- =====================================================================

-- =====================================================================
-- ROLLBACK SKETCH (ship as 019 or run inline if cutover misfires)
-- ---------------------------------------------------------------------
-- DO $$
-- DECLARE t TEXT;
--     forced_tables TEXT[] := ARRAY[
--         'installers','news_posts','helpline_learned_kb',
--         'product_brands','product_categories','appliances',
--         'assessment_requests','leads','beta_signups','newsletter_subscribers',
--         'upgrade_codes','admin_settings'
--     ];
-- BEGIN
--     FOREACH t IN ARRAY forced_tables LOOP
--         EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
--     END LOOP;
-- END;
-- $$;
-- =====================================================================
