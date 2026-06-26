"""
Unit tests for app.security.audit.

Phase 6 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 32.

The writer uses a test-sink hook so we don't need to spin up SQLite /
Postgres to cover the contract. The `live` integration is exercised
end-to-end by tests/security/test_keycloak_events.py's webhook leg.
"""

from __future__ import annotations

import pytest

from app.security import audit


@pytest.fixture(autouse=True)
def _sink():
    sink: list[dict] = []
    audit.set_test_sink(sink)
    yield sink
    audit.set_test_sink(None)


# ── Core contract ───────────────────────────────────────────────────────

def test_writes_minimal_action(_sink):
    assert audit.write_audit_event("ANY_ACTION") is True
    assert _sink[0]["action"] == "ANY_ACTION"
    assert _sink[0]["user_id"] is None
    assert _sink[0]["username"] == ""
    assert _sink[0]["ip_address"] == ""
    assert _sink[0]["details"] == ""
    assert _sink[0]["tenant_id"] is None
    assert _sink[0]["agent_id"] is None


def test_empty_action_dropped(_sink):
    assert audit.write_audit_event("") is False
    assert _sink == []


def test_dict_details_serialised_as_json(_sink):
    audit.write_audit_event("X", details={"k": "v", "n": 2})
    assert _sink[0]["details"] == '{"k":"v","n":2}'


def test_str_details_passthrough(_sink):
    audit.write_audit_event("X", details="plain message")
    assert _sink[0]["details"] == "plain message"


def test_none_details_normalised(_sink):
    audit.write_audit_event("X", details=None)
    assert _sink[0]["details"] == ""


def test_unjsonable_details_repr(_sink):
    class Weird:
        def __repr__(self): return "<weird>"
    audit.write_audit_event("X", details={"obj": Weird()})
    # default=str inside json.dumps stringifies the Weird instance.
    assert "weird" in _sink[0]["details"].lower()


# ── Convenience wrappers ────────────────────────────────────────────────

def test_audit_login_success(_sink):
    audit.audit_login_success(1, "alice", "1.1.1.1", tenant_id="t-1")
    row = _sink[0]
    assert row["action"] == "LOGIN_SUCCESS"
    assert row["user_id"] == 1
    assert row["username"] == "alice"
    assert row["ip_address"] == "1.1.1.1"
    assert row["tenant_id"] == "t-1"


def test_audit_login_failed_records_reason(_sink):
    audit.audit_login_failed("bob", "2.2.2.2", reason="bad_password")
    row = _sink[0]
    assert row["action"] == "LOGIN_FAILED"
    assert row["username"] == "bob"
    assert "bad_password" in row["details"]


def test_audit_logout(_sink):
    audit.audit_logout(5, "carol", "3.3.3.3", tenant_id="t-5")
    assert _sink[0]["action"] == "LOGOUT"
    assert _sink[0]["tenant_id"] == "t-5"


def test_audit_permission_denied(_sink):
    audit.audit_permission_denied(
        "/admin/secret",
        reason="forbidden_role",
        user_id=7,
        ip="9.9.9.9",
        tenant_id="t-7",
        agent_id=None,
        extra={"required": "platform_super_admin"},
    )
    row = _sink[0]
    assert row["action"] == "PERMISSION_DENIED"
    assert "/admin/secret" in row["details"]
    assert "platform_super_admin" in row["details"]


# ── Failure semantics ───────────────────────────────────────────────────

def test_write_returns_false_on_db_failure(monkeypatch):
    """When get_db() raises the writer must NOT propagate."""
    audit.set_test_sink(None)
    def _boom():
        raise RuntimeError("oops")
    monkeypatch.setattr(audit, "_resolve_get_db", lambda: _boom)
    assert audit.write_audit_event("X") is False


def test_write_returns_false_when_get_db_unavailable(monkeypatch):
    audit.set_test_sink(None)
    monkeypatch.setattr(audit, "_resolve_get_db", lambda: None)
    assert audit.write_audit_event("X") is False


# ── SOC 2 M3.2 -- chain hashing ─────────────────────────────────────────

