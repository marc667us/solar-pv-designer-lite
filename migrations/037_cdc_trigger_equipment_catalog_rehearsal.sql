-- 037 REHEARSAL -- the behavioural test for CDC slice 2.
--
-- THIS FILE IS NEVER APPLIED ON ITS OWN AND NEVER COMMITTED. The workflow
-- `Apply Migration 037 (CDC Trigger -- equipment_catalog)` concatenates:
--
--     BEGIN;
--       037_cdc_trigger_equipment_catalog.sql        <- attach the triggers
--       037_cdc_trigger_equipment_catalog_rehearsal.sql  <- THIS FILE: exercise them
--     ROLLBACK;
--
-- and runs the result against the REAL live database. Everything it does is undone.
--
-- WHY THIS EXISTS AS A FILE RATHER THAN A HEREDOC IN THE WORKFLOW
-- --------------------------------------------------------------
-- It was a heredoc first, and the heredoc body had to sit at column 0 to keep its closing
-- delimiter valid -- which is invalid inside a YAML block scalar and broke the workflow file.
-- As its own file the SQL is also diffable and reviewable on its own terms, which a test
-- deserves.
--
-- WHY A REHEARSAL IS THE TEST SUITE HERE
-- --------------------------------------
-- This project has no local Postgres (no psycopg2, no Docker, no psql), so there is nowhere
-- else to prove a trigger behaves. Running it against live inside a transaction that is
-- rolled back is the only way to test it on the real schema with the real column set -- and
-- the real schema is the thing at issue, because equipment_catalog has been extended by
-- runtime ALTER ... ADD COLUMN and does not match any CREATE TABLE in this repo.
--
-- Same pattern as scripts/backfill_onboarding_owner_roles.py --rehearse.

DO $REH$
DECLARE
    _base   bigint;   -- outbox high-water mark before we touch anything
    _id     text;
    _n      int;
    _op     text;
    _pay    jsonb;
    _tenant uuid;
