"""Tests for bot_defense.py + new_bot_defense_routes.py (revenue-leakage guard).

Design under test: honeypot ALWAYS blocks (zero false positives); automation-UA
blocks only when BOT_DEFENSE_ENFORCE is set (else monitored); empty-UA flagged;
trusted internal "SolarPro-*" automation is never touched. Fail-open throughout.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from flask import Flask

import bot_defense as bd
import new_bot_defense_routes as bdr


# ── pure logic ────────────────────────────────────────────────────────────────

def test_is_sensitive():
    assert bd.is_sensitive("POST", "/login")
    assert bd.is_sensitive("POST", "/upgrade/checkout")
    assert bd.is_sensitive("POST", "/paystack/verify")
    assert not bd.is_sensitive("GET", "/login")
    assert not bd.is_sensitive("POST", "/paystack/webhook")   # webhooks EXEMPT
    assert not bd.is_sensitive("POST", "/marketplace")


def test_classify_honeypot_always_bot():
    assert bd.classify("Mozilla/5.0", "spam")[0] == "honeypot"


def test_classify_bot_user_agents():
    for ua in ("python-requests/2.31", "curl/8.5", "Scrapy/2.11",
               "Go-http-client/1.1", "HeadlessChrome/120", "okhttp/4.9"):
        kind, reason = bd.classify(ua, "")
        assert kind == "ua", ua
        assert reason.startswith("ua:")


def test_classify_allows_real_browsers():
    for ua in ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36",
               "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1",
               "Mozilla/5.0 (Linux; Android 14) Chrome/126 Mobile"):
        assert bd.classify(ua, "")[0] == "allow", ua


def test_classify_allows_labelled_and_internal_clients():
    # A labelled "(e2e-bot)" browser UA must NOT be caught (broad token removed).
    assert bd.classify("Mozilla/5.0 (e2e-bot)", "")[0] == "allow"
    # Our own monitoring crons (SolarPro-*) are trusted, even via a tool.
    assert bd.classify("SolarPro-AgentTriage/1.0", "")[0] == "allow"
    assert bd.classify("SolarPro-BetaMonitor/1.0", "")[0] == "allow"


def test_classify_empty_ua_is_flag_only():
    assert bd.classify("", "") == ("empty", "empty-ua")


def test_classify_never_raises():
    kind, _ = bd.classify(None, None)     # must not raise; empty UA -> "empty"
    assert kind in ("allow", "honeypot", "ua", "empty")


# ── ledger ────────────────────────────────────────────────────────────────────

def test_schema_and_record():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    bd.ensure_bot_events_schema(c, False)
    bd.ensure_bot_events_schema(c, False)   # idempotent
    bd.record_bot_event(c, path="/login", method="POST", action="block",
                        reason="honeypot", ip="1.2.3.4", ua="curl/8")
    row = c.execute("SELECT * FROM bot_events").fetchone()
    assert row["action"] == "block" and row["reason"] == "honeypot"


# ── before_request hook (integration) ─────────────────────────────────────────

def _make_app(get_db):
    a = Flask(__name__)
    a.config["TESTING"] = True

    @a.route("/login", methods=["POST"])
    def login():
        return "ok", 200

    @a.route("/paystack/webhook", methods=["POST"])
    def webhook():
        return "wh", 200

    bdr.register_bot_defense(a, get_db=get_db, admin_required=lambda f: f,
                             current_user=lambda: None, get_real_ip=lambda: "9.9.9.9",
                             is_postgres=lambda: False)
    return a


@pytest.fixture
def app():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    @contextlib.contextmanager
    def get_db():
        yield conn
        conn.commit()

    a = _make_app(get_db)
    a._conn = conn
    return a


def test_honeypot_always_blocks(app, monkeypatch):
    monkeypatch.delenv("BOT_DEFENSE_ENFORCE", raising=False)   # even with enforce OFF
    r = app.test_client().post("/login", data={"company_website": "http://spam", "username": "x"})
    assert r.status_code == 403
    n = app._conn.execute("SELECT COUNT(*) FROM bot_events WHERE reason='honeypot' AND action='block'").fetchone()[0]
    assert n == 1


def test_bot_ua_monitored_not_blocked_by_default(app, monkeypatch):
    monkeypatch.delenv("BOT_DEFENSE_ENFORCE", raising=False)
    r = app.test_client().post("/login", data={"username": "x"},
                               headers={"User-Agent": "python-requests/2.31"})
    assert r.status_code == 200                # NOT blocked in monitor mode
    row = app._conn.execute("SELECT action FROM bot_events ORDER BY id DESC LIMIT 1").fetchone()
    assert row["action"] == "monitored"        # but recorded


def test_bot_ua_blocked_when_enforced(app, monkeypatch):
    monkeypatch.setenv("BOT_DEFENSE_ENFORCE", "1")
    r = app.test_client().post("/login", data={"username": "x"},
                               headers={"User-Agent": "curl/8.5"})
    assert r.status_code == 403


def test_real_browser_and_internal_pass(app):
    c = app.test_client()
    assert c.post("/login", data={"username": "x"},
                  headers={"User-Agent": "Mozilla/5.0 (Windows) Chrome/126"}).status_code == 200
    assert c.post("/login", data={"username": "x"},
                  headers={"User-Agent": "SolarPro-BetaMonitor/1.0"}).status_code == 200


def test_webhooks_never_touched(app):
    r = app.test_client().post("/paystack/webhook", data={"company_website": "bot"},
                               headers={"User-Agent": "python-requests/2.31"})
    assert r.status_code == 200 and r.data == b"wh"


def test_fails_open_when_db_broken():
    @contextlib.contextmanager
    def broken_db():
        raise RuntimeError("db gone")
        yield  # pragma: no cover

    a = _make_app(broken_db)
    c = a.test_client()
    # honeypot still blocks (decision doesn't need the DB; recording is best-effort)
    assert c.post("/login", data={"company_website": "bot"}).status_code == 403
    # a real browser passes even though recording fails
    assert c.post("/login", data={"username": "x"},
                  headers={"User-Agent": "Mozilla/5.0 Chrome/126"}).status_code == 200
