"""AI-SOC Slice 7 tests — Tier 3 repair package + approval gate.

Load-bearing acceptance (plan Slice 7): "no code path exists by which an agent
can deploy to production." Proven two ways here:
  (a) behaviour — approving an approval leaves the deployment_change 'proposed',
      never 'deployed';
  (b) structure — no SOC module contains a production-deploy MECHANISM
      (subprocess / gh workflow / Render deploy API / os.system).
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
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _mk_incident(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        eid = app.soc_capture_signal(source="backend", event_type="http_5xx",
                                     module="t3_" + _uk(), error_code="500")
        return app.soc_orchestrate(eid)


def _mk_admin(app):
    uname = ("soc7_" + _uk())[:32]
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


# ── package + request ───────────────────────────────────────────────────────

def test_repair_package_has_spec_fields(app):
    inc = _mk_incident(app)
    with app.app.app_context():
        pkg = app.soc_tier3_build_repair_package(inc)
    for k in ("incident_id", "error_details", "module", "logs", "repro_steps",
              "expected", "actual", "severity", "related_files", "related_endpoint",
              "related_tables", "tenant_impact", "proposed_tests"):
        assert k in pkg


def test_open_repair_creates_pending_approval_and_proposed_dc(app):
    inc = _mk_incident(app)
    with app.app.app_context():
        from web_app import get_db
        res = app.soc_tier3_open_repair(inc)
        assert res and res["approval_id"] and res["deployment_change_id"]
        with get_db() as c:
            ap = c.execute("SELECT status FROM support_approvals WHERE id=?",
                           (res["approval_id"],)).fetchone()
            dc = c.execute("SELECT status FROM deployment_changes WHERE id=?",
                           (res["deployment_change_id"],)).fetchone()
            assert (ap[0] if not hasattr(ap, "keys") else ap["status"]) == "pending"
            assert (dc[0] if not hasattr(dc, "keys") else dc["status"]) == "proposed"


# ── the load-bearing acceptance: approval != deploy ─────────────────────────

def test_approval_does_not_deploy(app):
    inc = _mk_incident(app)
    with app.app.app_context():
        from web_app import get_db
        res = app.soc_tier3_open_repair(inc)
        ok = app.soc_decide_approval(res["approval_id"], True, user_id=1)
        assert ok is True
        with get_db() as c:
            ap = c.execute("SELECT status FROM support_approvals WHERE id=?",
                           (res["approval_id"],)).fetchone()
            dc = c.execute("SELECT status FROM deployment_changes WHERE id=?",
                           (res["deployment_change_id"],)).fetchone()
            # approval is approved ...
            assert (ap[0] if not hasattr(ap, "keys") else ap["status"]) == "approved"
            # ... but NOTHING deployed: the deployment_change is still 'proposed'.
            assert (dc[0] if not hasattr(dc, "keys") else dc["status"]) == "proposed"


def test_no_deploy_mechanism_anywhere_in_soc(app):
    """Structural proof: no AI-SOC python module contains a production-deploy
    mechanism, and no soc_deploy-style symbol exists."""
    root = Path(__file__).resolve().parent
    # MECHANISMS that could actually trigger a deploy from app runtime — not mere
    # descriptive mentions of the human-run workflow (which are allowed in docs).
    forbidden = ("subprocess", "os.system", "api.render.com", "/deploys",
                 "RENDER_API_KEY", "requests.post", "requests.put", "os.popen")
    for f in sorted(root.glob("new_soc_slice*.py")):
        text = f.read_text(encoding="utf-8", errors="replace")
        for tok in forbidden:
            assert tok not in text, f"{f.name} contains deploy mechanism '{tok}'"
    for sym in ("soc_deploy", "soc_production_deploy", "soc_apply_to_production",
                "soc_ship"):
        assert getattr(app, sym, None) is None, f"unexpected deploy symbol {sym}"


# ── admin decide route ──────────────────────────────────────────────────────

def test_decide_route_requires_admin_and_csrf(app, client):
    inc = _mk_incident(app)
    with app.app.app_context():
        res = app.soc_tier3_open_repair(inc)
    aid = res["approval_id"]
    # anon
    assert client.post("/admin/soc/approvals/%d/decide" % aid,
                       data={"decision": "approve"}).status_code in (301, 302, 401, 403)
    # admin without csrf
    _login_admin(client, _mk_admin(app))
    assert client.post("/admin/soc/approvals/%d/decide" % aid,
                       data={"decision": "approve"}).status_code == 403
    # admin with csrf
    r = client.post("/admin/soc/approvals/%d/decide" % aid,
                    data={"_csrf": "tok", "decision": "approve"})
    assert r.status_code == 200 and r.get_json()["status"] == "approved"


def test_disabled_returns_none(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "0")
        assert app.soc_tier3_open_repair(1) is None
