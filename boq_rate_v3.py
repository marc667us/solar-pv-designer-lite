# boq_rate_v3.py
# Shared BOQ rate engine (2026-06-28 owner spec).
#
# IMPORTANT — the meaning of `supply` and `install` CHANGED from earlier
# versions: they are now PERCENTAGES (not currency amounts).
#
# Formula:
#     effective_vat   = 0 if vat_in_basic else vat
#     supply_amount   = basic * (1 + (supply + effective_vat) / 100)
#     install_amount  = basic * ((install + overhead + profit) / 100)
#     total_rate      = supply_amount + install_amount   (per unit)
#     line_total      = total_rate * qty
#
# Contingency is no longer applied. install_amount IS the labour portion,
# and overhead + profit are absorbed into install (they ride on the labour
# side of the build-up).


def boq_rate_v3(basic_price, supply_pct=0, install_pct=0,
                overhead_pct=0, profit_pct=0, vat_pct=0,
                vat_in_basic=False):
    """Return (supply_amount, install_amount, total_rate) for one BOQ line."""
    b = max(0.0, float(basic_price or 0))
    sp = max(0.0, float(supply_pct  or 0))
    ip = max(0.0, float(install_pct or 0))
    op = max(0.0, float(overhead_pct or 0))
    pp = max(0.0, float(profit_pct  or 0))
    vp = max(0.0, float(vat_pct or 0))
    eff_vat = 0.0 if vat_in_basic else vp
    supply_amount  = b * (1.0 + (sp + eff_vat) / 100.0)
    install_amount = b * ((ip + op + pp) / 100.0)
    total_rate = supply_amount + install_amount
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
