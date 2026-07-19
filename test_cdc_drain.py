"""Tests for the CDC outbox drainer (slice 3).

WHAT THESE CAN AND CANNOT PROVE. There is no local Postgres on this project (no psycopg2, no
Docker, no psql), and `cdc_outbox`, the capture triggers and `FOR UPDATE SKIP LOCKED` are all
Postgres-only. So these tests drive the route against a FAKE connection that records the SQL
it is handed. That is genuinely worth doing -- it pins the auth surface, the claim/notify/
consume ORDER, the idempotency key and the failure behaviour, which is where the design
decisions live. It does NOT prove the SQL runs on Postgres; the rehearsal workflow does that,
the same division of labour as migrations 036/037.

Run: python -m pytest test_cdc_drain.py -q
"""
import os

import pytest
from flask import Flask

import new_cdc_drain_routes as cdc


_PG_URL = "postgresql://user:pw@host/db"
_TOKEN = "test-drain-token"


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    """Records every statement; returns queued rows for the first SELECT."""

    def __init__(self, select_rows=None):
        self.statements = []          # list of (sql, params)
        self._select_rows = list(select_rows or [])

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql.lstrip().upper().startswith("SELECT"):
            rows, self._select_rows = self._select_rows, []
            return _FakeCursor(rows)
        return _FakeCursor([])

    # `with get_db() as c:` support
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def sql_text(self):
        return "\n".join(s for s, _ in self.statements)


def _make_app(conn, notify=None, token=_TOKEN, pg=True, monkeypatch=None):
    monkeypatch.setenv("CDC_DRAIN_TOKEN", token) if token is not None else \
        monkeypatch.delenv("CDC_DRAIN_TOKEN", raising=False)
    monkeypatch.setenv("DATABASE_URL", _PG_URL if pg else "sqlite:///solar.db")

    app = Flask(__name__)
    app.config["TESTING"] = True
    cdc.register_cdc_drain(app, get_db=lambda: conn, admin_notify=notify)
    return app.test_client()


def _post(client, token=_TOKEN):
    headers = {"Authorization": "Bearer " + token} if token is not None else {}
    return client.post("/cdc/outbox/drain", headers=headers)


# ── Auth surface ─────────────────────────────────────────────────────────────────────────
# All three properties are copied from /enterprise/jobs/drain and each is load-bearing.

def test_unset_token_is_404_not_an_open_door(monkeypatch):
    """A misconfiguration must make the endpoint VANISH, never make it public."""
    client = _make_app(_FakeConn(), token=None, monkeypatch=monkeypatch)
    assert _post(client, token="anything").status_code == 404


def test_missing_authorization_header_is_401(monkeypatch):
    client = _make_app(_FakeConn(), monkeypatch=monkeypatch)
    assert _post(client, token=None).status_code == 401


def test_wrong_token_is_401(monkeypatch):
    client = _make_app(_FakeConn(), monkeypatch=monkeypatch)
    assert _post(client, token="not-the-token").status_code == 401


def test_non_postgres_is_503_and_touches_nothing(monkeypatch):
    """A cron silently receiving 200 forever would hide a misconfigured environment."""
    conn = _FakeConn()
    client = _make_app(conn, pg=False, monkeypatch=monkeypatch)
    r = _post(client)
    assert r.status_code == 503
    assert conn.statements == []


# ── Claim semantics ──────────────────────────────────────────────────────────────────────

def test_empty_outbox_does_nothing_and_does_not_notify(monkeypatch):
    calls = []
    conn = _FakeConn(select_rows=[])
    client = _make_app(conn, notify=lambda *a, **k: calls.append((a, k)),
                       monkeypatch=monkeypatch)
    r = _post(client)
    assert r.status_code == 200
    assert r.get_json() == {"claimed": 0, "consumed": 0, "notified": False}
    assert calls == []
    # Nothing was claimed, so nothing may be stamped. Matched on the SET clauses, not on the
    # bare word UPDATE -- that appears in the claim's own `FOR UPDATE SKIP LOCKED`.
    assert "SET claimed_at" not in conn.sql_text()
    assert "SET consumed_at" not in conn.sql_text()


