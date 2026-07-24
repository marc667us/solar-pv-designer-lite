-- 040 REHEARSAL -- the behavioural test for CDC slice 6 (payments).
--
-- NEVER APPLIED ON ITS OWN. The workflow `Apply Migration 040 (CDC Trigger --
-- payments)` concatenates:  BEGIN; 040_cdc_trigger_payments.sql; THIS FILE; ROLLBACK;
-- and runs it against the REAL live database. Everything it does is undone.
--
-- Same design as the 037 rehearsal. The no-op UPDATE assertion is the load-bearing
-- one: it proves WHEN (OLD.* IS DISTINCT FROM NEW.*) suppresses a write that
-- changed nothing. Because this is the payment path, the INSERT also proves the
-- trigger does not abort a real payment write.

DO $REH$
DECLARE
    _base bigint;
    _uid  int;
    _id   text;
    _n    int;
    _op   text;
    _pay  jsonb;
    _tenant uuid;
BEGIN
    SELECT COALESCE(max(id), 0) INTO _base FROM cdc_outbox;

    -- A valid user_id to satisfy the FK (rolled back anyway). There is always at
    -- least the seeded admin/owner on live.
    SELECT id INTO _uid FROM users ORDER BY id LIMIT 1;
    IF _uid IS NULL THEN
        RAISE EXCEPTION 'no users on this database -- cannot rehearse a payments insert';
    END IF;

    -- 1. INSERT must publish -----------------------------------------------------------
    INSERT INTO payments (user_id, gateway, plan, amount_usd, currency, reference, status)
         VALUES (_uid, '__cdc_rehearsal__', 'professional', 0, 'USD', '__cdc_rehearsal_ref__', 'rehearsal')
      RETURNING id::text INTO _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id;
    IF _n <> 1 THEN RAISE EXCEPTION 'INSERT should have published exactly 1 event, saw %', _n; END IF;

    SELECT op, payload, tenant_id INTO _op, _pay, _tenant
      FROM cdc_outbox WHERE id > _base AND source_table = 'payments' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;
    IF _op <> 'INSERT' THEN RAISE EXCEPTION 'expected op=INSERT, got %', _op; END IF;

    -- The allowlist must have produced a payload with the fields we publish, and it
    -- must NOT carry the deliberately-excluded reference.
    IF NOT (_pay ? 'gateway') THEN
        RAISE EXCEPTION 'payload is missing the allowlisted column "gateway": %', _pay;
    END IF;
    IF (_pay ? 'reference') THEN
        RAISE EXCEPTION 'payload leaked the excluded column "reference": %', _pay;
    END IF;
    -- payments is GLOBAL (no tenant_id column) -> tenant must be NULL.
    IF _tenant IS NOT NULL THEN
        RAISE EXCEPTION 'tenant_id should be NULL for global payments, got %', _tenant;
    END IF;
    RAISE NOTICE '  INSERT  -> published (payload keys: %)',
        (SELECT string_agg(k, ',') FROM jsonb_object_keys(_pay) k);

    -- 2. A REAL UPDATE must publish ----------------------------------------------------
    UPDATE payments SET status = '__cdc_changed__' WHERE id::text = _id;
    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id;
    IF _n <> 2 THEN RAISE EXCEPTION 'a real UPDATE should have published, total should be 2, saw %', _n; END IF;
    SELECT op INTO _op FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id ORDER BY id DESC LIMIT 1;
    IF _op <> 'UPDATE' THEN RAISE EXCEPTION 'expected op=UPDATE, got %', _op; END IF;
    RAISE NOTICE '  UPDATE  -> published';

    -- 3. A NO-OP UPDATE must publish NOTHING -------------------------------------------
    UPDATE payments SET status = '__cdc_changed__' WHERE id::text = _id;
    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id;
    IF _n <> 2 THEN
        RAISE EXCEPTION
            'a no-op UPDATE must NOT publish -- expected still 2 events, saw %. '
            'The WHEN (OLD.* IS DISTINCT FROM NEW.*) clause is not suppressing it.', _n;
    END IF;
    RAISE NOTICE '  UPDATE (no-op) -> correctly suppressed';

    -- 4. DELETE must publish, carrying the OLD row -------------------------------------
    DELETE FROM payments WHERE id::text = _id;
    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id;
    IF _n <> 3 THEN RAISE EXCEPTION 'DELETE should have published, total should be 3, saw %', _n; END IF;
    SELECT op, payload INTO _op, _pay FROM cdc_outbox
     WHERE id > _base AND source_table = 'payments' AND row_pk = _id ORDER BY id DESC LIMIT 1;
    IF _op <> 'DELETE' THEN RAISE EXCEPTION 'expected op=DELETE, got %', _op; END IF;
    IF _pay ->> 'status' <> '__cdc_changed__' THEN
        RAISE EXCEPTION 'DELETE should publish the OLD row; status was %', _pay ->> 'status';
    END IF;
    RAISE NOTICE '  DELETE  -> published, carrying the OLD row';

    -- 5. Scope: capture only on the deliberate roster ----------------------------------
    SELECT count(*) INTO _n
      FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE p.proname = 'cdc_capture' AND NOT t.tgisinternal
       AND t.tgrelid IS DISTINCT FROM to_regclass('public.equipment_catalog')
       AND t.tgrelid IS DISTINCT FROM to_regclass('public.suppliers')
       AND t.tgrelid IS DISTINCT FROM to_regclass('public.payments');
    IF _n <> 0 THEN
        RAISE EXCEPTION
            'CDC SCOPE VIOLATION: % cdc trigger(s) outside the deliberate roster '
            '[equipment_catalog, suppliers, payments]', _n;
    END IF;
    RAISE NOTICE '  scope -> within the deliberate roster [equipment_catalog, suppliers, payments]';

    RAISE NOTICE 'REHEARSAL PASSED';
END $REH$;
