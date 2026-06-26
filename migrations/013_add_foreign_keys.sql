-- 013_add_foreign_keys.sql
-- =====================================================================
-- SOC 2 -- explicit FOREIGN KEY constraints across user-owned and
-- parent-child chains touched by migrations 007-012.
--
-- Industry-practice rationale: today most of these tables declare e.g.
-- `bom_id INTEGER NOT NULL` without a FK constraint, relying on app-
-- level enforcement that has demonstrably leaked. The 2026-06-25 batch
-- 2 + 3 RLS work surfaced 3 orphan marketplace_price_sheet_items and 4
-- orphan rfq_items (parent rows already deleted). FK constraints close
-- that gap and turn future orphans into immediate INSERT/DELETE errors.
--
-- Trust Services Criteria covered:
--   CC6.7 -- "Logical access to data restricted via policies"
--   CC7.2 -- "System monitoring detects security events" (FK violations
--            now surface as PG errors instead of silent orphans)
--
-- Production safety:
--   * Every ALTER ... ADD CONSTRAINT uses NOT VALID -- skips the full-
--     table scan so prod gets a brief AccessExclusive lock only for
--     constraint-definition write, not a multi-second hold.
--   * Idempotent via DROP CONSTRAINT IF EXISTS before ADD.
--   * Orphan cleanup is DELETE WHERE NOT IN parent -- idempotent.
--   * VALIDATE CONSTRAINT deferred to a future migration once monitoring
--     confirms no new orphans accumulate (see deferred work at footer).
--
-- ON DELETE semantics (industry practice):
--   * Owned children (feature-internal parent/child): ON DELETE CASCADE
--     -- deleting a parent BOM/RFQ cleanly removes its rates/items.
--   * User-owned data: NO ACTION (default = RESTRICT semantics) --
--     blocks user-row deletion if they still own data. Forces the app
--     to handle deactivation / soft-delete / anonymization explicitly.
--   * Nullable user FK (beta_feedback): ON DELETE SET NULL -- preserves
--     the feedback as anonymous after user deletion.
--   * Audit logs: NO ACTION -- preserve audit trail forever.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- Clean known orphans before adding constraints.
--          NOT VALID skips checking existing rows, but data-quality
--          hygiene says clean what we can identify.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    orphaned INTEGER;
BEGIN
    -- 3 orphan marketplace_price_sheet_items (batch 2 discovery)
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='marketplace_price_sheet_items' AND table_schema='public') THEN
        DELETE FROM marketplace_price_sheet_items
         WHERE sheet_id IS NOT NULL
           AND sheet_id NOT IN (SELECT id FROM marketplace_price_sheets);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        RAISE NOTICE 'Cleaned % orphan marketplace_price_sheet_items', orphaned;
    END IF;

    -- 4 orphan rfq_items (batch 3 discovery)
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='rfq_items' AND table_schema='public') THEN
        DELETE FROM rfq_items
         WHERE rfq_id IS NOT NULL
           AND rfq_id NOT IN (SELECT id FROM rfqs);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        RAISE NOTICE 'Cleaned % orphan rfq_items', orphaned;
    END IF;

    -- Sweep any other unknown orphans on the child sides we're about
    -- to FK. Idempotent; safe if zero rows.
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='rfq_supplier_targets' AND table_schema='public') THEN
        DELETE FROM rfq_supplier_targets WHERE rfq_id NOT IN (SELECT id FROM rfqs);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan rfq_supplier_targets', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='rfq_responses' AND table_schema='public') THEN
        DELETE FROM rfq_responses WHERE rfq_id NOT IN (SELECT id FROM rfqs);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan rfq_responses', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='rfq_response_items' AND table_schema='public') THEN
        DELETE FROM rfq_response_items WHERE response_id NOT IN (SELECT id FROM rfq_responses);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan rfq_response_items', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='marketplace_bom_rates' AND table_schema='public') THEN
        DELETE FROM marketplace_bom_rates WHERE bom_id NOT IN (SELECT id FROM marketplace_boms);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan marketplace_bom_rates', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='boq_buildings' AND table_schema='public') THEN
        DELETE FROM boq_buildings WHERE project_id NOT IN (SELECT id FROM boq_projects);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan boq_buildings', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='boq_floors' AND table_schema='public') THEN
        DELETE FROM boq_floors WHERE project_id NOT IN (SELECT id FROM boq_projects);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan boq_floors', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='boq_floor_items' AND table_schema='public') THEN
        DELETE FROM boq_floor_items WHERE project_id NOT IN (SELECT id FROM boq_projects);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan boq_floor_items', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='boq_floor_rate_buildup' AND table_schema='public') THEN
        DELETE FROM boq_floor_rate_buildup WHERE project_id NOT IN (SELECT id FROM boq_projects);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan boq_floor_rate_buildup', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='equipment_catalog_quotes' AND table_schema='public') THEN
        DELETE FROM equipment_catalog_quotes WHERE catalog_item_id NOT IN (SELECT id FROM equipment_catalog);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan equipment_catalog_quotes', orphaned; END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_name='equipment_catalog_price_history' AND table_schema='public') THEN
        DELETE FROM equipment_catalog_price_history WHERE catalog_item_id NOT IN (SELECT id FROM equipment_catalog);
        GET DIAGNOSTICS orphaned = ROW_COUNT;
        IF orphaned > 0 THEN RAISE NOTICE 'Cleaned % orphan equipment_catalog_price_history', orphaned; END IF;
    END IF;
