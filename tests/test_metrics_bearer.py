"""Regression tests for the /metrics Bearer gate (_bearer_ok).

WHAT: exercises app.observability.metrics._bearer_ok directly -- valid token,
wrong token (same AND different length), fail-closed on unset env, malformed
headers, and a non-ASCII token.
WHY: the gate was hand-rolled and early-returned on a length mismatch, which
leaked the token length via timing. It now uses hmac.compare_digest over
UTF-8 BYTES. The different-length and non-ASCII cases are the two that the
old implementation short-circuited / would have broken on, so they are the
load-bearing regression guards.

NOTE: web_app is deliberately NOT imported -- it SystemExits without a full
production environment. The function under test is env-only, so importing the
module directly is sufficient.
"""

import os

import pytest

from app.observability.metrics import _bearer_ok

TOKEN = "s3cr3t-metrics-token"


@pytest.fixture
def with_token(monkeypatch):
    """Sets METRICS_BEARER to the known-good token for the duration of a test."""
    monkeypatch.setenv("METRICS_BEARER", TOKEN)
    return TOKEN


def test_valid_token_accepted(with_token):
    # Load-bearing: Prometheus scrapes /metrics; a False here breaks observability.
    assert _bearer_ok(f"Bearer {TOKEN}") is True


def test_wrong_token_same_length_rejected(with_token):
    wrong = "x" * len(TOKEN)
    assert len(wrong) == len(TOKEN)
    assert _bearer_ok(f"Bearer {wrong}") is False


def test_wrong_token_different_length_rejected(with_token):
    # The case the old `if len(sent) != len(expected): return False` short-circuited.
    assert _bearer_ok("Bearer short") is False
    assert _bearer_ok(f"Bearer {TOKEN}-plus-extra-suffix") is False


def test_unset_env_fails_closed(monkeypatch):
    monkeypatch.delenv("METRICS_BEARER", raising=False)
    assert _bearer_ok(f"Bearer {TOKEN}") is False


def test_empty_env_fails_closed(monkeypatch):
    monkeypatch.setenv("METRICS_BEARER", "   ")
    assert _bearer_ok("Bearer    ") is False
    assert _bearer_ok(f"Bearer {TOKEN}") is False


def test_missing_header_rejected(with_token):
    assert _bearer_ok("") is False
    assert _bearer_ok(None) is False


def test_non_bearer_scheme_rejected(with_token):
    assert _bearer_ok(f"Basic {TOKEN}") is False
    assert _bearer_ok(TOKEN) is False
    assert _bearer_ok("Bearer") is False  # no trailing space -> not a bearer header


def test_non_ascii_token_returns_false_and_does_not_raise(with_token):
    # WSGI decodes headers latin-1, so a non-ASCII byte can reach us. Must be a
    # plain False, never a TypeError bubbling up as a 500.
    for bad in ("Bearer ÿþý", "Bearer café", "Bearer 你好"):
        assert _bearer_ok(bad) is False


def test_bearer_prefix_is_case_insensitive(with_token):
    assert _bearer_ok(f"bearer {TOKEN}") is True
    assert _bearer_ok(f"BEARER {TOKEN}") is True
    assert _bearer_ok(f"BeArEr {TOKEN}") is True


def test_token_is_stripped(with_token):
    assert _bearer_ok(f"Bearer   {TOKEN}   ") is True
