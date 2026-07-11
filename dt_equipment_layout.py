"""Equipment LAYOUT / General-Arrangement (GA) model for the SolarPro
Generation Station.

Produces three top-down (plan-view) equipment general-arrangement drawings --
one each for the **inverter station**, the **main substation**, and the
**control room** -- showing the equipment arranged INSIDE each room footprint as
labelled rectangles, with per-item sizes, operating/maintenance clearances
(aisles), cable-entry points, doors, a per-room equipment schedule and the
governing standards.

Reusability rule 0.3: PURE, importable model. It CONSUMES the project's already-
computed engineering figures (via ``dt_electrical_sld.build_sld_model`` -> the
Step-7 ``size_utility_pv`` sizing) -- it starts NO new sizing engine. Equipment
QUANTITIES and RATINGS therefore come from the committed design; only the room
GEOMETRY and the electrical working CLEARANCES are added here, and every
clearance is flagged as an explicit ASSUMPTION (IEC 61936-1 / IEC 60364 working
space) rather than presented as a committed figure.

All room + item geometry is returned in METRES (origin top-left, +x right,
+y down); the template scales it into an SVG viewBox. Never raises: every field
degrades to a safe default so a half-built project still renders.
"""
from __future__ import annotations

import math
from typing import Any

from dt_electrical_sld import build_sld_model, has_committed_sizing, _f, _load

__all__ = ["build_equipment_layout_model"]

# --- Category palette (item fill + legend colour) ----------------------------
# Kept deliberately close to the site-layout / SLD palette so the three GA
# drawings read as part of the same drawing set.
_CAT = {
    "inverter":    "#f59e0b",   # power conversion
    "transformer": "#3b5a7a",   # step-up / power transformers
    "lv_switch":   "#5b8fb0",   # LV AC switchgear / distribution
    "mv_switch":   "#16324f",   # MV switchgear / RMU line-up
    "dc":          "#2c7a5b",   # DC combiner / array termination
    "control":     "#6b5ca5",   # protection, control, SCADA, metering
    "battery":     "#a5744a",   # station battery / UPS / DC aux
    "aux":         "#6b7280",   # HVAC, auxiliary, welfare, earthing
    "grid":        "#8fb3d6",   # HV takeoff / grid interface
}
_CAT_LABEL = {
    "inverter":    "Inverter / power conversion",
    "transformer": "Power / step-up transformer",
    "lv_switch":   "LV AC switchgear / distribution",
    "mv_switch":   "MV switchgear / RMU",
    "dc":          "DC combiner / array termination",
    "control":     "Protection / control / SCADA",
    "battery":     "Battery / UPS / DC auxiliary",
    "aux":         "HVAC / auxiliary / welfare",
    "grid":        "HV takeoff / grid interface",
}
# Label ink: dark text on the light fills, near-white on the dark fills, so the
# tag/name stays legible inside every box.
_CAT_TEXT = {
    "inverter": "#3a2a06", "grid": "#0b1a2a", "lv_switch": "#08131f",
    "transformer": "#eaf2fb", "mv_switch": "#eaf2fb", "dc": "#eaf7f0",
    "control": "#f2eefb", "battery": "#faf2ea", "aux": "#f1f3f5",
}

# --- Clearance ASSUMPTIONS (electrical working space) ------------------------
# These are NOT committed figures for this project; they are the standard-based
# minimums the GA is drawn to when the design is silent. Every one is surfaced
# in the model's per-room ``assumptions`` list and the template prints them as
# assumptions. Values are conservative minimums; final layout confirms against
# the equipment vendor drawings + the electrical safety study.
_CLR_MV_AISLE_M   = 1.2    # MV switchgear front operating/maintenance aisle
_CLR_MV_REAR_M    = 0.8    # rear cable/access gangway behind MV switchgear
_CLR_TX_WALL_M    = 0.75   # oil/dry transformer body to wall/enclosure
_CLR_TX_TX_M      = 1.5    # transformer-to-transformer (firewall) separation
_CLR_LV_FRONT_M   = 1.0    # LV panel / distribution board front working space
_CLR_CIRC_M       = 1.0    # general circulation / escape route in a room


