"""Tests for default per-category operating hours ("timers"), owner directive
2026-07-06: a load must never enter the design calculation at 0 hours; the
operator's entered hours always take precedence over the category default.
Applies in the main project wizard (project_loads POST)."""
from __future__ import annotations

import importlib.util
import json
import time
import uuid
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label):
    _SEQ[0] += 1
    return f"hrs_{label}{_SEQ[0]}_{_RUN}"[:32]


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


@pytest.fixture
def client(app):
    return app.app.test_client()


def _mk_user(app):
    uname = _u("u")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,referral_code) "
                "VALUES (?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "T", "business", _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _mk_project(app, uid):
    seed = {"country": "Ghana", "region": "Greater Accra", "psh": 4.8,
            "currency": "GHS", "symbol": "GHS ", "cost_usd_kwp": 850, "fx_usd": 12.0}
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            c.execute("INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?)",
                      (uid, "hrs test", json.dumps(seed)))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _project_loads(app, pid):
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute("SELECT data_json FROM projects WHERE id=?", (pid,)).fetchone()
    return json.loads(row[0]).get("loads", [])


# ── Unit: the default-hours helper ───────────────────────────────────────────
def test_default_hours_values(app):
    assert app._default_hours_for("Lighting") == 14.0  # owner-specified
    assert app._default_hours_for("Cooling") == 10.0   # fans, owner-specified
    assert app._default_hours_for("Office") == 8.0
    assert app._default_hours_for("Unknown category") == 4.0  # fallback


# ── Wizard POST: blank hours -> category default; typed hours -> preserved ────
def test_loads_post_applies_default_and_preserves_typed(app, client):
    uid = _mk_user(app)
    pid = _mk_project(app, uid)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "t"
        s["_csrf"] = "tok"
    # Two loads: L1 Lighting with BLANK hours -> should default to 6;
    #            L2 Cooling with typed 5 hours -> should stay 5.
    form = [
        ("_csrf", "tok"),
        ("load_name[]", "L1"), ("load_cat[]", "Lighting"),
        ("load_watt[]", "100"), ("load_qty[]", "10"),
        ("load_hours[]", ""), ("load_df[]", ""),
        ("load_name[]", "L2"), ("load_cat[]", "Cooling"),
        ("load_watt[]", "1500"), ("load_qty[]", "1"),
        ("load_hours[]", "5"), ("load_df[]", ""),
    ]
    r = client.post(f"/project/{pid}/loads", data=MultiDict(form))
    assert r.status_code in (302, 200)
    loads = _project_loads(app, pid)
    by = {ld["name"]: ld for ld in loads}
    assert by["L1"]["hours"] == 14.0  # blank -> Lighting default
    assert by["L2"]["hours"] == 5.0   # typed value preserved


def test_loads_post_zero_hours_becomes_default(app, client):
    uid = _mk_user(app)
    pid = _mk_project(app, uid)
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"
    form = [
        ("_csrf", "tok"),
        ("load_name[]", "Pump"), ("load_cat[]", "Pumps"),
        ("load_watt[]", "750"), ("load_qty[]", "1"),
        ("load_hours[]", "0"), ("load_df[]", ""),
    ]
    r = client.post(f"/project/{pid}/loads", data=MultiDict(form))
    assert r.status_code in (302, 200)
    loads = _project_loads(app, pid)
    assert loads and loads[0]["hours"] == 3.0  # 0 -> Pumps default
