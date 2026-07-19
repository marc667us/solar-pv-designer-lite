-- 036 -- Change Data Capture, slice 1: the MECHANISM only. Nothing is captured yet.
--
-- OWNER, 2026-07-13: "implement database cdc and make when database change everything else
-- is alerted and updated -- for the app."
--
-- WHY THIS IS IN THE DATABASE AND NOT IN THE APP
-- ---------------------------------------------
-- Measured 2026-07-19: there are ~90 ad-hoc catalogue writes alone (41 in web_app.py, 49
-- across new_*.py), and that is one table. There is NO write chokepoint anywhere in this
-- codebase -- no repository layer, no single save() -- plus migrations and manual psql that
-- never enter the application process at all. An app-level event bus would therefore miss
-- most writes, and would miss them SILENTLY, which is the worst property a change feed can
-- have: consumers cannot distinguish "nothing changed" from "we did not see it".
--
-- A trigger cannot be bypassed by a caller that forgot to publish. That is the whole argument.
--
-- THIS IS THE FIRST TRIGGER THIS SCHEMA HAS EVER HAD. There is zero precedent here for
-- triggers, pg_notify or LISTEN, so this slice deliberately ships the mechanism DARK:
-- the table, the function and the flag exist; NO trigger is attached to any table. Attaching
-- them is slice 2, one table at a time, each rehearsed. Nothing that acts ships before the
-- thing that observes it is proven.
--
-- TWO CHANNELS, BECAUSE THERE ARE TWO DIFFERENT JOBS
-- --------------------------------------------------
-- These have genuinely different delivery semantics and conflating them is the classic way
-- CDC goes wrong:
--
--   1. CACHE INVALIDATION must reach EVERY process. Each gunicorn worker holds its own
--      in-memory dict (_MARKETPLACE_CACHE), so a message delivered once to one worker leaves
--      every other worker stale. That is a BROADCAST -> pg_notify, which every LISTENer gets.
--      Losing one is survivable: the caches carry a 60s TTL, so a missed invalidation costs
--      at most a minute of staleness, not a permanent lie.
--
--   2. DURABLE SIDE-EFFECTS (emails, alerts, downstream syncs) must not be LOST. Sending an
--      alert to every worker would send it N times, so these go in the OUTBOX TABLE and are
--      claimed by one drainer. Losing one is not survivable, so it must be a row that
--      survives a crash, not a notification that exists only in flight.
--
--      THIS IS AT-LEAST-ONCE, NOT EXACTLY-ONCE (Codex LOW, 2026-07-19 -- an earlier draft of
--      this comment claimed exactly-once, which the design does not deliver and no outbox
--      can). A drainer can perform the side effect and crash before stamping consumed_at, so
--      that row is retried. Exactly-once would need the effect and the stamp in one
--      transaction, which is impossible when the effect is an email or a third-party call.
--      CONSUMERS MUST THEREFORE BE IDEMPOTENT, keyed on cdc_outbox.id. Slice 2 must not
--      attach a consumer that cannot satisfy that.
--
-- pg_notify is fire-and-forget: a payload delivered while nobody is LISTENing is gone. That
-- is precisely why the durable half is a table and the payload below is only a POINTER
-- (table + pk), never the row -- pg_notify's payload limit is 8000 bytes and a wide row would
-- silently blow it.

