"""AI-SOC Slice 6 tests — Tier 2 diagnostics (READ-ONLY).

Load-bearing acceptance (plan Slice 6): "Tier 2 mutates nothing." Enforced here
by a count-invariance check across every SOC table before/after diagnose().
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


def _mk_incident(app, severity_module="tier2"):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        eid = app.soc_capture_signal(source="backend", event_type="http_5xx",
                                     module=severity_module + "_" + _uk(), error_code="500")
        return app.soc_orchestrate(eid)


_TABLES = ("support_incidents", "support_events", "support_actions",
           "support_agent_runs", "security_incidents", "knowledge_articles",
           "support_approvals")


def _snapshot(app):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            out = {}
            for t in _TABLES:
                r = c.execute("SELECT COUNT(*) FROM " + t).fetchone()
                out[t] = int((r[0] if r else 0) or 0)
            return out


def test_diagnose_mutates_nothing(app):
    inc = _mk_incident(app)
    before = _snapshot(app)
    with app.app.app_context():
        d = app.soc_tier2_diagnose(inc)
    after = _snapshot(app)
    assert d is not None
    assert before == after, "Tier 2 diagnose MUST NOT mutate any SOC table"


def test_diagnose_returns_hypothesis_fields(app):
    inc = _mk_incident(app)
    with app.app.app_context():
        d = app.soc_tier2_diagnose(inc)
    for k in ("root_cause", "proposed_fix", "rollback_plan", "risk_level",
              "evidence", "correlated"):
        assert k in d
    assert d["risk_level"] in ("low", "medium", "high")


def test_diagnose_disabled_returns_none(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "0")
        assert app.soc_tier2_diagnose(1) is None


def test_diagnose_missing_incident_none(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        assert app.soc_tier2_diagnose(99999999) is None


def test_record_writes_proposed_action(app):
    inc = _mk_incident(app)
    with app.app.app_context():
        from web_app import get_db
        aid = app.soc_tier2_record(inc)
        assert aid is not None
        with get_db() as c:
            row = c.execute("SELECT agent, action_type, mode, status FROM support_actions "
                            "WHERE id=?", (aid,)).fetchone()
            vals = [row[i] if not hasattr(row, "keys") else row[k]
                    for i, k in enumerate(("agent", "action_type", "mode", "status"))]
            assert vals[0] == "tier2" and vals[2] == "proposed"
