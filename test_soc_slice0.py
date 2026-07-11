"""AI-SOC Slice 0 tests — kill switch + schema foundations (automation OFF).

The load-bearing assertion of this slice is the spec's mandate:

    "with soc_automation_enabled=false, no agent may execute any action"

so the gate `soc_automation_allowed()` must be False by default and every
future agent action funnels through it. These tests also prove the ten tables
create on the active backend, the read-only status route works, and the
kill-switch route is admin + CSRF gated.
"""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label):
    _SEQ[0] += 1
    return f"soc_{label}{_SEQ[0]}_{_RUN}"[:32]


@pytest.fixture(scope="module")
def app():
    import os
    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    spec = importlib.util.spec_from_file_location(
        "web_app", Path(__file__).resolve().parent / "web_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _mk_admin(app):
    uname = _u("a")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,is_admin,referral_code) "
                "VALUES (?,?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "T", "business", 1, _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _login_admin(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"


def _set_flags(app, enabled, automation):
    """Force the two master flags to a known state (module-scoped DB persists
    between tests, so every test sets what it needs)."""
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1" if enabled else "0")
        app._admin_setting_set(app._SOC_AUTOMATION_KEY, "1" if automation else "0")


def _clear_pauses(app):
    with app.app.app_context():
        for a in app.SOC_AGENTS:
            app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + a, "0")


# ── the load-bearing default ────────────────────────────────────────────────

def test_automation_off_by_default(app):
    _set_flags(app, enabled=False, automation=False)
    with app.app.app_context():
        assert app.soc_enabled() is False
        assert app.soc_automation_enabled() is False
        assert app.soc_kill_switch_engaged() is True
        # THE gate: no agent may act.
        assert app.soc_automation_allowed() is False
        assert app.soc_automation_allowed("tier1") is False


def test_gate_requires_both_flags(app):
    # soc_enabled alone is not enough — automation must also be on.
    _set_flags(app, enabled=True, automation=False)
    with app.app.app_context():
        assert app.soc_automation_allowed() is False
    _set_flags(app, enabled=False, automation=True)
    with app.app.app_context():
        assert app.soc_automation_allowed() is False
    _set_flags(app, enabled=True, automation=True)
    with app.app.app_context():
        assert app.soc_automation_allowed() is True


def test_agent_pause_isolates_one_agent(app):
    _set_flags(app, enabled=True, automation=True)
    _clear_pauses(app)
    with app.app.app_context():
        app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + "tier1", "1")
        assert app.soc_automation_allowed() is True          # global still on
        assert app.soc_automation_allowed("tier1") is False  # this one paused
        assert app.soc_automation_allowed("tier2") is True   # others unaffected
        # an unknown agent name is never "paused" (defensive).
        assert app.soc_agent_paused("not_a_real_agent") is False


# ── schema ──────────────────────────────────────────────────────────────────

def test_schema_creates_all_ten_tables(app):
    assert len(app.SOC_TABLE_NAMES) == 10
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            for name in app.SOC_TABLE_NAMES:
                # a plain COUNT proves the table exists on the active backend.
                r = c.execute("SELECT COUNT(*) FROM " + name).fetchone()
                assert r is not None


def test_every_soc_table_carries_tenant_id(app):
    # Multi-tenant discipline (Directive §6): every operational table has tenant_id
    # so the 022 RLS migration can layer on.
    for name, cols, _idx in app._SOC_TABLES:
        assert "tenant_id" in cols, f"{name} missing tenant_id"


def test_schema_has_spec_columns(app):
    # Requirement fidelity (agentic support.txt): the runbook table must carry the
    # exact RemediationRunbook shape (L644-655) and the incident/security/knowledge
    # records must carry human_reviewer (Pass C §14, L1944). Drop+recreate so this
    # asserts the ACTUAL DDL, not a stale table left by an earlier run
    # (CREATE IF NOT EXISTS won't add columns to a pre-existing table).
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            for t in app.SOC_TABLE_NAMES:
                c.execute("DROP TABLE IF EXISTS " + t)
        with get_db() as c:
            app._ensure_soc_schema(c)

            def cols(t):
                return {r[1] for r in c.execute("PRAGMA table_info(" + t + ")").fetchall()}

            runbook = cols("support_runbooks")
            for need in ("name", "category", "allowed_tiers", "risk_level",
                         "requires_approval", "steps", "verification_steps",
                         "rollback_steps", "enabled"):
                assert need in runbook, f"support_runbooks missing spec column {need}"
            for t in ("support_incidents", "security_incidents", "knowledge_articles"):
                assert "human_reviewer" in cols(t), f"{t} missing human_reviewer"