def _fmt(v: float, nd: int = 0) -> str:
    """Format a number for a label; never raises."""
    try:
        return f"{float(v):,.{nd}f}"
    except (TypeError, ValueError):
        return "0"


def _item(x, y, w, h, label, size, cat, tag=""):
    """One placed equipment rectangle (metres). ``cat`` keys the palette."""
    return {
        "x": round(float(x), 2), "y": round(float(y), 2),
        "w": round(float(w), 2), "h": round(float(h), 2),
        "label": str(label), "size": str(size),
        "cat": cat, "fill": _CAT.get(cat, "#6b7280"),
        "text": _CAT_TEXT.get(cat, "#eaf2fb"),
        "tag": str(tag),
    }


def _clr(x, y, w, h, label):
    """One clearance / aisle zone (metres) drawn as a hatched band."""
    return {"x": round(float(x), 2), "y": round(float(y), 2),
            "w": round(float(w), 2), "h": round(float(h), 2),
            "label": str(label)}


def _legend_for(items: list[dict]) -> list[dict]:
    """Build a de-duplicated legend from the categories actually used."""
    seen: list[str] = []
    out: list[dict] = []
    for it in items:
        c = it.get("cat")
        if c and c not in seen:
            seen.append(c)
            out.append({"label": _CAT_LABEL.get(c, c), "fill": _CAT.get(c, "#6b7280")})
    return out


# ---------------------------------------------------------------------------
# Room builders. Each returns a self-contained render-ready room dict. Geometry
# is hand-laid in metres inside the room's interior box (0,0)->(w,h) so items
# never overlap and never leave the room; the template draws walls, a door with
# a swing arc, dimension lines, the clearance bands and a graphic scale.
# ---------------------------------------------------------------------------

def _inverter_station_room(fig: dict) -> dict:
    """Inverter station GA: one central-inverter station (1 of N identical).

    Houses the central inverter, its LV/MV step-up transformer, the LV AC
    switchgear, the MV switchgear (RMU), the DC combiner input termination and
    the station-service/aux panel, around a central operating aisle.
    """
    n_inv = int(fig["n_inv"])
    inv_kw = _f(fig["inv_kw"])
    inv_ac_v = _f(fig["inv_ac_v"])
    mv_kv = _f(fig["mv_kv"])
    xfmr_mva = _f(fig["xfmr_mva_each"])
    dc_feeders = int(fig["dc_feeders_per_station"])

    W, H = 14.0, 7.0                      # interior room dimensions (m)
    items: list[dict] = []
    # -- north (top) equipment row: DC in -> inverter -> LV -> MV --
    items.append(_item(0.4, 0.4, 2.2, 2.1,
                       "DC combiner termination",
                       f"~{dc_feeders} DC feeders in, 1500 V", "dc", "DB-01"))
    items.append(_item(3.0, 0.4, 3.6, 2.2,
                       "Central inverter",
                       f"{_fmt(inv_kw)} kWac, {_fmt(inv_ac_v)} V AC", "inverter", "INV-01"))
    items.append(_item(7.2, 0.4, 2.3, 2.1,
                       "LV AC switchgear",
                       f"ACB/MCCB, {_fmt(inv_ac_v)} V bus", "lv_switch", "LVSG-01"))
    items.append(_item(10.1, 0.4, 3.5, 2.4,
                       "MV switchgear (RMU)",
                       f"{_fmt(mv_kv)} kV, 2 ring + 1 tx feeder", "mv_switch", "MVSG-01"))
    # -- south (bottom) equipment row: transformer + aux/battery --
    items.append(_item(3.0, 4.5, 3.6, 2.1,
                       "LV/MV step-up transformer",
                       f"{_fmt(xfmr_mva, 2)} MVA, {_fmt(inv_ac_v/1000.0, 2)}/{_fmt(mv_kv)} kV Dyn11",
                       "transformer", "TX-01"))
    items.append(_item(7.2, 4.5, 2.3, 2.1,
                       "Station service / aux",
                       "LVAC aux + SPD + metering", "aux", "AUX-01"))
    items.append(_item(10.1, 4.5, 2.6, 2.1,
                       "Control / battery panel",
                       "Protection, 110 V DC aux", "battery", "CP-01"))

    # -- central operating / maintenance aisle (the empty middle band) --
    clears = [
        _clr(0.4, 2.7, 13.2, 1.6,
             f"Operating / maintenance aisle -- {_CLR_MV_AISLE_M:.1f} m min (assumed)"),
    ]
    door = {"side": "W", "pos": 5.4, "w": 1.2, "swing": "in"}   # west wall, near aisle
    cable_entry = {"side": "S", "pos": 4.8, "w": 1.6, "label": "MV/DC cable trench entry"}

    sched = [
        ("Central inverter", "1", "No."),
        ("Inverter unit rating", _fmt(inv_kw), "kWac"),
        ("LV/MV step-up transformer", "1", "No."),
        ("Transformer rating", _fmt(xfmr_mva, 2), "MVA"),
        ("LV AC switchgear", "1", "panel"),
        ("MV switchgear (RMU)", "1", "No."),
        ("DC combiner feeders (approx.)", _fmt(dc_feeders), "No."),
        ("Room footprint (interior)", f"{W:.0f} x {H:.0f}", "m"),
    ]
    return {
        "key": "inverter_station",
        "title": "Inverter Station",
        "subtitle": "General Arrangement (GA) -- equipment plan (top-down)",
        "count_note": (f"Typical -- 1 of {n_inv} identical inverter stations"
                       if n_inv > 1 else "Single inverter station"),
        "room": {"w": W, "h": H},
        "items": items,
        "clearances": clears,
        "door": door,
        "cable_entry": cable_entry,
        "legend": _legend_for(items),
        "schedule": sched,
        "assumptions": [
            f"Operating/maintenance aisle in front of switchgear >= {_CLR_MV_AISLE_M:.1f} m "
            "(IEC 61936-1 access, assumed).",
            f"Transformer body to wall/enclosure >= {_CLR_TX_WALL_M:.2f} m (assumed).",
            "Room dimensions are indicative for a packaged inverter/transformer "
            "station; confirm against the inverter vendor's e-house GA drawing.",
        ],
        "standards": ["IEC 62109", "IEC 61439", "IEC 60076", "IEC 62271-200",
                      "IEC 61936-1", "Ghana Grid Code"],
    }


