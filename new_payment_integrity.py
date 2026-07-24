"""Payment integrity & evidence layer (Slice 1 of the payments-legal suite).

WHAT THIS PROVIDES
    1. `ensure_payment_integrity_schema(conn, is_postgres)` -- creates, idempotently:
         * `payment_events` : an APPEND-ONLY evidence ledger. Every gateway
           interaction (webhook received, signature verified/failed, payment
           recorded, duplicate blocked, refund, dispute) writes one row here,
           with a REDACTED payload, the client IP, and whether the signature
           verified. This is the "collect payment evidence" requirement and the
           legal paper-trail for chargebacks/disputes.
         * a UNIQUE index on `payments(reference)` (non-empty refs only) --
           the DB-level guarantee of "only one payment, no double payment".
           The app already does a read-then-write existence check, but that
           races under concurrent webhook retries; the unique index closes it.
    2. `record_payment_event(...)` -- append one evidence row (never raises;
       evidence collection must not break a payment).
    3. `redact_payment_payload(d)` -- strip secrets/PII before storage.

WHY A SEPARATE MODULE
    web_app.py is CRLF + mojibake and must not be edited directly. This module
    holds the pure logic; web_app.py calls into it via a small byte-patch.

DIALECT NOTES
    Timestamps are stored as TEXT ('YYYY-MM-DD HH:MM:SS') to match every other
    table in this app (see migrations/001_mirror_sqlite.sql), so cross-engine
    string comparison stays valid. The cutoff/`now` value is computed in Python
    and bound as a param -- never `datetime('now')`, which is SQLite-only and
    500s on Postgres (UndefinedFunction).
"""

from __future__ import annotations

import json
from datetime import datetime


# Fields that must NEVER be persisted in the evidence payload. Gateways echo a
# lot back; we keep only what is needed to prove what happened, not card data
# or auth secrets. Matched case-insensitively against dict keys at any depth.
_REDACT_KEYS = {
    "authorization", "card", "card_number", "cvv", "cvc", "pin", "otp",
    "password", "secret", "signature", "access_code", "auth_token", "token",
    "bank_account", "account_number", "customer_code", "authorization_code",
    "last4", "bin", "exp_month", "exp_year", "email_token",
    # PII / financial identifiers (broader webhook payloads carry these).
    "phone", "phone_number", "msisdn", "address", "billing_address",
    "shipping_address", "pan", "iban", "routing_number", "account_name",
    "name", "first_name", "last_name", "full_name", "dob", "date_of_birth",
    "national_id", "ssn", "tax_id",
}

# Cap the stored payload so a hostile/oversized gateway body can't bloat the DB.
_MAX_PAYLOAD_CHARS = 6000


def redact_payload(obj, _depth=0):
    """Return a deep copy of `obj` with sensitive keys replaced by '[redacted]'.

    Input:  any JSON-ish value (dict/list/scalar) -- typically a parsed webhook
            body or a dict summary of one.
    Output: the same shape, sensitive keys masked. Never raises; on anything it
            cannot walk it returns the string form.
    """
    try:
        if _depth > 8:
            return "[truncated-depth]"
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if isinstance(k, str) and k.lower() in _REDACT_KEYS:
                    out[k] = "[redacted]"
                else:
                    out[k] = redact_payload(v, _depth + 1)
            return out
        if isinstance(obj, (list, tuple)):
            return [redact_payload(v, _depth + 1) for v in obj[:50]]
        return obj
    except Exception:
        return str(obj)[:200]


def redact_payment_payload(obj) -> str:
    """Redact + JSON-encode + length-cap a payload for storage. Never raises."""
    try:
        s = json.dumps(redact_payload(obj), default=str, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:_MAX_PAYLOAD_CHARS]


def ensure_payment_integrity_schema(conn, is_postgres: bool = False) -> None:
    """Create the evidence ledger + the idempotency index, idempotently.

    Input:  an open DB connection (the app's get_db() wrapper) and whether the
            backend is Postgres. Output: none -- side effect is DDL.

    Safe to call on every cold start: every statement is IF NOT EXISTS.
    """
    if is_postgres:
        conn.execute(
            """
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
            )
            """
        )
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_events (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                reference          TEXT    DEFAULT '',
                gateway            TEXT    DEFAULT '',
                event_type         TEXT    DEFAULT '',
                user_id            INTEGER DEFAULT NULL,
                amount_usd         REAL    DEFAULT 0,
                signature_verified INTEGER DEFAULT 0,
                client_ip          TEXT    DEFAULT '',
                payload_redacted   TEXT    DEFAULT '',
                created_at         TEXT    DEFAULT ''
            )
            """
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payment_events_reference "
        "ON payment_events(reference)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payment_events_created "
        "ON payment_events(created_at DESC)"
    )
    # The idempotency guarantee. Partial unique index scoped to REAL gateway
    # payments (paystack/stripe) with a non-empty reference. It deliberately
    # does NOT cover reference='' (legacy/manual grants) nor non-gateway grants
    # like demo activation (reference='DEMO-14d') or multi-use upgrade codes
    # (reference=<code>), which are legitimately repeatable -- constraining them
    # would silently drop valid ledger rows (Codex slice-1 finding).
    # Supported by SQLite >= 3.8.0 and Postgres.
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_reference "
            "ON payments(reference) "
            "WHERE reference <> '' AND gateway IN ('paystack','stripe')"
        )
    except Exception:
        pass


def record_payment_event(conn, *, reference="", gateway="", event_type="",
                         user_id=None, amount_usd=0, signature_verified=False,
                         client_ip="", payload=None) -> None:
    """Append one row to the evidence ledger. NEVER raises.

    Evidence collection is best-effort: a failure to log evidence must never
    turn a good payment into a failed one. Inputs mirror the columns; `payload`
    is redacted + JSON-encoded here. `created_at` is a Python-computed UTC
    string (never datetime('now'), which is SQLite-only).
    """
    try:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO payment_events (reference, gateway, event_type, "
            "user_id, amount_usd, signature_verified, client_ip, "
            "payload_redacted, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                str(reference or "")[:200],
                str(gateway or "")[:40],
                str(event_type or "")[:60],
                user_id,
                float(amount_usd or 0),
                1 if signature_verified else 0,
                str(client_ip or "")[:64],
                redact_payment_payload(payload) if payload is not None else "",
                now,
            ),
        )
    except Exception:
        # Deliberately swallow: the ledger is evidence, not the source of truth.
        pass
