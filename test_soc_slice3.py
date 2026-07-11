"""AI-SOC Slice 3 tests — admin UI in the Operations Centre.

Acceptance (plan Slice 3): every incident + status change is visible; every
route is @admin_required; the status-change POST is CSRF-gated. No new portal.
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


def _mk_admin(app):
    uname = ("soc3_" + _uk())[:32]
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


def _mk_incident(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        eid = app.soc_capture_signal(source="backend", event_type="http_5xx",
                                     module="ui_" + _uk(), error_code="500")
        return app.soc_orchestrate(eid)


# ── admin gating ────────────────────────────────────────────────────────────

ROUTES = [
    "/admin/soc/incidents",
    "/admin/soc/approvals",
    "/admin/soc/security",
    "/admin/soc/dashboard",
]


@pytest.mark.parametrize("route", ROUTES)
def test_routes_require_admin(app, client, route):
    r = client.get(route)
    assert r.status_code in (301, 302, 401, 403)


# ── read views ──────────────────────────────────────────────────────────────

def test_incidents_list_shows_created_incident(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/soc/incidents", headers={"Accept": "application/json"})
    assert r.status_code == 200
    ids = [i["id"] for i in r.get_json()["incidents"]]
    assert inc in ids


def test_incident_detail_has_events(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/soc/incidents/%d" % inc)
    assert r.status_code == 200
    j = r.get_json()
    assert j["id"] == inc
    assert "events" in j and "actions" in j and "approvals" in j
    assert len(j["events"]) >= 1


def test_incident_detail_404_for_missing(app, client):
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/soc/incidents/99999999")
    assert r.status_code == 404


def test_approvals_and_security_panels(app, client):
    _login_admin(client, _mk_admin(app))
    assert client.get("/admin/soc/approvals").status_code == 200
    assert client.get("/admin/soc/security").status_code == 200


def test_dashboard_renders_incident(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/soc/dashboard")
    assert r.status_code == 200
    assert b"AI-SOC" in r.data


# ── status control ──────────────────────────────────────────────────────────

def test_status_requires_csrf(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.post("/admin/soc/incidents/%d/status" % inc, data={"status": "Investigating"})
    assert r.status_code == 403


def test_status_rejects_bad_value(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.post("/admin/soc/incidents/%d/status" % inc,
                    data={"_csrf": "tok", "status": "Bogus"})
    assert r.status_code == 400


def test_status_update_applies(app, client):
    inc = _mk_incident(app)
    _login_admin(client, _mk_admin(app))
    r = client.post("/admin/soc/incidents/%d/status" % inc,
                    data={"_csrf": "tok", "status": "Resolved"})
    assert r.status_code == 200 and r.get_json()["status"] == "Resolved"
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute("SELECT status FROM support_incidents WHERE id=?", (inc,)).fetchone()
            assert (row[0] if not hasattr(row, "keys") else row["status"]) == "Resolved"
