"""Tests for new_payment_disputes.py (Slice 2: disputes + billing complaints).

Runs against a minimal Flask app with an in-memory SQLite DB and pass-through
auth stubs -- no web_app import, no network. GET routes render templates that
extend base.html (needs the full app), so render_template is stubbed to capture
the context; POST routes redirect and are exercised end-to-end via the client.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from flask import Flask

import new_payment_disputes as pd


@pytest.fixture
def ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
        "gateway TEXT, plan TEXT, amount_usd REAL, currency TEXT, reference TEXT, "
        "status TEXT, created_at TEXT)"
    )
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    conn.execute("INSERT INTO users (id, username, email) VALUES (1,'alice','a@x.com')")
    conn.execute("INSERT INTO users (id, username, email) VALUES (2,'bob','b@x.com')")
    # alice owns ref-A; bob owns ref-B
    conn.execute("INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status,created_at) "
                 "VALUES (1,'paystack','professional',49,'USD','ref-A','success','2026-07-24 10:00:00')")
    conn.execute("INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status,created_at) "
                 "VALUES (2,'stripe','business',99,'USD','ref-B','success','2026-07-24 11:00:00')")
    conn.commit()

    @contextlib.contextmanager
    def get_db():
        yield conn
        conn.commit()

    audits = []

    def _passthrough(f):
        return f

    app = Flask(__name__)
    app.secret_key = "test"
    app.config["TESTING"] = True

    pd.register_payment_disputes(
        app,
        get_db=get_db,
        login_required=_passthrough,
        admin_required=_passthrough,
        csrf_protect=lambda: None,
        current_user=lambda: {"id": 1, "username": "alice"},
        write_audit_event=lambda action, **kw: audits.append((action, kw)),
        record_payment_event=lambda *a, **k: None,
        send_email=lambda *a, **k: None,
        admin_notify=lambda *a, **k: None,
        is_postgres=lambda: False,
    )
    return app, conn, audits


def _client_as(app, uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
    return c


# ── schema ──────────────────────────────────────────────────────────────────

def test_schema_created_and_idempotent(ctx):
    _, conn, _ = ctx
    pd.ensure_disputes_schema(conn, False)
    pd.ensure_disputes_schema(conn, False)  # twice -> no error
    cols = [r[1] for r in conn.execute("PRAGMA table_info(payment_disputes)").fetchall()]
    for col in ("reference", "user_id", "category", "status", "resolution_note"):
        assert col in cols


# ── user: raise ─────────────────────────────────────────────────────────────

def test_user_raises_dispute_on_own_payment(ctx):
    app, conn, audits = ctx
    c = _client_as(app, 1)
    r = c.post("/account/disputes/new",
               data={"reference": "ref-A", "category": "duplicate_charge",
                     "description": "charged twice"})
    assert r.status_code == 302
    row = conn.execute("SELECT * FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()
    assert row["reference"] == "ref-A" and row["user_id"] == 1
    assert row["category"] == "duplicate_charge" and row["status"] == "open"
    assert row["gateway"] == "paystack" and row["amount_usd"] == 49  # pulled from payment, not trusted from form
    assert any(a[0] == "payment_dispute_opened" for a in audits)


def test_foreign_reference_is_not_linked(ctx):
    # alice references bob's payment -> must be treated as a general complaint,
    # never linked, and must not leak bob's amount/gateway.
    app, conn, _ = ctx
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "ref-B", "category": "other", "description": "hmm"})
    row = conn.execute("SELECT * FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()
    assert row["reference"] == ""          # cleared
    assert row["amount_usd"] == 0 and row["gateway"] == ""


def test_invalid_category_falls_back_to_other(ctx):
    app, conn, _ = ctx
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "", "category": "__nope__", "description": "x"})
    row = conn.execute("SELECT * FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()
    assert row["category"] == "other"


def test_empty_description_creates_no_row(ctx):
    app, conn, _ = ctx
    pd.ensure_disputes_schema(conn, False)  # empty-desc path returns before _ensure()
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "ref-A", "category": "other", "description": "   "})
    assert conn.execute("SELECT COUNT(*) FROM payment_disputes").fetchone()[0] == 0


# ── admin: update ───────────────────────────────────────────────────────────

def test_admin_updates_status_and_note(ctx):
    app, conn, audits = ctx
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "ref-A", "category": "refund_request", "description": "please refund"})
    did = conn.execute("SELECT id FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()[0]
    r = c.post(f"/admin/disputes/{did}/update",
               data={"status": "resolved", "resolution_note": "refund issued"})
    assert r.status_code == 302
    row = conn.execute("SELECT * FROM payment_disputes WHERE id=?", (did,)).fetchone()
    assert row["status"] == "resolved" and row["resolution_note"] == "refund issued"
    assert any(a[0] == "payment_dispute_updated" for a in audits)


def test_admin_rejects_invalid_status(ctx):
    app, conn, _ = ctx
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "", "category": "other", "description": "x"})
    did = conn.execute("SELECT id FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()[0]
    c.post(f"/admin/disputes/{did}/update",
           data={"status": "__bogus__", "resolution_note": "nope"})
    row = conn.execute("SELECT status FROM payment_disputes WHERE id=?", (did,)).fetchone()
    assert row["status"] == "open"   # unchanged


# ── GET handlers (render_template stubbed to capture context) ────────────────

def test_admin_list_and_detail_gather_data(ctx, monkeypatch):
    app, conn, _ = ctx
    captured = {}
    monkeypatch.setattr(pd, "render_template",
                        lambda tpl, **kw: captured.update({"tpl": tpl, **kw}) or "ok")
    c = _client_as(app, 1)
    c.post("/account/disputes/new",
           data={"reference": "ref-A", "category": "not_upgraded", "description": "no upgrade"})
    did = conn.execute("SELECT id FROM payment_disputes ORDER BY id DESC LIMIT 1").fetchone()[0]

    assert c.get("/admin/disputes").status_code == 200
    assert captured["tpl"] == "admin_disputes.html"
    assert len(captured["disputes"]) == 1
    assert captured["counts"]["open"] == 1

    assert c.get(f"/admin/disputes/{did}").status_code == 200
    assert captured["tpl"] == "admin_dispute_detail.html"
    assert captured["d"]["reference"] == "ref-A"
    assert captured["payment"] is not None
