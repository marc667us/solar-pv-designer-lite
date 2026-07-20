-- 038 REHEARSAL -- the behavioural test for CDC slice 5.
--
-- NEVER APPLIED ON ITS OWN AND NEVER COMMITTED. The workflow
-- `Apply Migration 038 (CDC Trigger -- suppliers)` concatenates:
--
--     BEGIN;
--       038_cdc_trigger_suppliers.sql            <- attach the triggers
--       038_cdc_trigger_suppliers_rehearsal.sql  <- THIS FILE: exercise them
--     ROLLBACK;
--
-- and runs the result against the REAL live database. Everything it does is undone.
--
-- Same reasoning as the 037 rehearsal: this project has no local Postgres (no psycopg2, no
-- Docker, no psql), so a transaction against live that is rolled back is the ONLY way to
-- prove a trigger behaves on the real schema with the real column set -- and the real column
-- set is precisely what is in question, because `suppliers` is extended at runtime by
-- ALTER ... ADD COLUMN IF NOT EXISTS (address, is_verified, user_id).
--
-- WHAT THIS ADDS OVER THE 037 REHEARSAL
-- -------------------------------------
-- Assertion 5 is new and is the reason this file is not a copy-paste of 037: `suppliers`
-- holds CONTACT DETAILS OF REAL PEOPLE, so the rehearsal deliberately writes a row WITH an
-- email, phone, address and contact name, and then asserts none of them reached the outbox.
-- Documenting a redaction rule in a header is not the same as proving it, and the outbox is
-- durable and gets summarised into admin alerts.

DO $REH$
DECLARE
    _base   bigint;   -- outbox high-water mark before we touch anything
    _id     text;
    _n      int;
    _op     text;
    _pay    jsonb;
    _tenant uuid;
    _leaked text[] := ARRAY[]::text[];
    _k      text;
    _tables text;
