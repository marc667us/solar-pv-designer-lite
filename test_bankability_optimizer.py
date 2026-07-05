"""
Tests for the bankability auto-optimizer (optimize_bankability). Uses mock
calc_boq / calc_economics so the SEARCH + APPLY semantics are locked down
independently of the real engine: a rejected loan project that becomes bankable,
an infeasible project, the self-funded outcome, already-bankable no-op, and the
guarantee that the engineering sizing is never mutated.

Run:  python -m pytest test_bankability_optimizer.py -q
"""
from bankability_optimizer import optimize_bankability


def _mock_boq(num_panels, num_bat, inv_kw, pv_kw, bat_kwh, unit_bat, chemistry,
              mppt_a, cost, fx, panel_wp, ac_cables=None, voltage=48,
              num_strings=1, supply_markup_pct=8, install_rate_pct=15):
    grand = cost * pv_kw * (1 + install_rate_pct / 100.0) * (1 + supply_markup_pct / 100.0)
    return [{"item": "sys", "cost": grand}], grand


def _mock_eco_cost_driven(pv_kw, num_panels, bat_kwh, num_bat, inv_kw, daily_kwh,
                          tariff, currency, symbol, cost, fx, autonomy,
                          boq_total_local=None, chemistry="LiFePO4",
                          funding_mode="loan", install_rate_pct=15):
    """Cheaper total -> better verdict. Loan stays 'BANKABLE'/'MARGINAL'/'NOT
    BANKABLE'; self funding reports 'SELF-FUNDED'."""
    t = boq_total_local
    if t <= 5200:
        v = "APPROVED"
    elif t <= 6200:
        v = "CONDITIONAL"
    else:
        v = "REJECTED"
    if funding_mode == "self":
        b = "SELF-FUNDED"
    else:
        b = {"APPROVED": "BANKABLE", "CONDITIONAL": "MARGINAL",
             "REJECTED": "NOT BANKABLE"}[v]
    return {"verdict": v, "bankability": b, "npv": 100000 - t,
            "total_local": t, "equip_local": t * 0.7, "install_local": t * 0.15}


def _base_data(**over):
    d = {
        "cost_usd_kwp": 900, "install_rate_pct": 15, "supply_markup_pct": 8,
        "funding_mode": "loan", "voltage": 48, "tariff": 2.0, "currency": "GHS",
        "symbol": "GHS ", "fx_usd": 12.0, "autonomy": 1,
        "results": {
            "num_panels": 20, "num_bat": 4, "inv_kw": 5, "pv_kw": 8,
            "bat_kwh": 10, "daily_kwh": 30, "unit_bat_kwh": 2.5,
            "chemistry": "LiFePO4", "mppt_a": 40, "panel_wp": 400,
            "ac_cables": {},
            "economics": {"verdict": "REJECTED", "bankability": "NOT BANKABLE",
                          "npv": -9000, "total_local": 6480},
        },
    }
    d.update(over)
    return d


def test_rejected_loan_becomes_bankable():
    d = _base_data()
    new_data, changes, achieved, before, after = optimize_bankability(
        d, _mock_boq, _mock_eco_cost_driven)
    assert achieved is True
    assert before["verdict"] == "REJECTED" and after["verdict"] == "APPROVED"
    assert after["bankability"] in ("BANKABLE", "SELF-FUNDED")
    assert changes                        # at least one lever moved
    # Engineering sizing untouched.
    assert new_data["results"]["pv_kw"] == 8
    assert new_data["results"]["num_panels"] == 20
    # Reduced-cost figures actually applied.
    assert new_data["cost_usd_kwp"] <= d["cost_usd_kwp"]
    assert new_data["results"]["economics"]["verdict"] == "APPROVED"


def test_already_bankable_is_noop():
    d = _base_data()
    d["results"]["economics"] = {"verdict": "APPROVED", "bankability": "BANKABLE",
                                 "npv": 5000}
    new_data, changes, achieved, _, _ = optimize_bankability(
        d, _mock_boq, _mock_eco_cost_driven)
    assert new_data is None and changes == [] and achieved is True


def test_self_funded_counts_as_achieved():
    """A project that can only reach APPROVED by switching to self funding must be
    reported as achieved (SELF-FUNDED is a solved outcome, not a failure)."""
    def eco(pv_kw, num_panels, bat_kwh, num_bat, inv_kw, daily_kwh, tariff,
            currency, symbol, cost, fx, autonomy, boq_total_local=None,
            chemistry="LiFePO4", funding_mode="loan", install_rate_pct=15):
        # Loan can never be approved here; self funding is always approved.
        if funding_mode == "self":
            return {"verdict": "APPROVED", "bankability": "SELF-FUNDED",
                    "npv": 20000, "total_local": boq_total_local}
        return {"verdict": "CONDITIONAL", "bankability": "MARGINAL",
                "npv": -1000, "total_local": boq_total_local}
    d = _base_data()
    d["results"]["economics"] = {"verdict": "CONDITIONAL",
                                 "bankability": "MARGINAL", "npv": -1000}
    new_data, changes, achieved, before, after = optimize_bankability(
        d, _mock_boq, eco)
    assert achieved is True
    assert after["bankability"] == "SELF-FUNDED"
    assert new_data["funding_mode"] == "self"
    assert any("Funding" in c for c in changes)


def test_infeasible_returns_none():
    """When nothing improves on the current verdict, no mutation is proposed."""
    def eco(*a, **k):
        return {"verdict": "REJECTED", "bankability": "NOT BANKABLE",
                "npv": -50000, "total_local": 99999}
    d = _base_data()
    new_data, changes, achieved, before, after = optimize_bankability(
        d, _mock_boq, eco)
    assert new_data is None and changes == [] and achieved is False
    assert before is after                # unchanged economics returned


def test_missing_results_is_safe():
    assert optimize_bankability({}, _mock_boq, _mock_eco_cost_driven)[0] is None
    assert optimize_bankability({"results": {}}, _mock_boq,
                                _mock_eco_cost_driven)[0] is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("all optimizer tests passed")
