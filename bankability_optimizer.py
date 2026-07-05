"""
Auto-adjust a standard PV project's FINANCIAL parameters to make it bankable /
approved (owner 2026-07-05: an "Update Project" action on the recommendations page
that automatically tunes the project so a not-bankable / conditional / rejected
project reaches APPROVED + BANKABLE where feasible).

Design principles (safety first -- this mutates a user's project):
  * Only FINANCIAL / procurement levers move: equipment cost per kWp, install
    rate %, supply markup %, and funding mode (loan vs self). The ENGINEERING
    sizing (kWp, panels, battery, inverter) is never touched -- the system that
    was designed still gets built; only its costing/financing is optimised, which
    mirrors the report's own recommendations ("obtain competitive quotes",
    "reduce system cost").
  * Levers move only DOWNWARD toward realistic market floors; the search never
    invents cheaper-than-possible equipment.
  * The recompute reuses the SAME calc_boq + calc_economics engine (injected, to
    avoid a circular import), so the optimised numbers are consistent with a
    normal project recompute -- no parallel model.
  * Returns the proposed new data + a human-readable change list + before/after
    economics. The caller decides whether to persist (and keeps a backup).

optimize_bankability(data, calc_boq, calc_economics) ->
    (new_data | None, changes: list[str], achieved: bool, before_eco, after_eco)
`new_data` is None when nothing could improve on the current verdict.
"""
from __future__ import annotations
import math

__all__ = ["optimize_bankability"]

# Verdict / bankability ordinal ranks (higher = better) for the search score.
_VERDICT_RANK = {"APPROVED": 3, "CONDITIONAL": 2, "REJECTED": 1}
_BANK_RANK = {"BANKABLE": 3, "MARGINAL": 2, "NOT BANKABLE": 1}
_COST_FLOOR = 400.0        # USD/kWp -- sane lower bound for competitive quotes
_INSTALL_FLOOR = 10.0      # % of equipment
_MARKUP_FLOOR = 5.0        # % supply markup


def _score(eco):
    return (_VERDICT_RANK.get(eco.get("verdict"), 0),
            _BANK_RANK.get(eco.get("bankability"), 0),
            float(eco.get("npv") or 0.0))


def _is_bankable(eco):
    return eco.get("verdict") == "APPROVED" and eco.get("bankability") == "BANKABLE"


def optimize_bankability(data, calc_boq, calc_economics):
    results = (data or {}).get("results") or {}
    eco0 = results.get("economics") or {}
    if not results or not eco0:
        return None, [], False, eco0, eco0
    # Already bankable -> nothing to do.
    if _is_bankable(eco0):
        return None, [], True, eco0, eco0

    # --- current financial levers ---
    cost0 = float(data.get("cost_usd_kwp", 900) or 900)
    install0 = float(data.get("install_rate_pct", 15) or 15)
    markup0 = float(data.get("supply_markup_pct", 8) or 8)
    fmode0 = data.get("funding_mode", "loan") or "loan"

    # --- fixed engineering outputs (NOT resized) ---
    try:
        num_panels = results["num_panels"]
        num_bat = results["num_bat"]
        inv_kw = results["inv_kw"]
        pv_kw = results["pv_kw"]
        bat_kwh = results["bat_kwh"]
        daily_kwh = results["daily_kwh"]
    except KeyError:
        return None, [], False, eco0, eco0
    unit_bat = results.get("unit_bat_kwh")
    chemistry = results.get("chemistry", "LiFePO4")
    mppt_a = results.get("mppt_a")
    panel_wp = results.get("panel_wp", 400)
    ac_cables = results.get("ac_cables")
    voltage = data.get("voltage", 48)
    pps = 2 if voltage <= 24 else 4 if voltage <= 48 else 8
    num_strings = math.ceil(num_panels / pps) if num_panels else 1
    tariff = data.get("tariff", 2.0)
    currency = data.get("currency", "USD")
    symbol = data.get("symbol", "$")
    fx = data.get("fx_usd", 1.0)
    autonomy = data.get("autonomy", 1)

    def run(cost, install, markup, fmode):
        rows, grand = calc_boq(
            num_panels, num_bat, inv_kw, pv_kw, bat_kwh, unit_bat, chemistry,
            mppt_a, cost, fx, panel_wp, ac_cables=ac_cables, voltage=voltage,
            num_strings=num_strings, supply_markup_pct=markup,
            install_rate_pct=install)
        eco = calc_economics(
            pv_kw, num_panels, bat_kwh, num_bat, inv_kw, daily_kwh, tariff,
            currency, symbol, cost, fx, autonomy, boq_total_local=grand,
            chemistry=chemistry, funding_mode=fmode, install_rate_pct=install)
        return rows, grand, eco

    # Bounded, monotone-downward search grid (procurement + financing structure).
    def _steps(v0, floor):
        vals = {round(v0, 2), round(max(floor, v0 * 0.9), 2),
                round(max(floor, v0 * 0.8), 2), round(max(floor, v0 * 0.75), 2),
                round(floor, 2)}
        return sorted(vals, reverse=True)   # try gentlest change first

    cost_opts = _steps(cost0, _COST_FLOOR)
    install_opts = sorted({install0, max(_INSTALL_FLOOR, install0 - 3.0),
                           _INSTALL_FLOOR}, reverse=True)
    markup_opts = sorted({markup0, max(_MARKUP_FLOOR, markup0 - 3.0),
                          _MARKUP_FLOOR}, reverse=True)
    fmode_opts = [fmode0] + (["self"] if fmode0 != "self" else ["loan"])

    base_score = _score(eco0)
    best = None
    for cost in cost_opts:
        for inst in install_opts:
            for mk in markup_opts:
                for fm in fmode_opts:
                    try:
                        rows, grand, eco = run(cost, inst, mk, fm)
                    except Exception:
                        continue
                    cand = {"cost": cost, "install": inst, "markup": mk,
                            "fmode": fm, "rows": rows, "grand": grand,
                            "eco": eco, "score": _score(eco)}
                    if best is None or cand["score"] > best["score"]:
                        best = cand
                    if _is_bankable(eco):
                        best = cand
                        break
                if best and _is_bankable(best["eco"]):
                    break
            if best and _is_bankable(best["eco"]):
                break
        if best and _is_bankable(best["eco"]):
            break

    if best is None or best["score"] <= base_score:
        return None, [], _is_bankable(eco0), eco0, eco0

    changes = []
    if best["cost"] != cost0:
        changes.append("Equipment cost per kWp reduced from %s to %s USD (competitive procurement)"
                       % (int(cost0), int(best["cost"])))
    if best["install"] != install0:
        changes.append("Installation rate reduced from %.0f%% to %.0f%%"
                       % (install0, best["install"]))
    if best["markup"] != markup0:
        changes.append("Supply markup reduced from %.0f%% to %.0f%%"
                       % (markup0, best["markup"]))
    if best["fmode"] != fmode0:
        changes.append("Funding structure changed from %s to %s"
                       % (fmode0.title(), best["fmode"].title()))
    if not changes:
        return None, [], _is_bankable(eco0), eco0, eco0

    new_data = dict(data)
    new_data["cost_usd_kwp"] = best["cost"]
    new_data["install_rate_pct"] = best["install"]
    new_data["supply_markup_pct"] = best["markup"]
    new_data["funding_mode"] = best["fmode"]
    new_results = dict(results)
    new_results["economics"] = best["eco"]
    new_results["boq_rows"] = best["rows"]
    new_results["boq_grand"] = best["grand"]
    new_data["results"] = new_results
    return new_data, changes, _is_bankable(best["eco"]), eco0, best["eco"]
