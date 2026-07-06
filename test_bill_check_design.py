"""Tests for the Check-My-Bill -> Solar Design auto-handoff (owner feature #1).

Covers:
  - _bc_synthetic_loads: undiversified monthly energy of the synthetic load
    equals the bill-estimated kWh (so coverage reads ~100%).
  - _bc_design_seed: seeds Ghana/GHS, a recomputed bill_check snapshot, and one
    synthetic load.
  - _run_project_design: produces the full results shape + a Full-Load coverage.
  - POST /bill-check/design (logged-in): creates a project + 302 -> results.
  - POST /bill-check/design (anon): stashes payload + 302 -> /register?next=...
  - GET  /bill-check/design/continue: consumes the stash + 302 -> results.
  - Plan-limit breach: free plan at its cap -> 302 -> dashboard (no project).
"""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

RES = "Residential Standard (0-300 kWh/month)"
_RUN_TAG = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label: str) -> str:
    _SEQ[0] += 1
    return f"bcd_{label}{_SEQ[0]}_{_RUN_TAG}"[:32]


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


def _mk_user(app, plan="business") -> int:
    uname = _u("u")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,referral_code) "
                "VALUES (?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "Tester", plan, _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def _project_data(app, pid):
    import json
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            row = c.execute("SELECT data_json FROM projects WHERE id=?", (pid,)).fetchone()
    return json.loads(row[0]) if row else None


# ── Unit: synthetic load energy round-trips the bill kWh ─────────────────────
def test_synthetic_load_energy_matches_bill_kwh(app):
    loads = app._bc_synthetic_loads(300.0)
    assert len(loads) == 1
    ld = loads[0]
    # undiversified monthly energy = w*q*h/1000 * 30.44
    monthly = ld["wattage"] * ld["quantity"] * ld["hours"] / 1000.0 * 30.44
    assert abs(monthly - 300.0) < 1.0
    assert ld["demand_factor"] == 1.0


def test_synthetic_load_zero_bill(app):
    loads = app._bc_synthetic_loads(0)
    assert loads[0]["wattage"] == 0.0


# ── Unit: seed produces Ghana/GHS + bill_check + one load ────────────────────
def test_design_seed_shape(app):
    with app.app.app_context():
        data, loads, name = app._bc_design_seed({"actual_bill": 800, "category": RES})
    assert data["country"] == "Ghana" and data["region"] == "Greater Accra"
    assert data["currency"] == "GHS"
    assert data["system_type"] == "grid-tied"
    assert data["from_bill_check"] is True
    assert data["bill_check"]["actual_bill"] == 800
    assert len(loads) == 1
    assert "bill" in name.lower()


# ── Unit: full design pass yields results + ~100% coverage ───────────────────
def test_run_project_design_full_coverage(app):
    with app.app.app_context():
        data, loads, _ = app._bc_design_seed({"actual_bill": 800, "category": RES})
        app._run_project_design(999_000_001, data, loads)
    assert "results" in data
    r = data["results"]
    for key in ("pv_kw", "num_panels", "inv_kw", "boq_grand", "economics"):
        assert key in r
    cov = data["coverage"]
    assert cov["available"] is True
    # Synthetic load energy == bill inversion energy -> Full Load (~100%).
    assert 90.0 <= cov["coverage_pct"] <= 115.0
    assert cov["coverage_status"] in (
        "Full Load Design", "Near Full Load Design",
        "Oversized or Future Load Design")


