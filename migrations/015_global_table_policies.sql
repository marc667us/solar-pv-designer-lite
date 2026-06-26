-- 015_global_table_policies.sql
-- =====================================================================
-- SOC 2 Phase-7-prep -- global-table allow-list policies for the 15
-- tenant-agnostic tables surfaced by batches 4 + 5.
--
-- Problem: 15 tables intentionally hold `tenant_id IS NULL` rows (they
-- carry platform-global data like product_brands, monitor_alerts, etc.).
-- The current parallel-run policy admits NULL tenant_id, which works
-- today but evaporates the moment Phase 7 cuts the NULL escape -- at
-- that point every row on these 15 tables becomes invisible to every
-- tenant.
--
-- This migration ships a per-intent strict policy ALONGSIDE each
-- existing parallel-run policy. PG combines permissive policies with
-- OR, so today the parallel-run policy still admits everything (no
-- behaviour change). Phase 7 cutover then just DROPs the parallel-run
-- policies and the strict ones take over.
--
-- Three intents, classified by inspection of how each table is read +
-- written today:
--
--   PUBLIC READ + ADMIN WRITE   (6 tables) -- anyone can SELECT;
--                                only an admin role can INSERT/UPDATE/DELETE.
--     installers, news_posts, helpline_learned_kb,
--     product_brands, product_categories, appliances
--
--   ADMIN READ + ANON INSERT    (4 tables) -- only admin can SELECT;
--                                anyone can INSERT (webform paths);
--                                only admin can UPDATE/DELETE.
--     assessment_requests, leads, beta_signups, newsletter_subscribers
--
--   ADMIN ONLY                  (5 tables) -- admin for everything.
--     monitor_alerts, monitor_state, upgrade_codes,
--     admin_settings, login_failures
--
-- App-side companion: `app/security/tenant_context.py::apply_tenant_guc`
-- must also write `app.current_role` so `current_user_is_admin()` can
-- evaluate it. That patch ships with this migration but lives in a
-- separate commit.
--
-- Idempotent: CREATE OR REPLACE for the helper; DROP POLICY IF EXISTS
-- + CREATE POLICY for each policy.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- current_user_is_admin() helper.
--
-- Reads the `app.current_role` GUC (set by apply_tenant_guc on every
-- request). Empty/unset returns FALSE. Considered "admin" iff value is
-- exactly 'admin' -- the Python side maps any of
-- {platform_super_admin, marketplace_admin, tenant_admin} to 'admin'
-- so this SQL stays stable when the role taxonomy evolves.
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
-- PART 2 -- PUBLIC READ + ADMIN WRITE policies (6 tables).
--
-- One "public_read" policy admits any SELECT.
-- One "admin_write" policy admits INSERT/UPDATE/DELETE when admin.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    public_read_tables TEXT[] := ARRAY[
        'installers',
        'news_posts',
        'helpline_learned_kb',
        'product_brands',
        'product_categories',
        'appliances'
    ];
BEGIN
    FOREACH t IN ARRAY public_read_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            -- Strict SELECT policy: everyone can read.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_public_read', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR SELECT
                    USING (true)
                $pol$, t || '_global_public_read', t);

            -- Strict INSERT policy: only admins can insert.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_insert', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR INSERT
                    WITH CHECK (current_user_is_admin())
                $pol$, t || '_global_admin_insert', t);

            -- Strict UPDATE policy: only admins can update.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_update', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR UPDATE
                    USING (current_user_is_admin())
                    WITH CHECK (current_user_is_admin())
                $pol$, t || '_global_admin_update', t);

            -- Strict DELETE policy: only admins can delete.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_delete', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR DELETE
                    USING (current_user_is_admin())
                $pol$, t || '_global_admin_delete', t);
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 3 -- ADMIN READ + ANON INSERT policies (4 tables).
--
-- Webform paths POST anonymous data (assessment_requests, leads,
-- beta_signups, newsletter_subscribers). Anonymous INSERT must be
-- admitted; everything else is admin-gated.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    anon_insert_tables TEXT[] := ARRAY[
        'assessment_requests',
        'leads',
        'beta_signups',
        'newsletter_subscribers'
    ];
BEGIN
    FOREACH t IN ARRAY anon_insert_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            -- Admin-only SELECT.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_select', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR SELECT
                    USING (current_user_is_admin())
                $pol$, t || '_global_admin_select', t);

            -- Anonymous INSERT (webform path).
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_anon_insert', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR INSERT
                    WITH CHECK (true)
                $pol$, t || '_global_anon_insert', t);

            -- Admin UPDATE.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_update', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR UPDATE
                    USING (current_user_is_admin())
                    WITH CHECK (current_user_is_admin())
                $pol$, t || '_global_admin_update', t);

            -- Admin DELETE.
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_delete', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR DELETE
                    USING (current_user_is_admin())
                $pol$, t || '_global_admin_delete', t);
        END IF;
    END LOOP;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- ADMIN ONLY policies (5 tables).
--
-- Platform observability + admin settings. No anonymous access at all.
-- login_failures: written by the auth path (system-side) -- the
-- bootstrap session runs as superuser (RLS bypassed) so anonymous
-- write is not needed via the policy layer.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    admin_only_tables TEXT[] := ARRAY[
        'monitor_alerts',
        'monitor_state',
        'upgrade_codes',
        'admin_settings',
        'login_failures'
    ];
BEGIN
    FOREACH t IN ARRAY admin_only_tables LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I',
                t || '_global_admin_all', t);
            EXECUTE format($pol$
                CREATE POLICY %I ON %I
                    FOR ALL
                    USING (current_user_is_admin())
                    WITH CHECK (current_user_is_admin())
                $pol$, t || '_global_admin_all', t);
        END IF;
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--
-- Helper present:
--   SELECT proname FROM pg_proc WHERE proname='current_user_is_admin';
--
-- Per-table policy counts (parallel-run is still there, plus new ones):
--
--   SELECT tablename, COUNT(*) AS policy_count
--     FROM pg_policies
--    WHERE tablename IN (
--      'installers','news_posts','helpline_learned_kb',
--      'product_brands','product_categories','appliances',
--      'assessment_requests','leads','beta_signups','newsletter_subscribers',
--      'monitor_alerts','monitor_state','upgrade_codes',
--      'admin_settings','login_failures')
--    GROUP BY tablename ORDER BY tablename;
--
--   Expected:
--     6 public_read tables:  1 (parallel) + 4 (public_read + admin_ins/upd/del) = 5
--     4 anon_insert tables:  1 (parallel) + 4 (admin_sel + anon_ins + admin_upd/del) = 5
--     5 admin_only tables:   1 (parallel) + 1 (admin_all) = 2
--
-- Behaviour smoke (parallel-run still wins, no breaking change today):
--
--   -- Without any GUC set, parallel-run admits reads.
--   SELECT COUNT(*) FROM product_brands;            -- works as before
--
--   -- With strict-mode app.current_tenant set + app.current_role='user':
--   SELECT set_config('app.current_tenant',
--      '11111111-1111-1111-1111-111111111111', true);
--   SELECT set_config('app.current_role', 'user', true);
--   SELECT COUNT(*) FROM product_brands;            -- 0 if parallel-run dropped
--   -- (today: still nonzero because parallel-run policy admits NULL tenant_id)
-- =====================================================================
