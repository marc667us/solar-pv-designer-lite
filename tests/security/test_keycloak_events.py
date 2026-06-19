"""
Unit tests for app.security.keycloak_events.

Phase 6 deliverable per docs/SECURITY_MIGRATION_KEYCLOAK.md §19 task 32.

Covers HMAC verification + event normalisation + dedupe. The webhook
route in web_app.py is a thin wrapper around these two functions; we
mount a minimal Flask Blueprint that mirrors the wire to keep the test
imports light.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from app.security import audit
from app.security import keycloak_events as ke


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """Each test starts with a known secret + empty dedupe cache +
    test-sink instead of real DB."""
    monkeypatch.setenv("KEYCLOAK_WEBHOOK_SECRET", "secret-x")
    ke.clear_dedupe_cache()
    sink: list[dict] = []
    audit.set_test_sink(sink)
    yield sink
    audit.set_test_sink(None)


# ── HMAC verification ───────────────────────────────────────────────────

def _sign(body: bytes, secret: bytes = b"secret-x") -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def test_verify_accepts_correct_signature():
    body = b'{"id":"e1"}'
    assert ke.verify_signature(body, _sign(body)) is True


def test_verify_accepts_bare_hex():
    body = b'{"id":"e1"}'
    sig = _sign(body)[len("sha256="):]  # drop prefix
    assert ke.verify_signature(body, sig) is True


def test_verify_rejects_wrong_signature():
    body = b'{"id":"e1"}'
    assert ke.verify_signature(body, "sha256=deadbeef") is False


def test_verify_rejects_when_secret_unset(monkeypatch):
    monkeypatch.delenv("KEYCLOAK_WEBHOOK_SECRET", raising=False)
    body = b'{"id":"e1"}'
    assert ke.verify_signature(body, "sha256=anything") is False


def test_verify_rejects_empty_provided():
    assert ke.verify_signature(b'{"id":"e1"}', "") is False


def test_verify_constant_time_against_length_mismatch():
    """hmac.compare_digest is constant-time even for length mismatches."""
    body = b'{"id":"e1"}'
    short = "sha256=" + "a"
    assert ke.verify_signature(body, short) is False


# ── process_event normalisation ─────────────────────────────────────────

def test_login_event_normalised_to_login_success(_reset):
    sink = _reset
    payload = {"id": "e1", "type": "LOGIN", "userId": "u-1", "ipAddress": "1.1.1.1"}
    assert ke.process_event(payload) == "stored"
    assert sink[0]["action"] == "LOGIN_SUCCESS"
    assert sink[0]["ip_address"] == "1.1.1.1"
    assert sink[0]["agent_id"] == "u-1"


def test_login_error_normalised(_reset):
    sink = _reset
    payload = {"id": "e2", "type": "LOGIN_ERROR", "userId": "u-2",
               "error": "invalid_user_credentials"}
    ke.process_event(payload)
    assert sink[0]["action"] == "LOGIN_FAILED"
    assert "invalid_user_credentials" in sink[0]["details"]


def test_unknown_user_event_gets_kc_prefix(_reset):
    sink = _reset
    ke.process_event({"id": "e3", "type": "WEIRD_NEW_EVENT"})
    assert sink[0]["action"] == "KC_WEIRD_NEW_EVENT"


def test_admin_event_detected_and_prefixed(_reset):
    sink = _reset
    payload = {
        "id": "a1",
        "operationType": "CREATE",
        "resourceType": "USER",
        "resourcePath": "users/u-7",
        "realmId": "solarpro",
        "authDetails": {"userId": "admin-uuid", "ipAddress": "9.9.9.9"},
    }
    ke.process_event(payload)
    assert sink[0]["action"] == "KC_ADMIN_CREATE"
    assert sink[0]["ip_address"] == "9.9.9.9"


def test_invalid_payload_returns_invalid(_reset):
    assert ke.process_event("not a dict") == "invalid"
    assert ke.process_event(None) == "invalid"


# ── Dedupe ──────────────────────────────────────────────────────────────

def test_duplicate_event_id_dropped(_reset):
    sink = _reset
    payload = {"id": "e7", "type": "LOGIN"}
    assert ke.process_event(payload, now=1000.0) == "stored"
    assert ke.process_event(payload, now=1001.0) == "duplicate"
    assert len(sink) == 1


def test_same_id_outside_ttl_processed_again(_reset, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_EVENT_DEDUPE_TTL", "60")
    payload = {"id": "e8", "type": "LOGIN"}
    assert ke.process_event(payload, now=1000.0) == "stored"
    # Outside the 60s window -> treated as a fresh event.
    assert ke.process_event(payload, now=1100.0) == "stored"


def test_event_without_id_not_deduped(_reset):
    sink = _reset
    # Two payloads with no id should both store.
    ke.process_event({"type": "LOGIN"})
    ke.process_event({"type": "LOGIN"})
    assert len(sink) == 2


# ── Audit writer failure surface ────────────────────────────────────────

def test_dropped_when_writer_fails(_reset, monkeypatch):
    """Simulate the audit writer returning False (DB unreachable)."""
    audit.set_test_sink(None)
    monkeypatch.setattr(audit, "_resolve_get_db", lambda: None)
    assert ke.process_event({"id": "e9", "type": "LOGIN"}) == "dropped"


# ── Webhook route integration (via a slim Flask wrapper) ───────────────

def test_webhook_route_returns_401_on_bad_sig():
    from flask import Flask, request as freq, jsonify
    app = Flask(__name__); app.testing = True
    @app.route("/api/keycloak/events", methods=["POST"])
    def _hook():
        raw = freq.get_data(cache=False, as_text=False) or b""
        if not ke.verify_signature(raw, freq.headers.get("X-Keycloak-Event-Signature", "")):
            return jsonify(error="INVALID_SIGNATURE"), 401
        return jsonify(result=ke.process_event(json.loads(raw))), 202

    with app.test_client() as c:
        body = b'{"id":"e10","type":"LOGIN"}'
        r = c.post("/api/keycloak/events", data=body, content_type="application/json",
                   headers={"X-Keycloak-Event-Signature": "sha256=deadbeef"})
        assert r.status_code == 401
        assert r.get_json()["error"] == "INVALID_SIGNATURE"


def test_webhook_route_stores_when_signature_ok(_reset):
    sink = _reset
    from flask import Flask, request as freq, jsonify
    app = Flask(__name__); app.testing = True
    @app.route("/api/keycloak/events", methods=["POST"])
    def _hook():
        raw = freq.get_data(cache=False, as_text=False) or b""
        if not ke.verify_signature(raw, freq.headers.get("X-Keycloak-Event-Signature", "")):
            return jsonify(error="INVALID_SIGNATURE"), 401
        return jsonify(result=ke.process_event(json.loads(raw))), 202

    body = b'{"id":"e11","type":"LOGIN","userId":"u-1","ipAddress":"4.4.4.4"}'
    with app.test_client() as c:
        r = c.post("/api/keycloak/events", data=body, content_type="application/json",
                   headers={"X-Keycloak-Event-Signature": _sign(body)})
    assert r.status_code == 202
    assert r.get_json()["result"] == "stored"
    assert sink[0]["action"] == "LOGIN_SUCCESS"
    assert sink[0]["ip_address"] == "4.4.4.4"
