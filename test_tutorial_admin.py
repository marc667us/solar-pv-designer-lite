"""Tutorial Manager (AC11) + Analytics (AC12) tests.

Load-bearing acceptance from pvsolar1/"video tutorial.txt":
  AC11 — admin can enable/disable tutorials (persisted; reflected in config).
  AC12 — tutorial analytics are recorded and summarised.
Plus: RBAC (admin routes deny anon), the config/event endpoints behave, and the
analytics-off switch truly stops recording.
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
    uname = ("tut_" + _uk())[:32]
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


# ── config endpoint (drives the engine gate) ────────────────────────────────

def test_config_defaults_enabled(app, client):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_MASTER_KEY, "1")
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
    r = client.get("/api/tutorial/config")
    assert r.status_code == 200
    j = r.get_json()
    assert j["enabled"] is True and j["analytics"] is True
    assert isinstance(j["disabled"], list)


# ── AC11: enable/disable persists + is reflected in config ──────────────────

def test_disable_then_enable_roundtrip(app):
    slug = "dashboard"
    with app.app.app_context():
        app._admin_setting_set(app._TUT_MASTER_KEY, "1")
        app.tutorial_set_disabled(slug, False)   # clean baseline: enabled
        assert app.tutorial_is_enabled(slug) is True
        assert app.tutorial_set_disabled(slug, True) is False   # now disabled
        assert app.tutorial_is_enabled(slug) is False
        assert slug in app.tutorial_disabled_slugs()
        assert app.tutorial_set_disabled(slug, False) is True    # re-enabled
        assert app.tutorial_is_enabled(slug) is True


def test_master_switch_off_disables_all(app):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_MASTER_KEY, "0")
        assert app.tutorial_is_enabled("dashboard") is False
        app._admin_setting_set(app._TUT_MASTER_KEY, "1")


def test_set_disabled_rejects_bad_slug(app):
    with app.app.app_context():
        assert app.tutorial_set_disabled("../etc/passwd", True) is None
        assert app.tutorial_set_disabled("Bad Slug!", True) is None


def test_toggle_route_persists_and_reflects_in_config(app, client):
    slug = "marketplace_public"
    _login_admin(client, _mk_admin(app))
    # enable baseline
    with app.app.app_context():
        app.tutorial_set_disabled(slug, False)
        app._admin_setting_set(app._TUT_MASTER_KEY, "1")
    # disable via route (JSON response)
    r = client.post("/admin/tutorials/%s/toggle" % slug,
                    data={"_csrf": "tok", "disable": "1"},
                    headers={"Accept": "application/json"})
    assert r.status_code == 200 and r.get_json()["enabled"] is False
    # config now lists it disabled
    cfg = client.get("/api/tutorial/config").get_json()
    assert slug in cfg["disabled"]


def test_toggle_requires_admin_and_csrf(app, client):
    slug = "landing"
    # anon
    assert client.post("/admin/tutorials/%s/toggle" % slug,
                       data={"disable": "1"}).status_code in (301, 302, 401, 403)
    # admin, no csrf
    _login_admin(client, _mk_admin(app))
    assert client.post("/admin/tutorials/%s/toggle" % slug,
                       data={"disable": "1"}).status_code == 403


# ── AC12: analytics recorded + summarised ───────────────────────────────────

def test_record_event_and_summary(app):
    page = "boms_list"
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
        assert app.tutorial_record_event(page, "started", mode="auto", total_steps=5) is True
        assert app.tutorial_record_event(page, "step_shown", step_index=0, step_title="Open") is True
        assert app.tutorial_record_event(page, "completed", step_index=4, total_steps=5) is True
        summary = app.tutorial_analytics_summary()
    assert summary["events"] >= 3
    assert summary["totals"].get("started", 0) >= 1
    assert summary["totals"].get("completed", 0) >= 1
    assert any(p["page"] == page for p in summary["by_page"])


def test_record_event_rejects_bad_type_and_slug(app):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
        assert app.tutorial_record_event("dashboard", "not_an_event") is False
        assert app.tutorial_record_event("../bad", "started") is False


def test_analytics_off_stops_recording(app):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "0")
        assert app.tutorial_record_event("dashboard", "started") is False
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")


def test_event_endpoint_accepts_beacon(app, client):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
    r = client.post("/api/tutorial/event",
                    json={"page": "dashboard", "event_type": "started",
                          "mode": "guided", "total_steps": 4})
    assert r.status_code == 202 and r.get_json()["ok"] is True


def test_event_endpoint_survives_non_object_body(app, client):
    """Codex HIGH regression: a JSON array/string/number parses but has no
    .get() — the beacon path must normalise to {} and never 500."""
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
    for bad in ([1, 2, 3], "hello", 42):
        r = client.post("/api/tutorial/event", json=bad)
        assert r.status_code == 202, "non-object body must not 500 (got %s)" % r.status_code
        assert r.get_json()["ok"] is False


def test_event_endpoint_drops_forged_type(app, client):
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
    r = client.post("/api/tutorial/event",
                    json={"page": "dashboard", "event_type": "DROP TABLE"})
    assert r.status_code == 202 and r.get_json()["ok"] is False


def test_step_replayed_is_recorded(app):
    """AC12 fidelity: a Prev/Restart replay is an accepted event type."""
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
        assert app.tutorial_record_event("dashboard", "step_replayed",
                                         step_index=1, step_title="Create") is True
        summary = app.tutorial_analytics_summary()
    assert summary["totals"].get("step_replayed", 0) >= 1


def test_avg_completion_seconds_from_duration(app):
    """AC12 fidelity: average completion TIME comes from completed durations."""
    page = "settings"
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
        app.tutorial_record_event(page, "completed", step_index=3,
                                  total_steps=4, duration_ms=8000)
        summary = app.tutorial_analytics_summary()
    assert "avg_completion_seconds" in summary
    assert summary["avg_completion_seconds"] > 0


def test_step_failed_feeds_most_confusing(app):
    page = "procurement_center"
    with app.app.app_context():
        app._admin_setting_set(app._TUT_ANALYTICS_KEY, "1")
        app.tutorial_record_event(page, "step_failed", step_index=2, step_title="Pick supplier")
        app.tutorial_record_event(page, "step_failed", step_index=2, step_title="Pick supplier")
        summary = app.tutorial_analytics_summary()
    hit = [m for m in summary["most_confusing"] if m["page"] == page]
    assert hit and hit[0]["fails"] >= 2


# ── admin pages render + RBAC ───────────────────────────────────────────────

def test_manager_page_requires_admin(app, client):
    assert client.get("/admin/tutorials").status_code in (301, 302, 401, 403)
    assert client.get("/admin/tutorials/analytics").status_code in (301, 302, 401, 403)


def test_manager_page_lists_scenarios_for_admin(app, client):
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/tutorials")
    assert r.status_code == 200
    assert b"Tutorial Manager" in r.data


def test_analytics_json_shape(app, client):
    _login_admin(client, _mk_admin(app))
    r = client.get("/admin/tutorials/analytics?format=json")
    assert r.status_code == 200
    j = r.get_json()
    for k in ("totals", "avg_completion_pct", "by_page", "most_confusing", "events"):
        assert k in j


def test_list_scenarios_reads_disk(app):
    with app.app.app_context():
        scenarios = app.tutorial_list_scenarios()
    # 60 scenario files ship in static/tutorial/scenarios/
    assert len(scenarios) >= 50
    assert all("slug" in s and "enabled" in s for s in scenarios)
