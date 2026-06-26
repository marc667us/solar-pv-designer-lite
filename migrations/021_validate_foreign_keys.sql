-- 021_validate_foreign_keys.sql
-- =====================================================================
-- SOC 2 follow-up to migration 013 -- VALIDATE every NOT VALID FK
-- constraint added in 013, after the 7-day clean monitoring window
-- documented in the session memory (earliest 2026-07-03).
--
-- Migration 013 added 22 FOREIGN KEY constraints with NOT VALID so the
-- ALTER TABLE skipped the full-table scan on prod and only checked
-- future inserts. This migration runs `ALTER TABLE ... VALIDATE
-- CONSTRAINT fk_<child>_<col>` on each so PG also checks the existing
-- rows. After this lands, every FK is genuinely enforced.
--
-- Discovery is dynamic (pg_constraint introspection), so:
--   * Constraints that were never installed don't trip the migration.
--   * Constraints that have already been VALIDATEd are silently
--     skipped (PG no-op).
--   * A FUTURE NOT VALID FK added by some later migration is picked up
--     on the next re-run of this script.
--
-- VALIDATE acquires a SHARE UPDATE EXCLUSIVE lock (allows reads + most
-- writes; blocks DDL on the same table). Each table is processed in
-- its own ALTER statement so the lock window stays bounded.
--
-- If VALIDATE fails because a row violates the constraint, PG raises
-- and the transaction rolls back. The expected failure mode here is a
-- LEFTOVER ORPHAN created between mig 013 (which cleaned known
-- orphans) and now. The error message identifies the offending row;
-- clean it up manually then re-run.
-- =====================================================================

BEGIN;

DO $$
DECLARE
    rec RECORD;
    validated_count INT := 0;
    skipped_count   INT := 0;
BEGIN
    FOR rec IN
        SELECT n.nspname  AS schema_name,
               c.relname  AS table_name,
               con.conname AS constraint_name
          FROM pg_constraint con
          JOIN pg_class      c ON c.oid = con.conrelid
          JOIN pg_namespace  n ON n.oid = c.relnamespace
         WHERE con.contype = 'f'             -- FOREIGN KEY
           AND con.convalidated = FALSE      -- still NOT VALID
           AND n.nspname = 'public'
           AND con.conname LIKE 'fk_%'       -- only the names mig 013 picked
         ORDER BY c.relname, con.conname
    LOOP
        BEGIN
            EXECUTE format(
                'ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',
                rec.schema_name, rec.table_name, rec.constraint_name
            );
            validated_count := validated_count + 1;
            RAISE NOTICE 'VALIDATED %.%', rec.table_name, rec.constraint_name;
        EXCEPTION WHEN check_violation OR foreign_key_violation THEN
            RAISE EXCEPTION
                'FK validation failed for %.% -- a row violates the '
                'foreign key. Clean up the offending row (the error '
                'detail above names the FK column + value) then re-run.',
                rec.table_name, rec.constraint_name;
        END;
    END LOOP;

    -- Re-count for the post-apply summary.
    SELECT COUNT(*) INTO skipped_count
      FROM pg_constraint con
      JOIN pg_class      c ON c.oid = con.conrelid
      JOIN pg_namespace  n ON n.oid = c.relnamespace
     WHERE con.contype = 'f'
       AND con.convalidated = FALSE
       AND n.nspname = 'public'
       AND con.conname LIKE 'fk_%';

    RAISE NOTICE 'FK VALIDATE summary: % validated this run, % still NOT VALID',
                 validated_count, skipped_count;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   -- Every fk_* constraint should now show convalidated=true:
--   SELECT c.relname, con.conname, con.convalidated
--     FROM pg_constraint con
--     JOIN pg_class      c ON c.oid = con.conrelid
--     JOIN pg_namespace  n ON n.oid = c.relnamespace
--    WHERE n.nspname='public'
--      AND con.contype='f'
--      AND con.conname LIKE 'fk_%'
--    ORDER BY c.relname, con.conname;
--   -- expect: all rows convalidated=t
--
--   -- Count summary:
--   SELECT
--     COUNT(*) FILTER (WHERE con.convalidated = true)  AS validated,
--     COUNT(*) FILTER (WHERE con.convalidated = false) AS still_not_valid,
--     COUNT(*) AS total_fk_named
--     FROM pg_constraint con
--     JOIN pg_class      c ON c.oid = con.conrelid
--     JOIN pg_namespace  n ON n.oid = c.relnamespace
--    WHERE n.nspname='public'
--      AND con.contype='f'
--      AND con.conname LIKE 'fk_%';
--   -- expect: validated=22 (or however many mig 013 left), still_not_valid=0.
-- =====================================================================
