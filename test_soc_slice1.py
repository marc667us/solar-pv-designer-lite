"""AI-SOC Slice 1 tests — signal capture (detection only, ZERO actions).

Load-bearing acceptance (plan §6 Slice 1): "a deliberate 500 produces exactly
one support_events row; app latency unchanged." Plus: capture is OFF unless the
soc_enabled master flag is on; dedupe collapses (module, error_code, hour); the
cron ingest is bearer-gated + fail-closed; nothing ever raises.
"""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"


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

    # Register a throwaway route that raises, so we can drive a real 500 through
    # the error handlers + the after_request capture hook.
    def _boom():
        raise RuntimeError("deliberate boom for SOC 5xx capture test")
    try:
        mod.app.add_url_rule("/_soc_test_boom", "_soc_test_boom", _boom)
    except Exception:
        pass
    return mod


@pytest.fixture
def client(app):
    return app.app.test_client()


def _soc_on(app, on=True):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1" if on else "0")
        app._admin_setting_set(app._SOC_AUTOMATION_KEY, "0")  # actions stay off


def _clear_events(app):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            try:
                c.execute("DELETE FROM support_events")
            except Exception:
                pass


def _count(app, event_type):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            r = c.execute("SELECT COUNT(*) FROM support_events WHERE event_type=?",
                          (event_type,)).fetchone()
            return int((r[0] if r else 0) or 0)


# ── gating ──────────────────────────────────────────────────────────────────

def test_capture_disabled_by_default(app):
    _soc_on(app, False)
    _clear_events(app)
    with app.app.app_context():
        rid = app.soc_capture_signal(source="test", event_type="unit_off",
                                     module="m_" + _RUN, error_code="x")
    assert rid is None                       # master flag off -> no capture
    assert _count(app, "unit_off") == 0


def test_capture_writes_one_row_when_enabled(app):
    _soc_on(app, True)
    _clear_events(app)
    with app.app.app_context():
        rid = app.soc_capture_signal(source="test", event_type="unit_on",
                                     module="m_" + _RUN, error_code="500")
    assert rid is None or rid == 0 or rid > 0
    assert _count(app, "unit_on") == 1


def test_dedupe_same_module_code_hour(app):
    _soc_on(app, True)
    _clear_events(app)
    with app.app.app_context():
        a = app.soc_capture_signal(source="test", event_type="unit_dedupe",
                                   module="dm_" + _RUN, error_code="500")
        b = app.soc_capture_signal(source="test", event_type="unit_dedupe",
                                   module="dm_" + _RUN, error_code="500")
    assert b == 0                            # second identical -> deduped
    assert _count(app, "unit_dedupe") == 1   # exactly one row


# ── the load-bearing acceptance: a 500 -> exactly one row ───────────────────

def _wait_count(app, event_type, want, timeout=4.0):
    """The 5xx capture is dispatched to a background thread, so poll briefly."""
    deadline = time.time() + timeout
    n = _count(app, event_type)
    while n < want and time.time() < deadline:
        time.sleep(0.1)
        n = _count(app, event_type)
    return n


def test_deliberate_500_produces_one_event(app, client):
    _soc_on(app, True)
    _clear_events(app)
    r1 = client.get("/_soc_test_boom")
    assert r1.status_code == 500
    # a second identical 500 in the same hour must NOT add a second row
    r2 = client.get("/_soc_test_boom")
    assert r2.status_code == 500
    # capture is async (fire-and-forget) -> wait for the row, then assert exactly 1
    assert _wait_count(app, "http_5xx", 1) == 1
    time.sleep(0.3)  # give any (incorrect) second write a chance to land
    assert _count(app, "http_5xx") == 1


def test_capture_never_raises_on_bad_input(app):
    _soc_on(app, True)
    with app.app.app_context():
        # objects that don't json-serialise cleanly must not blow up the writer
        app.soc_capture_signal(source="test", event_type="unit_badpayload",
                               module="bp_" + _RUN, error_code="1",
                               payload=object())  # not JSON-serialisable


# ── cron ingest ─────────────────────────────────────────────────────────────

def test_ingest_fail_closed_without_bearer(app, client, monkeypatch):
    # METRICS_BEARER unset -> ingest must reject even a well-formed post.
    monkeypatch.delenv("METRICS_BEARER", raising=False)
    r = client.post("/api/soc/ingest", json={"event_type": "x"})
    assert r.status_code == 401


def test_ingest_requires_correct_bearer(app, client, monkeypatch):
    monkeypatch.setenv("METRICS_BEARER", "sekret_" + _RUN)
    # wrong token
    r = client.post("/api/soc/ingest", json={"event_type": "x"},
                    headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_ingest_captures_with_bearer_when_enabled(app, client, monkeypatch):
    tok = "sekret_" + _RUN
    monkeypatch.setenv("METRICS_BEARER", tok)
    _soc_on(app, True)
    _clear_events(app)
    r = client.post("/api/soc/ingest",
                    json={"event_type": "ingest_ok", "module": "ig_" + _RUN,
                          "error_code": "503", "severity": "P2"},
                    headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 202
    assert r.get_json()["captured"] is True
    assert _count(app, "ingest_ok") == 1


def test_ingest_403_when_soc_disabled(app, client, monkeypatch):
    tok = "sekret_" + _RUN
    monkeypatch.setenv("METRICS_BEARER", tok)
    _soc_on(app, False)
    r = client.post("/api/soc/ingest",
                    json={"event_type": "ingest_off"},
                    headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403
