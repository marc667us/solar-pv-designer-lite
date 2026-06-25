-- 012_rls_batch5.sql
-- =====================================================================
-- SOC 2 M1.6 batch 5 -- RLS for 12 more tables (mostly global).
--
-- Owner directive (2026-06-25, batch 4): total table coverage takes
-- priority over conceptual purity. Most batch-5 tables are platform /
-- catalog / system-wide data; they get the column + RLS but tenant_id
-- stays NULL on every row (parallel-run NULL escape keeps them readable).
--
-- 2 user-owned tables (standard backfill):
--   referrals       <- referrer_id (the user earning the reward owns the row)
--   beta_feedback   <- user_id when present; rows from anonymous
--                      submitters keep tenant_id NULL
--
-- 10 global / tenant-agnostic tables (column added + RLS enabled; tenant_id
-- stays NULL on every row):
--   beta_signups            beta program signups (email-only, admin-managed)
--   monitor_alerts          RSS-crawler output (system-wide)
--   monitor_state           system-state singleton (id=1 CHECK constraint)
--   newsletter_subscribers  public mailing list
--   upgrade_codes           admin-created promo codes (no per-user scope)
--   login_failures          security log (indexed by username string, not FK)
--   product_brands          shared product catalog
--   product_categories      shared product taxonomy
--   admin_settings          system k/v settings
--   appliances              shared appliance catalog
--
-- PHASE 7 FOLLOW-UP REQUIRED for the 10 global tables. Same options as
-- migration 011's header (GLOBAL_TENANT_UUID sentinel / separate global
-- policy / admin-bypass GUC). Phase 7 cutover must NOT remove the NULL
-- escape on these tables until the alternative policy is in place.
--
-- Mirrors 003 / 007 / 008 / 009 / 010 / 011 structure. Idempotent.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Reuse helpers from 003.
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
-- PART 2 -- tenant_id UUID column on all 12 batch-5 tables.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    batch5_tables TEXT[] := ARRAY[
        'referrals',
        'beta_feedback',
        'beta_signups',
        'monitor_alerts',
        'monitor_state',
        'newsletter_subscribers',
        'upgrade_codes',
        'login_failures',
        'product_brands',
        'product_categories',
        'admin_settings',
        'appliances'
    ];
BEGIN
    FOREACH t IN ARRAY batch5_tables LOOP
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
-- PART 3 -- Backfill the 2 user-owned tables. The 10 global tables
--          intentionally keep tenant_id IS NULL.
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. referrals -- tagged with referrer_id's tenant.
    --    Conceptually the referee also relates to this row, but the
    --    REFERRER owns the data: they earn the reward, the row tracks
    --    THEIR success. Future cross-tenant referrals (rare today) will
    --    need a Phase 7 extension that admits the referee's tenant too.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='referrals' AND column_name='referrer_id') THEN
        UPDATE referrals
           SET tenant_id = _phase4_user_to_tenant(referrer_id)
         WHERE tenant_id IS NULL AND referrer_id IS NOT NULL;
    END IF;

    -- 2. beta_feedback -- partial backfill where user_id present.
    --    Rows from anonymous submitters (user_id IS NULL) stay NULL
    --    by design. Parallel-run policy keeps them visible to admin.
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='beta_feedback' AND column_name='user_id') THEN
        UPDATE beta_feedback
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 3-12. beta_signups, monitor_alerts, monitor_state,
    --       newsletter_subscribers, upgrade_codes, login_failures,
    --       product_brands, product_categories, admin_settings,
    --       appliances -- intentionally NOT backfilled. tenant_id
    --       stays NULL; parallel-run policy permits reads.
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour, identical pattern).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    batch5_tables TEXT[] := ARRAY[
        'referrals',
        'beta_feedback',
        'beta_signups',
        'monitor_alerts',
        'monitor_state',
        'newsletter_subscribers',
        'upgrade_codes',
        'login_failures',
        'product_brands',
        'product_categories',
        'admin_settings',
        'appliances'
    ];
BEGIN
    FOREACH t IN ARRAY batch5_tables LOOP
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
-- All present tables must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id' AND table_schema='public'
--      AND table_name IN (
--        'referrals','beta_feedback','beta_signups',
--        'monitor_alerts','monitor_state','newsletter_subscribers',
--        'upgrade_codes','login_failures',
--        'product_brands','product_categories',
--        'admin_settings','appliances');
--
-- Coverage:
--   user-owned (expect zero on referrals; beta_feedback may have NULLs
--     from anonymous submitters):
--     SELECT COUNT(*) FROM referrals WHERE tenant_id IS NULL;
--     SELECT COUNT(*) FROM beta_feedback WHERE tenant_id IS NULL AND user_id IS NOT NULL;
--   global (expect row count == row count -- NULL by design):
--     SELECT COUNT(*) FROM <table> WHERE tenant_id IS NULL;
-- =====================================================================
