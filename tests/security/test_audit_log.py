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