def test_canonical_content_treats_null_and_empty_as_equivalent():
    """Both PG-side and Python-side must agree that NULL and '' hash
    to the same string -- the migration's COALESCE pattern + the
    Python COALESCE-style fallback both collapse to empty string."""
    a = audit._canonical_audit_content(
        user_id=None, username="", action="X", ip_address="",
        details="", created_at="2026-06-26 12:00:00",
        tenant_id=None, agent_id=None,
    )
    b = audit._canonical_audit_content(
        user_id=None, username=None, action="X", ip_address=None,
        details=None, created_at="2026-06-26 12:00:00",
        tenant_id=None, agent_id=None,
    )
    assert a == b
    # Format invariant: pipe-joined, 8 fields total.
    assert a.count("|") == 7


def test_sha256_chain_hash_genesis_root():
    """Row 1's prev_hash is the GENESIS sentinel. Hash must be stable
    across runs (deterministic) and match the documented format."""
    h = audit._sha256_chain_hash(None, "user1|alice|LOGIN|1.1.1.1|||2026-06-26 12:00:00||")
    # Same input must produce the same hash.
    assert h == audit._sha256_chain_hash(None, "user1|alice|LOGIN|1.1.1.1|||2026-06-26 12:00:00||")
    # Empty prev maps to GENESIS internally.
    assert h == audit._sha256_chain_hash("", "user1|alice|LOGIN|1.1.1.1|||2026-06-26 12:00:00||")
    # Different content -> different hash.
    h2 = audit._sha256_chain_hash(None, "user1|alice|LOGOUT|1.1.1.1|||2026-06-26 12:00:00||")
    assert h != h2


def test_sha256_chain_hash_links_to_prev():
    """Row N's hash depends on row N-1's row_hash; changing prev_hash
    changes row_hash (otherwise tamper would be undetectable)."""
    content = "1|alice|LOGIN|1.1.1.1|||2026-06-26 12:00:00||"
    h1 = audit._sha256_chain_hash("abc123", content)
    h2 = audit._sha256_chain_hash("def456", content)
    assert h1 != h2


class _FakeRow(dict):
    def __getitem__(self, key):
        if isinstance(key, str):
            return dict.__getitem__(self, key)
        return list(self.values())[key]


