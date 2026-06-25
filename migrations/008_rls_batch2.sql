-- 008_rls_batch2.sql
-- =====================================================================
-- SOC 2 M1.6 batch 2 -- RLS for 6 more tenant-owned tables.
--
-- Closes the next slice of cross-tenant exposure flagged by the
-- 2026-06-25 tenant inventory. Tables:
--
--   marketplace_bom_rates            (per-BOM rate buildup)
--   marketplace_price_sheet_items    (price-sheet line items)
--   equipment_catalog_quotes         (vendor quotes against catalog items)
--   equipment_catalog_price_history  (price update history)
--   marketplace_audit_log            (marketplace admin action audit)
--   boq_user_item_overrides          (per-user BOQ rate overrides)
--
-- Mirrors 003 / 007 structure exactly:
--   PART 1 -- Reuses current_tenant_id() + _phase4_user_to_tenant() from 003.
--   PART 2 -- ADD COLUMN tenant_id UUID (nullable) on the 6 tables.
--   PART 3 -- Deterministic backfill -- via parent (BOM, price sheet)
--             or direct user_id column.
--   PART 4 -- ENABLE ROW LEVEL SECURITY + parallel-run policy per table.
--
-- Parallel-run safety: the policy is intentionally permissive when the
-- GUC is unset OR when the row's tenant_id is NULL. The Phase 7 cutover
-- (separate migration, post Phase B) tightens to FORCE ROW LEVEL SECURITY
-- + drops both NULL escapes.
--
-- Idempotent: every statement uses IF NOT EXISTS / IF EXISTS, so the file
-- can be applied twice without error.
--
-- KNOWN GAP: the parent tables marketplace_boms + marketplace_price_sheets
-- are NOT in this batch (per the saved batch-2 list). They remain
-- RLS-open until a follow-up batch picks them up. The children below are
-- still safely scoped because their tenant_id is computed from each
-- parent's user_id at backfill time, then enforced by their own policy.
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
-- PART 2 -- tenant_id UUID column on each batch-2 table.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    batch2_tables TEXT[] := ARRAY[
        'marketplace_bom_rates',
        'marketplace_price_sheet_items',
        'equipment_catalog_quotes',
        'equipment_catalog_price_history',
        'marketplace_audit_log',
        'boq_user_item_overrides'
    ];
BEGIN
    FOREACH t IN ARRAY batch2_tables LOOP
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
-- PART 3 -- Backfill.
--
-- Backfill source per table:
--   marketplace_bom_rates           <- parent marketplace_boms.user_id
--   marketplace_price_sheet_items   <- parent marketplace_price_sheets.user_id
--   equipment_catalog_quotes        <- recorded_by    (user_id, 0 means unknown)
--   equipment_catalog_price_history <- set_by_user_id (user_id, 0 means unknown)
--   marketplace_audit_log           <- user_id        (actor's tenant)
--   boq_user_item_overrides         <- user_id        (NOT NULL, owner)
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. marketplace_bom_rates -- from parent BOM
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_bom_rates' AND column_name='bom_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_boms' AND column_name='user_id') THEN
        UPDATE marketplace_bom_rates r
           SET tenant_id = _phase4_user_to_tenant(b.user_id)
          FROM marketplace_boms b
         WHERE r.bom_id = b.id
           AND r.tenant_id IS NULL
           AND b.user_id IS NOT NULL;
    END IF;

    -- 2. marketplace_price_sheet_items -- from parent price sheet
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_price_sheet_items' AND column_name='sheet_id')
       AND EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_price_sheets' AND column_name='user_id') THEN
        UPDATE marketplace_price_sheet_items i
           SET tenant_id = _phase4_user_to_tenant(s.user_id)
          FROM marketplace_price_sheets s
         WHERE i.sheet_id = s.id
           AND i.tenant_id IS NULL
           AND s.user_id IS NOT NULL;
    END IF;

    -- 3. equipment_catalog_quotes -- from recorded_by user (0 means unknown)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='equipment_catalog_quotes' AND column_name='recorded_by') THEN
        UPDATE equipment_catalog_quotes
           SET tenant_id = _phase4_user_to_tenant(recorded_by)
         WHERE tenant_id IS NULL
           AND recorded_by IS NOT NULL
           AND recorded_by > 0;
    END IF;

    -- 4. equipment_catalog_price_history -- from set_by_user_id (0 means unknown)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='equipment_catalog_price_history' AND column_name='set_by_user_id') THEN
        UPDATE equipment_catalog_price_history
           SET tenant_id = _phase4_user_to_tenant(set_by_user_id)
         WHERE tenant_id IS NULL
           AND set_by_user_id IS NOT NULL
           AND set_by_user_id > 0;
    END IF;

    -- 5. marketplace_audit_log -- from actor user_id (matches 003 / 007
    --    convention: audit rows carry the actor's tenant).
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='marketplace_audit_log' AND column_name='user_id') THEN
        UPDATE marketplace_audit_log
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 6. boq_user_item_overrides -- from owning user_id (NOT NULL by schema)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='boq_user_item_overrides' AND column_name='user_id') THEN
        UPDATE boq_user_item_overrides
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour, identical pattern to 003 / 007).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    batch2_tables TEXT[] := ARRAY[
        'marketplace_bom_rates',
        'marketplace_price_sheet_items',
        'equipment_catalog_quotes',
        'equipment_catalog_price_history',
        'marketplace_audit_log',
        'boq_user_item_overrides'
    ];
BEGIN
    FOREACH t IN ARRAY batch2_tables LOOP
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
-- All 6 must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id'
--      AND table_schema='public'
--      AND table_name IN (
--        'marketplace_bom_rates','marketplace_price_sheet_items',
--        'equipment_catalog_quotes','equipment_catalog_price_history',
--        'marketplace_audit_log','boq_user_item_overrides');
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname IN (
--        'marketplace_bom_rates_tenant_isolation',
--        'marketplace_price_sheet_items_tenant_isolation',
--        'equipment_catalog_quotes_tenant_isolation',
--        'equipment_catalog_price_history_tenant_isolation',
--        'marketplace_audit_log_tenant_isolation',
--        'boq_user_item_overrides_tenant_isolation');
--
-- Coverage check (zero unbackfilled expected on rows with a non-NULL parent
-- or non-zero user_id):
--
--   SELECT
--     (SELECT COUNT(*) FROM marketplace_bom_rates WHERE tenant_id IS NULL)
--       AS unbackfilled_bom_rates,
--     (SELECT COUNT(*) FROM marketplace_price_sheet_items WHERE tenant_id IS NULL)
--       AS unbackfilled_sheet_items,
--     (SELECT COUNT(*) FROM equipment_catalog_quotes WHERE tenant_id IS NULL)
--       AS unbackfilled_quotes,
--     (SELECT COUNT(*) FROM equipment_catalog_price_history WHERE tenant_id IS NULL)
--       AS unbackfilled_price_history,
--     (SELECT COUNT(*) FROM marketplace_audit_log WHERE tenant_id IS NULL)
--       AS unbackfilled_audit_log,
--     (SELECT COUNT(*) FROM boq_user_item_overrides WHERE tenant_id IS NULL)
--       AS unbackfilled_overrides;
-- =====================================================================
