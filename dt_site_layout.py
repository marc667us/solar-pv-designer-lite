"""Plant LAYOUT / PLOT-PLAN model for the SolarPro Generation Station.

Produces a scaled, top-down site arrangement of the physical plant: the PV array
field divided into inverter blocks, each block's inverter + step-up transformer
skid, the MV collection / main substation compound, the control / O&M building,
the internal access-road network, the perimeter security fence, and the entrance
gate -- plus a block schedule, overall dimensions and a graphic scale.

Reusability rule 0.3: PURE, importable model. It CONSUMES the project's committed
PV sizing (via dt_electrical_sld.build_sld_model) -- no new sizing engine -- and
lays it out geometrically. All geometry is returned in SITE METRES; the template
scales it into an SVG viewBox. Never raises: every field degrades to a safe
default so a half-built project still renders.
"""
from __future__ import annotations

import math
from typing import Any

from dt_electrical_sld import build_sld_model, _f, _load

__all__ = ["build_site_layout_model"]

# Land-use intensity (ha per MWp) for fixed-tilt utility PV in Ghana practice.
_HA_PER_MWP = 1.2
# Fraction of a block's footprint actually covered by module tables (GCR-ish).
_ROADS_SETBACK_M = 8.0


def build_site_layout_model(proj: dict[str, Any]) -> dict[str, Any]:
    """Build the plot-plan model for a Generation-Station project.

    Input: a project row/dict. Output: a render-ready dict with site dimensions,
    array blocks, skids, substation, control building, roads, fence, gate,
    legend, and a schedule. Geometry in metres. Never raises.
    """
    proj = proj if isinstance(proj, dict) else {}
    try:
        sld = build_sld_model(proj) or {}          # reuse: sizing-derived figures
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
    if n_inv <= 0:
        n_inv = max(1, int(math.ceil(ac_mw))) if ac_mw else 1   # ~1 block / MW fallback

    # --- Site envelope (metres). Land ~1.2 ha/MWp; landscape aspect ~1.45:1. ---
    # Floor the area (abs + 4 ha minimum) so a zero/negative/garbage capacity can
    # never drive sqrt of a negative or a degenerate envelope.
    area_m2 = max(40000.0, abs(dc_kwp / 1000.0) * _HA_PER_MWP * 10000.0)
    aspect = 1.45
    site_w = max(200.0, round(math.sqrt(area_m2 * aspect), 0))
    site_h = max(140.0, round(area_m2 / site_w, 0))
    land_ha = round(area_m2 / 10000.0, 1)

    # Setbacks: perimeter fence inset + ring road, and a substation strip along
    # the bottom edge (near the grid POI). The strip is a fraction of site height
    # (capped) so it can never exceed the field on a small site.
    m = max(12.0, min(site_w, site_h) * 0.03)           # perimeter margin
    fence = {"x": m, "y": m, "w": site_w - 2 * m, "h": site_h - 2 * m}
    sub_strip_h = min(max(60.0, site_h * 0.16), fence["h"] * 0.42)
    field = {"x": fence["x"] + 14, "y": fence["y"] + 14,
             "w": max(40.0, fence["w"] - 28),
             "h": max(40.0, fence["h"] - 28 - sub_strip_h)}

    # --- Array blocks: one block per inverter station, laid in a grid. ---
    cols = max(1, int(round(math.sqrt(n_inv * (field["w"] / max(field["h"], 1.0))))))
    rows = max(1, int(math.ceil(n_inv / cols)))
    gap = max(6.0, field["w"] * 0.012)                  # inter-block road/gap
    bw = max(8.0, (field["w"] - (cols - 1) * gap) / cols)
    bh = max(8.0, (field["h"] - (rows - 1) * gap) / rows)
    blocks = []
    skids = []
    placed = 0
    for r in range(rows):
        for c in range(cols):
            if placed >= n_inv:
                break
            bx = field["x"] + c * (bw + gap)
            by = field["y"] + r * (bh + gap)
            blocks.append({"x": round(bx, 1), "y": round(by, 1),
                           "w": round(bw, 1), "h": round(bh, 1), "n": placed + 1})
            # inverter + transformer skid sits at the block's south edge, centred
            skids.append({"x": round(bx + bw / 2, 1), "y": round(by + bh - 3, 1)})
            placed += 1
        if placed >= n_inv:
            break

    # --- Substation compound + control building in the bottom strip. ---
    strip_y = field["y"] + field["h"] + 14
    sub_w = min(fence["w"] * 0.30, 220.0)
    sub_h = min(sub_strip_h - 16, 120.0)
    substation = {"x": round(fence["x"] + fence["w"] - sub_w - 20, 1),
                  "y": round(strip_y, 1), "w": round(sub_w, 1), "h": round(sub_h, 1)}
    ctrl_w = min(fence["w"] * 0.16, 90.0)
    control = {"x": round(fence["x"] + 24, 1), "y": round(strip_y, 1),
               "w": round(ctrl_w, 1), "h": round(min(sub_h, 60.0), 1)}

    # --- Access roads: perimeter ring + central spine + substation link. ---
    rx, ry, rw, rh = fence["x"] + 6, fence["y"] + 6, fence["w"] - 12, fence["h"] - 12
    roads = [
        {"kind": "ring", "points": [(rx, ry), (rx + rw, ry), (rx + rw, ry + rh),
                                     (rx, ry + rh), (rx, ry)]},
        {"kind": "spine", "points": [(site_w / 2, ry), (site_w / 2, strip_y)]},
        {"kind": "sub", "points": [(site_w / 2, strip_y),
                                   (substation["x"] + substation["w"] / 2, strip_y)]},
    ]
    gate = {"x": round(site_w / 2, 1), "y": round(fence["y"], 1)}

    # --- Schedule / legend ---------------------------------------------------
    block_mwp = round((dc_kwp / n_inv) / 1000.0, 2) if n_inv else 0.0
    perimeter_km = round(2 * (fence["w"] + fence["h"]) / 1000.0, 2)
    road_km = round((2 * (rw + rh) + (strip_y - ry)) / 1000.0, 2)
    schedule = [
        ("Site land area", f"{land_ha:,.1f}", "ha"),
        ("Site dimensions (approx.)", f"{site_w:,.0f} x {site_h:,.0f}", "m"),
        ("Array blocks (inverter stations)", f"{n_inv:,}", "No."),
        ("Block grid", f"{cols} x {rows}", "-"),
        ("Nominal block size", f"{block_mwp:.2f}", "MWp"),
        ("Modules total", f"{n_mod:,}", "No."),
        ("MV collection voltage", f"{_f(volts.get('mv_kv') or 33):.0f}", "kV"),
        ("Grid POI voltage", f"{_f(volts.get('poi_kv') or 33):.0f}", "kV"),
        ("Perimeter fence", f"{perimeter_km:.2f}", "km"),
        ("Internal access roads (approx.)", f"{road_km:.2f}", "km"),
    ]
    legend = [
        {"key": "block", "label": "PV array block", "fill": "#16324f"},
        {"key": "skid", "label": "Inverter + step-up transformer", "fill": "#f59e0b"},
        {"key": "sub", "label": "MV / main substation", "fill": "#3b5a7a"},
        {"key": "ctrl", "label": "Control / O&M building", "fill": "#5b8fb0"},
        {"key": "road", "label": "Access road", "fill": "#6b7280"},
        {"key": "fence", "label": "Perimeter fence", "fill": "#94a3b8"},
    ]

    return {
        "project": {"name": pj.get("name") or "Solar Generation Station",
                    "dc_kwp": dc_kwp, "ac_mw": ac_mw, "n_modules": n_mod,
                    "n_blocks": n_inv},
        "site": {"w_m": site_w, "h_m": site_h, "area_ha": land_ha},
        "fence": fence,
        "field": field,
        "blocks": blocks,
        "skids": skids,
        "substation": substation,
        "control": control,
        "roads": roads,
        "gate": gate,
        "grid": {"cols": cols, "rows": rows},
        "legend": legend,
        "schedule": schedule,
        "standards": ["IEC 62548 (array layout)", "IEC 61936-1 (site clearances)",
                      "Ghana Grid Code (POI & access)", "Ghana Building Code"],
    }
