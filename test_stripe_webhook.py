"""Stripe webhook — revival + idempotency tests.

WHY THIS FILE EXISTS
    /stripe/webhook was DEAD from the commit that created it (86eadc2) until
    2026-07-20: it called request.get_data(raw=True), and werkzeug's get_data
    has no `raw` kwarg, so it raised TypeError on every request. The handler's
    own `except Exception: return "", 400` swallowed that, so Stripe saw a
    silent 400 and no event was ever processed.

    Reviving it is only safe WITH a dedupe guard, because Stripe RETRIES a
    webhook until it receives a 2xx. The load-bearing assertion here is
    therefore not "the webhook works" but "delivering the same event twice
    upgrades the user once and records ONE payment" -- _record_payment also
    emails the customer, so a duplicate is a double email as well as a double
    row.

    Lives at repo root (not tests/) to match the other web_app-importing
    suites, which need the same env + module-loading dance.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import time
import uuid
from pathlib import Path

import pytest

_SECRET = "whsec_test_secret_for_signature_only"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """Import web_app with Stripe configured and an isolated database."""
    import os

    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    # The handler returns 400 immediately unless STRIPE_SECRET is set, so both
    # must be present for any of this to execute.
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_dummy"
    os.environ["STRIPE_WEBHOOK_SECRET"] = _SECRET
    os.environ["DB_PATH"] = str(tmp_path_factory.mktemp("stripe") / "t.db")

    spec = importlib.util.spec_from_file_location(
        "web_app_stripe", Path(__file__).resolve().parent / "web_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.limiter.enabled = False
    except Exception:
        pass
    mod.app.config["TESTING"] = True
    return mod


@pytest.fixture
def user(app):
    """A real user row to upgrade, returned as its id."""
    uname = f"stripe_{uuid.uuid4().hex[:8]}"
    with app.get_db() as c:
        cur = c.execute(
            "INSERT INTO users (username, email, password_hash, plan) "
            "VALUES (?,?,?,?)",
            (uname, f"{uname}@test.local", "x", "free"),
        )
        uid = cur.lastrowid
    return uid


def _signed(payload: dict) -> tuple[bytes, str]:
    """Return (body, Stripe-Signature header) for a payload.

    Stripe signs "<timestamp>.<raw body>" with HMAC-SHA256 and sends
    "t=<ts>,v1=<hex>". Building a REAL signature matters: it exercises
    construct_event for real, which is the call that used to blow up on
    get_data(raw=True).
    """
    body = json.dumps(payload).encode("utf-8")
    ts = int(time.time())
    sig = hmac.new(
        _SECRET.encode("utf-8"),
        f"{ts}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return body, f"t={ts},v1={sig}"


def _checkout_event(uid: int, plan: str = "professional", session_id: str | None = None):
    return {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        # Real Stripe events carry "object": "event"; the SDK (15.x) reads it in
        # construct_event, so a fixture without it fails before the handler runs.
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id or f"cs_test_{uuid.uuid4().hex[:16]}",
            "metadata": {"plan": plan, "user_id": str(uid)},
        }},
    }


def _post(app, payload):
    body, sig = _signed(payload)
    return app.app.test_client().post(
        "/stripe/webhook", data=body,
        headers={"Stripe-Signature": sig, "Content-Type": "application/json"},
    )


def _payments(app, ref):
    with app.get_db() as c:
        return c.execute(
            "SELECT id, plan, status FROM payments WHERE reference=?", (ref,)
        ).fetchall()


# ── the revival ──────────────────────────────────────────────────────────

def test_webhook_accepts_a_valid_event(app, user):
    """The bug: this used to return 400 for EVERY event, forever."""
    ev = _checkout_event(user)
    resp = _post(app, ev)
    assert resp.status_code == 200, (
        f"valid signed event rejected with {resp.status_code} -- the handler is "
        "still dead"
    )


def test_valid_event_upgrades_the_user_and_records_the_payment(app, user):
    ev = _checkout_event(user, plan="business")
    ref = ev["data"]["object"]["id"]

    assert _post(app, ev).status_code == 200

    with app.get_db() as c:
        plan = c.execute("SELECT plan FROM users WHERE id=?", (user,)).fetchone()["plan"]
    assert plan == "business", "the user's plan was not upgraded"
    assert len(_payments(app, ref)) == 1, "expected exactly one payment row"


# ── the reason the fix waited: idempotency ───────────────────────────────

def test_redelivery_of_the_same_event_does_not_double_record(app, user):
    """THE LOAD-BEARING TEST.

    Stripe retries until it gets a 2xx. Without the dedupe guard, a retry
    would record a second payment AND send the customer a second confirmation
    email. This is why get_data was not fixed on its own.
    """
    ev = _checkout_event(user)
    ref = ev["data"]["object"]["id"]

    assert _post(app, ev).status_code == 200
    assert _post(app, ev).status_code == 200   # the retry
    assert _post(app, ev).status_code == 200   # and another

    rows = _payments(app, ref)
    assert len(rows) == 1, (
        f"{len(rows)} payment rows for one checkout session -- the dedupe guard "
        "is not holding, so a Stripe retry double-charges the record and "
        "double-emails the customer"
    )


def test_dedupes_against_the_browser_callback_path(app, user):
    """/upgrade/success records the SAME session id as `reference`
    (web_app.py:8103). If the customer's browser lands there first, the
    webhook must not record the payment a second time."""
    session_id = f"cs_test_{uuid.uuid4().hex[:16]}"

    # Simulate the browser-callback path having already recorded it.
    app._record_payment(user, "stripe", "professional", 49, reference=session_id)

    ev = _checkout_event(user, session_id=session_id)
    assert _post(app, ev).status_code == 200

    rows = _payments(app, session_id)
    assert len(rows) == 1, (
        f"{len(rows)} rows -- the webhook re-recorded a payment already booked "
        "by /upgrade/success"
    )


def test_cancellation_event_is_also_deduped(app, user):
    """The downgrade branch had NO reference at all before this change, so
    retries could pile up 'cancelled' rows. It now keys on the Stripe event
    id, which is unique per event."""
    ev = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"user_id": str(user)}}},
    }

    assert _post(app, ev).status_code == 200
    assert _post(app, ev).status_code == 200   # retry

    rows = _payments(app, ev["id"])
    assert len(rows) == 1, f"{len(rows)} cancellation rows for one event"
    with app.get_db() as c:
        plan = c.execute("SELECT plan FROM users WHERE id=?", (user,)).fetchone()["plan"]
    assert plan == "free", "the downgrade did not apply"


# ── it must still reject what it should reject ───────────────────────────

def test_bad_signature_is_rejected(app, user):
    """Reviving the handler must not weaken it."""
    body = json.dumps(_checkout_event(user)).encode("utf-8")
    resp = app.app.test_client().post(
        "/stripe/webhook", data=body,
        headers={"Stripe-Signature": "t=1,v1=deadbeef",
                 "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_unsigned_request_is_rejected(app, user):
    resp = app.app.test_client().post(
        "/stripe/webhook", data=b"{}",
        headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_no_upgrade_without_metadata(app):
    """A well-signed event with no user_id/plan must not touch anybody."""
    ev = {
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {"object": {"id": f"cs_{uuid.uuid4().hex[:12]}", "metadata": {}}},
    }
    assert _post(app, ev).status_code == 200
    assert _payments(app, ev["data"]["object"]["id"]) == []
