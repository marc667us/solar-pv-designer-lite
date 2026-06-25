-- 009_rls_batch3.sql
-- =====================================================================
-- SOC 2 M1.6 batch 3 -- RLS for the RFQ family (5 tables).
--
-- Extends migrations 003 / 007 / 008 to the RFQ workflow tables:
--
--   rfqs                  (root; buyer = creator)
--   rfq_items             (line items, parent rfqs)
--   rfq_supplier_targets  (junction: rfq <-> supplier; buyer-tagged)
--   rfq_responses         (supplier replies; buyer-tagged for now)
--   rfq_response_items    (per-line response items, 2-hop chain)
--
-- Mirrors 003 / 007 / 008 structure exactly:
--   PART 1 -- Reuses current_tenant_id() + _phase4_user_to_tenant() from 003.
--   PART 2 -- ADD COLUMN tenant_id UUID (nullable) on all 5 RFQ tables.
--   PART 3 -- Deterministic backfill ordered root -> children -> grandchild.
--   PART 4 -- ENABLE ROW LEVEL SECURITY + parallel-run policy per table.
--
-- TENANT CONVENTION: all 5 tables carry the BUYER's tenant_id (derived
-- from rfqs.user_id). That matches the "RFQ belongs to the buyer" data-
-- ownership model. Suppliers see rfq_supplier_targets / rfq_responses /
-- rfq_response_items rows targeted at them via the parallel-run NULL
-- escape (NULL OR buyer-tenant-match OR GUC-unset). The strict policy
-- in Phase 7 will need to also admit rows where
-- supplier_id = current_supplier_id() -- defer until then.
--
-- Parallel-run safety: the policy is intentionally permissive when the
-- GUC is unset OR when the row's tenant_id is NULL.
--
-- Idempotent: every statement uses IF NOT EXISTS / IF EXISTS, so the file
-- can be applied twice without error.
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
-- PART 2 -- tenant_id UUID column on each RFQ table.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    rfq_tables TEXT[] := ARRAY[
        'rfqs',
        'rfq_items',
        'rfq_supplier_targets',
        'rfq_responses',
        'rfq_response_items'
    ];
BEGIN
    FOREACH t IN ARRAY rfq_tables LOOP
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
-- PART 3 -- Backfill, ordered root -> children -> grandchild.
--
--   rfqs                 <- user_id        (NOT NULL by schema)
--   rfq_items            <- parent rfq
--   rfq_supplier_targets <- parent rfq
--   rfq_responses        <- parent rfq     (buyer-tagged; see header)
--   rfq_response_items   <- parent response -> grandparent rfq (2-hop)
-- ---------------------------------------------------------------------

DO $$
BEGIN
    -- 1. rfqs (root) -- from user_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='rfqs' AND column_name='user_id') THEN
        UPDATE rfqs
           SET tenant_id = _phase4_user_to_tenant(user_id)
         WHERE tenant_id IS NULL AND user_id IS NOT NULL;
    END IF;

    -- 2. rfq_items -- from parent rfq
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='rfq_items' AND column_name='rfq_id') THEN
        UPDATE rfq_items i
           SET tenant_id = r.tenant_id
          FROM rfqs r
         WHERE i.rfq_id = r.id
           AND i.tenant_id IS NULL
           AND r.tenant_id IS NOT NULL;
    END IF;

    -- 3. rfq_supplier_targets -- from parent rfq
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='rfq_supplier_targets' AND column_name='rfq_id') THEN
        UPDATE rfq_supplier_targets t
           SET tenant_id = r.tenant_id
          FROM rfqs r
         WHERE t.rfq_id = r.id
           AND t.tenant_id IS NULL
           AND r.tenant_id IS NOT NULL;
    END IF;

    -- 4. rfq_responses -- from parent rfq (buyer-tagged, see header)
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='rfq_responses' AND column_name='rfq_id') THEN
        UPDATE rfq_responses resp
           SET tenant_id = r.tenant_id
          FROM rfqs r
         WHERE resp.rfq_id = r.id
           AND resp.tenant_id IS NULL
           AND r.tenant_id IS NOT NULL;
    END IF;

    -- 5. rfq_response_items -- 2-hop chain via rfq_responses -> rfqs
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='rfq_response_items' AND column_name='response_id') THEN
        UPDATE rfq_response_items ri
           SET tenant_id = resp.tenant_id
          FROM rfq_responses resp
         WHERE ri.response_id = resp.id
           AND ri.tenant_id IS NULL
           AND resp.tenant_id IS NOT NULL;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- RLS policies (parallel-run flavour, identical pattern to 003 / 007 / 008).
-- ---------------------------------------------------------------------

DO $$
DECLARE
    t TEXT;
    pol_name TEXT;
    rfq_tables TEXT[] := ARRAY[
        'rfqs',
        'rfq_items',
        'rfq_supplier_targets',
        'rfq_responses',
        'rfq_response_items'
    ];
BEGIN
    FOREACH t IN ARRAY rfq_tables LOOP
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
-- All 5 must return a row:
--
--   SELECT table_name FROM information_schema.columns
--    WHERE column_name='tenant_id'
--      AND table_schema='public'
--      AND table_name IN (
--        'rfqs','rfq_items','rfq_supplier_targets',
--        'rfq_responses','rfq_response_items');
--
--   SELECT tablename, policyname FROM pg_policies
--    WHERE policyname IN (
--      'rfqs_tenant_isolation','rfq_items_tenant_isolation',
--      'rfq_supplier_targets_tenant_isolation',
--      'rfq_responses_tenant_isolation',
--      'rfq_response_items_tenant_isolation');
--
-- Coverage (zero unbackfilled expected on rows with a non-NULL parent):
--
--   SELECT
--     (SELECT COUNT(*) FROM rfqs                 WHERE tenant_id IS NULL) AS unbackfilled_rfqs,
--     (SELECT COUNT(*) FROM rfq_items            WHERE tenant_id IS NULL) AS unbackfilled_items,
--     (SELECT COUNT(*) FROM rfq_supplier_targets WHERE tenant_id IS NULL) AS unbackfilled_targets,
--     (SELECT COUNT(*) FROM rfq_responses        WHERE tenant_id IS NULL) AS unbackfilled_responses,
--     (SELECT COUNT(*) FROM rfq_response_items   WHERE tenant_id IS NULL) AS unbackfilled_response_items;
-- =====================================================================
