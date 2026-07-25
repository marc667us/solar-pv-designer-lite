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


# ── connection isolation (Codex C3) ─────────────────────────────────────────

class TestConnectionIsolation:
    """C3: isolation used to be enforced by CALLERS, not by this module.

    On Postgres that is not a style question. A failed statement aborts the whole
    transaction and psycopg2 then rejects every later statement on that connection with
    InFailedSqlTransaction. So "record_payment_event never raises" did NOT mean "cannot
    affect the payment": a swallowed evidence error on a SHARED connection still killed
    the caller's payment write that came afterwards.

    `connect=` moves the guarantee into the module. These tests assert the property that
    matters -- the caller's connection is untouched -- rather than the implementation.
    """

    class _PoisonOnEvidence:
        """Stands in for psycopg2's aborted-transaction behaviour.

        Any failed statement 'poisons' the connection, and every later statement on it
        raises -- which is exactly how a shared connection turns a best-effort evidence
        write into a failed payment.
        """

        def __init__(self):
            self.poisoned = False
            self.statements = []

        def execute(self, sql, params=None):
            if self.poisoned:
                raise RuntimeError("InFailedSqlTransaction: transaction is aborted")
            if "INSERT INTO payment_events" in sql:
                self.poisoned = True
                raise RuntimeError("evidence insert failed")
            self.statements.append(sql)
            return self

        def close(self):
            pass

    def test_shared_connection_is_how_a_payment_used_to_die(self):
        """Documents the hazard the isolated form exists to prevent.

        Not a regression test for our code -- it pins the BEHAVIOUR OF THE DATABASE that
        makes sharing unsafe, so nobody 'simplifies' the factory away later.
        """
        shared = self._PoisonOnEvidence()
        pi.record_payment_event(shared, reference="r1", event_type="payment_recorded")
        assert shared.poisoned, "the failed evidence write aborted the transaction"
        with pytest.raises(RuntimeError):
            shared.execute("INSERT INTO payments (user_id) VALUES (1)")

    def test_isolated_form_leaves_the_callers_connection_untouched(self):
        """The whole point: evidence failure must not reach the payment connection."""
        payment_conn = self._PoisonOnEvidence()
        broken = self._PoisonOnEvidence()
        pi.record_payment_event(connect=lambda: broken,
                                reference="r2", event_type="payment_recorded")
        assert broken.poisoned                      # the evidence connection took the hit
        assert not payment_conn.poisoned            # the payment connection did not
        payment_conn.execute("INSERT INTO payments (user_id) VALUES (1)")  # still usable

    class _OwnedConn:
        """Stands in for a connection the factory freshly opened.

        `connect` means "here is a NEW connection, you own it" -- the module closes what
        it opens. A test cannot hand over the shared fixture connection and then keep
        querying it, so this records the close rather than performing it. No __enter__:
        sqlite3/psycopg2 connections have one, but exercising the plain branch here keeps
        the two paths independently covered (the context-manager path has its own test).
        """

        def __init__(self, real):
            self._real = real
            self.closed = False

        def execute(self, *a, **k):
            return self._real.execute(*a, **k)

        def close(self):
            self.closed = True

    def test_isolated_form_actually_writes_the_row(self, conn):
        """Isolation must not be achieved by quietly not writing anything."""
        owned = self._OwnedConn(conn)
        pi.record_payment_event(connect=lambda: owned, reference="r3",
                                gateway="paystack", event_type="payment_recorded",
                                user_id=5, amount_usd=49)
        row = conn.execute(
            "SELECT reference, gateway, event_type, user_id FROM payment_events "
            "WHERE reference='r3'").fetchone()
        assert row == ("r3", "paystack", "payment_recorded", 5)

    def test_the_module_closes_the_connection_it_opened(self, conn):
        """The guarantee Codex's HIGH finding was about.

        A sqlite3/psycopg2 connection's `with` block manages the TRANSACTION and does not
        close the connection, so relying on the with-block alone leaked one connection per
        evidence write. CPython refcounting masked it; that is not a resource policy.
        """
        owned = self._OwnedConn(conn)
        pi.record_payment_event(connect=lambda: owned, reference="r7",
                                event_type="payment_recorded")
        assert owned.closed, "the module must close the connection it opened"

    def test_the_connection_is_closed_even_when_the_write_explodes(self, conn):
        """A leak on the failure path is the one that actually accumulates."""
        class Boom(self._OwnedConn):
            def execute(self, *a, **k):
                raise RuntimeError("db gone")

        owned = Boom(conn)
        pi.record_payment_event(connect=lambda: owned, reference="r8",
                                event_type="payment_recorded")
        assert owned.closed, "failure path must still release the connection"

    def test_a_factory_that_itself_explodes_is_still_swallowed(self):
        """Evidence logging cannot break a payment -- including when the DB is so far
        gone that opening a connection fails.
        """
        def boom():
            raise RuntimeError("cannot connect")
        pi.record_payment_event(connect=boom, reference="r4", event_type="x")

    def test_schema_helper_accepts_a_factory_too(self, conn):
        """Failed DDL aborts a Postgres transaction just as an INSERT does."""
        owned = self._OwnedConn(conn)
        pi.ensure_payment_integrity_schema(connect=lambda: owned, is_postgres=False)
        conn.execute("SELECT 1 FROM payment_events LIMIT 1")
        assert owned.closed

    def test_context_manager_factories_are_supported(self, conn):
        """get_db() is a context manager in this app -- the common real-world case."""
        import contextlib

        @contextlib.contextmanager
        def factory():
            yield conn

        pi.record_payment_event(connect=factory, reference="r5",
                                event_type="payment_recorded")
        assert conn.execute(
            "SELECT COUNT(*) FROM payment_events WHERE reference='r5'").fetchone()[0] == 1

    def test_the_legacy_conn_form_still_works(self, conn):
        """Back-compat: the live caller in web_app.py passes a conn and must keep working."""
        pi.record_payment_event(conn, reference="r6", event_type="payment_recorded")
        assert conn.execute(
            "SELECT COUNT(*) FROM payment_events WHERE reference='r6'").fetchone()[0] == 1

    def test_a_caller_supplied_connection_is_NEVER_closed(self, conn):
        """The severe inverse of the leak fix.

        The module closes what IT opens. Closing a connection the caller still owns would
        break the payment write that follows on the live path (web_app._record_payment
        passes its connection positionally). Ownership follows which door it came in.
        """
        owned = self._OwnedConn(conn)
        pi.record_payment_event(owned, reference="r9", event_type="payment_recorded")
        assert not owned.closed, "must not close a connection it did not open"