# ── Route: logged-in auto-design creates a project and redirects to results ──
def test_design_route_logged_in_creates_project(app, client):
    uid = _mk_user(app, plan="business")
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
        s["_csrf"] = "tok"
    r = client.post("/bill-check/design",
                    json={"actual_bill": 750, "category": RES},
                    headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "/project/" in loc and loc.endswith("/results")
    pid = int(loc.split("/project/")[1].split("/")[0])
    data = _project_data(app, pid)
    assert data and "results" in data
    assert data.get("from_bill_check") is True
    assert data["coverage"]["available"] is True


# ── Route: CSRF is enforced ──────────────────────────────────────────────────
def test_design_route_requires_csrf(app, client):
    uid = _mk_user(app, plan="business")
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "tok"
    r = client.post("/bill-check/design",
                    json={"actual_bill": 750, "category": RES})  # no header
    assert r.status_code == 403


# ── Route: anonymous stashes the bill and bounces through registration ───────
def test_design_route_anon_stashes_and_registers(app):
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["_csrf"] = "tok"
    r = c.post("/bill-check/design",
               json={"actual_bill": 500, "category": RES},
               headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert "/register" in loc
    assert "next=" in loc  # /bill-check/design/continue, url-encoded
    with c.session_transaction() as s:
        stash = s.get("pending_bill_design")
    assert stash is not None
    assert float(stash["actual_bill"]) == 500


# ── Route: continue GET is non-mutating; POST consumes stash and designs ─────
def test_design_continue_get_is_interstitial_then_post_designs(app):
    uid = _mk_user(app, plan="business")
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
        s["pending_bill_design"] = {"actual_bill": 900, "category": RES}
        s["_csrf"] = "tok"
    # GET must NOT mutate: returns the auto-submit interstitial, stash intact.
    g = c.get("/bill-check/design/continue")
    assert g.status_code == 200
    body = g.get_data(as_text=True)
    assert "/bill-check/design/continue" in body and 'name="_csrf"' in body
    with c.session_transaction() as s:
        assert s.get("pending_bill_design") is not None  # not consumed by GET
    # POST (CSRF) actually creates the project + redirects to results.
    r = c.post("/bill-check/design/continue", headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/results")
    with c.session_transaction() as s:
        assert "pending_bill_design" not in s  # consumed exactly once


def test_design_continue_post_requires_csrf(app):
    uid = _mk_user(app, plan="business")
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["pending_bill_design"] = {"actual_bill": 900, "category": RES}
        s["_csrf"] = "tok"
    r = c.post("/bill-check/design/continue")  # no CSRF header
    assert r.status_code == 403


# ── Route: continue with no stash redirects back to the bill-check landing ───
def test_design_continue_without_stash(app):
    uid = _mk_user(app, plan="business")
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
    r = c.get("/bill-check/design/continue")
    assert r.status_code == 302
    assert "/bill-check" in r.headers["Location"]


# ── Route: zero / sub-service-charge bill is rejected server-side ────────────
def test_design_route_rejects_zero_bill(app):
    uid = _mk_user(app, plan="business")
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
        s["_csrf"] = "tok"
    r = c.post("/bill-check/design",
               json={"actual_bill": 0, "category": RES},
               headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 302
    assert "/results" not in r.headers["Location"]  # no degenerate project


# ── Unit: user-tuned Cost/kWp (GHS) is threaded into the design ──────────────
def test_design_seed_threads_cost_per_kwp(app):
    with app.app.app_context():
        data, _, _ = app._bc_design_seed(
            {"actual_bill": 800, "category": RES, "system_cost_per_kwp": 9000})
    # 9000 GHS / fx(12) == 750 USD/kWp
    assert abs(data["cost_usd_kwp"] - 9000 / data["fx_usd"]) < 1e-6


# ── Route: free plan at its cap cannot auto-design (redirect, no project) ─────
def test_design_route_plan_limit(app):
    import json
    uid = _mk_user(app, plan="free")
    with app.app.app_context():
        from web_app import get_db
        with get_db() as c:
            c.execute(
                "INSERT INTO projects (user_id, name, data_json) VALUES (?,?,?)",
                (uid, "existing", json.dumps({})))
    c = app.app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = "tester"
        s["_csrf"] = "tok"
    r = c.post("/bill-check/design",
               json={"actual_bill": 600, "category": RES},
               headers={"X-CSRF-Token": "tok"})
    assert r.status_code == 302
    assert "/results" not in r.headers["Location"]  # blocked before design
