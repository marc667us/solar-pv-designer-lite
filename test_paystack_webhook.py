"""Paystack webhook — end-to-end tests.

WHY THIS FILE EXISTS
    The webhook was dead from 86eadc2 until 2026-07-20 (a get_data(raw=True)
    TypeError). Fixing that made it reachable and exposed a SECOND fault:
    _record_payment() was called inside `with get_db() as c:`, nesting a
    second connection. SQLite answers "database is locked", the handler's own
    `except Exception: pass` swallowed it, and it returned 200 -- so Paystack
    was told the event was processed while the customer was NOT upgraded, and
    a 200 stops Paystack retrying, losing the payment for good.

    Nothing tested this path end to end, which is exactly why a loud failure
    (500, retried) was quietly converted into a silent one (200, never
    retried). These tests assert the OUTCOME -- plan upgraded, exactly one
    payment row -- not merely the status code, because the status code was
    200 the whole time it was broken.
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import uuid
from pathlib import Path

import pytest

_SECRET = "sk_test_paystack_signature_only"


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    import os

    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    os.environ["PAYSTACK_SECRET_KEY"] = _SECRET
    os.environ["DB_PATH"] = str(tmp_path_factory.mktemp("paystack") / "t.db")

    spec = importlib.util.spec_from_file_location(
        "web_app_paystack", Path(__file__).resolve().parent / "web_app.py")
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
    uname = f"ps_{uuid.uuid4().hex[:8]}"
    with app.get_db() as c:
        uid = c.execute(
            "INSERT INTO users (username, email, password_hash, plan) "
            "VALUES (?,?,?,?)",
            (uname, f"{uname}@test.local", "x", "free"),
        ).lastrowid
    return uid


def _post(app, payload: dict):
    """Deliver a correctly-signed Paystack event.

    Paystack signs the RAW BODY with HMAC-SHA512 and sends the hex digest in
    X-Paystack-Signature.
    """
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(_SECRET.encode("utf-8"), msg=body,
                   digestmod=hashlib.sha512).hexdigest()
    return app.app.test_client().post(
        "/paystack/webhook", data=body,
        headers={"x-paystack-signature": sig,
                 "Content-Type": "application/json"},
    )


def _charge(uid: int, ref: str, plan: str = "professional"):
    return {"event": "charge.success",
            "data": {"reference": ref, "amount": 4900,
                     "metadata": {"user_id": str(uid), "plan": plan}}}


def _rows(app, ref):
    with app.get_db() as c:
        return c.execute("SELECT id FROM payments WHERE reference=?",
                         (ref,)).fetchall()


def _plan(app, uid):
    with app.get_db() as c:
        return c.execute("SELECT plan FROM users WHERE id=?",
                         (uid,)).fetchone()["plan"]


def test_valid_event_actually_upgrades_the_user(app, user):
    """THE LOAD-BEARING TEST.

    A 200 alone proves nothing here: the handler returned 200 for the entire
    period it was silently dropping payments. Assert the OUTCOME.
    """
    ref = f"ps_{uuid.uuid4().hex[:12]}"
    assert _post(app, _charge(user, ref)).status_code == 200

    assert _plan(app, user) == "professional", (
        "the webhook returned 200 but did NOT upgrade the user -- this is the "
        "silent-failure mode: Paystack treats 200 as delivered and never "
        "retries, so the payment is lost"
    )
    assert len(_rows(app, ref)) == 1, "expected exactly one payment row"


def test_redelivery_does_not_double_record(app, user):
    """Paystack retries on non-2xx; the reference dedupe must hold."""
    ref = f"ps_{uuid.uuid4().hex[:12]}"
    assert _post(app, _charge(user, ref)).status_code == 200
    assert _post(app, _charge(user, ref)).status_code == 200
    assert _post(app, _charge(user, ref)).status_code == 200

    rows = _rows(app, ref)
    assert len(rows) == 1, (
        f"{len(rows)} payment rows for one reference -- dedupe is not holding, "
        "so a retry double-records and double-emails the customer"
    )


def test_dedupes_against_the_verify_callback(app, user):
    """/paystack/verify records the SAME reference (web_app.py:8143). If the
    browser callback lands first, the webhook must not record it again."""
    ref = f"ps_{uuid.uuid4().hex[:12]}"
    app._record_payment(user, "paystack", "professional", 49, reference=ref)

    assert _post(app, _charge(user, ref)).status_code == 200
    assert len(_rows(app, ref)) == 1, (
        "the webhook re-recorded a payment already booked by /paystack/verify"
    )


def test_bad_signature_rejected(app, user):
    body = json.dumps(_charge(user, "ps_bad")).encode("utf-8")
    resp = app.app.test_client().post(
        "/paystack/webhook", data=body,
        headers={"x-paystack-signature": "deadbeef",
                 "Content-Type": "application/json"})
    assert resp.status_code == 400
    assert _plan(app, user) == "free", "a forged event changed the user's plan"


def test_non_ascii_signature_is_400_not_500(app, user):
    """Regression guard for the compare_digest fix shipped the same day: a
    non-ASCII header must be an honest rejection, never an unhandled 500."""
    body = json.dumps(_charge(user, "ps_evil")).encode("utf-8")
    resp = app.app.test_client().post(
        "/paystack/webhook", data=body,
        headers={"x-paystack-signature": "ÿþ",
                 "Content-Type": "application/json"})
    assert resp.status_code == 400


def test_unrelated_event_type_is_ignored(app, user):
    assert _post(app, {"event": "charge.failed", "data": {}}).status_code == 200
    assert _plan(app, user) == "free"
