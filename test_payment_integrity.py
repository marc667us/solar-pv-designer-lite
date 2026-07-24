"""Tests for new_payment_integrity.py (Slice 1: payment integrity + evidence).

Uses an in-memory SQLite DB with a minimal `payments` table so it needs no
live DB, no network, and no web_app import.
"""

from __future__ import annotations

import sqlite3

import pytest

import new_payment_integrity as pi


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id INTEGER, gateway TEXT, plan TEXT, amount_usd REAL, "
        "currency TEXT, reference TEXT, status TEXT, created_at TEXT)"
    )
    pi.ensure_payment_integrity_schema(c, is_postgres=False)
    return c


# ── redaction ───────────────────────────────────────────────────────────────

def test_redaction_masks_sensitive_keys_at_any_depth():
    payload = {
        "reference": "ps_123",
        "amount": 4900,
        "authorization": {"card_number": "4111111111111111", "last4": "1111",
                          "bin": "411111", "exp_month": "12"},
        "customer": {"email": "a@b.com", "customer_code": "CUS_x"},
        "signature": "deadbeef",
    }
    out = pi.redact_payload(payload)
    assert out["reference"] == "ps_123"
    assert out["amount"] == 4900
    assert out["authorization"] == "[redacted]"      # whole sub-obj keyed 'authorization'
    assert out["customer"]["email"] == "a@b.com"     # email kept (needed for receipts)
    assert out["customer"]["customer_code"] == "[redacted]"
    assert out["signature"] == "[redacted]"


def test_redaction_masks_pii_and_financial_keys():
    payload = {
        "phone": "+233200000000", "address": "12 Main St", "iban": "GB00XXX",
        "pan": "4111111111111111", "routing_number": "011000015",
        "account_name": "A Person", "full_name": "A Person", "reference": "keep",
    }
    out = pi.redact_payload(payload)
    for k in ("phone", "address", "iban", "pan", "routing_number",
              "account_name", "full_name"):
        assert out[k] == "[redacted]", k
    assert out["reference"] == "keep"


def test_redact_payment_payload_is_length_capped_and_never_raises():
    big = {"blob": "x" * 50000}
    s = pi.redact_payment_payload(big)
    assert len(s) <= pi._MAX_PAYLOAD_CHARS
    # A non-JSON-serialisable object still returns a string, no exception.
    assert isinstance(pi.redact_payment_payload(object()), str)


# ── idempotency (no double payment) ─────────────────────────────────────────

def test_unique_index_blocks_a_second_gateway_payment_with_same_reference(conn):
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (1, 'paystack', 'ref-1', 'success')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (1, 'paystack', 'ref-1', 'success')")


def test_empty_references_do_not_collide(conn):
    # Legacy/manual grants carry reference='' and must be allowed to repeat.
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (1, 'paystack', '', 'success')")
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (2, 'stripe', '', 'success')")
    n = conn.execute("SELECT COUNT(*) FROM payments WHERE reference=''").fetchone()[0]
    assert n == 2


def test_non_gateway_grants_with_same_reference_repeat(conn):
    # Demo activation (reference='DEMO-14d') and multi-use upgrade codes
    # (reference=<code>) legitimately repeat a reference; the index is scoped to
    # gateway IN ('paystack','stripe') so it must NOT constrain them.
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (1, 'demo', 'DEMO-14d', 'success')")
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (2, 'demo', 'DEMO-14d', 'success')")
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (3, 'code', 'PROMO50', 'success')")
    conn.execute("INSERT INTO payments (user_id, gateway, reference, status) VALUES (4, 'code', 'PROMO50', 'success')")
    assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 4


# ── evidence ledger ─────────────────────────────────────────────────────────

def test_record_payment_event_writes_a_redacted_row(conn):
    pi.record_payment_event(
        conn, reference="ps_1", gateway="paystack", event_type="charge.success",
        user_id=7, amount_usd=49, signature_verified=True, client_ip="1.2.3.4",
        payload={"reference": "ps_1", "authorization": {"card_number": "4111"}},
    )
    row = conn.execute(
        "SELECT reference, gateway, event_type, user_id, amount_usd, "
        "signature_verified, client_ip, payload_redacted, created_at "
        "FROM payment_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "ps_1" and row[1] == "paystack" and row[2] == "charge.success"
    assert row[3] == 7 and row[4] == 49 and row[5] == 1 and row[6] == "1.2.3.4"
    assert "4111" not in row[7]            # card data redacted
    assert "[redacted]" in row[7]
    assert row[8]                           # created_at populated (no datetime('now'))


def test_record_payment_event_never_raises_on_bad_conn():
    class Boom:
        def execute(self, *a, **k):
            raise RuntimeError("db gone")
    # Must swallow -- evidence logging cannot break a payment.
    pi.record_payment_event(Boom(), reference="x", event_type="y")


def test_schema_is_idempotent(conn):
    # Calling twice must not raise.
    pi.ensure_payment_integrity_schema(conn, is_postgres=False)
    pi.ensure_payment_integrity_schema(conn, is_postgres=False)