class _FakeConn:
    """Stand-in for psycopg2/_PgConnAdapter that returns canned rows.

    `audit_logs_rows` is the seed list; `query` is the last SQL run."""
    def __init__(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.query = None
    def execute(self, sql, params=()):
        self.query = sql
        if "WHERE 1=0" in sql:
            class _C: pass
            c = _C()
            c.description = [(n,) for n in self.columns]
            return c
        if "ORDER BY id DESC LIMIT 1" in sql:
            class _C2:
                def __init__(self, r): self._r = r
                def fetchone(self): return self._r
            tail = [r for r in self.rows if r["row_hash"]]
            return _C2(_FakeRow(tail[-1]) if tail else None)
        # ORDER BY id ASC walker for verify_audit_chain
        class _C3:
            def __init__(self, rs): self._rs = rs
            def fetchall(self): return [_FakeRow(r) for r in self._rs]
        return _C3(self.rows)


def _seed_two_row_chain(extra_rows=None):
    """Build a 2-row valid chain matching the canonical format."""
    cols_phase6 = ["id","user_id","username","action","ip_address","details",
                   "created_at","prev_hash","row_hash","tenant_id","agent_id"]
    content1 = audit._canonical_audit_content(
        user_id=1, username="alice", action="LOGIN",
        ip_address="1.1.1.1", details="", created_at="2026-06-26 12:00:00",
        tenant_id=None, agent_id=None,
    )
    h1 = audit._sha256_chain_hash(None, content1)
    content2 = audit._canonical_audit_content(
        user_id=2, username="bob", action="LOGOUT",
        ip_address="2.2.2.2", details="", created_at="2026-06-26 12:01:00",
        tenant_id=None, agent_id=None,
    )
    h2 = audit._sha256_chain_hash(h1, content2)
    rows = [
        {"id": 1, "user_id": 1, "username": "alice", "action": "LOGIN",
         "ip_address": "1.1.1.1", "details": "", "created_at": "2026-06-26 12:00:00",
         "prev_hash": audit.GENESIS_HASH, "row_hash": h1,
         "tenant_id": None, "agent_id": None},
        {"id": 2, "user_id": 2, "username": "bob", "action": "LOGOUT",
         "ip_address": "2.2.2.2", "details": "", "created_at": "2026-06-26 12:01:00",
         "prev_hash": h1, "row_hash": h2,
         "tenant_id": None, "agent_id": None},
    ]
    if extra_rows:
        rows.extend(extra_rows)
    return cols_phase6, rows


def test_verify_audit_chain_clean_two_rows(_sink):
    audit.reset_schema_probe()
    cols, rows = _seed_two_row_chain()
    conn = _FakeConn(cols, rows)
    out = audit.verify_audit_chain(conn)
    assert out["total"] == 2
    assert out["verified"] == 2
    assert out["unchained"] == 0
    assert out["first_break"] is None
    assert out["last_chained_id"] == 2


def test_verify_audit_chain_detects_tampered_content(_sink):
    """Mutating any column on a row must invalidate that row's
    row_hash -- the verifier emits tamper_row_hash_mismatch."""
    audit.reset_schema_probe()
    cols, rows = _seed_two_row_chain()
    rows[1]["action"] = "TAMPERED"  # change column content; stored row_hash now wrong
    conn = _FakeConn(cols, rows)
    out = audit.verify_audit_chain(conn)
    assert out["first_break"] is not None
    assert out["first_break"]["id"] == 2
    assert out["first_break"]["reason"] == "tamper_row_hash_mismatch"
    assert out["last_chained_id"] == 1


def test_verify_audit_chain_detects_prev_hash_break(_sink):
    """Deleting (or replacing) row N's prev_hash so it doesn't match
    row N-1's row_hash must emit tamper_prev_hash_mismatch."""
    audit.reset_schema_probe()
    cols, rows = _seed_two_row_chain()
    # Force row 2's prev_hash to a fake value; row 2 content still
    # hashes correctly against its (wrong) prev_hash, so the verifier
    # falls through the row_hash check and catches the prev_hash break.
    rows[1]["prev_hash"] = "0" * 64
    rows[1]["row_hash"] = audit._sha256_chain_hash(rows[1]["prev_hash"], audit._canonical_audit_content(
        user_id=rows[1]["user_id"], username=rows[1]["username"], action=rows[1]["action"],
        ip_address=rows[1]["ip_address"], details=rows[1]["details"],
        created_at=rows[1]["created_at"],
        tenant_id=rows[1]["tenant_id"], agent_id=rows[1]["agent_id"],
    ))
    conn = _FakeConn(cols, rows)
    out = audit.verify_audit_chain(conn)
    assert out["first_break"] is not None
    assert out["first_break"]["id"] == 2
    assert out["first_break"]["reason"] == "tamper_prev_hash_mismatch"


def test_verify_audit_chain_skips_unchained_legacy_rows(_sink):
    """Rows from before migration 016 carry NULL row_hash; the
    verifier counts them as 'unchained' rather than tamper."""
    audit.reset_schema_probe()
    cols, rows = _seed_two_row_chain([
        {"id": 3, "user_id": 9, "username": "legacy", "action": "PRE_CHAIN",
         "ip_address": "9.9.9.9", "details": "", "created_at": "2026-06-26 11:00:00",
         "prev_hash": None, "row_hash": None,
         "tenant_id": None, "agent_id": None},
    ])
    conn = _FakeConn(cols, rows)
    out = audit.verify_audit_chain(conn)
    assert out["total"] == 3
    assert out["verified"] == 2
    assert out["unchained"] == 1
    assert out["first_break"] is None


def test_verify_audit_chain_reports_missing_columns(_sink):
    """A DB that hasn't applied migration 016 yet returns a clean
    'columns missing' signal rather than crashing."""
    audit.reset_schema_probe()
    cols = ["id","user_id","username","action","ip_address","details","created_at"]
    conn = _FakeConn(cols, [])
    out = audit.verify_audit_chain(conn)
    assert "error" in out
    assert "migration 016" in out["error"]
