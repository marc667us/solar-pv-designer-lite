
# ─── Energy Coverage Analysis (Solar Designer ↔ Check My Bill integration) ───
# Added 2026-07-06. Determines what % of a customer's estimated FULL monthly
# energy demand the solar design covers, so partial-load designs are flagged and
# the customer's own bill can be used to size funding capacity.
#
# Owner directives baked in:
#   1. PURC rates are the LIVE GHANA_PURC_TARIFFS (verified Q3 2026) — no assumptions.
#   2. The bill→kWh estimate is derived INDEPENDENTLY here by inverting the PURC
#      banded tariff on the customer's actual bill — it does NOT trust Check My
#      Bill's own flat-rate kWh (which can be circular when run from the load
#      schedule). Only a genuine user-entered meter reading is reused.
#
# Supervisor note (basis): calc_loads() returns DIVERSIFIED daily energy (each
# load × demand factor). A monthly bill reflects ACTUAL (undiversified) energy,
# so the designer side of the coverage ratio must also be undiversified energy —
# the raw sum of the entered loads (w·q·h), NOT results['daily_kwh']. Otherwise a
# fully-entered load schedule would read ~70% and be mislabelled "Partial".
#
# All functions are pure/module-level and unit-testable.

def _bc_bill_to_kwh(actual_bill, category="Residential Standard (0-300 kWh/month)"):
    """Invert the PURC banded tariff.

    Input : actual monthly bill in GHS (treated as PURC energy + service charge,
            the same simplification the Check My Bill estimator uses — levies not
            separated), and the customer tariff category.
    Output: estimated monthly consumption in kWh (float, >= 0).
    Uses the live GHANA_PURC_TARIFFS so it always tracks the current schedule.
    """
    bill = max(0.0, float(actual_bill or 0))
    if bill <= 0:
        return 0.0

    # Residential non-lifeline: first 300 kWh @ standard rate, remainder @ high rate.
    if "Residential" in category and "Non-" not in category and "Lifeline" not in category:
        std = GHANA_PURC_TARIFFS["Residential Standard (0-300 kWh/month)"]
        hi  = GHANA_PURC_TARIFFS["Residential High Use (>300 kWh/month)"]
        energy = bill - std["fixed_ghc"]
        if energy <= 0:
            return 0.0
        band1 = 300.0 * std["rate_ghc"]
        if energy <= band1:
            return energy / std["rate_ghc"]
        return 300.0 + (energy - band1) / hi["rate_ghc"]

    # Non-residential: same two-band shape.
    if category.startswith("Non-Residential"):
        std = GHANA_PURC_TARIFFS["Non-Residential Standard (0-300 kWh/month)"]
        hi  = GHANA_PURC_TARIFFS["Non-Residential High Use (>300 kWh/month)"]
        energy = bill - std["fixed_ghc"]
        if energy <= 0:
            return 0.0
        band1 = 300.0 * std["rate_ghc"]
        if energy <= band1:
            return energy / std["rate_ghc"]
        return 300.0 + (energy - band1) / hi["rate_ghc"]

    # Lifeline + all flat categories (SLT-LV/MV/HV, industrial, EV): single rate.
    info = GHANA_PURC_TARIFFS.get(category)
    if info:
        energy = bill - info["fixed_ghc"]
        if energy <= 0:
            return 0.0
        kwh = energy / info["rate_ghc"]
        # Lifeline is a customer CLASS capped at 30 kWh; above that the customer
        # is billed on the Residential Standard/High bands (mirrors the forward
        # logic in _bc_expected_purc_bill).
        if "Lifeline" in category and kwh > 30.0:
            return _bc_bill_to_kwh(bill, "Residential Standard (0-300 kWh/month)")
        return kwh

    # Unknown category → residential standard fallback.
    return _bc_bill_to_kwh(bill, "Residential Standard (0-300 kWh/month)")


