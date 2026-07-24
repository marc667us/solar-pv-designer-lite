"""Idempotency test for the /paystack/verify browser-callback path.

A replayed verify (same reference) must upgrade the user ONCE and record exactly
one payment -- not re-run the plan UPDATE / re-send the receipt on every replay.
Mirrors the webhook suite's app-import dance; pins PAYSTACK_SECRET past the
secrets-broker cache (same reason as test_paystack_webhook).
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest

_SECRET = "sk_test_verify_signature_only"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    import os
    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    os.environ["PAYSTACK_SECRET_KEY"] = _SECRET
    os.environ["DB_PATH"] = str(tmp_path_factory.mktemp("verify") / "t.db")

    spec = importlib.util.spec_from_file_location(
        "web_app_verify", Path(__file__).resolve().parent / "web_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    mod.app.config["TESTING"] = True
    mod.PAYSTACK_SECRET = _SECRET   # pin past the secrets-broker cache
    return mod


@pytest.fixture
def user(app):
    uname = f"v_{uuid.uuid4().hex[:8]}"
    with app.get_db() as c:
        uid = c.execute(
            "INSERT INTO users (username, email, password_hash, plan) VALUES (?,?,?,?)",
            (uname, f"{uname}@test.local", "x", "free")).lastrowid
    return uid


class _FakeResp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()
    def read(self):
        return self._p
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _post_verify(app, monkeypatch, uid, ref, plan="professional"):
    # Both external calls must report success for the upgrade branch to run.
    monkeypatch.setattr(app._api.payment, "verify", lambda r: (True, {"data": {}}), raising=False)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _FakeResp({"status": True, "data": {"status": "success"}}))
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"
    return c.post("/paystack/verify",
                  data={"reference": ref, "plan": plan, "_csrf": "tok"})


def _plan(app, uid):
    with app.get_db() as c:
        return c.execute("SELECT plan FROM users WHERE id=?", (uid,)).fetchone()["plan"]


def _rows(app, ref):
    with app.get_db() as c:
        return c.execute("SELECT id FROM payments WHERE reference=?", (ref,)).fetchall()


def test_first_verify_upgrades_and_records_once(app, user, monkeypatch):
    ref = f"vref_{uuid.uuid4().hex[:12]}"
    r = _post_verify(app, monkeypatch, user, ref)
    assert r.status_code in (302, 303)
    assert _plan(app, user) == "professional"
    assert len(_rows(app, ref)) == 1


def test_replayed_verify_is_idempotent(app, user, monkeypatch):
    ref = f"vref_{uuid.uuid4().hex[:12]}"
    _post_verify(app, monkeypatch, user, ref)
    # deliver the SAME reference again (browser back / double-submit)
    _post_verify(app, monkeypatch, user, ref)
    _post_verify(app, monkeypatch, user, ref)
    # exactly one payment row, plan upgraded once (not re-charged / re-recorded)
    assert len(_rows(app, ref)) == 1
    assert _plan(app, user) == "professional"