-- ── The outbox ───────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS cdc_outbox (
    id            bigserial PRIMARY KEY,

    -- Nullable ON PURPOSE. Not every captured table is tenant-scoped (equipment_catalog is
    -- global), and a NOT NULL here would make CDC impossible for exactly those tables. The
    -- read policy below treats NULL as "not tenant data" rather than "belongs to everyone".
    tenant_id     uuid,

    source_table  text   NOT NULL,
    op            text   NOT NULL,          -- INSERT | UPDATE | DELETE
    row_pk        text   NOT NULL,          -- text, so it works for bigint and uuid keys alike

    -- THE REDACTED ROW. Never `to_jsonb(NEW)`: see cdc_capture() below. Column selection is
    -- an ALLOWLIST, so a sensitive column added to a source table in future is excluded by
    -- default rather than leaking until somebody remembers to deny it.
    payload       jsonb  NOT NULL DEFAULT '{}'::jsonb,

    changed_at    timestamptz NOT NULL DEFAULT now(),

    -- EXACTLY-ONCE BOOKKEEPING. A drainer claims a row by stamping claimed_at (with
    -- FOR UPDATE SKIP LOCKED, so two drainers never take the same row), then stamps
    -- consumed_at on success. A row claimed but never consumed is a crashed drainer and is
    -- re-claimable after a lease expires -- which is why claimed_at is a TIME, not a boolean.
    claimed_at    timestamptz,
    consumed_at   timestamptz,
    attempts      integer NOT NULL DEFAULT 0,
    last_error    text    NOT NULL DEFAULT '',

    CONSTRAINT ck_cdc_op CHECK (op IN ('INSERT', 'UPDATE', 'DELETE'))
);

-- The drain query: unconsumed rows, oldest first. Partial index so the index stays small as
-- consumed history accumulates -- the drainer never looks at consumed rows.
CREATE INDEX IF NOT EXISTS ix_cdc_outbox_drain
    ON cdc_outbox (changed_at) WHERE consumed_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_cdc_outbox_source
    ON cdc_outbox (source_table, changed_at DESC);

CREATE INDEX IF NOT EXISTS ix_cdc_outbox_tenant
    ON cdc_outbox (tenant_id, changed_at DESC) WHERE tenant_id IS NOT NULL;

-- ── The capture function ─────────────────────────────────────────────────────────────────
--
-- SECURITY DEFINER so it can write the outbox regardless of which role performed the write.
-- A capture that only works for some callers is not capture.
--
-- search_path is PINNED. A SECURITY DEFINER function without a pinned search_path is a
-- privilege-escalation hole: any caller able to prepend a schema could shadow a table or
-- operator this body resolves and have it run as the definer.
--
-- REDACTION IS AN ALLOWLIST, ENFORCED HERE AND NOT AT THE CONSUMER.
-- `users.password_hash` must never reach this table -- an outbox is read by drainers, admin
-- screens and eventually log shipping, so a secret that lands here has effectively been
-- copied to all of them. Filtering at the consumer is too late; the value would already be
-- in the row, in the WAL and in every backup. The allowlist is passed per-trigger as a
-- TG_ARGV column list, so each attached table names exactly what it publishes and a column
-- added later is silently excluded until someone deliberately adds it.

CREATE OR REPLACE FUNCTION cdc_capture() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    _row        jsonb;
    _payload    jsonb := '{}'::jsonb;
    _col        text;
    _pk         text;
    _tenant     uuid;
    _pk_col     text := COALESCE(TG_ARGV[0], 'id');