def _bc_designer_monthly_kwh(data):
    """Undiversified monthly energy of the loads the customer ENTERED into the
    designer (raw w·q·h, no demand factor) — the correct apples-to-apples basis
    for comparison against a bill (see the basis note above). Falls back to the
    diversified results['daily_kwh'] only when the load list is unavailable."""
    loads = (data or {}).get("loads") or []
    raw_daily = 0.0
    for ld in loads:
        raw_daily += (float(ld.get("wattage", 0) or 0)
                      * float(ld.get("quantity", 1) or 0)
                      * float(ld.get("hours", 0) or 0)) / 1000.0
    if raw_daily > 0:
        return raw_daily * 30.44
    res = (data or {}).get("results") or {}
    return float(res.get("daily_kwh") or 0) * 30.44


def _bc_coverage(designer_monthly_kwh, actual_bill,
                 category="Residential Standard (0-300 kWh/month)",
                 bill_monthly_kwh=None):
    """Compare designer monthly energy with the bill-estimated FULL monthly
    consumption and return the Energy Coverage dict.

    designer_monthly_kwh : undiversified monthly energy of the entered design
                           (use _bc_designer_monthly_kwh()).
    actual_bill          : customer's actual monthly bill (GHS) from Check My Bill.
    category             : PURC tariff category.
    bill_monthly_kwh     : optional override — pass ONLY a genuine user-entered
                           meter reading; otherwise the bill is inverted via PURC.

    savings + loan capacity are derived from the customer's ACTUAL monthly bill
    (owner directive), not the designer-estimated or PURC-expected bill.
    """
    out = {"available": False, "warning": None}

    designer_monthly = float(designer_monthly_kwh or 0)
    if designer_monthly <= 0:
        out["warning"] = ("Solar design result is required before energy "
                          "coverage can be calculated.")
        return out

    bill = max(0.0, float(actual_bill or 0))

    if bill_monthly_kwh and float(bill_monthly_kwh) > 0:
        bill_monthly = float(bill_monthly_kwh)         # genuine meter reading
        basis = "meter_reading"
    else:
        bill_monthly = _bc_bill_to_kwh(bill, category)  # independent PURC inversion
        basis = "purc_bill_inversion"

    if bill_monthly <= 0:
        out["warning"] = ("Estimated utility energy could not be calculated. "
                          "Please check the bill amount and tariff category.")
        return out

    coverage_pct = designer_monthly / bill_monthly * 100.0
    remaining = max(bill_monthly - designer_monthly, 0.0)
    excess    = max(designer_monthly - bill_monthly, 0.0)

    if coverage_pct < 80:
        status = "Partial Load Design"
    elif coverage_pct < 95:
        status = "Near Full Load Design"
    elif coverage_pct <= 105:
        status = "Full Load Design"
    else:
        status = "Oversized or Future Load Design"

    # Savings/funding capacity keyed off the customer's ACTUAL monthly bill.
    savings = bill * min(coverage_pct, 100.0) / 100.0

    out.update({
        "available":                 True,
        "designer_monthly_kwh":      round(designer_monthly, 2),
        "bill_monthly_kwh":          round(bill_monthly, 2),
        "coverage_pct":              round(coverage_pct, 1),
        "remaining_kwh":             round(remaining, 2),
        "excess_kwh":                round(excess, 2),
        "coverage_status":           status,
        "actual_monthly_bill":       round(bill, 2),
        "estimated_monthly_savings": round(savings, 2),
        "loan_repayment_capacity":   round(savings, 2),
        "tariff_category":           category,
        "estimate_basis":            basis,
        "purc_quarter":              GHANA_PURC_TARIFF_META.get("quarter"),
        "bill_provided":             bill > 0,
    })
    return out


def _bc_refresh_coverage(data):
    """Recompute data['coverage'] from the current design + saved bill_check.
    No-op unless BOTH exist. Designer side is undiversified entered-load energy;
    bill side is derived independently from the actual bill + live PURC bands
    (except a genuine user-entered meter reading)."""
    bc  = data.get("bill_check")
    res = data.get("results")
    if not bc or not res:
        return
    energy = bc.get("energy") or {}
    override = energy.get("monthly_kwh") if energy.get("source") == "user_provided_kwh" else None
    category = (bc.get("inputs") or {}).get("category") or "Residential Standard (0-300 kWh/month)"
    data["coverage"] = _bc_coverage(_bc_designer_monthly_kwh(data), bc.get("actual_bill"),
                                    category, bill_monthly_kwh=override)

