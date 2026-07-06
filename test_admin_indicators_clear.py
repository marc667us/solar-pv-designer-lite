"""Tests for the admin dashboard "Clear All" indicators button (owner 2026-07-06).

Covers: RBAC (admin only), CSRF, and that it marks all admin notifications read
(so the bell badge / Notifications indicator resets)."""
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
    return f"ind_{label}{_SEQ[0]}_{_RUN}"[:32]


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


def _as(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"


def test_requires_admin(app, client):
    non = _mk_user(app, is_admin=0)
    _as(client, non)
    assert client.post("/admin/indicators/clear", data={"_csrf": "tok"}).status_code == 403
    with client.session_transaction() as s:
        s.clear()
    assert client.post("/admin/indicators/clear").status_code in (301, 302)


def test_requires_csrf(app, client):
    admin = _mk_user(app, is_admin=1)
    _as(client, admin)
    assert client.post("/admin/indicators/clear").status_code == 403


def test_clears_unread_notifications(app, client):
    admin = _mk_user(app, is_admin=1)
    _as(client, admin)
    marker = "IND CLEAR " + _RUN
    with app.app.app_context():
        from web_app import get_db
        app._admin_notify("test", "info", marker)
        with get_db() as c:
            before = c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE read_at IS NULL").fetchone()[0]
    assert before >= 1
    r = client.post("/admin/indicators/clear", data={"_csrf": "tok"})
    assert r.status_code in (301, 302)  # redirect back to dashboard
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            after = c.execute(
                "SELECT COUNT(*) FROM admin_notifications WHERE read_at IS NULL").fetchone()[0]
    assert after == 0  # all marked read -> indicators reset
