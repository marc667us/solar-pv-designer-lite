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


def _si(v: Any) -> int:
    """Never-raising safe int: coerces via _f, rejects nan/inf, floors to 0.

    Guards the never-raises contract against a non-finite float sneaking out of
    _f() (e.g. a garbage pv_config value) -- int(float('nan')) would raise.
    """
    try:
        x = _f(v)
        if x != x or x in (float("inf"), float("-inf")):
            return 0
        return int(x)
    except (TypeError, ValueError):
        return 0


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
    pj = sld.get("project") if isinstance(sld.get("project"), dict) else {}
    volts = sld.get("voltages") if isinstance(sld.get("voltages"), dict) else {}
    dc_kwp = _f(pj.get("dc_kwp"))
    ac_mw = _f(pj.get("ac_mw"))
    n_mod = _si(pj.get("n_modules"))

    # _load never-raises but may return a non-dict; guard before .get so the
    # whole model honours its never-raises contract (High-sev review finding).
    _cfg = _load(proj.get("pv_config"))
    sz = _cfg.get("sizing") if isinstance(_cfg, dict) else None
    sz = sz if isinstance(sz, dict) else {}
    n_inv = _si(sz.get("n_central_inverters"))
    combiners = _si(sz.get("combiners"))
    mps = _si(sz.get("modules_per_string") or 28) or 28
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

    # Truthful design aerial (no-lies rule): the Showcase depicts THIS customer's
    # design + matches the 3D twin arrangement instead of a generic stock photo.
    # We only DETECT availability here (build the twin scene graph, cheap) and
    # reposition the callout chips onto the real equipment; the actual PNG is
    # served by the same-origin, browser-cacheable endpoint
    # capital_investment_showcase_aerial (so a 100+ KB image is not embedded as a
    # base64 data-URI in the HTML on every page view). Never raises: any failure
    # leaves aerial_scene None and the Showcase falls back to labelled stock art.
    aerial_scene = None
    try:
        from PIL import Image as _PILImage  # noqa: F401  (aerial needs Pillow)
        from new_capital_investment_routes import (build_scene_from_project,
                                                   _ci_normalize_proj_for_agents)
        from dt_scene_v2 import augment_scene_v2
        import dt_showcase_aerial as _aer
        _scene = augment_scene_v2(
            build_scene_from_project(_ci_normalize_proj_for_agents(proj)), proj)
        # HONESTY GATE (no-lies rule): only call it "your design" when the
        # project actually carries design data. An empty project still yields a
        # default placeholder plant from the scene generator -- presenting THAT
        # as the customer's design would be a lie, so require real sizing first.
        if (isinstance(_scene, dict) and _scene.get("objects")
                and (n_mod > 0 or dc_kwp > 0)):
            aerial_scene = {
                "key": "aerial", "label": "Your Design", "is_aerial": True,
                "caption": ("Generated aerial of YOUR design - same arrangement "
                            "as the interactive 3D twin (not a stock photo)."),
            }
            _anchors = _aer.aerial_callout_anchors(_scene, 1600, 900)
            for _c in callouts:
                _a = _anchors.get(_c["key"])
                if _a:
                    _c["x"], _c["y"] = _a["x"], _a["y"]
    except Exception:
        aerial_scene = None

    if aerial_scene:
        # design aerial is the hero + first gallery item; the stock photos become
        # clearly-labelled illustrative equipment references (not this plant).
        ref_scenes = [dict(s, caption="Illustrative reference - " + s["caption"])
                      for s in _SCENES if s["key"] != "aerial"]
        scenes = [aerial_scene] + ref_scenes
        hero = aerial_scene
    else:
        # No design data yet: the page is ENTIRELY stock art. Be honest about it
        # (no-lies rule) -- every scene, including the hero, is labelled as an
        # illustrative reference rather than presented as this customer's plant.
        scenes = [dict(s, caption="Illustrative reference - " + s["caption"])
                  for s in _SCENES]
        hero = scenes[0]

    return {
        "project": {"name": pj.get("name") or "Solar Generation Station",
                    "dc_kwp": dc_kwp, "ac_mw": ac_mw, "n_modules": n_mod},
        "scenes": scenes,
        "hero": hero,
        "is_design_aerial": bool(aerial_scene),
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
