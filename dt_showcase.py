"""Customer-facing PHOTOREAL SHOWCASE model for the SolarPro Generation Station.

Purpose: a "wow the customer" presentation surface. Instead of browser-primitive
3D (which never matches a photograph), the showcase presents self-hosted
photoreal scene imagery of a utility solar farm with LIVE project data overlaid
as callout chips + a KPI bar. It is a sales/demo asset, not an engineering tool.

Reusability rule 0.3: this is a PURE, importable model. It CONSUMES the project's
committed PV sizing (via dt_electrical_sld.build_sld_model) and Step-8 finance
(via _ci_dt_metrics) -- no new sizing/finance engine. Never raises: every field
degrades to a safe default so a half-built project still renders.

Scene assets are self-hosted under static/capital_investment/hero/ (CSP-safe,
zero external hosts). Callout positions are percentages of the hero image so they
scale responsively.
"""
from __future__ import annotations

from typing import Any

from dt_electrical_sld import build_sld_model, _f, _load

__all__ = ["build_showcase_model"]

# The five real photographic scenes (derived from the reference aerial). Each maps
# to a self-hosted image + thumbnail under static/capital_investment/hero/.
_SCENES: list[dict[str, str]] = [
    {"key": "aerial",     "label": "Aerial View",
     "img": "farm-aerial.jpg",     "thumb": "farm-aerial-thumb.jpg",
     "caption": "Full-plant aerial — arrays, inverter stations & substation"},
    {"key": "panels",     "label": "Array / Ground View",
     "img": "scene-panels.jpg",    "thumb": "scene-panels-thumb.jpg",
     "caption": "Fixed-tilt module tables on driven-pile mounting"},
    {"key": "inverter",   "label": "Inverter Station",
     "img": "scene-inverter.jpg",  "thumb": "scene-inverter-thumb.jpg",
     "caption": "Central-inverter skid + LV/MV step-up transformer"},
    {"key": "substation", "label": "Substation",
     "img": "scene-substation.jpg","thumb": "scene-substation-thumb.jpg",
     "caption": "MV collection & main export substation compound"},
    {"key": "night",      "label": "Night View",
     "img": "scene-night.jpg",     "thumb": "scene-night-thumb.jpg",
     "caption": "Round-the-clock plant — lit substation & access roads"},
]


def _fmt_int(v: float) -> str:
    try:
        return f"{int(round(v)):,}"
    except (TypeError, ValueError):
        return "0"


def build_showcase_model(proj: dict[str, Any]) -> dict[str, Any]:
    """Build the photoreal-showcase context for a Generation-Station project.

    Input: a project row/dict. Output: {project, scenes, hero, callouts, kpis,
    finance} render-ready dict. Reuses build_sld_model sizing + _ci_dt_metrics
    finance; never raises.
    """
    proj = proj if isinstance(proj, dict) else {}
    # build_sld_model is itself never-raises, but guard defensively so this
    # model honours its own never-raises contract even if that changes.
    try:
        sld = build_sld_model(proj) or {}           # reuse: sizing-derived figures
    except Exception:
        sld = {}
    pj = sld.get("project") or {}
    volts = sld.get("voltages") or {}
    dc_kwp = _f(pj.get("dc_kwp"))
    ac_mw = _f(pj.get("ac_mw"))
    n_mod = int(_f(pj.get("n_modules")))

    sz = _load(proj.get("pv_config")).get("sizing")
    sz = sz if isinstance(sz, dict) else {}
    n_inv = int(_f(sz.get("n_central_inverters")))
    combiners = int(_f(sz.get("combiners")))
    mps = int(_f(sz.get("modules_per_string") or 28)) or 28
    # Module "tables": 2-portrait (2P) racking, ~74 modules per table (2 rows x
    # ~37) is standard utility practice -- indicative count.
    per_table = 74
    n_tables = int(round(n_mod / per_table)) if n_mod else 0
    land_ha = round(dc_kwp * 0.0012, 1) if dc_kwp else 0.0   # ~1.2 ha/MWp

    # Finance / energy headline (reuse the Step-8 metrics helper; lazy import so
    # this model stays importable standalone). Degrades to None fields.
    finance: dict[str, Any] = {}
    annual_mwh = None
    try:
        from new_capital_investment_routes import _ci_dt_metrics
        m = _ci_dt_metrics(proj) or {}
        finance = m.get("finance") or {}
        annual_mwh = finance.get("annual_energy_mwh")
    except Exception:
        finance = {}

    # KPI strip (mirrors the reference PROJECT SUMMARY row).
    kpis = [
        {"label": "AC Capacity",  "value": f"{ac_mw:.0f}",       "unit": "MWac",  "icon": "bi-lightning-charge"},
        {"label": "DC Capacity",  "value": f"{dc_kwp/1000.0:.0f}","unit": "MWp",  "icon": "bi-sun"},
        {"label": "Modules",      "value": _fmt_int(n_mod),      "unit": "No.",   "icon": "bi-grid-3x3"},
        {"label": "Inverters",    "value": _fmt_int(n_inv),      "unit": "No.",   "icon": "bi-cpu"},
        {"label": "Module Tables","value": _fmt_int(n_tables),   "unit": "No.",   "icon": "bi-collection"},
        {"label": "Land Area",    "value": f"{land_ha:.0f}",     "unit": "ha",    "icon": "bi-map"},
    ]

    # Callout chips positioned over the hero aerial (percent coords tuned to the
    # farm-aerial.jpg composition: array field, inverter compound, substation).
    callouts = [
        {"key": "array", "title": "PV ARRAY", "x": 34, "y": 45,
         "lines": [f"Tables: {_fmt_int(n_tables)}", f"Modules: {_fmt_int(n_mod)}"]},
        {"key": "inverter", "title": "INVERTER STATION", "x": 82, "y": 44,
         "lines": [f"Inverters: {_fmt_int(n_inv)}", f"Capacity: {ac_mw:.0f} MWac"]},
        {"key": "substation", "title": "SUBSTATION", "x": 47, "y": 82,
         "lines": [f"Combiners: {_fmt_int(combiners)}",
                   f"Export: {ac_mw:.0f} MW @ {_f(volts.get('poi_kv') or 33):.0f} kV"]},
    ]

    return {
        "project": {"name": pj.get("name") or "Solar Generation Station",
                    "dc_kwp": dc_kwp, "ac_mw": ac_mw, "n_modules": n_mod},
        "scenes": _SCENES,
        "hero": _SCENES[0],
        "callouts": callouts,
        "kpis": kpis,
        "finance": {
            "currency": finance.get("currency") or "GHS",
            "capex": finance.get("capex"),
            "lcoe": finance.get("lcoe"),
            "irr_pct": finance.get("irr_pct"),
            "annual_energy_mwh": annual_mwh,
        },
    }
