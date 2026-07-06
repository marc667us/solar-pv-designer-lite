"""Tests for the Lighting & Fan Circuit Schedule (owner directive 2026-07-06).

Covers: grouping into circuits of <=7 points; summed load fixing the MCB; the
shared category timer (lights 14h / fans 10h); other categories excluded;
overload flagging; breaker BOM; and the route (RBAC + paid gate)."""
from __future__ import annotations

import importlib.util
import time
import uuid
from pathlib import Path

import pytest

_RUN = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
_SEQ = [0]


def _u(label):
    _SEQ[0] += 1
    return f"cir_{label}{_SEQ[0]}_{_RUN}"[:32]


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


# ── Engine: grouping ─────────────────────────────────────────────────────────
def test_groups_seven_points_per_circuit(app):
    loads = [{"name": "Downlight", "category": "Lighting", "wattage": 12, "quantity": 20}]
    s = app._circuit_schedule(loads)
    # 20 lights -> ceil(20/7) = 3 circuits of 7,7,6
    ltg = [c for c in s["circuits"] if c["type"] == "Lighting"]
    assert [c["points"] for c in ltg] == [7, 7, 6]
    assert s["summary"]["total_points"] == 20


def test_fans_grouped_separately_with_fan_timer(app):
    loads = [{"name": "Ceiling fan", "category": "Cooling", "wattage": 75, "quantity": 8}]
    s = app._circuit_schedule(loads)
    fans = [c for c in s["circuits"] if c["type"] == "Fans"]
    assert [c["points"] for c in fans] == [7, 1]
    assert all(c["timer_h"] == 10.0 for c in fans)  # fans = 10h


def test_lighting_timer_is_14h(app):
    loads = [{"name": "LED", "category": "Lighting", "wattage": 10, "quantity": 3}]
    s = app._circuit_schedule(loads)
    assert all(c["timer_h"] == 14.0 for c in s["circuits"])  # lights = 14h


# ── Engine: MCB sizing from summed load ──────────────────────────────────────
def test_breaker_sized_from_summed_current(app):
    # 7 x 300W = 2100W @230V = 9.13A -> next standard MCB = 10A
    loads = [{"name": "Floodlight", "category": "Lighting", "wattage": 300, "quantity": 7}]
    s = app._circuit_schedule(loads)
    c = s["circuits"][0]
    assert c["total_w"] == 2100.0
    assert 9.0 < c["current_a"] < 9.5
    assert c["breaker_a"] == 10


def test_small_load_gets_smallest_mcb(app):
    loads = [{"name": "LED", "category": "Lighting", "wattage": 9, "quantity": 5}]
    s = app._circuit_schedule(loads)
    assert s["circuits"][0]["breaker_a"] == 6  # smallest standard MCB


def test_overload_flagged_when_exceeds_max_mcb(app):
    # 7 x 3000W = 21000W @230V = 91A > 63A max MCB -> overloaded
    loads = [{"name": "Big AC", "category": "Cooling", "wattage": 3000, "quantity": 7}]
    s = app._circuit_schedule(loads)
    c = s["circuits"][0]
    assert c["overloaded"] is True
    assert c["breaker_a"] == 63
    assert s["summary"]["overloaded"] is True


# ── Engine: scope ────────────────────────────────────────────────────────────
def test_other_categories_excluded(app):
    loads = [
        {"name": "Fridge", "category": "Appliances", "wattage": 150, "quantity": 2},
        {"name": "Pump", "category": "Pumps", "wattage": 750, "quantity": 1},
        {"name": "LED", "category": "Lighting", "wattage": 10, "quantity": 2},
    ]
    s = app._circuit_schedule(loads)
    # only the lighting load produces a circuit
    assert s["summary"]["circuit_count"] == 1
    assert s["circuits"][0]["type"] == "Lighting"


def test_empty_loads_no_circuits(app):
    s = app._circuit_schedule([])
    assert s["summary"]["circuit_count"] == 0
    assert s["circuits"] == []


def test_malformed_rows_do_not_raise(app):
    loads = [
        {"category": "Lighting"},                                   # no wattage/qty/name
        {"name": "x", "category": "Lighting", "wattage": "bad", "quantity": "bad"},
    ]
    s = app._circuit_schedule(loads)  # must not raise
    assert s["summary"]["circuit_count"] >= 1


def test_breaker_bom_counts(app):
    loads = [{"name": "LED", "category": "Lighting", "wattage": 10, "quantity": 14}]
    s = app._circuit_schedule(loads)  # 2 circuits, both 6A
    bom = {b["rating"]: b["count"] for b in s["summary"]["breaker_bom"]}
    assert bom == {6: 2}


# ── Engine: robustness / DoS bound ───────────────────────────────────────────
def test_huge_quantity_is_bounded_and_fast(app):
    # A malformed/malicious quantity must not explode memory/CPU: circuits are
    # built arithmetically and the group is capped. Must complete quickly.
    t0 = time.time()
    s = app._circuit_schedule(
        [{"name": "LED", "category": "Lighting", "wattage": 10, "quantity": 10_000_000}])
    assert time.time() - t0 < 2.0
    assert s["summary"]["truncated"] is True
    assert s["summary"]["total_points"] <= app._MAX_POINTS_PER_GROUP
    # circuit count is bounded to ~cap/7, not millions
    assert s["summary"]["circuit_count"] <= app._MAX_POINTS_PER_GROUP


# ── Route: RBAC + paid gate ──────────────────────────────────────────────────
def _mk_user(app, plan="business"):
    uname = _u("u")
    with app.app.app_context():
        from web_app import get_db, generate_password_hash, _gen_referral_code
        with get_db() as c:
            c.execute(
                "INSERT INTO users (username,email,password_hash,name,plan,is_admin,referral_code) "
                "VALUES (?,?,?,?,?,?,?)",
                (uname, uname + "@t.test", generate_password_hash("pw"),
                 "T", plan, 0, _gen_referral_code()))
            return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_route_requires_login(app, client):
    r = client.get("/project/1/report/circuits")
    assert r.status_code in (301, 302)  # -> login