BEGIN
    -- Count only what WE cause. A high-water mark needs no DELETE rights on an RLS table.
    -- Every assertion ALSO filters on the throwaway row's own pk, which no other session can
    -- be writing, so a concurrent supplier edit cannot fail a rehearsal of a correct trigger.
    SELECT COALESCE(max(id), 0) INTO _base FROM cdc_outbox;

    -- 1. INSERT must publish -------------------------------------------------------------
    -- Contact fields are populated ON PURPOSE so assertion 5 has something real to catch.
    -- `name` is the only NOT NULL column; the rest are supplied to exercise redaction.
    INSERT INTO suppliers (name, country, is_active,
                           contact_name, phone, email, address)
         VALUES ('__cdc_rehearsal__', '__CDC__', 1,
                 '__cdc_person__', '+000000000000',
                 '__cdc_rehearsal__@example.invalid', '__cdc_address__')
      RETURNING id::text INTO _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id;
    IF _n <> 1 THEN
        RAISE EXCEPTION 'INSERT should have published exactly 1 event, saw %', _n;
    END IF;

    SELECT op, payload, tenant_id INTO _op, _pay, _tenant
      FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;

    IF _op <> 'INSERT' THEN RAISE EXCEPTION 'expected op=INSERT, got %', _op; END IF;

    -- The allowlist must actually have produced a payload. An empty one would mean
    -- cdc_capture() skipped every column, i.e. the allowlist does not match the table.
    IF NOT (_pay ? 'name') THEN
        RAISE EXCEPTION 'payload is missing the allowlisted column "name": %', _pay;
    END IF;

    -- `suppliers` is GLOBAL, like equipment_catalog. A non-NULL tenant here would mean CDC
    -- invented tenancy for a table that has none.
    IF _tenant IS NOT NULL THEN
        RAISE EXCEPTION 'tenant_id should be NULL for the global suppliers table, got %', _tenant;
    END IF;
    RAISE NOTICE '  INSERT  -> published (payload keys: %)',
        (SELECT string_agg(k, ',') FROM jsonb_object_keys(_pay) k);

    -- 2. A REAL UPDATE must publish ------------------------------------------------------
    UPDATE suppliers SET country = '__CDC_CHANGED__' WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id;
    IF _n <> 2 THEN
        RAISE EXCEPTION 'a real UPDATE should have published, total should be 2, saw %', _n;
    END IF;
    SELECT op INTO _op FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;
    IF _op <> 'UPDATE' THEN RAISE EXCEPTION 'expected op=UPDATE, got %', _op; END IF;
    RAISE NOTICE '  UPDATE  -> published';

    -- 3. A NO-OP UPDATE must publish NOTHING ---------------------------------------------
    -- The only thing that proves WHEN (OLD.* IS DISTINCT FROM NEW.*) is doing its job.
    -- If this starts failing, the outbox is recording WRITES, not CHANGES.
    UPDATE suppliers SET country = '__CDC_CHANGED__' WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id;
    IF _n <> 2 THEN
        RAISE EXCEPTION
            'a no-op UPDATE must NOT publish -- expected still 2 events, saw %. '
            'The WHEN (OLD.* IS DISTINCT FROM NEW.*) clause is not suppressing it.', _n;
    END IF;
    RAISE NOTICE '  UPDATE (no-op) -> correctly suppressed';

    -- 4. An UPDATE to a NON-allowlisted column still publishes ---------------------------
    -- Worth pinning explicitly: the WHEN clause is OLD.* IS DISTINCT FROM NEW.*, i.e. the
    -- WHOLE ROW, not the allowlist. So changing `phone` -- which is deliberately NOT
    -- published -- still emits an event, carrying only the allowlisted fields. That is the
    -- correct behaviour: a consumer learns the row changed and can re-read it, while the
    -- feed still carries no contact data.
    UPDATE suppliers SET phone = '+111111111111' WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id;
    IF _n <> 3 THEN
        RAISE EXCEPTION
            'an UPDATE to a non-allowlisted column should still publish (the WHEN clause '
            'compares the whole row) -- expected 3 events, saw %', _n;
    END IF;
    RAISE NOTICE '  UPDATE (non-allowlisted column) -> published, payload still redacted';

    -- 5. REDACTION -- the assertion this table exists to justify --------------------------
    -- The row we created carries a real-looking email, phone, address and contact name.
    -- NONE of them may appear in ANY event this rehearsal produced. Checked over every
    -- event, not just the last, and by KEY -- because a key is what a consumer would read.
    FOR _pay IN
        SELECT payload FROM cdc_outbox
         WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id
    LOOP
        FOREACH _k IN ARRAY ARRAY['contact_name', 'phone', 'email', 'address',
                                  'notes', 'user_id']
        LOOP
            IF _pay ? _k THEN
                _leaked := _leaked || _k;
            END IF;
        END LOOP;
    END LOOP;

    IF array_length(_leaked, 1) > 0 THEN
        RAISE EXCEPTION
            'REDACTION FAILURE: the outbox published contact column(s) % from suppliers. '
            'The outbox is durable and is summarised into admin alerts -- personal data '
            'must not enter the change feed.',
            array_to_string(_leaked, ', ');
    END IF;
    RAISE NOTICE '  redaction -> no contact column reached the outbox';

    -- 6. DELETE must publish, and must publish the row that went away --------------------
    DELETE FROM suppliers WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id;
    IF _n <> 4 THEN
        RAISE EXCEPTION 'DELETE should have published, total should be 4, saw %', _n;
    END IF;
    SELECT op, payload INTO _op, _pay FROM cdc_outbox
     WHERE id > _base AND source_table = 'suppliers' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;
    IF _op <> 'DELETE' THEN RAISE EXCEPTION 'expected op=DELETE, got %', _op; END IF;

    -- DELETE must carry OLD, not NEW. If this returned a pre-update value the capture
    -- function is publishing the wrong tuple and a consumer would act on stale state.
    IF _pay ->> 'country' <> '__CDC_CHANGED__' THEN
        RAISE EXCEPTION 'DELETE should publish the OLD row; country was %', _pay ->> 'country';
    END IF;
    RAISE NOTICE '  DELETE  -> published, carrying the OLD row';

    -- 7. Scope: exactly the two tables this project has deliberately attached ------------
    -- 037's equivalent assertion allowed ONLY equipment_catalog, which was correct when it
    -- was the only attached table. It is updated in the same commit as this file so the two
    -- rehearsals agree; if they ever disagree, one of them is lying about the slice.
    -- Compare REGCLASS values, not rendered text. tgrelid::regclass::text renders
    -- schema-qualified ("public.suppliers") or bare ("suppliers") depending on search_path,
    -- so a string comparison would pass or fail for reasons that have nothing to do with
    -- the triggers. 037 got this right by comparing regclass; this mirrors it.
    SELECT count(*) INTO _n
      FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE p.proname = 'cdc_capture' AND NOT t.tgisinternal
       AND t.tgrelid NOT IN ('public.equipment_catalog'::regclass,
                             'public.suppliers'::regclass);
    IF _n <> 0 THEN
        -- Only build the human-readable list when something is actually wrong.
        SELECT string_agg(DISTINCT t.tgrelid::regclass::text, ', ')
          INTO _tables
          FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
         WHERE p.proname = 'cdc_capture' AND NOT t.tgisinternal
           AND t.tgrelid NOT IN ('public.equipment_catalog'::regclass,
                                 'public.suppliers'::regclass);
        RAISE EXCEPTION
            'SLICE-5 SCOPE VIOLATION: cdc trigger(s) on table(s) outside the deliberate '
            'roster [equipment_catalog, suppliers]: [%]. Capture must widen one table at '
            'a time.', COALESCE(_tables, '(unknown)');
    END IF;

    -- ...and the other direction: this slice must actually have attached BOTH triggers to
    -- suppliers. "Nothing outside the roster" is satisfied trivially by attaching nothing.
    SELECT count(*) INTO _n
      FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE p.proname = 'cdc_capture' AND NOT t.tgisinternal
       AND t.tgrelid = 'public.suppliers'::regclass;
    IF _n <> 2 THEN
        RAISE EXCEPTION
            'expected 2 cdc triggers on suppliers (ins_del + upd), found %', _n;
    END IF;
    RAISE NOTICE '  scope -> equipment_catalog + suppliers, as the slice claims';

    RAISE NOTICE 'REHEARSAL PASSED';
END $REH$;
