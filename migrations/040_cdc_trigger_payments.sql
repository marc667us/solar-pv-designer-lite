-- 040 -- Change Data Capture, slice 6: attach capture to `payments`.
--
-- Roster so far (037, 038): equipment_catalog, suppliers. This adds payments.
--
-- HIGHER STAKES THAN 037/038 -- this is the PAYMENT PATH
-- ------------------------------------------------------
-- 037 chose equipment_catalog partly because it is "not on the login or payment
-- path, so if capture misbehaves the blast radius is the marketplace". This
-- migration deliberately puts a trigger in front of every INSERT/UPDATE/DELETE
-- on `payments`. cdc_capture() is written never to raise (it skips any column a
-- row lacks), and the apply workflow's behavioural rehearsal proves the trigger
-- against the REAL table inside a rolled-back transaction before anything is
-- committed. Still: apply this ONLY after reading that rehearsal output.
--
-- ALLOWLIST -- deliberately excludes `reference`
-- ----------------------------------------------
-- The outbox row always carries the pk, so a consumer that needs the full row
-- (including the gateway reference) re-reads payments by id. Publishing the
-- reference into the feed is therefore unnecessary, and keeping the payment-path
-- payload minimal is the conservative default. Identity + what a consumer needs
-- to decide whether it cares: who paid, how, for what, how much, and whether it
-- succeeded.
--
-- TWO TRIGGERS (INSERT/DELETE always; UPDATE only on real change) for the same
-- reason as 037: WHEN (OLD.* IS DISTINCT FROM NEW.*) cannot sit on a combined
-- trigger because OLD does not exist for INSERT.
--
-- IDEMPOTENT: DROP TRIGGER IF EXISTS before each CREATE.
--
-- ROLLBACK:
--   DROP TRIGGER IF EXISTS trg_cdc_payments_ins_del ON payments;
--   DROP TRIGGER IF EXISTS trg_cdc_payments_upd     ON payments;

DO $$
DECLARE
    _cols    text[] := ARRAY[
        'user_id', 'gateway', 'plan', 'amount_usd', 'currency', 'status'
    ];
    _pk_col  text   := 'id';
    _c       text;
    _missing text[] := ARRAY[]::text[];
    _args    text;
BEGIN
    IF to_regclass('public.cdc_outbox') IS NULL THEN
        RAISE EXCEPTION 'cdc_outbox is missing -- apply migration 036 (CDC slice 1) first';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'cdc_capture') THEN
        RAISE EXCEPTION 'cdc_capture() is missing -- apply migration 036 (CDC slice 1) first';
    END IF;
    IF to_regclass('public.payments') IS NULL THEN
        RAISE EXCEPTION 'payments does not exist on this database';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='payments' AND column_name=_pk_col
    ) THEN
        RAISE EXCEPTION 'payments has no % column to use as the CDC row_pk', _pk_col;
    END IF;

    FOREACH _c IN ARRAY _cols LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_schema='public' AND table_name='payments' AND column_name=_c
        ) THEN
            _missing := _missing || _c;
        END IF;
    END LOOP;
    IF array_length(_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'CDC allowlist names column(s) that do not exist on payments: %. '
            'Fix the list in migrations/040 -- do not let the payload shrink silently.',
            array_to_string(_missing, ', ');
    END IF;

    _args := quote_literal(_pk_col);
    FOREACH _c IN ARRAY _cols LOOP
        _args := _args || ', ' || quote_literal(_c);
    END LOOP;

    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_payments_ins_del ON public.payments';
    EXECUTE 'DROP TRIGGER IF EXISTS trg_cdc_payments_upd     ON public.payments';

    EXECUTE format(
        'CREATE TRIGGER trg_cdc_payments_ins_del '
        'AFTER INSERT OR DELETE ON public.payments '
        'FOR EACH ROW EXECUTE FUNCTION cdc_capture(%s)', _args);

    EXECUTE format(
        'CREATE TRIGGER trg_cdc_payments_upd '
        'AFTER UPDATE ON public.payments '
        'FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) '
        'EXECUTE FUNCTION cdc_capture(%s)', _args);

    RAISE NOTICE 'CDC slice 6: triggers attached to payments (allowlist: %)',
        array_to_string(_cols, ', ');
END $$;