BEGIN
    -- Count only what WE cause. Deleting the outbox to get a clean slate would be a write
    -- against a table with RLS and no DELETE policy; a high-water mark needs no such rights.
    --
    -- The high-water mark ALONE is not sufficient (Codex LOW, 2026-07-19). Under READ
    -- COMMITTED this transaction can see rows another session commits after _base is taken.
    -- That is harmless on the first run -- no triggers exist yet, so nobody else can produce
    -- an outbox row -- but this workflow is re-runnable, and once 037 IS applied a concurrent
    -- catalogue write would land id > _base and fail a rehearsal of a perfectly correct
    -- trigger. So every assertion below ALSO filters on the throwaway row's own pk, which no
    -- other session can be writing: the id comes from a fresh sequence value.
    SELECT COALESCE(max(id), 0) INTO _base FROM cdc_outbox;

    -- 1. INSERT must publish -------------------------------------------------------------
    -- Only the NOT NULL columns are supplied. Naming more would be guessing at a schema this
    -- repo does not authoritatively describe; defaults fill the rest.
    INSERT INTO equipment_catalog (category, name)
         VALUES ('__cdc_rehearsal__', '__cdc_rehearsal__')
      RETURNING id::text INTO _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id;
    IF _n <> 1 THEN
        RAISE EXCEPTION 'INSERT should have published exactly 1 event, saw %', _n;
    END IF;

    SELECT op, payload, tenant_id INTO _op, _pay, _tenant
      FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;

    IF _op <> 'INSERT' THEN RAISE EXCEPTION 'expected op=INSERT, got %', _op; END IF;

    -- The event must identify the row, or a consumer cannot re-read it. That is asserted by
    -- the count above rather than by a separate comparison: every query here filters on
    -- row_pk = _id, so "exactly 1 event matched" IS the proof that cdc_capture() stamped the
    -- correct pk. A standalone row_pk = _id check under that filter would be a tautology
    -- dressed up as a test.

    -- The allowlist must actually have produced a payload. An empty payload would mean
    -- cdc_capture() skipped every column, i.e. the allowlist does not match the table.
    IF NOT (_pay ? 'name') THEN
        RAISE EXCEPTION 'payload is missing the allowlisted column "name": %', _pay;
    END IF;

    -- equipment_catalog is GLOBAL. A non-NULL tenant here would mean CDC invented tenancy.
    IF _tenant IS NOT NULL THEN
        RAISE EXCEPTION 'tenant_id should be NULL for the global catalogue, got %', _tenant;
    END IF;
    RAISE NOTICE '  INSERT  -> published (payload keys: %)',
        (SELECT string_agg(k, ',') FROM jsonb_object_keys(_pay) k);

    -- 2. A REAL UPDATE must publish ------------------------------------------------------
    UPDATE equipment_catalog SET brand = '__cdc_changed__' WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id;
    IF _n <> 2 THEN
        RAISE EXCEPTION 'a real UPDATE should have published, total should be 2, saw %', _n;
    END IF;
    SELECT op INTO _op FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;
    IF _op <> 'UPDATE' THEN RAISE EXCEPTION 'expected op=UPDATE, got %', _op; END IF;
    RAISE NOTICE '  UPDATE  -> published';

    -- 3. A NO-OP UPDATE must publish NOTHING ---------------------------------------------
    -- THE MOST IMPORTANT ASSERTION IN THIS FILE. It is the only thing that proves
    -- WHEN (OLD.* IS DISTINCT FROM NEW.*) is doing its job. Without that clause every bulk
    -- catalogue sweep that rewrites unchanged rows would flood the outbox with non-events.
    -- If this ever starts failing, the outbox is recording WRITES, not CHANGES.
    UPDATE equipment_catalog SET brand = '__cdc_changed__' WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id;
    IF _n <> 2 THEN
        RAISE EXCEPTION
            'a no-op UPDATE must NOT publish -- expected still 2 events, saw %. '
            'The WHEN (OLD.* IS DISTINCT FROM NEW.*) clause is not suppressing it.', _n;
    END IF;
    RAISE NOTICE '  UPDATE (no-op) -> correctly suppressed';

    -- 4. DELETE must publish, and must publish the row that went away --------------------
    DELETE FROM equipment_catalog WHERE id::text = _id;

    SELECT count(*) INTO _n FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id;
    IF _n <> 3 THEN
        RAISE EXCEPTION 'DELETE should have published, total should be 3, saw %', _n;
    END IF;
    SELECT op, payload INTO _op, _pay FROM cdc_outbox
     WHERE id > _base AND source_table = 'equipment_catalog' AND row_pk = _id
     ORDER BY id DESC LIMIT 1;
    IF _op <> 'DELETE' THEN RAISE EXCEPTION 'expected op=DELETE, got %', _op; END IF;

    -- DELETE must carry OLD, not NEW. If this returned the pre-update value the capture
    -- function is publishing the wrong tuple and a consumer would act on stale state.
    IF _pay ->> 'brand' <> '__cdc_changed__' THEN
        RAISE EXCEPTION 'DELETE should publish the OLD row; brand was %', _pay ->> 'brand';
    END IF;
    RAISE NOTICE '  DELETE  -> published, carrying the OLD row';

    -- 5. Exactly one table in scope ------------------------------------------------------
    SELECT count(*) INTO _n
      FROM pg_trigger t JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE p.proname = 'cdc_capture' AND NOT t.tgisinternal
       AND t.tgrelid <> 'public.equipment_catalog'::regclass;
    IF _n <> 0 THEN
        RAISE EXCEPTION
            'SLICE-2 VIOLATION: % cdc trigger(s) on tables other than equipment_catalog', _n;
    END IF;
    RAISE NOTICE '  scope -> equipment_catalog only, as the slice claims';

    RAISE NOTICE 'REHEARSAL PASSED';
END $REH$;
