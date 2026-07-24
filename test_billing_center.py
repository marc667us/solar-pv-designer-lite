"""Tests for new_billing_center.py (Slice 3: user billing/transaction preview).

Minimal Flask app + in-memory SQLite + stubbed render_template to capture the
context (the template extends base.html which needs the full app). No web_app
import, no network.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from flask import Flask

import new_billing_center as bc
import new_payment_disputes as pd


@pytest.fixture
def ctx(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
        "gateway TEXT, plan TEXT, amount_usd REAL, currency TEXT, reference TEXT, "
        "status TEXT, created_at TEXT)"
    )
    pd.ensure_disputes_schema(conn, False)
    # user 1 payments: paid (ref-A), refunded (ref-B via dispute), disputed (ref-C),
    # and a demo grant with empty reference.
    conn.executemany(
        "INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "paystack", "professional", 49, "USD", "ref-A", "success", "2026-07-24 10:00:00"),
            (1, "stripe",   "business",     99, "USD", "ref-B", "success", "2026-07-24 11:00:00"),
            (1, "paystack", "professional", 49, "USD", "ref-C", "success", "2026-07-24 12:00:00"),
            (1, "demo",     "professional",  0, "USD", "",      "success", "2026-07-24 13:00:00"),
            (2, "stripe",   "business",     99, "USD", "ref-X", "success", "2026-07-24 09:00:00"),
        ],
    )
    conn.execute("INSERT INTO payment_disputes (reference,user_id,status,created_at,updated_at) "
                 "VALUES ('ref-B',1,'refunded','x','x')")
    conn.execute("INSERT INTO payment_disputes (reference,user_id,status,created_at,updated_at) "
                 "VALUES ('ref-C',1,'open','x','x')")
    conn.commit()

    @contextlib.contextmanager
    def get_db():
        yield conn
        conn.commit()

    app = Flask(__name__)
    app.secret_key = "test"
    app.config["TESTING"] = True

    captured = {}
    monkeypatch.setattr(bc, "render_template",
                        lambda tpl, **kw: captured.update({"tpl": tpl, **kw}) or "ok")

    bc.register_billing_center(
        app,
        get_db=get_db,
        login_required=lambda f: f,
        current_user=lambda: {"id": 1, "plan": "business"},
        is_postgres=lambda: False,
    )
    return app, captured


def _client_as(app, uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
    return c


def test_lists_only_own_transactions(ctx):
    app, cap = ctx
    assert _client_as(app, 1).get("/billing").status_code == 200
    assert cap["tpl"] == "billing.html"
    # user 1 has 4 payments; user 2's ref-X must not appear
    refs = [t["reference"] for t in cap["txns"]]
    assert "ref-X" not in refs
    assert cap["count"] == 4


def test_status_derivation(ctx):
    app, cap = ctx
    _client_as(app, 1).get("/billing")
    by_ref = {t["reference"]: t for t in cap["txns"]}
    assert by_ref["ref-A"]["kind"] == "paid"
    assert by_ref["ref-B"]["kind"] == "refunded"
    assert by_ref["ref-C"]["kind"] == "disputed"
    assert by_ref[""]["kind"] == "paid"        # demo grant, no dispute


def test_total_paid_excludes_refunds(ctx):
    app, cap = ctx
    _client_as(app, 1).get("/billing")
    # 49 (A) + 49 (C) + 0 (demo) = 98 ; ref-B (99) is refunded -> excluded
    assert cap["total_paid"] == 98.0


def test_works_when_disputes_table_absent(monkeypatch):
    # A user who has never opened the disputes page: payment_disputes may not
    # exist yet. /billing must still render (ensure creates it; the read is
    # guarded).
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
        "gateway TEXT, plan TEXT, amount_usd REAL, currency TEXT, reference TEXT, "
        "status TEXT, created_at TEXT)"
    )
    conn.execute("INSERT INTO payments (user_id,gateway,plan,amount_usd,currency,reference,status,created_at) "
                 "VALUES (1,'paystack','professional',49,'USD','ref-A','success','x')")
    conn.commit()

    @contextlib.contextmanager
    def get_db():
        yield conn
        conn.commit()

    app = Flask(__name__)
    app.secret_key = "test"
    captured = {}
    monkeypatch.setattr(bc, "render_template",
                        lambda tpl, **kw: captured.update({"tpl": tpl, **kw}) or "ok")
    bc.register_billing_center(app, get_db=get_db, login_required=lambda f: f,
                               current_user=lambda: {"id": 1}, is_postgres=lambda: False)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = 1
    assert c.get("/billing").status_code == 200
    assert captured["txns"][0]["kind"] == "paid"
