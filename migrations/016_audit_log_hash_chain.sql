-- 016_audit_log_hash_chain.sql
-- =====================================================================
-- SOC 2 M3.2 -- immutable audit log via SHA-256 hash chain.
--
-- Each audit_logs row carries:
--   prev_hash  TEXT -- the row_hash of the previous row in id order
--                     (or 'GENESIS' for row #1).
--   row_hash   TEXT -- sha256(prev_hash || '|' || canonical_content)
--                     where canonical_content is the pipe-joined,
--                     COALESCE-to-empty-string serialisation of the
--                     audit columns. Recomputed by both PG (this
--                     backfill) and the Python writer in
--                     app/security/audit.py so each side can verify
--                     the chain independently.
--
-- Tamper-detection invariant: editing any row's content invalidates
-- that row's row_hash AND breaks every subsequent row's chain because
-- their prev_hash references no longer match. Deleting a row breaks
-- the chain at the next row. The verifier walks id ASC and reports
-- the first break.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS + the backfill DO-block skips
-- rows that already have a row_hash. Safe to re-run.
-- =====================================================================

BEGIN;

-- ---------------------------------------------------------------------
-- PART 1 -- pgcrypto for the digest function used in backfill.
-- ---------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ---------------------------------------------------------------------
-- PART 2 -- add the chain columns. Both nullable so legacy rows that
--           haven't been backfilled still surface in queries; the
--           verifier treats NULL hashes as "unchained" warnings rather
--           than tamper indicators.
-- ---------------------------------------------------------------------

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS prev_hash TEXT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS row_hash  TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_logs_row_hash
    ON audit_logs (row_hash);


-- ---------------------------------------------------------------------
-- PART 3 -- canonical content helper. Pipe-joined, COALESCE-to-empty
--           so a NULL column and an empty string column hash the same.
--           Matches the Python serialisation in app/security/audit.py.
-- ---------------------------------------------------------------------

CREATE OR REPLACE FUNCTION _audit_canonical_content(
    p_user_id   BIGINT,
    p_username  TEXT,
    p_action    TEXT,
    p_ip        TEXT,
    p_details   TEXT,
    p_created   TEXT,
    p_tenant_id UUID,
    p_agent_id  TEXT
) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT
        COALESCE(p_user_id::text, '')   || '|' ||
        COALESCE(p_username, '')         || '|' ||
        COALESCE(p_action, '')           || '|' ||
        COALESCE(p_ip, '')               || '|' ||
        COALESCE(p_details, '')          || '|' ||
        COALESCE(p_created, '')          || '|' ||
        COALESCE(p_tenant_id::text, '')  || '|' ||
        COALESCE(p_agent_id, '')
$$;


CREATE OR REPLACE FUNCTION _audit_row_hash(prev TEXT, content TEXT)
    RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT encode(digest(COALESCE(prev, 'GENESIS') || '|' || content, 'sha256'), 'hex')
$$;


-- ---------------------------------------------------------------------
-- PART 4 -- backfill existing rows in id order. Idempotent: skip any
--           row that already has a row_hash. The first un-hashed row
--           inherits its prev_hash from the LAST hashed row (or
--           'GENESIS' if no rows are hashed yet).
-- ---------------------------------------------------------------------

-- Pre-condition: migration 004 already added audit_logs.tenant_id +
-- agent_id on PG (idempotent CREATE EXTENSION-style add-column gate
-- in 004). If 004 hasn't applied yet, the backfill SELECT below would
-- fail to parse -- guard with a dynamic EXECUTE that builds the
-- column list at runtime so this migration can run before OR after
-- the Phase 6 column add without crashing.

DO $$
DECLARE
    r RECORD;
    prev TEXT;
    content TEXT;
    h TEXT;
    has_tenant BOOLEAN;
    has_agent  BOOLEAN;
    cur REFCURSOR;
    sel_sql TEXT;
BEGIN
    has_tenant := EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='audit_logs' AND column_name='tenant_id');
    has_agent  := EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_name='audit_logs' AND column_name='agent_id');

    -- Resume from the last hashed row (or GENESIS).
    SELECT row_hash INTO prev
      FROM audit_logs
     WHERE row_hash IS NOT NULL
     ORDER BY id DESC
     LIMIT 1;
    IF prev IS NULL THEN
        prev := 'GENESIS';
    END IF;

    sel_sql := 'SELECT id, user_id, username, action, ip_address, details, created_at, '
            || CASE WHEN has_tenant THEN 'tenant_id::text' ELSE 'NULL::text' END
            || ' AS tenant_id_text, '
            || CASE WHEN has_agent  THEN 'agent_id'        ELSE 'NULL::text' END
            || ' AS agent_id_text '
            || 'FROM audit_logs WHERE row_hash IS NULL ORDER BY id ASC';

    OPEN cur FOR EXECUTE sel_sql;
    LOOP
        FETCH cur INTO r;
        EXIT WHEN NOT FOUND;
        content :=
            COALESCE(r.user_id::text, '')      || '|' ||
            COALESCE(r.username, '')           || '|' ||
            COALESCE(r.action, '')             || '|' ||
            COALESCE(r.ip_address, '')         || '|' ||
            COALESCE(r.details, '')            || '|' ||
            COALESCE(r.created_at, '')         || '|' ||
            COALESCE(r.tenant_id_text, '')     || '|' ||
            COALESCE(r.agent_id_text, '');
        h := encode(digest(prev || '|' || content, 'sha256'), 'hex');
        UPDATE audit_logs
           SET prev_hash = prev,
               row_hash  = h
         WHERE id = r.id;
        prev := h;
    END LOOP;
    CLOSE cur;
END;
$$;

COMMIT;

-- =====================================================================
-- POST-APPLY VERIFICATION
-- ---------------------------------------------------------------------
--   -- All rows must now have both hashes:
--   SELECT COUNT(*) FILTER (WHERE row_hash IS NULL)  AS unchained,
--          COUNT(*) FILTER (WHERE row_hash IS NOT NULL) AS chained,
--          COUNT(*) AS total
--     FROM audit_logs;
--
--   -- Spot-check the chain is internally consistent. Mismatch => tamper.
--   WITH chain AS (
--     SELECT id, prev_hash, row_hash,
--            _audit_canonical_content(
--              user_id, username, action, ip_address, details, created_at,
--              CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
--                                 WHERE table_name='audit_logs' AND column_name='tenant_id')
--                   THEN tenant_id END,
--              CASE WHEN EXISTS (SELECT 1 FROM information_schema.columns
--                                 WHERE table_name='audit_logs' AND column_name='agent_id')
--                   THEN agent_id END
--            ) AS content
--       FROM audit_logs ORDER BY id ASC
--   )
--   SELECT id, prev_hash, row_hash,
--          _audit_row_hash(prev_hash, content) AS recomputed,
--          row_hash = _audit_row_hash(prev_hash, content) AS chain_ok
--     FROM chain LIMIT 5;
-- =====================================================================