def _substation_room(fig: dict) -> dict:
    """Substation GA: main/grid substation compound.

    Grid step-up power transformer(s), the MV switchgear line-up, protection &
    metering, the control/relay (SCADA) panel, the station battery/DC aux, the
    HV takeoff to the grid, plus perimeter fence, gate and earthing note.
    """
    mv_kv = _f(fig["mv_kv"])
    poi_kv = _f(fig["poi_kv"])
    main_mva = _f(fig["main_mva"])
    n_grid_tx = int(fig["n_grid_tx"])
    n_feeders = int(fig["n_mv_feeders"])

    W, H = 22.0, 13.0
    items: list[dict] = []
    # -- HV takeoff gantry along the north edge (grid side) --
    items.append(_item(0.6, 0.5, 20.8, 0.9,
                       "HV takeoff gantry / line bay",
                       f"Grid POI {_fmt(poi_kv)} kV", "grid", "HV-01"))
    # -- grid step-up power transformer(s), drawn up to 2 (count stated) --
    tx_draw = 1 if n_grid_tx <= 1 else 2
    tx_mva_each = round(main_mva / max(n_grid_tx, 1), 1) if main_mva else main_mva
    tx_w, tx_h = 4.0, 3.6
    for i in range(tx_draw):
        tx_x = 2.5 + i * (tx_w + _CLR_TX_TX_M)
        items.append(_item(tx_x, 2.2, tx_w, tx_h,
                           f"Grid step-up transformer" + (f" T{i+1}" if tx_draw > 1 else ""),
                           f"{_fmt(tx_mva_each, 1)} MVA, {_fmt(mv_kv)}/{_fmt(poi_kv)} kV",
                           "transformer", f"GT-0{i+1}"))
    # -- MV switchroom line-up (indoor) on the east side --
    items.append(_item(13.5, 2.2, 7.9, 3.2,
                       f"MV switchgear line-up",
                       f"{_fmt(mv_kv)} kV, 1 incomer + {n_feeders} feeders", "mv_switch", "MVSG"))
    # -- protection & metering panel --
    items.append(_item(13.5, 6.2, 3.6, 1.8,
                       "Protection & revenue metering",
                       "Class 0.2S CT/VT, IEDs", "control", "PM-01"))
    # -- control / relay / SCADA panel --
    items.append(_item(17.5, 6.2, 3.9, 1.8,
                       "Control / relay / SCADA panel",
                       "IEC 61850 station bus", "control", "SC-01"))
    # -- station battery / DC auxiliary --
    items.append(_item(13.5, 8.8, 3.4, 2.0,
                       "Station battery / DC aux",
                       "110 V DC + charger", "battery", "BAT-01"))
    # -- auxiliary / earthing transformer (station service) --
    items.append(_item(2.5, 7.0, 3.4, 2.4,
                       "Aux / earthing transformer",
                       "Station service LVAC", "aux", "AT-01"))
    # -- earthing grid marker (informational tile) --
    items.append(_item(7.0, 8.4, 4.5, 2.0,
                       "Earthing grid access pit",
                       "Buried Cu ring, Rg <= 1 ohm", "aux", "E-01"))

    clears = [
        _clr(2.5, 6.0, 9.0, 0.9,
             f"Transformer maintenance access -- {_CLR_TX_WALL_M:.2f} m to wall (assumed)"),
        _clr(13.5, 5.5, 7.9, 0.6,
             f"MV switchgear operating aisle -- {_CLR_MV_AISLE_M:.1f} m min (assumed)"),
    ]
    door = {"side": "E", "pos": 4.0, "w": 1.2, "swing": "out"}    # switchroom escape
    gate = {"side": "S", "pos": 11.0, "w": 4.0, "label": "Access gate"}
    fence = {"inset": 0.35}                                        # perimeter fence inset (m)
    cable_entry = {"side": "S", "pos": 6.0, "w": 2.0, "label": "MV collector cable trench"}

    sched = [
        ("Grid step-up transformer(s)", _fmt(n_grid_tx), "No."),
        ("Main export rating", _fmt(main_mva, 1), "MVA"),
        ("MV collection voltage", _fmt(mv_kv), "kV"),
        ("Grid POI voltage", _fmt(poi_kv), "kV"),
        ("MV feeders (collector rings)", _fmt(n_feeders), "No."),
        ("Compound footprint (interior)", f"{W:.0f} x {H:.0f}", "m"),
    ]
    return {
        "key": "substation",
        "title": "Main Substation",
        "subtitle": "General Arrangement (GA) -- compound equipment plan (top-down)",
        "count_note": "Plant main / grid substation (1 No.)",
        "room": {"w": W, "h": H},
        "items": items,
        "clearances": clears,
        "door": door,
        "gate": gate,
        "fence": fence,
        "cable_entry": cable_entry,
        "legend": _legend_for(items),
        "schedule": sched,
        "assumptions": [
            f"Transformer body clearance to wall/firewall >= {_CLR_TX_WALL_M:.2f} m and "
            f"transformer-to-transformer >= {_CLR_TX_TX_M:.1f} m (IEC 61936-1, assumed).",
            f"MV switchgear operating/maintenance aisle >= {_CLR_MV_AISLE_M:.1f} m; rear "
            f"gangway >= {_CLR_MV_REAR_M:.1f} m (assumed).",
            f"Number of grid step-up transformers assumed {n_grid_tx} "
            "(1 up to ~40 MVA, else 2); confirm in the grid-connection study.",
            "Earthing grid resistance target <= 1 ohm; step/touch within IEC 61936-1 "
            "limits -- confirm by earthing study.",
        ],
        "standards": ["IEC 60076", "IEC 62271", "IEC 61850", "IEC 61936-1",
                      "IEC 62305", "Ghana Grid Code", "ECG/NEDCo Rules"],
    }


