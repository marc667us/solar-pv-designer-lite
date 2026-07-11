"""AI-SOC Slice 2 tests — orchestrator + deterministic classification.

Acceptance (plan §6 Slice 2): P1..P4 map per spec §6/§8; DB-unreachable => P1;
cosmetic => P4; every NEW incident appears in the admin inbox; the orchestrator
is deterministic and records an agent run. Still zero actions.
"""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _uk():
    _SEQ[0] += 1
    return f"{_RUN}_{_SEQ[0]}"


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


def _soc_on(app, on=True):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1" if on else "0")
        app._admin_setting_set(app._SOC_AUTOMATION_KEY, "0")


# ── deterministic classifier ────────────────────────────────────────────────

def test_classify_platform_down_is_p1(app):
    d = app._soc_classify({"source": "cron", "event_type": "health_degraded",
                           "module": "health.boot"})
    assert d["severity"] == "P1" and d["tier"] == "tier3"


def test_classify_database_is_p1(app):
    d = app._soc_classify({"source": "database", "event_type": "db_error",
                           "module": "database"})
    assert d["severity"] == "P1"


def test_classify_cosmetic_is_p4(app):
    d = app._soc_classify({"source": "backend", "event_type": "ui_glitch",
                           "module": "dashboard"})
    assert d["severity"] == "P4" and d["tier"] == "tier1"


def test_classify_backend_5xx_is_p3(app):
    d = app._soc_classify({"source": "backend", "event_type": "http_5xx",
                           "module": "marketplace", "error_code": "500"})
    assert d["severity"] == "P3" and d["tier"] == "tier2"


def test_classify_payment_5xx_is_p2(app):
    d = app._soc_classify({"source": "backend", "event_type": "http_5xx",
                           "module": "paystack_verify", "error_code": "500"})
    assert d["severity"] == "P2" and d["tier"] == "tier3"


def test_classify_security_cross_tenant_is_p1_security(app):
    d = app._soc_classify({"source": "security", "event_type": "cross_tenant_attempt",
                           "module": "projects"})
    assert d["severity"] == "P1" and d["tier"] == "security"


def test_classify_generic_security_is_p2_security(app):
    d = app._soc_classify({"source": "security", "event_type": "brute_force",
                           "module": "login"})
    assert d["severity"] == "P2" and d["tier"] == "security"


# ── orchestration ───────────────────────────────────────────────────────────

def _incident_count(app, fp):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            r = c.execute("SELECT COUNT(*) FROM support_incidents WHERE fingerprint=?",
                          (fp,)).fetchone()
            return int((r[0] if r else 0) or 0)


def test_orchestrate_creates_incident_and_inbox(app):
    _soc_on(app, True)
    with app.app.app_context():
        from web_app import get_db
        mod = "orch_" + _uk()
        eid = app.soc_capture_signal(source="backend", event_type="http_5xx",
                                     module=mod, error_code="500")
        assert eid and eid > 0
        inc = app.soc_orchestrate(eid)
        assert inc and inc > 0
        with get_db() as c:
            row = c.execute("SELECT severity, tier, status "
                            "FROM support_incidents WHERE id=?", (inc,)).fetchone()
            assert row is not None
            assert (row[2] if not hasattr(row, "keys") else row["status"]) == "Classified"
            # event now linked to the incident
            ev = c.execute("SELECT incident_id FROM support_events WHERE id=?",
                           (eid,)).fetchone()
            assert (ev[0] if not hasattr(ev, "keys") else ev["incident_id"]) == inc
            # inbox mirror written
            n = c.execute("SELECT COUNT(*) FROM admin_notifications "
                          "WHERE ref_type='support_incident' AND ref_id=?",
                          (inc,)).fetchone()
            assert int((n[0] if n else 0) or 0) >= 1
            # orchestrator agent run recorded
            ar = c.execute("SELECT COUNT(*) FROM support_agent_runs "
                           "WHERE agent='orchestrator' AND incident_id=?",
                           (inc,)).fetchone()
            assert int((ar[0] if ar else 0) or 0) >= 1


def test_orchestrate_dedups_same_fingerprint(app):
    _soc_on(app, True)
    with app.app.app_context():
        from web_app import get_db
        fp = "fp_" + _uk()
        # two distinct events sharing a fingerprint (bypass capture dedup)
        with get_db() as c:
            app._ensure_soc_schema(c)
            for _ in range(2):
                c.execute("INSERT INTO support_events "
                          "(source, event_type, severity, module, error_code, fingerprint) "
                          "VALUES (?,?,?,?,?,?)",
                          ("backend", "http_5xx", "P3", "dd_" + _uk(), "500", fp))
            ids = [r[0] for r in c.execute(
                "SELECT id FROM support_events WHERE fingerprint=? ORDER BY id", (fp,)).fetchall()]
        for eid in ids:
            app.soc_orchestrate(eid)
        assert _incident_count(app, fp) == 1   # attached, not duplicated


def test_orchestrate_disabled_returns_none(app):
    _soc_on(app, False)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            c.execute("INSERT INTO support_events (source, event_type, module, fingerprint) "
                      "VALUES (?,?,?,?)", ("backend", "http_5xx", "off_" + _uk(), "off_" + _uk()))
            eid = c.execute("SELECT MAX(id) FROM support_events").fetchone()[0]
        assert app.soc_orchestrate(eid) is None


def test_orchestrate_pending_batch(app):
    _soc_on(app, True)
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            base = "pend_" + _uk()
            for i in range(2):
                c.execute("INSERT INTO support_events "
                          "(source, event_type, module, error_code, fingerprint) "
                          "VALUES (?,?,?,?,?)",
                          ("backend", "http_5xx", base + str(i), "500", base + str(i)))
        n = app.soc_orchestrate_pending(limit=50)
        assert n >= 2
