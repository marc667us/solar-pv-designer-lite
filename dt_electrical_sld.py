"""Electrical single-line-diagram (SLD) + mounting-detail model for the
SolarPro Generation Station.

Pure, importable engineering model (reusability rule 0.3): it reads a project's
ALREADY-COMPUTED PV sizing (``pv_config.sizing`` from ``size_utility_pv``) plus
its ``electrical_config`` / ``site_config`` and returns a structured description
of the power-export chain --

    PV strings -> string combiner boxes -> DC array switchgear -> inverters
    -> LV AC switchgear -> LV/MV step-up transformer -> MV switchgear (RMU)
    -> MV collection / main substation -> HV switchgear -> grid POI

together with per-stage quantities, ratings, protection, the applicable
Ghana + IEC standards, a PV table mounting-support detail, the full input-
variable list, and a consolidated reference list. Nothing here computes a NEW
sizing engine -- it consumes the existing one and adds the electrical topology
and citations the SLD view and the design report both render.

Units: SI. Voltages in volts unless a field name says kV. Never raises: every
field degrades to a safe default so a half-built project still renders.
"""
from __future__ import annotations

import math
from typing import Any

__all__ = ["build_sld_model", "GHANA_IEC_REFERENCES"]

# --- Consolidated standards the SLD + design report cite (Ghana + IEC) --------
GHANA_IEC_REFERENCES: list[dict[str, str]] = [
    {"code": "IEC 62548",        "title": "Photovoltaic (PV) arrays - Design requirements"},
    {"code": "IEC 60364-7-712",  "title": "Low-voltage electrical installations - Solar PV power supply systems"},
    {"code": "IEC 61215 / 61730","title": "PV module design qualification, type approval & safety"},
    {"code": "IEC 62109-1/-2",   "title": "Safety of power converters for use in PV power systems (inverters)"},
    {"code": "IEC 61727 / 62116","title": "PV systems - Utility interface & anti-islanding test procedures"},
    {"code": "IEC 60269",        "title": "Low-voltage fuses (string / array fuse protection)"},
    {"code": "IEC 61439",        "title": "Low-voltage switchgear & controlgear assemblies (AC LV boards)"},
    {"code": "IEC 60076",        "title": "Power transformers (LV/MV step-up units)"},
    {"code": "IEC 62271",        "title": "High-voltage switchgear & controlgear (MV RMU / HV)"},
    {"code": "IEC 61850",        "title": "Communication networks & systems for power utility automation (SCADA)"},
    {"code": "IEC 62305",        "title": "Protection against lightning (LPS & SPD coordination)"},
    {"code": "IEC 60287",        "title": "Electric cables - Calculation of the continuous current rating"},
    {"code": "IEC 60364-5-54",   "title": "Earthing arrangements & protective conductors"},
    {"code": "Ghana Grid Code",  "title": "GRIDCo Grid Code - connection & operation of generating plant"},
    {"code": "ECG/NEDCo Rules",  "title": "Distribution network connection requirements (MV interconnection)"},
    {"code": "Ghana EC LI 2413", "title": "Energy Commission - Renewable Energy (regulation & licensing)"},
    {"code": "GS IEC/ASTM",      "title": "Ghana Standards Authority - adopted electrotechnical standards"},
]