def _control_room(fig: dict) -> dict:
    """Control room GA: control / O&M building internal layout.

    SCADA/HMI workstations, the server/comms rack, protection & control panels,
    the LVAC distribution board, the UPS/battery cabinet, the HVAC unit and an
    operations office / welfare space, around a central circulation aisle.
    """
    n_ws = int(fig["n_workstations"])

    W, H = 13.0, 9.0
    items: list[dict] = []
    # -- server / comms rack (top-left) --
    items.append(_item(0.4, 0.4, 3.2, 2.6,
                       "Server / comms rack",
                       "SCADA server, RTU, telecoms", "control", "RK-01"))
    # -- protection & control panels down the left wall --
    items.append(_item(0.4, 3.4, 3.2, 4.4,
                       "Protection & control panels",
                       "Feeder IEDs, station HMI", "control", "PC-01"))
    # -- SCADA / HMI workstation desks (top centre) --
    items.append(_item(4.4, 0.4, 5.6, 1.6,
                       f"SCADA / HMI workstations (x{n_ws})",
                       "Operator consoles + video wall", "control", "WS-01"))
    # -- LVAC distribution board (top-right) --
    items.append(_item(11.0, 0.4, 1.6, 3.0,
                       "LVAC distribution board",
                       "400/230 V, TN-S", "lv_switch", "DB-01"))
    # -- UPS + battery cabinet (right) --
    items.append(_item(11.0, 3.8, 1.6, 2.2,
                       "UPS + battery cabinet",
                       "Control supply backup", "battery", "UPS-01"))
    # -- HVAC package unit (bottom-right corner) --
    items.append(_item(11.0, 6.4, 1.6, 2.2,
                       "HVAC unit",
                       "Precision cooling", "aux", "AC-01"))
    # -- operations office / welfare (bottom centre) --
    items.append(_item(4.4, 5.6, 5.6, 3.0,
                       "Operations office / welfare",
                       "O&M staff, meeting", "aux", "OFF-01"))

    clears = [
        _clr(4.4, 2.4, 5.6, 3.0,
             f"Circulation / panel working space -- {_CLR_CIRC_M:.1f} m min (assumed)"),
    ]
    door = {"side": "S", "pos": 6.5, "w": 1.2, "swing": "out"}    # main entrance
    cable_entry = {"side": "W", "pos": 8.4, "w": 1.4, "label": "Control cable entry"}

    sched = [
        ("SCADA / HMI workstations", _fmt(n_ws), "No."),
        ("Server / comms rack", "1", "No."),
        ("Protection & control panels", "1", "line-up"),
        ("LVAC distribution board", "1", "No."),
        ("UPS + battery cabinet", "1", "No."),
        ("HVAC unit", "1", "No."),
        ("Room footprint (interior)", f"{W:.0f} x {H:.0f}", "m"),
    ]
    return {
        "key": "control_room",
        "title": "Control Room",
        "subtitle": "General Arrangement (GA) -- building equipment plan (top-down)",
        "count_note": "Plant control / O&M room (1 No.)",
        "room": {"w": W, "h": H},
        "items": items,
        "clearances": clears,
        "door": door,
        "cable_entry": cable_entry,
        "legend": _legend_for(items),
        "schedule": sched,
        "assumptions": [
            f"Front working space to panels / distribution boards >= {_CLR_LV_FRONT_M:.1f} m "
            "(IEC 60364-7 / building code, assumed).",
            f"General circulation / escape route >= {_CLR_CIRC_M:.1f} m clear (assumed).",
            "Workstation count is indicative for a plant of this size; confirm "
            "against the O&M staffing plan.",
        ],
        "standards": ["IEC 61850", "IEC 60364", "IEC 62305", "Ghana Building Code"],
    }