# ── routes ──────────────────────────────────────────────────────────────────

def test_status_route_requires_admin(app, client):
    # anonymous -> must NOT get a 200 JSON body.
    r = client.get("/admin/soc/status")
    assert r.status_code in (301, 302, 401, 403)


def test_status_route_reports_flags_and_counts(app, client):
    _set_flags(app, enabled=False, automation=False)
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/soc/status", headers={"Accept": "application/json"})
    assert r.status_code == 200
    j = r.get_json()
    assert j["soc_enabled"] is False
    assert j["soc_automation_enabled"] is False
    assert j["automation_allowed"] is False
    assert set(j["table_row_counts"].keys()) == set(app.SOC_TABLE_NAMES)
    assert set(j["agents"]) == set(app.SOC_AGENTS)


def test_kill_switch_requires_admin(app, client):
    # anonymous POST must be rejected (not a 200 success).
    r = client.post("/admin/soc/kill-switch",
                    data={"flag": "soc_enabled", "value": "1"})
    assert r.status_code in (301, 302, 401, 403)


def test_kill_switch_requires_csrf(app, client):
    _login_admin(client, _mk_admin(app))
    # authenticated admin, no _csrf -> csrf_protect() aborts 403.
    r = client.post("/admin/soc/kill-switch",
                    data={"flag": "soc_enabled", "value": "1"})
    assert r.status_code == 403


def test_kill_switch_toggles_and_gate_follows(app, client):
    _set_flags(app, enabled=False, automation=False)
    _login_admin(client, _mk_admin(app))
    hdr = {"Accept": "application/json"}

    # turn the subsystem on
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "flag": "soc_enabled", "value": "1"},
                    headers=hdr)
    assert r.status_code == 200 and r.get_json()["soc_enabled"] is True
    # still braked: automation flag not yet on
    assert r.get_json()["automation_allowed"] is False

    # enable automation
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "flag": "soc_automation_enabled", "value": "1"},
                    headers=hdr)
    assert r.get_json()["automation_allowed"] is True

    # hit the kill switch — automation off again
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "flag": "soc_automation_enabled", "value": "0"},
                    headers=hdr)
    assert r.get_json()["automation_allowed"] is False


def test_kill_switch_rejects_unknown_flag_and_agent(app, client):
    _login_admin(client, _mk_admin(app))
    hdr = {"Accept": "application/json"}
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "flag": "not_a_flag", "value": "1"},
                    headers=hdr)
    assert r.status_code == 400
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "pause_agent": "not_an_agent", "value": "1"},
                    headers=hdr)
    assert r.status_code == 400


def test_pause_agent_via_route(app, client):
    _set_flags(app, enabled=True, automation=True)
    _clear_pauses(app)
    _login_admin(client, _mk_admin(app))
    hdr = {"Accept": "application/json"}
    r = client.post("/admin/soc/kill-switch",
                    data={"_csrf": "tok", "pause_agent": "security", "value": "1"},
                    headers=hdr)
    assert r.status_code == 200
    with app.app.app_context():
        assert app.soc_agent_paused("security") is True
        assert app.soc_automation_allowed("security") is False
        assert app.soc_automation_allowed("tier1") is True


# ── RLS migration ───────────────────────────────────────────────────────────

def test_rls_migration_covers_every_table(app):
    sql = (Path(__file__).resolve().parent / "migrations" / "022_soc_rls.sql").read_text()
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "current_user_is_admin()" in sql
    for name in app.SOC_TABLE_NAMES:
        assert name in sql, f"022_soc_rls.sql does not mention {name}"
