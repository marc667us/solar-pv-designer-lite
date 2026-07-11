"""AI-SOC Slice 4 tests — Tier 1 + runbook catalogue (first automation).

Load-bearing acceptance (plan Slice 4): a runbook runs ONLY when enabled AND
automation is on; every run writes support_actions; a failed verification
triggers rollback. Default-deny is the whole point — automation OFF or runbook
disabled must NOT execute the handler.
"""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _uk():
    _SEQ[0] += 1
    return f"{_RUN}_{_SEQ[0]}"


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
    with mod.app.app_context():
        mod.soc_seed_runbooks()
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _automation(app, on, pause_tier1=False):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        app._admin_setting_set(app._SOC_AUTOMATION_KEY, "1" if on else "0")
        for a in app.SOC_AGENTS:
            app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + a, "0")
        if pause_tier1:
            app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + "tier1", "1")


def _actions(app, incident_id, status=None):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            if status:
                rows = c.execute("SELECT status FROM support_actions WHERE incident_id=? AND status=?",
                                 (incident_id, status)).fetchall()
            else:
                rows = c.execute("SELECT status FROM support_actions WHERE incident_id=?",
                                 (incident_id,)).fetchall()
            return [(r[0] if not hasattr(r, "keys") else r["status"]) for r in rows]


def _new_runbook(app, rkey, enabled=1, requires_approval=0):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            c.execute("INSERT INTO support_runbooks (rkey,name,risk_level,requires_approval,enabled) "
                      "VALUES (?,?,?,?,?)", (rkey, rkey, "low", requires_approval, enabled))


# ── catalogue ───────────────────────────────────────────────────────────────

def test_seed_creates_catalogue_dark(app):
    with app.app.app_context():
        rb = app._soc_get_runbook("noop_selftest")
    assert rb is not None
    assert rb["enabled"] is False           # ships dark


# ── the gating matrix ───────────────────────────────────────────────────────

def test_blocked_when_automation_off(app):
    _automation(app, on=False)
    calls = []
    rk = "t_off_" + _uk()
    _new_runbook(app, rk, enabled=1)
    app.soc_register_runbook_handler(rk, lambda: calls.append("do") or "ok")
    inc = 900000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["ran"] is False
    assert res["reason"] == "automation_blocked"
    assert calls == []                       # handler NEVER invoked
    assert "blocked" in _actions(app, inc)


def test_disabled_runbook_does_not_run(app):
    _automation(app, on=True)
    calls = []
    rk = "t_dis_" + _uk()
    _new_runbook(app, rk, enabled=0)         # disabled
    app.soc_register_runbook_handler(rk, lambda: calls.append("do") or "ok")
    inc = 910000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["ran"] is False
    assert res["reason"] == "runbook_not_runnable"
    assert calls == []


def test_enabled_runbook_runs_and_records(app):
    _automation(app, on=True)
    calls = []
    rk = "t_run_" + _uk()
    _new_runbook(app, rk, enabled=1)
    app.soc_register_runbook_handler(rk, lambda: calls.append("do") or "did the thing",
                                     verify=lambda: True)
    inc = 920000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["ran"] is True and res["verified"] is True and res["rolled_back"] is False
    assert calls == ["do"]
    assert "executed" in _actions(app, inc)


def test_verification_failure_triggers_rollback(app):
    _automation(app, on=True)
    events = []
    rk = "t_fail_" + _uk()
    _new_runbook(app, rk, enabled=1)
    app.soc_register_runbook_handler(
        rk,
        do=lambda: events.append("do") or "attempted",
        verify=lambda: False,                # force failure
        rollback=lambda: events.append("rollback"))
    inc = 930000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["ran"] is True
    assert res["verified"] is False
    assert res["rolled_back"] is True
    assert events == ["do", "rollback"]
    acts = _actions(app, inc)
    assert "executed" in acts and "rolled_back" in acts


def test_pause_tier1_blocks_even_with_automation_on(app):
    _automation(app, on=True, pause_tier1=True)
    calls = []
    rk = "t_pause_" + _uk()
    _new_runbook(app, rk, enabled=1)
    app.soc_register_runbook_handler(rk, lambda: calls.append("do") or "ok")
    inc = 940000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["reason"] == "automation_blocked"
    assert calls == []


def test_approval_required_runbook_not_tier1_auto(app):
    _automation(app, on=True)
    calls = []
    rk = "t_appr_" + _uk()
    _new_runbook(app, rk, enabled=1, requires_approval=1)   # needs approval
    app.soc_register_runbook_handler(rk, lambda: calls.append("do") or "ok")
    inc = 950000 + _SEQ[0]
    with app.app.app_context():
        res = app.soc_tier1_run(inc, rk)
    assert res["reason"] == "runbook_not_runnable"
    assert calls == []


# ── admin toggle ────────────────────────────────────────────────────────────

def _mk_admin(app):
    uname = ("soc4_" + _uk())[:32]
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


def test_runbooks_route_requires_admin(app, client):
    assert client.get("/admin/soc/runbooks").status_code in (301, 302, 401, 403)


def test_admin_toggle_requires_csrf_and_works(app, client):
    _login_admin(client, _mk_admin(app))
    # no csrf -> 403
    assert client.post("/admin/soc/runbooks/noop_selftest/toggle",
                       data={"value": "1"}).status_code == 403
    # with csrf -> enables
    r = client.post("/admin/soc/runbooks/noop_selftest/toggle",
                    data={"_csrf": "tok", "value": "1"})
    assert r.status_code == 200 and r.get_json()["enabled"] is True
    with app.app.app_context():
        assert app._soc_get_runbook("noop_selftest")["enabled"] is True
    # disable again to leave catalogue dark
    app.soc_set_runbook_enabled("noop_selftest", False)