def build_equipment_layout_model(proj: dict[str, Any]) -> dict[str, Any]:
    """Build the three-room equipment GA model for a Generation-Station project.

    Input: a project row/dict (uses ``pv_config.sizing`` + ``electrical_config``
    via ``dt_electrical_sld.build_sld_model``). Output: a render-ready dict with
    ``rooms`` (inverter station, substation, control room), each carrying its
    footprint, placed equipment items (metres), clearance zones, door, schedule,
    per-room clearance assumptions and standards. Geometry in metres. NEVER
    raises: every field degrades to a safe default so a half-built project still
    renders an (indicative) drawing.
    """
    proj = proj if isinstance(proj, dict) else {}
    try:
        sld = build_sld_model(proj) or {}          # reuse: sizing-derived figures
    except Exception:
        sld = {}
    pj = sld.get("project") if isinstance(sld.get("project"), dict) else {}
    volts = sld.get("voltages") if isinstance(sld.get("voltages"), dict) else {}
    stages = {s.get("key"): s for s in (sld.get("stages") or [])
              if isinstance(s, dict)}

    def _stage_qty(key: str) -> int:
        return int(_f((stages.get(key) or {}).get("qty")))

    dc_kwp = _f(pj.get("dc_kwp"))
    ac_mw = _f(pj.get("ac_mw"))

    # Sizing numbers: prefer the committed pv_config.sizing (same source the SLD
    # + site-layout use); fall back to the SLD's own derived stage counts so a
    # pre-Step-7 project still renders. Never divide by zero.
    sz = _load(proj.get("pv_config")).get("sizing")
    sz = sz if isinstance(sz, dict) else {}
    n_inv = int(_f(sz.get("n_central_inverters"))) or _stage_qty("inverter")
    if n_inv <= 0:
        n_inv = max(1, int(math.ceil(ac_mw))) if ac_mw else 1
    inv_kw = _f(sz.get("central_inverter_kw")) or 1500.0
    combiners = int(_f(sz.get("combiners"))) or _stage_qty("combiner")

    inv_ac_v = _f(volts.get("inverter_ac_v")) or 800.0
    mv_kv = _f(volts.get("mv_kv")) or 33.0
    poi_kv = _f(volts.get("poi_kv")) or mv_kv

    # Derived ratings (mirror dt_electrical_sld's basis: ~0.9 pf).
    xfmr_mva_each = round(max(inv_kw, 1.0) / 0.9 / 1000.0, 2)
    main_mva = round(max(ac_mw * 1000.0, 1.0) / 0.9 / 1000.0, 1) if ac_mw else round(
        max(n_inv * inv_kw, 1.0) / 0.9 / 1000.0, 1)
    # Assumption: 1 main power transformer up to ~40 MVA, else 2.
    n_grid_tx = 1 if main_mva <= 40.0 else 2
    # DC combiner feeders landing at each inverter station.
    dc_feeders_per_station = max(1, int(math.ceil(combiners / max(n_inv, 1)))) if combiners else 6
    # MV collector feeders into the substation (ring pairs); at least 1.
    n_mv_feeders = max(1, int(math.ceil(n_inv / 4.0)))
    # SCADA workstations scale gently with plant size (2..5).
    n_workstations = max(2, min(5, 1 + int(math.ceil(ac_mw / 25.0)))) if ac_mw else 2

    fig = {
        "n_inv": n_inv, "inv_kw": inv_kw, "inv_ac_v": inv_ac_v,
        "mv_kv": mv_kv, "poi_kv": poi_kv, "xfmr_mva_each": xfmr_mva_each,
        "main_mva": main_mva, "n_grid_tx": n_grid_tx,
        "dc_feeders_per_station": dc_feeders_per_station,
        "n_mv_feeders": n_mv_feeders, "n_workstations": n_workstations,
    }

    rooms = []
    for builder in (_inverter_station_room, _substation_room, _control_room):
        try:
            rooms.append(builder(fig))
        except Exception:
            # A single room must never sink the whole drawing set.
            continue

    try:
        committed = has_committed_sizing(proj)
    except Exception:
        committed = False

    return {
        "project": {"name": pj.get("name") or proj.get("project_name")
                    or "Solar Generation Station",
                    "dc_kwp": dc_kwp, "ac_mw": ac_mw,
                    "n_inverter_stations": n_inv},
        "committed": bool(committed),
        "rooms": rooms,
        "assumptions": [
            "Room dimensions and equipment positions are INDICATIVE general "
            "arrangements for planning; they are confirmed against vendor "
            "equipment drawings and the electrical safety/earthing study.",
            "Working clearances are drawn to IEC 61936-1 (HV/MV access) and "
            "IEC 60364 (LV working space) minimums where the design is silent.",
        ],
        "standards": ["IEC 61936-1", "IEC 60076", "IEC 62271", "IEC 61439",
                      "IEC 60364", "IEC 61850", "Ghana Grid Code",
                      "Ghana Building Code"],
    }
