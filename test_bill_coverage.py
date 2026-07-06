"""Tests for the Energy Coverage Analysis (Solar Designer <-> Check My Bill).
Covers the independent PURC bill->kWh inversion, undiversified designer energy,
coverage math, status thresholds, savings-from-actual-bill, and recompute."""
import os

os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")

import web_app as wa

RES = "Residential Standard (0-300 kWh/month)"
LIFELINE = "Residential Lifeline (≤ 30 kWh/month)"


# ── PURC Q3 2026 schedule is loaded ──────────────────────────────────────────
def test_purc_schedule_is_q3_2026():
    assert wa.GHANA_PURC_TARIFF_META["quarter"] == "Q3 2026"
    assert wa.GHANA_PURC_TARIFF_META["effective_from"] == "2026-07-01"
    assert abs(wa.GHANA_PURC_TARIFFS[LIFELINE]["rate_ghc"] - 0.8993) < 1e-6


# ── Independent bill -> kWh inversion (does NOT trust Check My Bill) ──────────
def test_bill_to_kwh_first_band():
    std = wa.GHANA_PURC_TARIFFS[RES]
    bill = std["fixed_ghc"] + 100.0 * std["rate_ghc"]      # exactly 100 kWh
    assert abs(wa._bc_bill_to_kwh(bill, RES) - 100.0) < 1e-6


def test_bill_to_kwh_crosses_into_high_band():
    std = wa.GHANA_PURC_TARIFFS[RES]
    hi = wa.GHANA_PURC_TARIFFS["Residential High Use (>300 kWh/month)"]
    bill = std["fixed_ghc"] + 300.0 * std["rate_ghc"] + 100.0 * hi["rate_ghc"]  # 400 kWh
    assert abs(wa._bc_bill_to_kwh(bill, RES) - 400.0) < 1e-6


def test_lifeline_stays_flat_when_under_30kwh():
    life = wa.GHANA_PURC_TARIFFS[LIFELINE]
    bill = life["fixed_ghc"] + 20.0 * life["rate_ghc"]      # 20 kWh, within lifeline
    assert abs(wa._bc_bill_to_kwh(bill, LIFELINE) - 20.0) < 1e-6


def test_lifeline_switches_to_standard_bands_above_30kwh():
    life = wa.GHANA_PURC_TARIFFS[LIFELINE]
    bill = life["fixed_ghc"] + 50.0 * life["rate_ghc"]      # flat lifeline would give 50 kWh
    got = wa._bc_bill_to_kwh(bill, LIFELINE)
    assert got != 50.0
    assert got == wa._bc_bill_to_kwh(bill, RES)             # re-inverted on standard bands
    assert got < 30.0


def test_bill_to_kwh_zero_and_below_service():
    assert wa._bc_bill_to_kwh(0, RES) == 0.0
    assert wa._bc_bill_to_kwh(-50, RES) == 0.0
    assert wa._bc_bill_to_kwh(1.0, RES) == 0.0             # below the service charge


# ── Designer side uses UNDIVERSIFIED entered-load energy (Finding 1 fix) ──────
def test_designer_monthly_ignores_demand_factor():
    data = {"loads": [{"wattage": 1000, "quantity": 1, "hours": 5, "demand_factor": 0.5,
                       "category": "Other"}]}
    # raw = 1000*1*5/1000 = 5 kWh/day * 30.44 = 152.2 (demand factor 0.5 must NOT apply)
    assert abs(wa._bc_designer_monthly_kwh(data) - 152.2) < 0.05


def test_designer_monthly_falls_back_to_results_when_no_loads():
    assert abs(wa._bc_designer_monthly_kwh({"results": {"daily_kwh": 10.0}}) - 304.4) < 0.05


# ── Coverage math + status thresholds (bill side pinned to 1000 kWh) ──────────
def _cov(designer_monthly, bill_kwh=1000.0, bill=0.0):
    return wa._bc_coverage(designer_monthly, bill, RES, bill_monthly_kwh=bill_kwh)


def test_coverage_percentage_and_remaining():
    c = _cov(625.0, bill_kwh=1000.0)
    assert c["available"] is True
    assert abs(c["coverage_pct"] - 62.5) < 0.05
    assert abs(c["remaining_kwh"] - 375.0) < 0.5
    assert c["excess_kwh"] == 0.0


