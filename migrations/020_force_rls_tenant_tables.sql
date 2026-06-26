-- 020_force_rls_tenant_tables.sql
-- =====================================================================
-- SOC 2 Phase 7 close-out -- FORCE ROW LEVEL SECURITY on the 33
-- tenant-scoped tables, with the existing parallel-run policy widened
-- to admit platform admins so cross-tenant admin views keep working.
--
-- WHY THIS IS SAFE
-- ----------------
-- The existing `<table>_tenant_isolation` parallel-run policy admits
-- when EITHER:
--   * current_tenant_id() IS NULL  (no GUC -> NULL escape)
--   * tenant_id IS NULL            (legacy/unbackfilled rows)
--   * tenant_id = current_tenant_id() (caller's own tenant)
--
-- For the four paths SolarPro actually runs on:
--
--   * Anonymous (no JWT, no GUC). current_tenant_id()=NULL, admitted
--     via first clause. Behaviour unchanged after FORCE.
--   * Authenticated tenant user with KC JWT. apply_tenant_guc sets
--     `app.current_tenant` to the user's tenant UUID. Policy admits
--     matching + NULL rows. Defence in depth; the app already
--     filters by user_id at the SQL layer.
--   * Authenticated platform/marketplace/tenant ADMIN. Same as above
--     for tenant filter -- BUT the admin clause added by this
--     migration ALSO admits the row regardless of tenant. Preserves
--     cross-tenant admin views that today rely on owner bypass.
--   * Owner connection in a no-GUC context (init_db, migration
--     scripts, ad-hoc psql). current_tenant_id()=NULL, admitted.
--
-- Net effect: tenant isolation now genuinely enforces against the
-- app's connection for NON-ADMIN authenticated requests. Owner-bypass
-- is closed but no admin route regresses because the admin clause
-- preserves their visibility.
--
-- PHASE B CUTOVER (future migration): drop the NULL escape + admin
-- clause and require every INSERT to set tenant_id. That's a bigger
-- change because every INSERT site in web_app.py needs to publish
-- tenant_id from session. Tracked separately.
--
-- Idempotent: DROP POLICY IF EXISTS + CREATE POLICY per table,
-- ALTER TABLE FORCE per table.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Helper guard: current_user_is_admin() must already exist
--           (migration 015 applied).
-- ---------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname='current_user_is_admin') THEN
        RAISE EXCEPTION
            'Pre-condition failed: current_user_is_admin() not found. '
            'Migration 015 must be applied first.';
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- For every table that carries a *_tenant_isolation policy
--           AND is NOT in the 15 globals (already handled by 015 + 017
--           + 018 + 019), DROP the existing parallel-run policy,
--           CREATE the widened (admin escape) version, then FORCE.
--
-- Dynamic discovery via pg_policies so a new tenant table added to a
-- future batch is automatically swept on the next re-run.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    rec RECORD;
    pol_name TEXT;
    globals TEXT[] := ARRAY[
        'installers','news_posts','helpline_learned_kb',
        'product_brands','product_categories','appliances',
        'assessment_requests','leads','beta_signups','newsletter_subscribers',
        'monitor_alerts','monitor_state','upgrade_codes',
        'admin_settings','login_failures'
    ];
    affected_count INT := 0;
BEGIN
    FOR rec IN
        SELECT DISTINCT tablename
          FROM pg_policies
         WHERE schemaname='public'
           AND policyname LIKE '%_tenant_isolation'
           AND tablename != ALL(globals)
         ORDER BY tablename
    LOOP
        pol_name := rec.tablename || '_tenant_isolation';

        -- Drop the existing parallel-run policy (it's about to be
        -- replaced by the wider admin-escape version).
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                       pol_name, rec.tablename);

        -- Re-create with admin escape.
        EXECUTE format($pol$
            CREATE POLICY %I ON %I
                USING (
                    current_tenant_id() IS NULL
                    OR tenant_id IS NULL
                    OR tenant_id = current_tenant_id()
                    OR current_user_is_admin()
                )
                WITH CHECK (
                    current_tenant_id() IS NULL
                    OR tenant_id IS NULL
                    OR tenant_id = current_tenant_id()
                    OR current_user_is_admin()
                )
            $pol$, pol_name, rec.tablename);

        -- FORCE so the owner-bypass closes on this table too.
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',
                       rec.tablename);

        affected_count := affected_count + 1;
    END LOOP;

    RAISE NOTICE 'tenant FORCE applied to % tables', affected_count;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--
--   -- Count FORCE-enabled tenant tables (parallel-run policy survives,
--   -- 15 globals excluded):
--   SELECT COUNT(*) AS tenant_force_count
--     FROM pg_class c
--     JOIN pg_namespace n ON n.oid = c.relnamespace
--    WHERE n.nspname='public'
--      AND c.relrowsecurity = true
--      AND c.relforcerowsecurity = true
--      AND c.relname NOT IN (
--        'installers','news_posts','helpline_learned_kb',
--        'product_brands','product_categories','appliances',
--        'assessment_requests','leads','beta_signups','newsletter_subscribers',
--        'monitor_alerts','monitor_state','upgrade_codes',
--        'admin_settings','login_failures');
--   -- expect: ~33 (depending on which tenant tables landed in earlier batches)
--
--   -- Behaviour smoke -- the wider policy must:
--   --   * admit when no GUC is set (NULL escape):
--   BEGIN;
--     SELECT set_config('app.current_tenant', '', true);
--     SELECT set_config('app.current_role',   '', true);
--     SELECT COUNT(*) FROM projects;  -- expect actual count
--   COMMIT;
--
--   --   * filter to caller's tenant when a UUID GUC is set:
--   BEGIN;
--     SELECT set_config('app.current_tenant',
--       '11111111-1111-1111-1111-111111111111', true);
--     SELECT set_config('app.current_role', '', true);
--     SELECT COUNT(*) FROM projects;  -- expect rows matching that tenant + NULL rows
--   COMMIT;
--
--   --   * admit everything when admin GUC is set, regardless of tenant:
--   BEGIN;
--     SELECT set_config('app.current_tenant',
--       'ffffffff-ffff-ffff-ffff-ffffffffffff', true);
--     SELECT set_config('app.current_role', 'admin', true);
--     SELECT COUNT(*) FROM projects;  -- expect actual count (admin escape)
--   COMMIT;
-- =====================================================================

-- =====================================================================
-- ROLLBACK SKETCH (ship as 021 if cutover regresses)
-- ---------------------------------------------------------------------
-- DO $$
-- DECLARE rec RECORD; pol_name TEXT;
--     globals TEXT[] := ARRAY[
--         'installers','news_posts','helpline_learned_kb',
--         'product_brands','product_categories','appliances',
--         'assessment_requests','leads','beta_signups','newsletter_subscribers',
--         'monitor_alerts','monitor_state','upgrade_codes',
--         'admin_settings','login_failures'];
-- BEGIN
--     FOR rec IN
--         SELECT DISTINCT tablename FROM pg_policies
--          WHERE schemaname='public' AND policyname LIKE '%_tenant_isolation'
--            AND tablename != ALL(globals)
--     LOOP
--         pol_name := rec.tablename || '_tenant_isolation';
--         EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', rec.tablename);
--         EXECUTE format('DROP POLICY IF EXISTS %I ON %I', pol_name, rec.tablename);
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
--             $pol$, pol_name, rec.tablename);
--     END LOOP;
-- END;
-- $$;
-- =====================================================================
