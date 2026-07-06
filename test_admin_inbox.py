"""Tests for the Admin Notification Inbox + device alerting (owner feature #3).

Covers:
  - _admin_notify writes a row; unread count tracks it; fingerprint dedupe
    suppresses a repeat within the window.
  - /admin/inbox renders for admin, 403 for non-admin, redirect for anon.
  - /admin/inbox/status JSON shape (unread / latest_id / alerts_enabled).
  - mark-read + mark-all-read (CSRF enforced).
  - settings toggle flips alerts_enabled.
  - /admin/inbox/test creates a notification.
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
    return f"inbox_{label}{_SEQ[0]}_{_RUN}"[:32]


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


def _mk_user(app, is_admin=0):
    uname = _u("a" if is_admin else "u")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,is_admin,referral_code) "
                "VALUES (?,?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "T", "business", is_admin, _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _as(client, uid, csrf="tok"):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "t"
        s["_csrf"] = csrf


# ── Writer + dedupe ──────────────────────────────────────────────────────────
def test_admin_notify_writes_and_counts(app):
    with app.app.app_context():
        before = app._inbox_unread_count()
        nid = app._admin_notify("test", "info", "Hello inbox", "body text")
        after = app._inbox_unread_count()
    assert nid and nid > 0
    assert after == before + 1


def test_admin_notify_fingerprint_dedupes(app):
    fp = "fp_" + _RUN
    with app.app.app_context():
        a = app._admin_notify("error", "critical", "Boom", "x", fingerprint=fp)
        b = app._admin_notify("error", "critical", "Boom again", "y", fingerprint=fp)
    assert a and a > 0
    assert b == 0  # deduped within window


def test_admin_notify_severity_normalised(app):
    title = "Sev probe " + _RUN
    with app.app.app_context():
        app._admin_notify("system", "not-a-severity", title)
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT severity FROM admin_notifications WHERE title=? ORDER BY id DESC LIMIT 1",
                (title,)).fetchone()
    assert row[0] == "info"


# ── Inbox page RBAC ──────────────────────────────────────────────────────────
def test_inbox_admin_renders(app, client):
    uid = _mk_user(app, is_admin=1)
    with app.app.app_context():
        app._admin_notify("test", "warning", "Visible item", "detail")
    _as(client, uid)
    r = client.get("/admin/inbox")
    assert r.status_code == 200
    assert "Notification Inbox" in r.get_data(as_text=True)


def test_inbox_non_admin_403(app, client):
    uid = _mk_user(app, is_admin=0)
    _as(client, uid)
    assert client.get("/admin/inbox").status_code == 403
    assert client.get("/admin/inbox/status").status_code == 403


def test_inbox_anon_redirect(app, client):
    with client.session_transaction() as s:
        s.clear()
    r = client.get("/admin/inbox")
    assert r.status_code in (301, 302)


# ── Status endpoint ──────────────────────────────────────────────────────────
def test_inbox_status_shape(app, client):
    uid = _mk_user(app, is_admin=1)
    with app.app.app_context():
        app._admin_notify("test", "info", "Status probe")
    _as(client, uid)
    j = client.get("/admin/inbox/status").get_json()
    assert set(("unread", "latest_id", "alerts_enabled", "latest")).issubset(j)
    assert isinstance(j["unread"], int) and j["unread"] >= 1
    assert isinstance(j["latest"], list)


# ── Mark read + CSRF ─────────────────────────────────────────────────────────
def test_mark_read_and_csrf(app, client):
    uid = _mk_user(app, is_admin=1)
    with app.app.app_context():
        nid = app._admin_notify("test", "info", "Mark me")
    _as(client, uid)
    # CSRF required
    assert client.post(f"/admin/inbox/{nid}/read").status_code == 403
    before = client.get("/admin/inbox/status").get_json()["unread"]
    r = client.post(f"/admin/inbox/{nid}/read", headers={"X-CSRF-Token": "tok"})
    assert r.status_code in (302, 200)
    after = client.get("/admin/inbox/status").get_json()["unread"]
    assert after == before - 1


def test_mark_all_read(app, client):
    uid = _mk_user(app, is_admin=1)
    with app.app.app_context():
        app._admin_notify("test", "info", "bulk1")
        app._admin_notify("test", "info", "bulk2")
    _as(client, uid)
    r = client.post("/admin/inbox/read-all", headers={"X-CSRF-Token": "tok"},
                    data={"_csrf": "tok"})
    assert r.status_code in (302, 200)
    assert client.get("/admin/inbox/status").get_json()["unread"] == 0


# ── Settings toggle ──────────────────────────────────────────────────────────
def test_settings_toggle(app, client):
    uid = _mk_user(app, is_admin=1)
    _as(client, uid)
    client.post("/admin/inbox/settings", data={"_csrf": "tok", "browser_alerts": "1"},
                headers={"X-CSRF-Token": "tok"})
    assert client.get("/admin/inbox/status").get_json()["alerts_enabled"] is True
    client.post("/admin/inbox/settings", data={"_csrf": "tok"},
                headers={"X-CSRF-Token": "tok"})  # unchecked -> off
    assert client.get("/admin/inbox/status").get_json()["alerts_enabled"] is False


# ── Producer hook: a recorded 500 fans into the inbox ────────────────────────
def test_record_error_creates_notification(app):
    with app.app.test_request_context("/some/failing/path"):
        before = app._inbox_unread_count()
        try:
            raise ValueError("synthetic boom for inbox test")
        except ValueError as e:
            app._record_error(e, status=500)
        after = app._inbox_unread_count()
        from web_app import get_db
        with get_db() as c:
            row = c.execute(
                "SELECT source, severity FROM admin_notifications ORDER BY id DESC LIMIT 1"
            ).fetchone()
    assert after == before + 1
    assert row[0] == "error" and row[1] == "critical"


# ── Test-notification endpoint ───────────────────────────────────────────────
def test_send_test_notification(app, client):
    uid = _mk_user(app, is_admin=1)
    _as(client, uid)
    before = client.get("/admin/inbox/status").get_json()["unread"]
    r = client.post("/admin/inbox/test", headers={"X-CSRF-Token": "tok"},
                    data={"_csrf": "tok"})
    assert r.status_code in (302, 200)
    after = client.get("/admin/inbox/status").get_json()["unread"]
    assert after == before + 1
