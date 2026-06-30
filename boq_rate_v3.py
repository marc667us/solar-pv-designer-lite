# boq_rate_v3.py
# Shared BOQ rate engine (2026-06-30 owner spec).
#
# IMPORTANT — the meaning of `supply` and `install` are PERCENTAGES.
#
# Formula (revised 2026-06-30 — Overhead + Profit RIDE ON SUPPLY):
#     effective_vat   = 0 if vat_in_basic else vat
#     supply_amount   = basic * (supply  + overhead + profit + effective_vat) / 100   (markup)
#     install_amount  = basic * install / 100                                          (markup)
#     total_rate      = basic + supply_amount + install_amount                          (per unit)
#     line_total      = total_rate * qty
#
# Why OH + Profit shifted from install to supply (2026-06-30):
#   Supply Amount Rate is the SOLD-side markup the contractor charges. It
#   carries margin (overhead + profit) + freight/handling (VAT). Install
#   Amount Rate is the pure labour line — no margin, no overhead. This
#   matches how Ghana contractors actually price BOQs.
#
# Column meanings:
#   Basic Price                = supplier's per-unit cost
#   Supply Amount Rate         = markup covering freight/VAT + overhead + profit
#   Installation Amount Rate   = pure labour markup
#   Total Amount Rate          = Basic + Supply Amount + Installation Amount   (per unit)
#   Amount                     = qty * Total Amount Rate


def boq_rate_v3(basic_price, supply_pct=0, install_pct=0,
                overhead_pct=0, profit_pct=0, vat_pct=0,
                vat_in_basic=False):
    """Return (supply_amount, install_amount, total_rate) for one BOQ line.
    supply_amount + install_amount are MARKUP amounts (don't include basic).
    total_rate INCLUDES basic so the line total reads `qty * total_rate`.

    2026-06-30: overhead + profit now ride on Supply (was Install). Install
    Amount Rate is the pure labour markup."""
    b = max(0.0, float(basic_price or 0))
    sp = max(0.0, float(supply_pct  or 0))
    ip = max(0.0, float(install_pct or 0))
    op = max(0.0, float(overhead_pct or 0))
    pp = max(0.0, float(profit_pct  or 0))
    vp = max(0.0, float(vat_pct or 0))
    eff_vat = 0.0 if vat_in_basic else vp
    supply_amount  = b * (sp + op + pp + eff_vat) / 100.0
    install_amount = b * ip / 100.0
    total_rate = b + supply_amount + install_amount
    return supply_amount, install_amount, total_rate


def boq_rate_v3_dict(basic_price, supply_pct=0, install_pct=0,
                     overhead_pct=0, profit_pct=0, vat_pct=0,
                     vat_in_basic=False):
    """Dict variant for templates / API responses."""
    sa, ia, tr = boq_rate_v3(basic_price, supply_pct, install_pct,
                             overhead_pct, profit_pct, vat_pct, vat_in_basic)
    return {
        "basic_price":    float(basic_price or 0),
        "supply_pct":     float(supply_pct or 0),
        "install_pct":    float(install_pct or 0),
        "overhead_pct":   float(overhead_pct or 0),
        "profit_pct":     float(profit_pct or 0),
        "vat_pct":        float(vat_pct or 0),
        "vat_in_basic":   1 if vat_in_basic else 0,
        "supply_amount":  sa,
        "install_amount": ia,
        "total_rate":     tr,
    }


def coerce_pct_bool(value):
    """Form-helper: accept truthy strings (1/on/true/yes) as True."""
    if value is None:
        return False
    s = str(value).strip().lower()
    return s in ("1", "on", "true", "yes", "y", "checked")