def _f(v: Any, default: float = 0.0) -> float:
    """Coerce to float; return default on garbage (never raises)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe(d: Any) -> dict:
    return d if isinstance(d, dict) else {}


def _load(v: Any) -> dict:
    """Project config blobs are stored as JSON strings OR already-parsed dicts;
    normalise either to a dict (empty on anything else). Never raises."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        import json
        try:
            out = json.loads(v)
            return out if isinstance(out, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _sizing_of(proj: dict) -> dict:
    """Return the project's stored PV sizing dict, or a minimal fallback derived
    from whatever target capacity is available so the SLD still renders."""
    pv = _load(proj.get("pv_config"))
    sizing = _safe(pv.get("sizing"))
    if sizing.get("n_modules"):
        return sizing
    # Pre-sizing fallback: REUSE the real engine (size_utility_pv) rather than a
    # parallel formula, so the SLD never drifts from Step-7 sizing. Lazy import
    # avoids a load-time cycle; a coarse inline default is the last resort only
    # if that import is unavailable (e.g. the model imported standalone).
    kwp = _f(pv.get("kwp") or proj.get("target_kwp") or 0.0)
    wp = _f(pv.get("module_wp") or 550.0) or 550.0
    if kwp > 0:
        try:
            from new_capital_investment_routes import size_utility_pv
            out = size_utility_pv(kwp=kwp, module_wp=wp,
                                  dc_ac_ratio=_f(pv.get("dc_ac_ratio") or 1.20),
                                  tilt_deg=_f(pv.get("tilt_deg") or 12.0),
                                  azimuth_deg=_f(pv.get("azimuth_deg") or 180.0))
            if isinstance(out, dict) and out.get("n_modules"):
                return out
        except Exception:
            pass
    n_modules = int(math.ceil(kwp * 1000 / wp)) if kwp > 0 else 0
    mps, spc, inv_kw, dcac = 28, 20, 1500.0, 1.20
    dc_actual = round(n_modules * wp / 1000.0, 2)
    strings = int(math.ceil(n_modules / mps)) if n_modules else 0
    combiners = int(math.ceil(strings / spc)) if strings else 0
    inv_ac = round(dc_actual / dcac, 2) if dc_actual else 0.0   # match engine: off actual DC
    n_inv = int(math.ceil(inv_ac / inv_kw)) if inv_ac else 0
    return {"kwp_input": kwp, "dc_kwp_actual": dc_actual,
            "module_wp": wp, "n_modules": n_modules, "dc_ac_ratio": dcac,
            "inverter_ac_kw": inv_ac, "n_central_inverters": n_inv,
            "central_inverter_kw": inv_kw, "strings": strings,
            "modules_per_string": mps, "combiners": combiners,
            "strings_per_combiner": spc}


def build_sld_model(proj: dict[str, Any]) -> dict[str, Any]:
    """Build the SLD + mounting-detail model for a Generation-Station project.

    Input: a project row/dict (uses ``pv_config.sizing`` + ``electrical_config``
    + ``site_config``). Output: a render-ready dict (see module docstring).
    """
    proj = _safe(proj)
    sz = _sizing_of(proj)
    pvcfg = _load(proj.get("pv_config"))
    elec = _load(proj.get("electrical_config"))
    site = _load(proj.get("site_config"))
    row_pitch_m = _f(pvcfg.get("row_pitch_m") or sz.get("row_pitch_m") or 6.0)

    n_modules   = int(_f(sz.get("n_modules")))
    module_wp   = _f(sz.get("module_wp") or 550.0)
    dc_kwp      = _f(sz.get("dc_kwp_actual") or sz.get("kwp_input"))
    strings     = int(_f(sz.get("strings")))
    mps         = int(_f(sz.get("modules_per_string") or 28))
    combiners   = int(_f(sz.get("combiners")))
    spc         = int(_f(sz.get("strings_per_combiner") or 20))
    n_inv       = int(_f(sz.get("n_central_inverters")))
    inv_kw      = _f(sz.get("central_inverter_kw") or 1500.0)
    inv_ac_kw   = _f(sz.get("inverter_ac_kw"))
    dc_ac       = _f(sz.get("dc_ac_ratio") or 1.20)

    # --- Voltage plan (defaults follow Ghana utility practice; overridable) ---
    v_module_vmp = _f(elec.get("module_vmp_v") or 41.7)     # 550 Wp module ~41.7 Vmp
    v_module_voc = _f(elec.get("module_voc_v") or 49.9)
    string_vmp   = round(v_module_vmp * mps, 0)             # operating string voltage
    string_voc_cold = round(v_module_voc * mps * 1.14, 0)   # cold-Voc for 1500V check
    dc_system_v  = 1500.0
    inv_ac_v     = _f(elec.get("inverter_ac_v") or 800.0)   # central-inverter LV AC
    mv_kv        = _f(elec.get("mv_kv") or 33.0)            # ECG/GRIDCo MV collection
    poi_kv       = _f(elec.get("poi_kv") or mv_kv)          # grid point of interconnection

    ac_mw = round(inv_ac_kw / 1000.0, 2)
    # One LV/MV step-up transformer per inverter station; rated ~ inverter AC / pf.
    xfmr_mva_each = round(max(inv_kw, 1.0) / 0.9 / 1000.0, 2)
    main_mva = round(max(inv_ac_kw, 1.0) / 0.9 / 1000.0, 2)

    # String fuse: IEC 62548 -> 1.5 x Isc(STC); 550 Wp ~ 13.9 A Isc -> ~20-25 A gPV
    isc = _f(elec.get("module_isc_a") or 13.9)
    string_fuse_a = int(math.ceil(1.5 * isc / 5.0) * 5)     # rounded up to 5 A step

    stages = [
        {"key": "array", "title": "PV Array", "symbol": "pv",
         "qty": n_modules, "qty_label": "modules",
         "ratings": [("Module", f"{module_wp:.0f} Wp"),
                     ("Array DC", f"{dc_kwp:,.0f} kWp"),
                     ("System voltage", f"{dc_system_v:.0f} V DC max")],
         "protection": "Module-level: bypass diodes; frame bonding",
         "standards": ["IEC 61215", "IEC 61730"],
         "note": f"{n_modules:,} x {module_wp:.0f} Wp mono-PERC/bifacial modules."},

        {"key": "string", "title": "PV Strings", "symbol": "string",
         "qty": strings, "qty_label": "strings",
         "ratings": [("Modules/string", f"{mps}"),
                     ("String Vmp", f"{string_vmp:.0f} V"),
                     ("String Voc (cold)", f"{string_voc_cold:.0f} V")],
         "protection": f"Series string fuse {string_fuse_a} A gPV (both poles)",
         "standards": ["IEC 62548", "IEC 60269-6"],
         "note": ("Max string voltage (cold Voc) checked against the "
                  + ("1500 V DC system limit per IEC 62548 -- REVIEW: exceeds limit, reduce modules/string."
                     if string_voc_cold > dc_system_v else
                     "1500 V DC system limit per IEC 62548 (within limit)."))},

        {"key": "combiner", "title": "String Combiner Boxes", "symbol": "combiner",
         "qty": combiners, "qty_label": "combiner boxes",
         "ratings": [("Strings/combiner", f"{spc}"),
                     ("String fuses", f"{string_fuse_a} A gPV x2"),
                     ("SPD", "Type 1+2 DC, 1500 V")],
         "protection": "Per-string fuses + DC SPD + load-break isolator + monitoring",
         "standards": ["IEC 62548", "IEC 60364-7-712", "IEC 62305"],
         "note": "DC string currents combined onto array feeders to the inverters."},

        {"key": "dc_switchgear", "title": "DC Array Switchgear", "symbol": "dc_sw",
         "qty": n_inv, "qty_label": "DC combiner/rec. units",
         "ratings": [("Feeders", f"{combiners} -> {n_inv} inverters"),
                     ("DC disconnect", "1500 V load-break"),
                     ("SPD", "Type 2 DC at inverter input")],
         "protection": "Main DC isolator + Type 2 SPD per inverter DC input",
         "standards": ["IEC 62548", "IEC 60364-7-712"],
         "note": "Array feeders recombined and isolated ahead of each inverter."},

        {"key": "inverter", "title": "Inverters", "symbol": "inverter",
         "qty": n_inv, "qty_label": "central inverters",
         "ratings": [("Unit rating", f"{inv_kw:.0f} kWac"),
                     ("Plant AC", f"{ac_mw:.1f} MWac"),
                     ("DC/AC ratio", f"{dc_ac:.2f}"),
                     ("AC output", f"{inv_ac_v:.0f} V, 50 Hz")],
         "protection": "DC & AC disconnects, anti-islanding, LVRT, fault ride-through",
         "standards": ["IEC 62109-1/-2", "IEC 61727", "IEC 62116", "Ghana Grid Code"],
         "note": "MPPT conversion 1500 V DC -> LV AC; grid-code compliant."},

        {"key": "ac_switchgear", "title": "LV AC Switchgear", "symbol": "ac_sw",
         "qty": n_inv, "qty_label": "LV AC panels",
         "ratings": [("Per inverter", "ACB/MCCB + metering"),
                     ("Bus voltage", f"{inv_ac_v:.0f} V AC"),
                     ("SPD", "Type 2 AC")],
         "protection": "ACB with O/C + E/F protection, AC SPD, isolation",
         "standards": ["IEC 61439-1/-2", "IEC 62305"],
         "note": "LV AC collected at each inverter station switchboard."},

        {"key": "transformer", "title": "LV/MV Step-up Transformers", "symbol": "transformer",
         "qty": n_inv, "qty_label": "station transformers",
         "ratings": [("Rating (each)", f"{xfmr_mva_each:.2f} MVA"),
                     ("Ratio", f"{inv_ac_v/1000.0:.2f}/{mv_kv:.0f} kV"),
                     ("Vector group", "Dyn11"),
                     ("Impedance", "~6 %")],
         "protection": "HV fuse/CB, Buchholz, WTI/OTI, differential (main unit)",
         "standards": ["IEC 60076-1/-2/-3", "IEC 60076-11"],
         "note": "Each inverter station steps LV AC up to the MV collection voltage."},

        {"key": "mv_switchgear", "title": "MV Switchgear (RMU)", "symbol": "rmu",
         "qty": n_inv, "qty_label": "ring main units",
         "ratings": [("Voltage", f"{mv_kv:.0f} kV"),
                     ("Config", "2 ring + 1 transformer feeder"),
                     ("Breaking", "SF6 / vacuum")],
         "protection": "MV CB with IDMT O/C + E/F relays; interlocks",
         "standards": ["IEC 62271-200", "IEC 62271-100"],
         "note": "Station RMUs form the MV collector ring to the main substation."},

        {"key": "substation", "title": "MV Collection / Main Substation", "symbol": "substation",
         "qty": 1, "qty_label": "plant substation",
         "ratings": [("Collector", f"{mv_kv:.0f} kV ring"),
                     ("Export", f"{main_mva:.1f} MVA @ {poi_kv:.0f} kV"),
                     ("Metering", "Revenue CT/VT, Class 0.2S")],
         "protection": "Main incomer/feeder protection, busbar & transformer diff, SCADA",
         "standards": ["IEC 62271", "IEC 61850", "Ghana Grid Code"],
         "note": "All station rings collected; export metering & plant protection."},

        {"key": "grid", "title": "HV Switchgear / Grid POI", "symbol": "grid",
         "qty": 1, "qty_label": "point of interconnection",
         "ratings": [("POI voltage", f"{poi_kv:.0f} kV"),
                     ("Export", f"{ac_mw:.1f} MW"),
                     ("Compliance", "P/Q, LVRT, frequency response")],
         "protection": "Grid interface protection, tele-protection, synchronising",
         "standards": ["Ghana Grid Code", "ECG/NEDCo Rules", "IEC 62271"],
         "note": "Connection to the GRIDCo/ECG network at the agreed POI."},
    ]

    # --- Cable schedule (indicative sizes; IEC 60287 rating basis) ------------
    dc_cable_m = int(_f(sz.get("dc_cable_m_est") or dc_kwp * 6.5))
    ac_cable_m = int(_f(sz.get("ac_cable_m_est") or dc_kwp * 3.5))
    cables = [
        {"segment": "Module -> string", "type": "PV1-F DC", "size": "1x6 mm² Cu",
         "length_m": None, "standard": "IEC 62930 / EN 50618"},
        {"segment": "String -> combiner", "type": "PV1-F DC", "size": "1x6-10 mm² Cu",
         "length_m": None, "standard": "IEC 62930"},
        {"segment": "Combiner -> inverter (DC array feeder)", "type": "DC XLPE",
         "size": "1x120-300 mm² Al/Cu", "length_m": dc_cable_m, "standard": "IEC 60287"},
        {"segment": "Inverter -> LV board", "type": "LV XLPE/PVC", "size": "per phase busduct",
         "length_m": None, "standard": "IEC 60364-5-52"},
        {"segment": "LV board -> transformer", "type": "LV XLPE", "size": "1-c Al",
         "length_m": ac_cable_m, "standard": "IEC 60287"},
        {"segment": f"Transformer -> MV ring ({mv_kv:.0f} kV)", "type": "MV XLPE",
         "size": "3-c 95-240 mm² Al", "length_m": None, "standard": "IEC 60502-2"},
        {"segment": "MV ring -> main substation", "type": "MV XLPE",
         "size": "3-c 240-400 mm² Al", "length_m": None, "standard": "IEC 60502-2"},
    ]

    earthing = {
        "system": "TN-S at LV; solidly/impedance earthed MV per grid code",
        "components": ["Buried Cu ring earth grid", "Module frame & mounting bonding",
                       "Inverter/transformer neutral earthing", "Lightning air terminals + down-conductors"],
        "target": "Grid resistance <= 1 Ω (substation); step/touch within IEC 61936 limits",
        "standards": ["IEC 60364-5-54", "IEC 62305", "IEC 61936-1"],
    }

    # --- PV table mounting-support detail -------------------------------------
    tilt = _f(sz.get("tilt_deg") or 12.0)
    modules_per_table = int(_f(elec.get("modules_per_table") or 28))
    mounting = {
        "structure": "Fixed-tilt ground-mount steel table",
        "tilt_deg": tilt,
        "azimuth_deg": _f(sz.get("azimuth_deg") or 180.0),
        "module_orientation": "2 x portrait (2P) per table",
        "modules_per_table": modules_per_table,
        "torque_tube": "Galvanised steel torque tube / purlin, hot-dip Z600",
        "posts": "Driven steel I/C-section piles (2-3 per table)",
        "ground_clearance_m": 0.8,
        "row_pitch_m": row_pitch_m,
        "foundation": "Driven pile (ram) - refusal/pull-out tested; concrete where required",
        "design_loads": "Wind (site basic wind speed), self-weight, snow n/a (Ghana)",
        "standards": ["IEC 62548", "EN 1991-1-4 / ASCE 7 (wind)", "EN 1993 (steel)",
                      "Ghana Building Code (structural loads)"],
    }

    inputs = [
        ("Installed DC capacity", f"{dc_kwp:,.0f}", "kWp"),
        ("Plant AC capacity", f"{ac_mw:.1f}", "MWac"),
        ("DC/AC ratio", f"{dc_ac:.2f}", "-"),
        ("Module power", f"{module_wp:.0f}", "Wp"),
        ("Number of modules", f"{n_modules:,}", "No."),
        ("Modules per string", f"{mps}", "No."),
        ("Number of strings", f"{strings:,}", "No."),
        ("Strings per combiner", f"{spc}", "No."),
        ("Combiner boxes", f"{combiners:,}", "No."),
        ("Central inverters", f"{n_inv}", "No."),
        ("Inverter unit rating", f"{inv_kw:.0f}", "kVA"),
        ("Inverter AC voltage", f"{inv_ac_v:.0f}", "V"),
        ("MV collection voltage", f"{mv_kv:.0f}", "kV"),
        ("Grid POI voltage", f"{poi_kv:.0f}", "kV"),
        ("Station transformer (each)", f"{xfmr_mva_each:.2f}", "MVA"),
        ("Array tilt", f"{tilt:.0f}", "deg"),
        ("Row pitch", f"{mounting['row_pitch_m']:.1f}", "m"),
        ("String fuse rating", f"{string_fuse_a}", "A"),
    ]

    return {
        "project": {"name": proj.get("project_name") or "Solar Generation Station",
                    "dc_kwp": dc_kwp, "ac_mw": ac_mw, "n_modules": n_modules,
                    "module_wp": module_wp},
        "voltages": {"dc_system_v": dc_system_v, "string_vmp": string_vmp,
                     "inverter_ac_v": inv_ac_v, "mv_kv": mv_kv, "poi_kv": poi_kv},
        "stages": stages,
        "cables": cables,
        "earthing": earthing,
        "mounting": mounting,
        "inputs": inputs,
        "references": GHANA_IEC_REFERENCES,
    }
