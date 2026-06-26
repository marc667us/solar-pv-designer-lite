-- 017_phase7_drop_parallel_run.sql
-- =====================================================================
-- SOC 2 Phase 7 cutover -- drop the parallel-run RLS policies on the
-- 15 global tables so the per-intent strict policies added in
-- migration 015 take over as the sole gate.
--
-- Pre-conditions enforced by this migration (NOT just by the
-- workflow's pre-flight) so a bad ordering can't quietly remove the
-- one policy a table still relied on:
--
--   * Helper `current_user_is_admin()` exists (migration 015 applied).
--   * Every table in the cutover list carries at least one
--     `<table>_global_*` strict policy. If any table is missing its
--     strict cover, this migration RAISES EXCEPTION and rolls back
--     the entire transaction -- no policy is dropped.
--
-- Caveat: background jobs writing to monitor_alerts / monitor_state /
-- login_failures must set `app.current_role = 'admin'` OR run as a
-- super-user that bypasses RLS, otherwise the strict admin_all policy
-- denies the write. The /metrics gauge `solarpro_audit_chain_*` reads
-- on its scrape job already inherit the request's role GUC; ad-hoc
-- background writes (Apinto sync, cron monitors) need an explicit GUC
-- write before they touch these tables.
--
-- Rollback: there is NO automatic rollback. If the cutover misfires,
-- run the un-cutover migration sketched at the bottom of this file
-- which re-creates the parallel-run policies. Restoring the policies
-- restores the behaviour because the strict policies stay in place.
--
-- Idempotent: each DROP POLICY IF EXISTS so a re-run is a no-op.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Hard pre-condition: helper + strict policies must be live.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    has_helper BOOLEAN;
    t TEXT;
    n INT;
    global_tables TEXT[] := ARRAY[
        'installers', 'news_posts', 'helpline_learned_kb',
        'product_brands', 'product_categories', 'appliances',
        'assessment_requests', 'leads', 'beta_signups', 'newsletter_subscribers',
        'monitor_alerts', 'monitor_state', 'upgrade_codes',
        'admin_settings', 'login_failures'
    ];
BEGIN
    SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname='current_user_is_admin')
      INTO has_helper;
    IF NOT has_helper THEN
        RAISE EXCEPTION
            'Pre-condition failed: current_user_is_admin() not found. '
            'Migration 015 must be applied before this cutover.';
    END IF;

    FOREACH t IN ARRAY global_tables LOOP
        -- Skip tables that don't exist on this PG (some installs may
        -- not carry every optional table).
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
                'strict policy. Migration 015 must be applied first. '
                'Refusing to drop tenant_isolation (would block all '
                'access).', t;
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- Drop the parallel-run policy on every global table.
--           The strict <table>_global_* policies installed by 015 stay
--           in place and become the sole gate.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    global_tables TEXT[] := ARRAY[
        'installers', 'news_posts', 'helpline_learned_kb',
        'product_brands', 'product_categories', 'appliances',
        'assessment_requests', 'leads', 'beta_signups', 'newsletter_subscribers',
        'monitor_alerts', 'monitor_state', 'upgrade_codes',
        'admin_settings', 'login_failures'
    ];
BEGIN
    FOREACH t IN ARRAY global_tables LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name=t
        ) THEN
            CONTINUE;
        END IF;
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                       t || '_tenant_isolation', t);
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--
--   -- All 15 tenant_isolation policies on globals must be gone:
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname IN (
--      'installers_tenant_isolation','news_posts_tenant_isolation',
--      'helpline_learned_kb_tenant_isolation','product_brands_tenant_isolation',
--      'product_categories_tenant_isolation','appliances_tenant_isolation',
--      'assessment_requests_tenant_isolation','leads_tenant_isolation',
--      'beta_signups_tenant_isolation','newsletter_subscribers_tenant_isolation',
--      'monitor_alerts_tenant_isolation','monitor_state_tenant_isolation',
--      'upgrade_codes_tenant_isolation','admin_settings_tenant_isolation',
--      'login_failures_tenant_isolation');
--   -- expect: 0 rows
--
--   -- All 15 strict policy sets remain:
--   SELECT tablename, COUNT(*) FROM pg_policies
--    WHERE tablename IN (
--      'installers','news_posts','helpline_learned_kb',
--      'product_brands','product_categories','appliances',
--      'assessment_requests','leads','beta_signups','newsletter_subscribers',
--      'monitor_alerts','monitor_state','upgrade_codes',
--      'admin_settings','login_failures')
--    GROUP BY tablename ORDER BY tablename;
--   -- expect:
--   --   public_read tables  -> 4 policies each (public_read + admin INS/UPD/DEL)
--   --   anon_insert tables  -> 4 policies each (admin SEL + anon INS + admin UPD/DEL)
--   --   admin_only tables   -> 1 policy each  (admin_all)
--
-- =====================================================================

-- =====================================================================
-- UN-CUTOVER (017-undo) SKETCH -- ship as migration 018 if needed.
-- ---------------------------------------------------------------------
--
-- DO $$
-- DECLARE
--     t TEXT;
--     pol_name TEXT;
--     global_tables TEXT[] := ARRAY[
--         'installers','news_posts','helpline_learned_kb',
--         'product_brands','product_categories','appliances',
--         'assessment_requests','leads','beta_signups','newsletter_subscribers',
--         'monitor_alerts','monitor_state','upgrade_codes',
--         'admin_settings','login_failures'
--     ];
-- BEGIN
--     FOREACH t IN ARRAY global_tables LOOP
--         pol_name := t || '_tenant_isolation';
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol_name, t);
--         EXECUTE format($pol$
--             CREATE POLICY %I ON %I
--                 USING (
--                     current_tenant_id() IS NULL
--                     OR tenant_id IS NULL
--                     OR tenant_id = current_tenant_id()
--                 )
--                 WITH CHECK (
--                     current_tenant_id() IS NULL
--                     OR tenant_id IS NULL
--                     OR tenant_id = current_tenant_id()
--                 )
--             $pol$, pol_name, t);
--     END LOOP;
-- END;
-- $$;
--
-- =====================================================================
