-- 010_rls_batch3b.sql
-- =====================================================================
-- SOC 2 M1.6 batch 3b -- close the parent gap from batch 2.
--
-- Migration 008 RLS-enforced the children (marketplace_bom_rates +
-- marketplace_price_sheet_items) but explicitly left their parents
-- open. This migration closes that hole:
--
--   marketplace_boms          (parent of marketplace_bom_rates)
--   marketplace_price_sheets  (parent of marketplace_price_sheet_items)
--
-- Both have user_id INTEGER NOT NULL by schema (verified during the
-- batch-2 prep grep), so the backfill is a direct
-- _phase4_user_to_tenant(user_id) call.
--
-- Mirrors 003 / 007 / 008 / 009 structure exactly:
--   PART 1 -- Reuses current_tenant_id() + _phase4_user_to_tenant() from 003.
--   PART 2 -- ADD COLUMN tenant_id UUID (nullable) on both tables.
--   PART 3 -- Deterministic backfill from user_id.
--   PART 4 -- ENABLE ROW LEVEL SECURITY + parallel-run policy per table.
--
-- Parallel-run safety: policy permissive on NULL GUC or NULL tenant_id.
--
-- Idempotent: every statement uses IF NOT EXISTS / IF EXISTS.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Reuse helpers from 003. Re-CREATE OR REPLACE so this migration
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
-- PART 2 -- tenant_id UUID column on each batch-3b table.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    batch3b_tables TEXT[] := ARRAY[
        'marketplace_boms',
        'marketplace_price_sheets'
    ];
BEGIN
    FOREACH t IN ARRAY batch3b_tables LOOP
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
-- PART 3 -- Backfill from user_id (NOT NULL by schema on both tables).
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. marketplace_boms -- from owning user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_boms' AND column_name='user_id') THEN
        UPDATE marketplace_boms
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 2. marketplace_price_sheets -- from owning user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_price_sheets' AND column_name='user_id') THEN
        UPDATE marketplace_price_sheets
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour, identical pattern).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    batch3b_tables TEXT[] := ARRAY[
        'marketplace_boms',
        'marketplace_price_sheets'
    ];
BEGIN
    FOREACH t IN ARRAY batch3b_tables LOOP
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
-- Both must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id'
--      AND table_schema='public'
--      AND table_name IN ('marketplace_boms','marketplace_price_sheets');
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname IN (
--      'marketplace_boms_tenant_isolation',
--      'marketplace_price_sheets_tenant_isolation');
--
-- Coverage (zero unbackfilled expected -- user_id is NOT NULL):
--
--   SELECT
--     (SELECT COUNT(*) FROM marketplace_boms         WHERE tenant_id IS NULL) AS unbackfilled_boms,
--     (SELECT COUNT(*) FROM marketplace_price_sheets WHERE tenant_id IS NULL) AS unbackfilled_sheets;
-- =====================================================================