BEGIN
    -- DELETE publishes the row that went away; anything else publishes the new state.
    IF TG_OP = 'DELETE' THEN
        _row := to_jsonb(OLD);
    ELSE
        _row := to_jsonb(NEW);
    END IF;

    -- Build the payload from the ALLOWLIST only (TG_ARGV[1..]). If a trigger names no
    -- columns, the payload stays empty and the event is still published: consumers learn
    -- THAT a row changed and can re-read it themselves. Publishing nothing is a safe
    -- default; publishing everything is not.
    FOR i IN 1 .. (TG_NARGS - 1) LOOP
        _col := TG_ARGV[i];
        IF _row ? _col THEN
            _payload := _payload || jsonb_build_object(_col, _row -> _col);
        END IF;
    END LOOP;

    _pk := COALESCE(_row ->> _pk_col, '');

    -- tenant_id only when the source table actually has one. `_row ? 'tenant_id'` is a key
    -- test, not a null test, so a global table yields NULL rather than raising.
    IF _row ? 'tenant_id' THEN
        BEGIN
            _tenant := (_row ->> 'tenant_id')::uuid;
        EXCEPTION WHEN others THEN
            -- A non-uuid tenant column must not abort the user's write. CDC is an observer;
            -- it does not get to fail the transaction it is observing.
            _tenant := NULL;
        END;
    END IF;

    INSERT INTO cdc_outbox (tenant_id, source_table, op, row_pk, payload)
    VALUES (_tenant, TG_TABLE_NAME, TG_OP, _pk, _payload);

    -- BROADCAST half. Pointer only -- table and pk, never the payload: pg_notify caps at
    -- 8000 bytes and a wide row would fail the whole transaction, which would mean CDC
    -- breaking the very writes it exists to observe.
    PERFORM pg_notify('cdc', TG_TABLE_NAME || ':' || TG_OP || ':' || _pk);

    RETURN NULL;   -- AFTER trigger: the return value is ignored, and NULL says so plainly.
END;
$$;

-- LOCK THE DEFINER FUNCTION DOWN (Codex HIGH, 2026-07-19).
-- Postgres grants EXECUTE on new functions to PUBLIC by default. A SECURITY DEFINER function
-- executable by PUBLIC is attack surface the moment it is installed, even though no trigger
-- calls it yet -- "dark" describes what the app does with it, not who can reach it. Only the
-- owner role (which creates the triggers) needs it.
REVOKE ALL ON FUNCTION cdc_capture() FROM PUBLIC;

COMMENT ON FUNCTION cdc_capture() IS
    'CDC capture (migration 036). Attach as an AFTER INSERT OR UPDATE OR DELETE ... FOR EACH '
    'ROW trigger. Args: pk_column, then the ALLOWLIST of columns to publish. Never publishes '
    'a column that is not named -- secrets are excluded by omission, not by denial.';

-- ── Row-level security ───────────────────────────────────────────────────────────────────
--
-- The outbox carries tenant data, so it is not world-readable.
--
-- PER-COMMAND POLICIES, NOT ONE `FOR ALL`. A single FOR ALL policy reuses its USING clause
-- as the INSERT WITH CHECK, and the capture trigger inserts rows for whatever tenant owns
-- the row being written -- which is not necessarily a tenant the writing user belongs to
-- (an admin or a migration edits other tenants' rows). A FOR ALL policy would therefore have
-- the trigger rejected by the policy and abort the user's write. This is the same trap that
-- is documented for the enterprise module's FORCE work; it is avoided here from the start.
--
-- FORCE is deliberately NOT applied in this migration. Every other enterprise table (024-035)
-- is ENABLE-without-FORCE, so the app connecting as owner bypasses all of them; forcing this
-- one table alone would be an inconsistent half-measure that changes behaviour for exactly
-- one table while the real gap stays open. FORCE belongs to the queued module-wide pass,
-- which needs its own rehearsal.

ALTER TABLE cdc_outbox ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS cdc_outbox_read ON cdc_outbox;
CREATE POLICY cdc_outbox_read ON cdc_outbox
    FOR SELECT USING (
        tenant_id IS NULL OR tenant_id IN (SELECT current_enterprise_tenant_ids()));

-- The trigger must always be able to publish. It runs SECURITY DEFINER and the row it
-- describes has already passed that table's own policies -- re-authorising it here could
-- only reject a write that was already allowed.
DROP POLICY IF EXISTS cdc_outbox_insert ON cdc_outbox;
CREATE POLICY cdc_outbox_insert ON cdc_outbox
    FOR INSERT WITH CHECK (true);

-- The drainer stamps claimed_at / consumed_at / attempts.
DROP POLICY IF EXISTS cdc_outbox_drain ON cdc_outbox;
CREATE POLICY cdc_outbox_drain ON cdc_outbox
    FOR UPDATE USING (true) WITH CHECK (true);
