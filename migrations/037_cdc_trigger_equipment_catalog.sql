-- 037 -- Change Data Capture, slice 2: attach the FIRST trigger, to ONE table.
--
-- Slice 1 (036) shipped the mechanism dark: cdc_outbox, cdc_capture(), RLS, REVOKE, and
-- deliberately ZERO triggers. This migration makes the mechanism live for exactly one table:
-- equipment_catalog. No other table is touched. No consumer is attached.
--
-- WHY equipment_catalog FIRST
-- --------------------------
-- It is the table that motivated the whole design. Measured 2026-07-19: ~90 ad-hoc write
-- sites (41 in web_app.py, 49 across new_*.py) with no chokepoint between them, which is
-- precisely the situation an app-level event bus cannot cover and a trigger can. It is also
-- the LOWEST-RISK first choice:
--   * it is GLOBAL, not tenant-scoped, so cdc_outbox.tenant_id stays NULL and none of the
--     enterprise RLS/tenant questions are in play for the first trigger this schema has ever
--     had;
--   * it holds no secrets, so a redaction mistake here cannot leak a credential;
--   * its writes are catalogue edits and admin sweeps -- not on the login or payment path, so
--     if capture misbehaves the blast radius is the marketplace, not authentication.
--
-- CAPTURE ONLY. NO CONSUMER. Rows accumulate in the outbox and nothing reads them yet. That
-- ordering is deliberate: a change feed must be proven to observe correctly before anything
-- is allowed to ACT on what it observed. Retention already shipped ahead of this
-- (`CDC Outbox Retention`), so an append-only table cannot quietly grow without a bound.
--
-- TWO TRIGGERS, NOT ONE -- and the reason is the WHEN clause
-- ---------------------------------------------------------
-- The UPDATE trigger carries `WHEN (OLD.* IS DISTINCT FROM NEW.*)` so an UPDATE that rewrites
-- a row with identical values publishes NOTHING. This app does bulk catalogue sweeps that
-- re-write many rows unconditionally, and a no-op UPDATE is not a change -- publishing it
-- would fill the outbox with events that no consumer can act on and that no cache needs
-- invalidating for.
--
-- That clause CANNOT go on a combined trigger: OLD does not exist for INSERT, so a single
-- `AFTER INSERT OR UPDATE OR DELETE ... WHEN (OLD.* ...)` is rejected by Postgres. Hence one
-- trigger for INSERT/DELETE (always publish) and one for UPDATE (publish only real changes).
-- Both call the same cdc_capture() with the same arguments, so there is one allowlist, not two.
--
-- THE ALLOWLIST IS ASSERTED, NOT ASSUMED
-- --------------------------------------
-- cdc_capture() skips any named column the row does not have (`IF _row ? _col`). That is the
-- right behaviour for the function -- it must never abort a user's write -- but it means a
-- typo'd or dropped column degrades SILENTLY into a smaller payload. This schema is not the
-- one in migrations/001: equipment_catalog has been extended by ALTER ... ADD COLUMN IF NOT
-- EXISTS at runtime, so what the source files declare and what live actually has are not the
-- same thing. Guessing at that gap caused a wrong "fix" to be shipped and reverted on
-- 2026-07-19. So this migration RAISES if any allowlisted column is absent: a mismatch
-- between what we think we publish and what we publish is a loud failure here, not a quiet
-- one discovered later by a consumer receiving less than it expected.
--
-- IDEMPOTENT. DROP TRIGGER IF EXISTS before each CREATE, so re-running is safe and re-running
-- after the allowlist changes actually updates the trigger arguments (trigger args are fixed
-- at CREATE time -- editing this list without recreating the trigger would do nothing).
--
-- ROLLBACK:
--   DROP TRIGGER IF EXISTS trg_cdc_equipment_catalog_ins_del ON equipment_catalog;
--   DROP TRIGGER IF EXISTS trg_cdc_equipment_catalog_upd     ON equipment_catalog;
-- That restores exactly the pre-037 behaviour and leaves the slice-1 mechanism intact.

