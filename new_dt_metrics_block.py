# Standard PV loss-category shares (fractions of TOTAL system loss). The Digital
# Twin "System Losses" donut presents the project's single Step-7 performance
# ratio as the familiar PVsyst-style stack: the TOTAL (1 - PR) is the real,
# project-specific figure; this split follows conventional utility-scale
# proportions and is labelled "modelled split" in the UI so it is not mistaken
# for a per-category simulation.
_CI_LOSS_SHARES = [
    ("Irradiance / soiling", 0.185, "#22c55e"),
    ("Temperature",          0.360, "#f59e0b"),
    ("Shading",              0.200, "#a855f7"),
    ("Wiring / DC",          0.100, "#3b82f6"),
    ("Inverter",             0.070, "#ef4444"),
    ("Mismatch / other",     0.085, "#94a3b8"),
]


def _ci_dt_metrics(proj) -> dict:
    """Read-only dashboard metrics for the 3D Digital Twin.

    Pulls finance headline figures from the Step-8 finance engine
    (finance_config.computed), the energy-yield profile from _ci_yield_profile
    over the Step-7 sizing, and a standard system-loss stack derived from the
    project performance ratio. Never raises: every field degrades to a safe
    default so the twin still renders on a half-built project.
    """
    def _fl(v, d=0.0):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    pv = _safe_json(proj.get("pv_config"))
    fin = _safe_json(proj.get("finance_config"))
    site = _safe_json(proj.get("site_config"))
    sizing = pv.get("sizing") if isinstance(pv.get("sizing"), dict) else {}
    computed = fin.get("computed") if isinstance(fin.get("computed"), dict) else {}
    cur = proj.get("currency") or "GHS"

    lat = site.get("gps_lat", site.get("latitude"))
    energy = _ci_yield_profile(pv, gps_lat=lat, years=25) or {}

    annual_mwh = _fl(energy.get("annual_gen_mwh")) or _fl(sizing.get("annual_gen_mwh"))
    pr = _fl(sizing.get("performance_ratio"), 0.0)
    total_loss = round((1.0 - pr) * 100.0, 1) if 0.0 < pr <= 1.0 else 0.0
    losses = {"available": total_loss > 0.0, "total_pct": total_loss,
              "pr_pct": round(pr * 100.0, 1) if pr else 0.0, "items": []}
    if total_loss > 0.0:
        losses["items"] = [
            {"label": lbl, "pct": round(total_loss * share, 1), "color": col}
            for (lbl, share, col) in _CI_LOSS_SHARES]

    finance = {
        "available": bool(computed),
        "currency": cur,
        "capex": computed.get("total_capex_local"),
        "lcoe": computed.get("lcoe_local_per_kwh"),
        "irr_pct": computed.get("irr_pct"),
        "npv": computed.get("npv_local"),
        "payback_years": computed.get("payback_years"),
        "tariff": computed.get("tariff_local_per_kwh"),
        "annual_energy_mwh": round(annual_mwh, 0) if annual_mwh else None,
    }
    return {"finance": finance, "energy": energy, "losses": losses}


