"""
Q-gate 3.7 — CSRF protection micro-tests.

Every POST that mutates state must require a valid `_csrf` form field (or
`X-CSRF-Token` header for JSON endpoints). Missing or wrong token → 400/403,
no mutation persisted.

Current state: scaffold for the 4 highest-risk POST routes. Each template
asserts (a) the route rejects when the token is missing, (b) the route
rejects when the token is wrong, (c) no DB side-effect is observable when
rejected.

Tests are `pytest.skip()` until wired — keeps CI green.
"""

import pytest


@pytest.fixture
def client():
    pytest.skip("client fixture not wired yet")


@pytest.fixture
def authed_session(client):
    """Logged-in session WITHOUT a fresh CSRF token in the request."""
    pytest.skip("authed_session fixture not wired yet")


# ---------------------------------------------------------------------------
# Auth POSTs — login + register + password-reset all need CSRF
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token_state, expected_status", [
    ("missing",   400),
    ("wrong",     400),
    ("valid",     200),  # baseline — should succeed
])
def test_login_csrf(token_state, expected_status):
    pytest.skip(f"login CSRF template — wire to POST /login with token_state={token_state}")


@pytest.mark.parametrize("token_state, expected_status", [
    ("missing",   400),
    ("wrong",     400),
    ("valid",     302),  # successful register redirects to /dashboard
])
def test_register_csrf(token_state, expected_status):
    pytest.skip(f"register CSRF template — wire to POST /register with token_state={token_state}")


# ---------------------------------------------------------------------------
# Account mutations — feedback / settings / account-cancel
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token_state, expected_status, expect_db_row", [
    ("missing",   400, False),
    ("wrong",     400, False),
    ("valid",     200, True),
])
def test_feedback_csrf(token_state, expected_status, expect_db_row):
    """POST /feedback must reject without CSRF and not insert a feedback row."""
    pytest.skip(f"feedback CSRF template — wire to POST /feedback with token_state={token_state}")


# ---------------------------------------------------------------------------
# Payment webhooks — Paystack uses signature, not CSRF, but the /verify
# endpoint that JS calls back into IS CSRF-protected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("token_state, expected_status", [
    ("missing",   400),
    ("wrong",     400),
    ("valid",     200),
])
def test_paystack_verify_csrf(token_state, expected_status):
    pytest.skip(f"paystack/verify CSRF template — wire to POST /paystack/verify with token_state={token_state}")


# ---------------------------------------------------------------------------
# Webhook signature verification — Paystack /paystack/webhook
# Different from CSRF: uses HMAC-SHA512 signature in x-paystack-signature header
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_state, expected_status", [
    ("missing",  400),
    ("forged",   400),
    ("replayed", 400),  # replay older valid signature should also fail
    ("valid",    200),
])
def test_paystack_webhook_signature(sig_state, expected_status):
    """POST /paystack/webhook must verify x-paystack-signature with HMAC-SHA512."""
    pytest.skip(f"paystack/webhook signature template — wire with sig_state={sig_state}")
