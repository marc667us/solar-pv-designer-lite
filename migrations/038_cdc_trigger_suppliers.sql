-- 038 -- Change Data Capture, slice 5: attach the SECOND table, `suppliers`.
--
-- Slice 2 (037) attached the first triggers this schema has ever had, to equipment_catalog
-- alone. Slices 3 and 4 built the consumers: a drain that alerts, and a pg_notify listener
-- that invalidates the marketplace cache in every worker. So the mechanism is now proven
-- end to end and this migration widens CAPTURE by exactly one table. No other table is
-- touched, and no consumer changes.
--
-- WHY `suppliers` IS THE RIGHT SECOND TABLE
-- ----------------------------------------
-- The live consumer is marketplace cache invalidation, and the marketplace catalogue does
-- not read equipment_catalog alone -- it JOINs suppliers for the supplier name shown on
-- every card and row:
--     SELECT e.*, s.name ... FROM equipment_catalog e LEFT JOIN suppliers s ON e.supplier_id = s.id
-- (web_app.py:9278, :9417, :15966, :16969 -- 51 references to the table in all).
--
-- So today a supplier rename, or a supplier being DEACTIVATED, changes what the cached page
-- renders while producing no CDC event at all. Capture is blind to half of what the cache it
-- feeds actually depends on. That is the concrete gap this closes -- not "more tables for the
-- sake of coverage".
--
-- It also carries the same low-risk profile that made equipment_catalog the right first
-- table: it is GLOBAL rather than tenant-scoped, so cdc_outbox.tenant_id stays NULL and no
-- enterprise RLS question is in play; and its writes are catalogue/admin edits, not the login
-- or payment path.
--
-- REDACTION -- THE PART THAT IS DIFFERENT FROM 037
-- -----------------------------------------------
-- equipment_catalog holds no personal data. `suppliers` DOES: contact_name, phone, email and
-- address are contact details of real people at real companies. The outbox is a durable table
-- that a drain reads and summarises into an ADMIN ALERT, so anything published here is copied
-- and forwarded.
--
-- None of those columns are in the allowlist below, and their absence is the point, not an
-- oversight. The CDC design's redaction rule ("users.password_hash must never reach an
-- outbox") is not only about credentials -- a change feed should carry what a consumer needs
-- to DECIDE, and nothing else. A consumer that genuinely needs a supplier's contact details
-- can re-read the row by pk, which is why the outbox always carries one.
--
-- WHAT THE ALLOWLIST DOES CARRY, and why each one earns its place:
--   name        -- rendered on every marketplace card; a rename must invalidate the cache
--   country     -- drives the /marketplace?country= filter
--   categories  -- drives category filtering
--   is_active   -- flipping this ADDS or REMOVES the supplier's products from the public page
--   is_verified -- drives the per-card verification badge
-- Anything not named is excluded BY OMISSION, so a column added to this table in future is
-- not published until somebody deliberately adds it here.
--
-- TWO TRIGGERS, NOT ONE -- same reason as 037
-- ------------------------------------------
-- The UPDATE trigger carries `WHEN (OLD.* IS DISTINCT FROM NEW.*)` so an UPDATE that rewrites
-- a row with identical values publishes nothing. That clause cannot go on a combined trigger:
-- OLD does not exist for INSERT, so `AFTER INSERT OR UPDATE OR DELETE ... WHEN (OLD.* ...)`
-- is rejected by Postgres. Hence one trigger for INSERT/DELETE and one for UPDATE, both
-- calling the same cdc_capture() with the same argument list -- one allowlist, not two.
--
-- THE ALLOWLIST IS ASSERTED, NOT ASSUMED
-- --------------------------------------
-- cdc_capture() skips any named column the row does not have, which is correct for the
-- function (it must never abort a user's write) but means a typo degrades SILENTLY into a
-- smaller payload. `suppliers` is extended at runtime by ALTER ... ADD COLUMN IF NOT EXISTS
-- (address, is_verified, user_id), so what this repo declares and what live actually has are
-- not the same thing -- guessing at exactly that gap caused a wrong fix to ship and be
-- reverted on 2026-07-19. This migration therefore RAISES if any allowlisted column is
-- absent.
--
-- IDEMPOTENT. DROP TRIGGER IF EXISTS before each CREATE, so re-running is safe -- and so that
-- re-running after the allowlist changes actually updates the trigger arguments, which are
-- fixed at CREATE time.
--
-- ROLLBACK:
--   DROP TRIGGER IF EXISTS trg_cdc_suppliers_ins_del ON suppliers;
--   DROP TRIGGER IF EXISTS trg_cdc_suppliers_upd     ON suppliers;
-- That restores exactly the pre-038 behaviour and leaves 036/037 intact.

DO $$
DECLARE
    -- Identity + the fields a consumer needs to decide whether it cares. See the header for
    -- why contact_name / phone / email / address are deliberately NOT here.
    _cols    text[] := ARRAY[
        'name', 'country', 'categories', 'is_active', 'is_verified'
    ];
    _pk_col  text   := 'id';
    _c       text;
    _missing text[] := ARRAY[]::text[];
    _leaky   text[] := ARRAY[]::text[];
    -- Columns that must NEVER be published from this table. Asserted below rather than merely
    -- documented: a future edit that adds one of these to _cols should fail loudly here, not
    -- quietly start copying personal data into an outbox that feeds admin alerts.
    _forbidden text[] := ARRAY[
        'contact_name', 'phone', 'email', 'address', 'notes', 'user_id'
    ];
    _args    text;
BEGIN
    -- ── Preconditions: slices 1 and 2 must actually be present ───────────────────────────
    IF to_regclass('public.cdc_outbox') IS NULL THEN
        RAISE EXCEPTION 'cdc_outbox is missing -- apply migration 036 (CDC slice 1) first';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'cdc_capture') THEN
        RAISE EXCEPTION 'cdc_capture() is missing -- apply migration 036 (CDC slice 1) first';
    END IF;

    -- 037 is not strictly required for 038 to work, but capture arriving out of order would
    -- mean the mechanism was never proven on its first, lowest-risk table. Fail loudly.
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgname = 'trg_cdc_equipment_catalog_ins_del'
           AND NOT tgisinternal
    ) THEN
        RAISE EXCEPTION
            'CDC slice 2 (migration 037, equipment_catalog) is not applied. Widen capture '
            'only after the first table is live and proven.';
    END IF;

    IF to_regclass('public.suppliers') IS NULL THEN
        RAISE EXCEPTION 'suppliers does not exist on this database';
    END IF;

    -- ── The pk column must exist ─────────────────────────────────────────────────────────
    -- cdc_capture() falls back to '' for a missing pk, which would produce outbox rows that
    -- point at nothing. A feed of unidentifiable events is worse than no feed.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name   = 'suppliers'
           AND column_name  = _pk_col
    ) THEN
        RAISE EXCEPTION 'suppliers has no % column to use as the CDC row_pk', _pk_col;
    END IF;

    -- ── REDACTION GUARD: no forbidden column may be in the allowlist ─────────────────────
    -- Runs BEFORE the existence check so the message is about privacy, not about a typo.
    FOREACH _c IN ARRAY _cols LOOP
        IF _c = ANY (_forbidden) THEN
            _leaky := _leaky || _c;
        END IF;
    END LOOP;

    IF array_length(_leaky, 1) > 0 THEN
        RAISE EXCEPTION
            'CDC allowlist for suppliers names column(s) that must never be published: %. '
            'The outbox is durable and is summarised into admin alerts -- contact details '
            'do not belong in a change feed. A consumer that needs them can re-read the row '
            'by pk.',
            array_to_string(_leaky, ', ');
    END IF;

    -- ── Every allowlisted column must really exist ───────────────────────────────────────
    FOREACH _c IN ARRAY _cols LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'suppliers'
               AND column_name  = _c
        ) THEN
            _missing := _missing || _c;
        END IF;
    END LOOP;

    IF array_length(_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'CDC allowlist names column(s) that do not exist on suppliers: %. '
            'Fix the list in migrations/038 -- do not let the payload shrink silently.',
            array_to_string(_missing, ', ');
    END IF;

    -- ── Build the trigger argument list: pk first, then the allowlist ────────────────────
    -- quote_literal on every element: these become SQL string literals in a CREATE TRIGGER
    -- built by string concatenation.
    _args := quote_literal(_pk_col);
    FOREACH _c IN ARRAY _cols LOOP
        _args := _args || ', ' || quote_literal(_c);
    END LOOP;

    -- ── Attach ───────────────────────────────────────────────────────────────────────────
    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_suppliers_ins_del ON public.suppliers';
    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_suppliers_upd     ON public.suppliers';

    -- INSERT and DELETE always publish: a row appearing or disappearing is always a change.
    EXECUTE format(
        'CREATE TRIGGER trg_cdc_suppliers_ins_del '
        'AFTER INSERT OR DELETE ON public.suppliers '
        'FOR EACH ROW EXECUTE FUNCTION cdc_capture(%s)', _args);

    -- UPDATE publishes only when the row actually differs.
    EXECUTE format(
        'CREATE TRIGGER trg_cdc_suppliers_upd '
        'AFTER UPDATE ON public.suppliers '
        'FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) '
        'EXECUTE FUNCTION cdc_capture(%s)', _args);

    RAISE NOTICE 'CDC slice 5: triggers attached to suppliers (allowlist: %)',
        array_to_string(_cols, ', ');
END $$;