END;
$$;


-- ---------------------------------------------------------------------
-- PART 2 -- Add FOREIGN KEY constraints with NOT VALID (skips full-
--          table scan on prod; future inserts checked, existing rows
--          deferred until VALIDATE CONSTRAINT in a follow-up).
--
-- Each ADD is idempotent: DROP IF EXISTS then ADD with the same name.
-- ---------------------------------------------------------------------

DO $$
DECLARE
    fks CONSTANT TEXT[][] := ARRAY[
        -- {child, child_col, parent, parent_col, on_delete}
        --
        -- ===== Owned children (CASCADE) =====
        ARRAY['marketplace_bom_rates',           'bom_id',          'marketplace_boms',         'id', 'CASCADE'],
        ARRAY['marketplace_price_sheet_items',   'sheet_id',        'marketplace_price_sheets', 'id', 'CASCADE'],
        ARRAY['equipment_catalog_quotes',        'catalog_item_id', 'equipment_catalog',        'id', 'CASCADE'],
        ARRAY['equipment_catalog_price_history', 'catalog_item_id', 'equipment_catalog',        'id', 'CASCADE'],
        ARRAY['boq_buildings',                   'project_id',      'boq_projects',             'id', 'CASCADE'],
        ARRAY['boq_floors',                      'project_id',      'boq_projects',             'id', 'CASCADE'],
        ARRAY['boq_floor_items',                 'project_id',      'boq_projects',             'id', 'CASCADE'],
        ARRAY['boq_floor_rate_buildup',          'project_id',      'boq_projects',             'id', 'CASCADE'],
        ARRAY['rfq_items',                       'rfq_id',          'rfqs',                     'id', 'CASCADE'],
        ARRAY['rfq_supplier_targets',            'rfq_id',          'rfqs',                     'id', 'CASCADE'],
        ARRAY['rfq_responses',                   'rfq_id',          'rfqs',                     'id', 'CASCADE'],
        ARRAY['rfq_response_items',              'response_id',     'rfq_responses',            'id', 'CASCADE'],
        --
        -- ===== User-owned (NO ACTION = restrict) =====
        ARRAY['marketplace_boms',                'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['marketplace_price_sheets',        'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['boq_projects',                    'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['boq_user_item_overrides',         'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['boq_audit_log',                   'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['marketplace_audit_log',           'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['rfqs',                            'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['ticket_replies',                  'user_id',         'users',                    'id', 'NO ACTION'],
        ARRAY['email_logs',                      'user_id',         'users',                    'id', 'NO ACTION'],
        --
        -- ===== Nullable user FK (SET NULL on user delete) =====
        ARRAY['beta_feedback',                   'user_id',         'users',                    'id', 'SET NULL']
    ];
    fk_row TEXT[];
    constraint_name TEXT;
BEGIN
    FOREACH fk_row SLICE 1 IN ARRAY fks LOOP
        -- fk_row = [child, child_col, parent, parent_col, on_delete]
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = fk_row[1] AND table_schema = 'public'
        ) AND EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = fk_row[3] AND table_schema = 'public'
        ) AND EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = fk_row[1] AND column_name = fk_row[2] AND table_schema = 'public'
        ) THEN
            constraint_name := 'fk_' || fk_row[1] || '_' || fk_row[2];

            -- Idempotent: drop then add. NOT VALID skips full-table
            -- scan; just records the constraint definition.
            EXECUTE format(
                'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I',
                fk_row[1], constraint_name
            );
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I(%I) ON DELETE %s NOT VALID',
                fk_row[1], constraint_name,
                fk_row[2], fk_row[3], fk_row[4],
                fk_row[5]
            );
            RAISE NOTICE 'Added FK % on %.% -> %.% ON DELETE %',
                constraint_name, fk_row[1], fk_row[2], fk_row[3], fk_row[4], fk_row[5];
        ELSE
            RAISE NOTICE 'Skipped FK on %.% -> %.% (table or column missing)',
                fk_row[1], fk_row[2], fk_row[3], fk_row[4];
        END IF;
    END LOOP;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
-- Expect ~22 FK constraints (depending on which tables exist on live PG):
--
--   SELECT conrelid::regclass AS child, conname, confdeltype
--     FROM pg_constraint
--    WHERE conname LIKE 'fk_%'
--      AND contype = 'f'
--    ORDER BY conrelid::regclass, conname;
--
-- Validate freshness (these will all be NOT VALID until follow-up):
--
--   SELECT conrelid::regclass AS child, conname, convalidated
--     FROM pg_constraint
--    WHERE conname LIKE 'fk_%'
--      AND contype = 'f'
--      AND NOT convalidated;
--
-- DEFERRED WORK (separate migration once data quality monitored):
--
--   ALTER TABLE <child> VALIDATE CONSTRAINT fk_<child>_<col>;
--
-- This scans the whole child table to confirm zero violations. Each
-- VALIDATE is independently rollback-able. Run during low-traffic
-- window after 7-14 days of monitoring confirms no new orphans.
--
-- A real `tenants(id UUID PK)` table that all tenant_id columns FK to
-- is also industry standard but defer to Phase 7 -- requires migrating
-- the tenant_id values from md5() hashes to real UUIDs first.
-- =====================================================================