def test_claim_uses_for_update_skip_locked_and_the_drain_predicate(monkeypatch):
    """The enterprise drain gets away with an unlocked SELECT; this one must not.

    The predicate also has to keep `consumed_at IS NULL` so it can use the partial index
    ix_cdc_outbox_drain, and must bound attempts and honour the claim lease.
    """
    conn = _FakeConn(select_rows=[(7, "equipment_catalog", "INSERT", "1", {})])
    client = _make_app(conn, notify=lambda *a, **k: 1, monkeypatch=monkeypatch)
    _post(client)

    select_sql = conn.statements[0][0].upper()
    assert "FOR UPDATE SKIP LOCKED" in select_sql
    assert "CONSUMED_AT IS NULL" in select_sql
    assert "ATTEMPTS <" in select_sql
    assert "CLAIMED_AT IS NULL OR CLAIMED_AT <" in select_sql
    assert "ORDER BY CHANGED_AT" in select_sql


def test_claim_stamps_claimed_at_and_increments_attempts_FOR_THE_CLAIMED_IDS_ONLY(monkeypatch):
    """Scope matters as much as the SET clause (Codex LOW, 2026-07-19).

    The earlier version of this test asserted only the SET clauses, so it would still have
    passed if the UPDATE had stamped EVERY row in cdc_outbox -- which would claim the whole
    table on every tick and starve every other drainer. The WHERE scope and the bound
    parameters are now asserted too.
    """
    conn = _FakeConn(select_rows=[(7, "equipment_catalog", "INSERT", "1", {}),
                                  (8, "equipment_catalog", "INSERT", "2", {})])
    client = _make_app(conn, notify=lambda *a, **k: 1, monkeypatch=monkeypatch)
    _post(client)

    claim_sql, claim_params = conn.statements[1]
    assert "SET claimed_at = ?" in claim_sql
    assert "attempts = attempts + 1" in claim_sql
    # Scoped, and scoped to exactly the ids that were claimed.
    assert "WHERE id IN (?,?)" in claim_sql
    assert list(claim_params[1:]) == [7, 8]


# ── Order of operations: claim -> notify -> consume ──────────────────────────────────────

def test_rows_are_consumed_only_after_a_successful_notification(monkeypatch):
    order = []
    conn = _FakeConn(select_rows=[(9, "equipment_catalog", "UPDATE", "3", {})])

    def _notify(*a, **k):
        # At this instant the consume stamp must NOT have happened yet. Matched on
        # "SET consumed_at": the plain column name also appears in the claim predicate
        # (`WHERE consumed_at IS NULL`), so the loose form would always be true.
        order.append("notify")
        assert "SET consumed_at" not in conn.sql_text()
        return 42          # a real _admin_notify returns the new row id

    client = _make_app(conn, notify=_notify, monkeypatch=monkeypatch)
    r = _post(client)
    order.append("done")

    assert r.status_code == 200
    assert order == ["notify", "done"]
    assert "SET consumed_at = ?" in conn.sql_text()


def test_failed_notification_does_not_consume_and_records_the_error(monkeypatch):
    """Consuming on a delivery failure would turn one bad send into permanent silence."""
    conn = _FakeConn(select_rows=[(11, "equipment_catalog", "DELETE", "5", {})])

    def _boom(*a, **k):
        raise RuntimeError("brevo exploded")

    client = _make_app(conn, notify=_boom, monkeypatch=monkeypatch)
    r = _post(client)

    assert r.status_code == 500
    assert r.get_json()["consumed"] == 0
    assert "SET consumed_at" not in conn.sql_text()

    # Assert the VALUE, not just that the column was written (Codex LOW, 2026-07-19): the
    # earlier assertion would have passed even if last_error had been set to "" -- which is
    # precisely the failure that makes a stuck row undiagnosable.
    err_stmt = [(s, p) for s, p in conn.statements if "SET last_error = ?" in s]
    assert len(err_stmt) == 1
    assert "brevo exploded" in err_stmt[0][1][0]