DO $$
DECLARE
    -- THE ALLOWLIST. Identity + the fields a consumer would need to decide whether it cares:
    -- what the product is, who supplies it, what it costs, whether it is live. Deliberately
    -- excludes free-text `notes` and `spec` (large, and not decision-relevant -- a consumer
    -- that needs them can re-read the row by pk, which is why the outbox always carries one).
    -- Anything not named here is excluded BY OMISSION. A column added to this table in future
    -- is therefore not published until somebody deliberately adds it below.
    _cols    text[] := ARRAY[
        'category', 'name', 'brand', 'model', 'unit',
        'price_usd', 'supplier_id', 'is_active'
    ];
    _pk_col  text   := 'id';
    _c       text;
    _missing text[] := ARRAY[]::text[];
    _args    text;
BEGIN
    -- ── Preconditions: slice 1 must actually be present ──────────────────────────────────
    -- Attaching a trigger whose function is missing would break every catalogue write, so
    -- this fails before it changes anything rather than after.
    IF to_regclass('public.cdc_outbox') IS NULL THEN
        RAISE EXCEPTION 'cdc_outbox is missing -- apply migration 036 (CDC slice 1) first';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'cdc_capture') THEN
        RAISE EXCEPTION 'cdc_capture() is missing -- apply migration 036 (CDC slice 1) first';
    END IF;

    IF to_regclass('public.equipment_catalog') IS NULL THEN
        RAISE EXCEPTION 'equipment_catalog does not exist on this database';
    END IF;

    -- ── The pk column must exist ─────────────────────────────────────────────────────────
    -- cdc_capture() falls back to '' for a missing pk, which would produce outbox rows that
    -- point at nothing. A feed of unidentifiable events is worse than no feed.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name   = 'equipment_catalog'
           AND column_name  = _pk_col
    ) THEN
        RAISE EXCEPTION 'equipment_catalog has no % column to use as the CDC row_pk', _pk_col;
    END IF;

    -- ── Every allowlisted column must really exist ───────────────────────────────────────
    FOREACH _c IN ARRAY _cols LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name   = 'equipment_catalog'
               AND column_name  = _c
        ) THEN
            _missing := _missing || _c;
        END IF;
    END LOOP;

    IF array_length(_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'CDC allowlist names column(s) that do not exist on equipment_catalog: %. '
            'Fix the list in migrations/037 -- do not let the payload shrink silently.',
            array_to_string(_missing, ', ');
    END IF;

    -- ── Build the trigger argument list: pk first, then the allowlist ────────────────────
    -- quote_literal on every element: these become SQL string literals in a CREATE TRIGGER
    -- built by string concatenation, and an unquoted identifier here would be an injection
    -- point if this list ever became data rather than a constant.
    _args := quote_literal(_pk_col);
    FOREACH _c IN ARRAY _cols LOOP
        _args := _args || ', ' || quote_literal(_c);
    END LOOP;

    -- ── Attach ───────────────────────────────────────────────────────────────────────────
    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_equipment_catalog_ins_del ON public.equipment_catalog';
    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_equipment_catalog_upd     ON public.equipment_catalog';

    -- INSERT and DELETE always publish: a row appearing or disappearing is always a change.
    EXECUTE format(
        'CREATE TRIGGER trg_cdc_equipment_catalog_ins_del '
        'AFTER INSERT OR DELETE ON public.equipment_catalog '
        'FOR EACH ROW EXECUTE FUNCTION cdc_capture(%s)', _args);

    -- UPDATE publishes only when the row actually differs. See the header note on why this
    -- cannot be folded into the trigger above.
    EXECUTE format(
        'CREATE TRIGGER trg_cdc_equipment_catalog_upd '
        'AFTER UPDATE ON public.equipment_catalog '
        'FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) '
        'EXECUTE FUNCTION cdc_capture(%s)', _args);

    RAISE NOTICE 'CDC slice 2: triggers attached to equipment_catalog (allowlist: %)',
        array_to_string(_cols, ', ');
END $$;
