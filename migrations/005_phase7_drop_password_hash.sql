-- 005_phase7_drop_password_hash.sql
-- =====================================================================
-- Phase 7 cleanup (Day +14 after a successful Keycloak cutover) of
-- docs/SECURITY_MIGRATION_KEYCLOAK.md.
--
-- After 14 days of the new auth surface running clean, the legacy
-- bcrypt column is no longer used by any code path. We rename it to
-- `legacy_password_hash` (rather than DROP) so a forensic SELECT can
-- still recover the hash for a specific user if we discover an edge
-- case during the next 30 days.
--
-- A follow-up migration (006) -- run only after the legacy-hash audit
-- is signed off -- finally drops the column.
--
-- Same applies to the `is_admin` boolean: it's harmless to keep
-- around (Phase 4 RLS no longer reads it), but renaming makes
-- accidental reuse loud.
--
-- Idempotent: re-running is a no-op via DO blocks that check
-- information_schema before renaming.
-- =====================================================================

BEGIN;

DO $$
BEGIN
    -- 1) password_hash -> legacy_password_hash
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'password_hash'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'legacy_password_hash'
    ) THEN
        EXECUTE 'ALTER TABLE users RENAME COLUMN password_hash TO legacy_password_hash';
    END IF;

    -- 2) is_admin -> legacy_is_admin
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'is_admin'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name = 'legacy_is_admin'
    ) THEN
        EXECUTE 'ALTER TABLE users RENAME COLUMN is_admin TO legacy_is_admin';
    END IF;

    -- 3) login_failures append-only audit window: keep 90 days of
    --    history then truncate. We do NOT delete the table itself --
    --    the brute-force lockout still relies on its 15-minute
    --    window during the rollback period.
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'login_failures'
    ) THEN
        EXECUTE 'DELETE FROM login_failures '
                'WHERE created_at < NOW() - INTERVAL ''90 days''';
    END IF;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name = 'users'
--      AND column_name IN ('legacy_password_hash','legacy_is_admin');
--   -- Expect both rows.
--
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name = 'users'
--      AND column_name IN ('password_hash','is_admin');
--   -- Expect NO rows (renamed).
-- =====================================================================
