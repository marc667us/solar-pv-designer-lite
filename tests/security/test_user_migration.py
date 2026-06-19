"""
Unit tests for scripts/migrate_users_to_keycloak.py.

Phase 7 task 33 deliverable. Covers the pure-Python mapping layer
(role assignment + user-representation build) and the partial-import
HTTP path (mocked requests.post). No live DB or Keycloak required.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# Load the script as a module (it's outside the regular package tree).
SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts" / "migrate_users_to_keycloak.py"
)


@pytest.fixture(scope="module")
def mig():
    spec = importlib.util.spec_from_file_location(
        "migrate_users_to_keycloak", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_users_to_keycloak"] = module
    spec.loader.exec_module(module)
    return module


# ── Role mapping ────────────────────────────────────────────────────────

@pytest.mark.parametrize("row, expected", [
    ({"is_admin": 1, "role": ""},                ["platform_super_admin"]),
    ({"is_admin": 1, "role": "admin"},           ["platform_super_admin"]),
    ({"is_admin": 1, "role": "platform_admin"},  ["platform_super_admin"]),
    ({"is_admin": 0, "role": "supplier_admin"},  ["supplier_admin"]),
    ({"is_admin": 0, "role": "supplier_user"},   ["supplier_user"]),
    ({"is_admin": 0, "role": "procurement_specialist"},
                                                  ["procurement_specialist"]),
    ({"is_admin": 0, "role": "tenant_admin"},    ["tenant_admin"]),
    ({"is_admin": 0, "role": "marketplace_admin"},
                                                  ["marketplace_admin"]),
    ({"is_admin": 0, "role": "finance_officer"}, ["finance_officer"]),
    ({"is_admin": 0, "role": "support_agent"},   ["support_agent"]),
    ({"is_admin": 0, "role": "catalogue_manager"},
                                                  ["catalogue_manager"]),
    ({"is_admin": 0, "role": "customer"},        ["customer"]),
    # Legacy default: non-admin with no role -> solar_engineer
    ({"is_admin": 0, "role": ""},                ["solar_engineer"]),
    ({"is_admin": 0, "role": None},              ["solar_engineer"]),
    # Unknown role -> least privilege
    ({"is_admin": 0, "role": "wizard"},          ["customer"]),
])
def test_map_realm_roles(mig, row, expected):
    assert mig.map_realm_roles(row) == expected


def test_map_realm_roles_case_insensitive(mig):
    assert mig.map_realm_roles(
        {"is_admin": 0, "role": "Supplier_Admin"}
    ) == ["supplier_admin"]


# ── Name splitting ──────────────────────────────────────────────────────

@pytest.mark.parametrize("name, expected", [
    ("Alice Adams",            ("Alice", "Adams")),
    ("Bob",                    ("Bob",   "")),
    ("Catherine de la Mer",    ("Catherine", "de la Mer")),
    ("",                       ("", "")),
    (None,                     ("", "")),
])
def test_split_name(mig, name, expected):
    assert mig._split_name(name) == expected


# ── UserRepresentation ──────────────────────────────────────────────────

def test_build_user_representation_minimal(mig):
    row = {
        "id": 1, "username": "alice", "email": "alice@example.com",
        "name": "Alice Adams",
        "company": None, "country": None, "plan": None,
        "is_admin": 0, "role": "",
        "email_verified": 1,
        "trial_end_date": None, "referral_code": None,
    }
    u = mig.build_user_representation(row)
    assert u["username"] == "alice"
    assert u["email"] == "alice@example.com"
    assert u["emailVerified"] is True
    assert u["enabled"] is True
    assert u["firstName"] == "Alice"
    assert u["lastName"] == "Adams"
    assert u["requiredActions"] == ["UPDATE_PASSWORD"]
    assert u["realmRoles"] == ["solar_engineer"]
    assert u["attributes"] == {}  # all the optional attrs were None


def test_build_user_representation_with_attributes(mig):
    row = {
        "id": 2, "username": "bob", "email": "bob@example.com",
        "name": "Bob",
        "company": "Acme", "country": "GH", "plan": "professional",
        "is_admin": 1, "role": "admin",
        "email_verified": 0,
        "trial_end_date": "2026-07-01",
        "referral_code": "BOB12345",
    }
    u = mig.build_user_representation(row)
    assert u["emailVerified"] is False
    assert u["realmRoles"] == ["platform_super_admin"]
    assert u["attributes"]["country"] == ["GH"]
    assert u["attributes"]["company"] == ["Acme"]
    assert u["attributes"]["plan"] == ["professional"]
    assert u["attributes"]["trial_end_date"] == ["2026-07-01"]
    assert u["attributes"]["referral_code"] == ["BOB12345"]


def test_build_user_representation_strips_empty_attributes(mig):
    row = {
        "id": 3, "username": "carol", "email": "carol@example.com",
        "name": "Carol",
        "company": "", "country": "", "plan": "free",
        "is_admin": 0, "role": "",
        "email_verified": 0,
        "trial_end_date": "", "referral_code": "",
    }
    u = mig.build_user_representation(row)
    # plan="free" is non-empty so it survives; the empty strings drop.
    assert u["attributes"] == {"plan": ["free"]}


# ── Admin token ─────────────────────────────────────────────────────────

def test_admin_token_happy_path(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "http://kc.test/realms/solarpro")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"access_token": "ey.admin"}
    with patch.object(mig.requests, "post", return_value=resp):
        token = mig._admin_token("solarpro-admin-console", "secret")
    assert token == "ey.admin"


def test_admin_token_missing_issuer_raises(mig, monkeypatch):
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    with pytest.raises(SystemExit, match="KEYCLOAK_ISSUER"):
        mig._admin_token("c", "s")


def test_admin_token_bad_status_raises(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "http://kc.test/realms/solarpro")
    bad = MagicMock(status_code=401, text='{"error":"invalid_client"}')
    with patch.object(mig.requests, "post", return_value=bad):
        with pytest.raises(SystemExit, match="401"):
            mig._admin_token("c", "s")


# ── Realm resolution ────────────────────────────────────────────────────

def test_resolve_realm_extracts_name(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "https://auth.aiappinvent.com/realms/solarpro")
    assert mig._resolve_realm() == "solarpro"


def test_resolve_realm_extracts_with_trailing_slash(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "https://kc.test/realms/myrealm/")
    assert mig._resolve_realm() == "myrealm"


def test_resolve_realm_rejects_missing_segment(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER", "https://kc.test/auth")
    with pytest.raises(SystemExit, match="realms"):
        mig._resolve_realm()


def test_admin_base_combines_correctly(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "https://kc.test/realms/solarpro")
    assert mig._admin_base() == "https://kc.test/admin/realms/solarpro"


# ── push_partial_import ─────────────────────────────────────────────────

def test_push_partial_import_happy_path(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "https://kc.test/realms/solarpro")
    token_resp = MagicMock(status_code=200)
    token_resp.json.return_value = {"access_token": "ey.admin"}
    import_resp = MagicMock(status_code=200)
    import_resp.json.return_value = {"added": 3, "skipped": 1, "overwritten": 0}
    with patch.object(mig.requests, "post",
                      side_effect=[token_resp, import_resp]) as p:
        result = mig.push_partial_import(
            [{"username": "alice"}, {"username": "bob"}, {"username": "carol"}],
            if_exists="SKIP",
            client_id="solarpro-admin-console",
            client_secret="s",
        )
    assert result["added"] == 3
    assert p.call_count == 2

    # Confirm the import call shape.
    import_call = p.call_args_list[1]
    assert import_call.args[0].endswith("/admin/realms/solarpro/partialImport")
    sent = import_call.kwargs["json"]
    assert sent["ifResourceExists"] == "SKIP"
    assert len(sent["users"]) == 3
    assert import_call.kwargs["headers"]["Authorization"] == "Bearer ey.admin"


def test_push_partial_import_bad_status_raises(mig, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_ISSUER",
                       "https://kc.test/realms/solarpro")
    token_resp = MagicMock(status_code=200)
    token_resp.json.return_value = {"access_token": "ey.admin"}
    bad = MagicMock(status_code=409, text='{"errorMessage":"conflict"}')
    with patch.object(mig.requests, "post",
                      side_effect=[token_resp, bad]):
        with pytest.raises(SystemExit, match="409"):
            mig.push_partial_import(
                [], if_exists="FAIL",
                client_id="c", client_secret="s",
            )
