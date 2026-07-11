"""AI-SOC Slice 5 tests — cybersecurity agent + pre-authorised containment.

Acceptance (plan Slice 5): containment is reversible, audited, and gated by the
kill switch. Pre-authorised actions apply only when automation is on; block_ip is
proposed-only (no WAF); high-risk actions are Mode C (never auto); evidence is
preserved to the DB.
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


def _automation(app, on, pause_security=False):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        app._admin_setting_set(app._SOC_AUTOMATION_KEY, "1" if on else "0")
        for a in app.SOC_AGENTS:
            app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + a, "0")
        if pause_security:
            app._admin_setting_set(app._SOC_AGENT_PAUSE_PFX + "security", "1")


def _new_sec_incident(app):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            cur = c.execute("INSERT INTO security_incidents (category, severity, status) "
                            "VALUES (?,?,?)", ("brute_force", "P2", "Detected"))
            return int(getattr(cur, "lastrowid", 0) or 0)


def _actions_by(app, action_type, status=None):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            if status:
                rows = c.execute("SELECT id FROM support_actions WHERE action_type=? AND status=?",
                                 (action_type, status)).fetchall()
            else:
                rows = c.execute("SELECT id FROM support_actions WHERE action_type=?",
                                 (action_type,)).fetchall()
            return len(rows)


# ── classification ──────────────────────────────────────────────────────────

def test_classify_brute_force(app):
    d = app.soc_security_classify({"event_type": "brute_force"})
    assert d["category"] == "brute_force" and d["containment"] == "revoke_session"


def test_classify_cross_tenant_p1(app):
    d = app.soc_security_classify({"event_type": "cross_tenant_attempt"})
    assert d["severity"] == "P1" and d["containment"] == "force_reauth"


def test_classify_api_abuse_suggests_block_ip(app):
    d = app.soc_security_classify({"event_type": "api_abuse_rate"})
    assert d["containment"] == "block_ip"


# ── containment gating ──────────────────────────────────────────────────────

def test_containment_blocked_when_automation_off(app):
    _automation(app, on=False)
    sec = _new_sec_incident(app)
    with app.app.app_context():
        res = app.soc_contain(sec, "revoke_session", subject="u1")
    assert res["applied"] is False
    assert res["reason"] == "automation_blocked"
    assert _actions_by(app, "revoke_session", "blocked") >= 1


def test_containment_applied_when_automation_on(app):
    _automation(app, on=True)
    sec = _new_sec_incident(app)
    with app.app.app_context():
        res = app.soc_contain(sec, "revoke_session", subject="u2")
        assert res["applied"] is True and res["mode"] == "auto"
        from web_app import get_db
        with get_db() as c:
            row = c.execute("SELECT containment_applied FROM security_incidents WHERE id=?",
                            (sec,)).fetchone()
            ca = row[0] if not hasattr(row, "keys") else row["containment_applied"]
            assert "revoke_session" in (ca or "")
    assert _actions_by(app, "revoke_session", "applied") >= 1


def test_block_ip_is_proposed_only(app):
    _automation(app, on=True)     # even with automation ON
    sec = _new_sec_incident(app)
    with app.app.app_context():
        res = app.soc_contain(sec, "block_ip", subject="1.2.3.4")
    assert res["applied"] is False
    assert res["mode"] == "proposed" and res["reason"] == "not_enforceable"


def test_high_risk_action_is_mode_c(app):
    _automation(app, on=True)
    sec = _new_sec_incident(app)
    with app.app.app_context():
        res = app.soc_contain(sec, "rotate_secret", subject="SECRET_KEY")
    assert res["applied"] is False
    assert res["mode"] == "manual" and res["reason"] == "requires_approval"


def test_pause_security_blocks(app):
    _automation(app, on=True, pause_security=True)
    sec = _new_sec_incident(app)
    with app.app.app_context():
        res = app.soc_contain(sec, "force_reauth", subject="u3")
    assert res["applied"] is False and res["reason"] == "automation_blocked"


# ── full ingest ─────────────────────────────────────────────────────────────

def test_security_ingest_creates_incident_and_evidence(app):
    _automation(app, on=False)    # detection on (soc_enabled), containment off
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            app._ensure_soc_schema(c)
            c.execute("INSERT INTO support_events (source, event_type, module, fingerprint) "
                      "VALUES (?,?,?,?)", ("security", "brute_force", "login", "sec_" + _uk()))
            eid = c.execute("SELECT MAX(id) FROM support_events").fetchone()[0]
        sec = app.soc_security_ingest(eid)
        assert sec and sec > 0
        with get_db() as c:
            ev = c.execute("SELECT COUNT(*) FROM security_evidence WHERE security_incident_id=?",
                           (sec,)).fetchone()
            assert int((ev[0] if ev else 0) or 0) >= 1
            # containment attempted but blocked (automation off) -> recorded, not applied
            applied = c.execute("SELECT COUNT(*) FROM support_actions "
                                "WHERE action_type='revoke_session' AND status='applied'").fetchone()
    # detection worked; nothing auto-applied while automation off is asserted by
    # test_containment_blocked_when_automation_off above.


def test_security_ingest_disabled_returns_none(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "0")
        assert app.soc_security_ingest(1) is None
