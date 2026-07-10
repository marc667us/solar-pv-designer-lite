"""CSRF regression tests for the three admin-ops POST routes that were missing
csrf_protect() (security audit 2026-07-10).

Each mutates state (backup file write / session clear / DB VACUUM) and must
reject an authenticated POST that carries no CSRF token, matching the project
convention that every state-changing POST calls csrf_protect()."""
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
    return f"csrf_{label}{_SEQ[0]}_{_RUN}"[:32]


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


ROUTES = [
    "/admin/ops/backup/run",
    "/admin/ops/security/revoke-all-sessions",
    "/admin/ops/db/vacuum",
]


@pytest.mark.parametrize("route", ROUTES)
def test_admin_post_without_csrf_is_rejected(app, client, route):
    _login_admin(client, _mk_admin(app))
    # authenticated admin, but no _csrf token -> csrf_protect() must abort 403
    assert client.post(route).status_code == 403


def test_vacuum_with_valid_csrf_passes(app, client):
    # positive control: proves the 403 above is specifically the CSRF gate,
    # not a blanket rejection. VACUUM on the test DB is a safe side effect.
    _login_admin(client, _mk_admin(app))
    r = client.post("/admin/ops/db/vacuum", data={"_csrf": "tok"})
    assert r.status_code == 200
