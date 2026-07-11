"""AI-SOC Slice 8 tests — knowledge base (redacted) + Supervisor.

Load-bearing acceptance (plan Slice 8 / spec L1887-1895): the knowledge article
must NOT expose secrets/tokens/PII — proven with planted secrets. Plus: articles
are searchable; the Supervisor produces a digest.
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


# ── redaction (the security-critical piece) ─────────────────────────────────

def test_redact_masks_secrets_and_pii(app):
    planted = ("key sk-liveABCDEFGH12345678 and xkeysib-abcdef1234567890 and "
               "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig and password=hunter2 and "
               "user@example.com and AKIAABCDEFGHIJKLMNOP and "
               "deadbeefdeadbeefdeadbeefdeadbeef00 and "
               "AIzaSyABCDEFGHIJKLMNOPQRSTUVWX12345678 and "
               "xoxb-1234567890-ABCDEFGHIJ and sk_live_ABCDEFGH12345678")
    out = app._soc_redact(planted)
    for leak in ("sk-liveABCDEFGH12345678", "xkeysib-abcdef1234567890",
                 "hunter2", "user@example.com", "AKIAABCDEFGHIJKLMNOP",
                 "deadbeefdeadbeefdeadbeefdeadbeef00",
                 "AIzaSyABCDEFGHIJKLMNOPQRSTUVWX12345678",
                 "xoxb-1234567890-ABCDEFGHIJ", "sk_live_ABCDEFGH12345678"):
        assert leak not in out, f"redaction leaked: {leak}"


def test_planted_secret_not_in_written_article(app):
    with app.app.app_context():
        from web_app import get_db
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        secret = "sk-live" + _uk().replace("_", "") + "ZZ"
        # create an incident whose summary/cause carries a planted secret
        with get_db() as c:
            app._ensure_soc_schema(c)
            c.execute(
                "INSERT INTO support_incidents (status, severity, module, title, summary, probable_cause, fingerprint) "
                "VALUES (?,?,?,?,?,?,?)",
                ("Closed", "P2", "billing", "Payment failure",
                 "leaked token " + secret + " in summary",
                 "cause references password=" + secret, "kb_" + _uk()))
            inc = c.execute("SELECT MAX(id) FROM support_incidents").fetchone()[0]
        aid = app.soc_knowledge_write(inc)
        assert aid
        with get_db() as c:
            row = c.execute("SELECT title, symptom, root_cause, resolution, tags, redacted "
                            "FROM knowledge_articles WHERE id=?", (aid,)).fetchone()
            blob = " ".join(str(x) for x in (row if not hasattr(row, "keys")
                                             else [row[k] for k in row.keys()]))
        assert secret not in blob, "planted secret leaked into the knowledge article"


# ── search + supervisor ─────────────────────────────────────────────────────

def test_knowledge_search_finds_article(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "1")
        from web_app import get_db
        tag = "srch" + _uk().replace("_", "")
        with get_db() as c:
            app._ensure_soc_schema(c)
            c.execute("INSERT INTO support_incidents (status, severity, module, title, fingerprint) "
                      "VALUES (?,?,?,?,?)", ("Closed", "P3", tag, "findme " + tag, "kf_" + _uk()))
            inc = c.execute("SELECT MAX(id) FROM support_incidents").fetchone()[0]
        app.soc_knowledge_write(inc)
        res = app.soc_knowledge_search(tag)
        assert any(tag in (r.get("title") or "") or tag in (r.get("tags") or "") for r in res)


def test_supervisor_report_shape(app):
    with app.app.app_context():
        rep = app.soc_supervisor_report()
    for k in ("by_severity", "by_status", "open_incidents",
              "duplicate_fingerprints", "articles", "agent_runs"):
        assert k in rep


def test_knowledge_write_disabled_none(app):
    with app.app.app_context():
        app._admin_setting_set(app._SOC_ENABLED_KEY, "0")
        assert app.soc_knowledge_write(1) is None


# ── admin routes ────────────────────────────────────────────────────────────

def test_admin_routes_require_admin(app):
    client = app.app.test_client()
    assert client.get("/admin/soc/knowledge").status_code in (301, 302, 401, 403)
    assert client.get("/admin/soc/supervisor").status_code in (301, 302, 401, 403)
