-- 039_payment_evidence_and_idempotency.sql
-- Slice 1 of the payments-legal suite.
--
--   1. payment_events : APPEND-ONLY evidence ledger. Every gateway interaction
--      writes one row with a REDACTED payload, the client IP, and whether the
--      signature verified. This is the legal paper-trail for disputes/
--      chargebacks ("collect payment evidence").
--   2. ux_payments_reference : a PARTIAL UNIQUE index over non-empty references
--      of REAL gateway payments (paystack/stripe) -- the DB-level guarantee of
--      "only one payment, no double payment". The app already does a
--      read-then-write existence check, but that races under concurrent webhook
--      retries; the unique index closes it. It deliberately EXCLUDES demo
--      activation and multi-use upgrade codes (which legitimately repeat a
--      reference) by scoping to gateway IN ('paystack','stripe').
--
-- Idempotent (IF NOT EXISTS throughout) and safe to re-run. Postgres only
-- (the SQLite build creates the same shapes via new_payment_integrity.py on
-- first payment).

CREATE TABLE IF NOT EXISTS payment_events (
    id                 SERIAL PRIMARY KEY,
    reference          TEXT    DEFAULT '',
    gateway            TEXT    DEFAULT '',
    event_type         TEXT    DEFAULT '',
    user_id            INTEGER DEFAULT NULL,
    amount_usd         REAL    DEFAULT 0,
    signature_verified INTEGER DEFAULT 0,
    client_ip          TEXT    DEFAULT '',
    payload_redacted   TEXT    DEFAULT '',
    created_at         TEXT    DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_payment_events_reference ON payment_events(reference);
CREATE INDEX IF NOT EXISTS idx_payment_events_created   ON payment_events(created_at DESC);

-- Guard: refuse to add the unique index if live data already violates it,
-- with a clear message, rather than letting CREATE UNIQUE INDEX fail opaquely.
DO $$
DECLARE dup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO dup_count FROM (
        SELECT reference FROM payments
         WHERE reference IS NOT NULL AND reference <> ''
           AND gateway IN ('paystack','stripe')
         GROUP BY reference HAVING COUNT(*) > 1
    ) d;
    IF dup_count > 0 THEN
        RAISE EXCEPTION
          'payments has % duplicate non-empty reference(s); resolve before adding the UNIQUE index',
          dup_count;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_reference
    ON payments(reference) WHERE reference <> '' AND gateway IN ('paystack','stripe');