def test_notify_returning_None_is_a_FAILURE_and_must_not_consume(monkeypatch):
    """THE REGRESSION TEST FOR THE WORST BUG IN THIS MODULE (Codex HIGH, 2026-07-19).

    `_admin_notify` never raises -- it swallows write failures and returns None. The first
    draft only handled the exception path, so a failed alert would have been treated as
    success and the rows consumed, losing those changes permanently while the module
    docstring promised nothing is ever silently dropped.
    """
    conn = _FakeConn(select_rows=[(13, "equipment_catalog", "UPDATE", "7", {})])
    client = _make_app(conn, notify=lambda *a, **k: None, monkeypatch=monkeypatch)
    r = _post(client)

    assert r.status_code == 500
    assert r.get_json()["consumed"] == 0
    assert "SET consumed_at" not in conn.sql_text()


def test_notify_returning_zero_is_DEDUPE_and_counts_as_success(monkeypatch):
    """0 means "an unread alert for this fingerprint already exists" -- the idempotency key
    working on a replayed batch. Treating it as failure would retry the batch forever."""
    conn = _FakeConn(select_rows=[(14, "equipment_catalog", "UPDATE", "8", {})])
    client = _make_app(conn, notify=lambda *a, **k: 0, monkeypatch=monkeypatch)
    r = _post(client)

    assert r.status_code == 200
    assert r.get_json()["consumed"] == 1
    assert "SET consumed_at = ?" in conn.sql_text()


# ── Idempotency: keyed on cdc_outbox.id, as migration 036 requires ───────────────────────

def test_fingerprint_is_keyed_on_the_max_outbox_id(monkeypatch):
    """At-least-once means the same batch can be replayed; the same batch must dedupe."""
    captured = {}
    rows = [(4, "equipment_catalog", "INSERT", "1", {}),
            (17, "equipment_catalog", "UPDATE", "2", {}),
            (9, "equipment_catalog", "UPDATE", "3", {})]
    conn = _FakeConn(select_rows=rows)

    def _notify(*a, **k):
        captured.update(k)
        return 42          # a real _admin_notify returns the new row id

    client = _make_app(conn, notify=_notify, monkeypatch=monkeypatch)
    r = _post(client)

    assert captured["fingerprint"] == "cdc_drain:17"
    assert captured["ref_id"] == 17
    assert captured["ref_type"] == "cdc_outbox"
    assert r.get_json()["max_outbox_id"] == 17


# ── Aggregation: one alert per pass, not one per row ─────────────────────────────────────

def test_summary_aggregates_rather_than_flooding():
    rows = [(1, "equipment_catalog", "INSERT", "a", {}),
            (2, "equipment_catalog", "UPDATE", "b", {}),
            (3, "equipment_catalog", "UPDATE", "c", {})]
    title, body, severity, max_id = cdc._summarise(rows)
    assert title == "3 database changes captured"
    assert "equipment_catalog: 1 insert, 2 update" in body
    assert severity == "info"
    assert max_id == 3


def test_single_change_is_not_pluralised():
    title, _, _, _ = cdc._summarise([(1, "equipment_catalog", "INSERT", "a", {})])
    assert title == "1 database change captured"


def test_a_delete_raises_severity_to_warning():
    """DELETE is the one op that destroys information."""
    rows = [(1, "equipment_catalog", "INSERT", "a", {}),
            (2, "equipment_catalog", "DELETE", "b", {})]
    _, _, severity, _ = cdc._summarise(rows)
    assert severity == "warning"


def test_summary_splits_by_source_table():
    """Slice 3 drains one table today, but the outbox is not single-table by design."""
    rows = [(1, "equipment_catalog", "INSERT", "a", {}),
            (2, "suppliers", "DELETE", "b", {})]
    _, body, _, _ = cdc._summarise(rows)
    assert "equipment_catalog: 1 insert" in body
    assert "suppliers: 1 delete" in body


# ── Backend detection matches get_db() exactly ───────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("postgresql://u:p@h/d", True),
    ("postgres://u:p@h/d", True),
    ("sqlite:///solar.db", False),      # the trap _inbox_is_pg exists to avoid
    ("", False),
])
def test_is_postgres_matches_get_db_detection(monkeypatch, url, expected):
    monkeypatch.setenv("DATABASE_URL", url)
    assert cdc._is_postgres() is expected