def test_status_thresholds():
    assert _cov(700.0)["coverage_status"] == "Partial Load Design"
    assert _cov(850.0)["coverage_status"] == "Near Full Load Design"
    assert _cov(1000.0)["coverage_status"] == "Full Load Design"
    assert _cov(1100.0)["coverage_status"] == "Oversized or Future Load Design"


def test_savings_from_actual_bill():
    c = _cov(625.0, bill_kwh=1000.0, bill=4000.0)          # coverage 62.5%
    assert abs(c["estimated_monthly_savings"] - 2500.0) < 0.5
    assert c["loan_repayment_capacity"] == c["estimated_monthly_savings"]


def test_oversized_savings_capped_at_100pct():
    c = _cov(1500.0, bill_kwh=1000.0, bill=1000.0)         # coverage 150%
    assert abs(c["estimated_monthly_savings"] - 1000.0) < 0.5


# ── Guard rails ──────────────────────────────────────────────────────────────
def test_missing_design_returns_warning():
    c = wa._bc_coverage(0.0, 500.0, RES)
    assert c["available"] is False and "design result is required" in c["warning"]


def test_zero_bill_no_override_warns():
    c = wa._bc_coverage(608.8, 0.0, RES)                   # no bill, no override
    assert c["available"] is False and "could not be calculated" in c["warning"]


# ── Recompute wiring ─────────────────────────────────────────────────────────
def test_refresh_uses_independent_inversion_not_bill_check_value():
    std = wa.GHANA_PURC_TARIFFS[RES]
    data = {
        "loads": [{"wattage": 1000, "quantity": 1, "hours": 10}],   # raw 10 kWh/day
        "results": {"daily_kwh": 7.0},
        "bill_check": {
            "actual_bill": std["fixed_ghc"] + 300.0 * std["rate_ghc"],   # ~300 kWh
            "energy": {"monthly_kwh": 99999.0, "source": "derived_from_bill"},  # must be ignored
            "inputs": {"category": RES},
        },
    }
    wa._bc_refresh_coverage(data)
    cov = data["coverage"]
    assert cov["available"] is True
    assert abs(cov["bill_monthly_kwh"] - 300.0) < 1.0          # from inversion, NOT 99999
    assert abs(cov["designer_monthly_kwh"] - 10.0 * 30.44) < 0.1  # raw loads, not 7*30.44
    assert cov["estimate_basis"] == "purc_bill_inversion"


def test_refresh_trusts_genuine_meter_reading():
    data = {
        "loads": [{"wattage": 1000, "quantity": 1, "hours": 10}],
        "results": {"daily_kwh": 10.0},
        "bill_check": {
            "actual_bill": 0.0,
            "energy": {"monthly_kwh": 500.0, "source": "user_provided_kwh"},
            "inputs": {"category": RES},
        },
    }
    wa._bc_refresh_coverage(data)
    assert data["coverage"]["bill_monthly_kwh"] == 500.0
    assert data["coverage"]["estimate_basis"] == "meter_reading"


def test_refresh_noop_without_both_inputs():
    d1 = {"results": {"daily_kwh": 10.0}}
    wa._bc_refresh_coverage(d1)
    assert "coverage" not in d1


# ── Report section renders / self-computes ───────────────────────────────────
def test_coverage_md_self_computes_when_not_persisted():
    std = wa.GHANA_PURC_TARIFFS[RES]
    d = {
        "loads": [{"wattage": 1000, "quantity": 1, "hours": 10}],
        "results": {"daily_kwh": 10.0},
        "bill_check": {
            "actual_bill": std["fixed_ghc"] + 300.0 * std["rate_ghc"],
            "energy": {"monthly_kwh": 0.0, "source": "derived_from_bill"},
            "inputs": {"category": RES},
        },
    }
    md = wa._coverage_md(d)
    assert "Energy Coverage and Bill Comparison Analysis" in md
    assert md.startswith("## ")                             # H2, not H1


def test_coverage_md_empty_without_data():
    assert wa._coverage_md({}) == ""
    assert wa._coverage_md({"results": {"daily_kwh": 5}}) == ""   # no bill_check
