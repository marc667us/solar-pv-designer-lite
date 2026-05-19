"""
AC Mains Cable Selection Engine — BS 7671:2018 (IEC 60364-5-52)
Sizes AC cables for: inverter-to-DB, main feeder, grid interconnection,
generator backup, and AC sub-distribution feeders.
"""
import math

CABLE_SIZES_MM2 = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300]

# Current-carrying capacity (A) — copper PVC 70°C cables, BS 7671:2018 Appendix 4
CAPACITY = {
    "A":  [11.5,15,   20,   26,   36,   47,   61,   75,   90,   115,  138,  159,  182,  207,  240,  278],
    "B":  [13,   17.5, 23,   30,   40,   54,   70,   86,   103,  130,  156,  179,  203,  230,  269,  306],
    "C":  [15.5, 21,   28,   36,   50,   66,   84,   103,  122,  153,  182,  210,  240,  272,  322,  371],
    "D":  [18,   24,   31,   39,   52,   67,   86,   103,  122,  151,  179,  203,  230,  258,  297,  336],
    "E":  [17.5, 24,   32,   41,   57,   76,   99,   121,  144,  184,  219,  253,  287,  328,  382,  441],
    "F":  [19.5, 26,   35,   46,   63,   85,   112,  138,  168,  213,  258,  299,  344,  392,  461,  530],
}

# Voltage drop mV/A/m — single-phase copper 70°C, BS 7671:2018 Appendix 4
VD_SP = [29, 18, 11, 7.3, 4.4, 2.8, 1.75, 1.25, 0.93, 0.63, 0.47, 0.37, 0.30, 0.245, 0.190, 0.154]
VD_3P = [v * 0.866 for v in VD_SP]   # three-phase factor

# Temperature correction — 70°C cables, reference 30°C ambient (Table 4B2)
TEMP_FACTORS = {25:1.06, 30:1.00, 35:0.94, 40:0.87, 45:0.79, 50:0.71, 55:0.61, 60:0.50}

# Grouping correction — circuits in same enclosure/tray (Table 4B1)
GROUP_FACTORS = {1:1.00, 2:0.80, 3:0.70, 4:0.65, 5:0.60}

INSTALL_METHODS = {
    "A": "Enclosed in conduit in thermally insulating wall",
    "B": "Enclosed in conduit on wall / in trunking",
    "C": "Clipped direct to surface",
    "D": "Underground in duct or direct buried",
    "E": "On cable tray (cables touching)",
    "F": "On cable tray — single-core cables spaced",
}

STD_BREAKERS = [6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400]


def _temp_factor(ambient_c):
    pts = sorted(TEMP_FACTORS)
    if ambient_c <= pts[0]:  return TEMP_FACTORS[pts[0]]
    if ambient_c >= pts[-1]: return TEMP_FACTORS[pts[-1]]
    for i in range(len(pts)-1):
        t1, t2 = pts[i], pts[i+1]
        if t1 <= ambient_c <= t2:
            f1, f2 = TEMP_FACTORS[t1], TEMP_FACTORS[t2]
            return f1 + (f2-f1)*(ambient_c-t1)/(t2-t1)
    return 1.00


def _group_factor(n):
    if n >= 5: return GROUP_FACTORS[5]
    return GROUP_FACTORS.get(n, 1.00)


def size_cable(power_w, voltage_v, length_m, phase="single",
               pf=0.90, install_method="C", ambient_c=30,
               num_circuits=1, max_vd_pct=3.0):
    """
    Size a single AC cable per BS 7671:2018.

    Returns a dict with all sizing parameters and results.
    """
    if phase == "three":
        I_b = power_w / (math.sqrt(3) * voltage_v * pf)
        vd_table = VD_3P
    else:
        I_b = power_w / (voltage_v * pf)
        vd_table = VD_SP

    Ct = _temp_factor(ambient_c)
    Cg = _group_factor(num_circuits)
    I_z_min = I_b / (Ct * Cg)

    cap_table = CAPACITY.get(install_method.upper(), CAPACITY["C"])

    # Select by current
    idx = next((i for i, c in enumerate(cap_table) if c >= I_z_min),
                len(CABLE_SIZES_MM2) - 1)

    # Upgrade for voltage drop
    max_vd_v = (max_vd_pct / 100) * voltage_v
    while idx < len(CABLE_SIZES_MM2) - 1:
        vd_v = (vd_table[idx] * I_b * length_m) / 1000
        if vd_v <= max_vd_v:
            break
        idx += 1

    size    = CABLE_SIZES_MM2[idx]
    cap     = cap_table[idx]
    mv_am   = vd_table[idx]
    vd_v    = (mv_am * I_b * length_m) / 1000
    vd_pct  = (vd_v / voltage_v) * 100

    breaker = next((b for b in STD_BREAKERS if b >= I_b * 1.05), STD_BREAKERS[-1])
    if breaker > cap:
        breaker = next((b for b in reversed(STD_BREAKERS) if b <= cap), STD_BREAKERS[0])

    vd_limit_v = (max_vd_pct / 100) * voltage_v
    return {
        "power_kw":       round(power_w/1000, 2),
        "phase":          phase,
        "voltage_v":      voltage_v,
        "pf":             pf,
        "design_current": round(I_b, 2),
        "length_m":       length_m,
        "install_method": install_method,
        "install_desc":   INSTALL_METHODS.get(install_method.upper(), ""),
        "ambient_c":      ambient_c,
        "num_circuits":   num_circuits,
        "temp_factor":    round(Ct, 3),
        "group_factor":   round(Cg, 3),
        "i_z_required":   round(I_z_min, 2),
        "cable_size_mm2": size,
        "cable_capacity": cap,
        "vd_mv_am":       mv_am,
        "vd_volts":       round(vd_v, 3),
        "vd_limit_pct":   max_vd_pct,
        "vd_limit_v":     round(vd_limit_v, 2),
        "vd_percent":     round(vd_pct, 3),
        "vd_ok":          vd_pct <= max_vd_pct,
        "breaker_a":      breaker,
        "core_type":      "Multicore" if size <= 50 else "Single-core",
    }


def size_all_cables(inverter_kw, pv_kw, system_type, phase, ambient_c=30,
                    install_method="C"):
    """Size all AC circuits for a PV system. Returns list of results."""
    pf = 0.90
    v  = 415 if phase == "three" else 230

    circuits = [
        ("Inverter to Main DB",             inverter_kw*1000*1.25, v,   10, phase, 1.5),
        ("Main AC Distribution Feeder",     inverter_kw*1000,      v,   25, phase, 2.5),
        ("Sub-distribution (Lighting/Sockets)", min(inverter_kw*0.3*1000,5000), 230, 30, "single", 3.0),
    ]
    if system_type in ("hybrid", "grid-tied"):
        circuits.append(("Grid Interconnection Cable", pv_kw*1000, v, 20, phase, 2.0))
    if system_type in ("off-grid", "hybrid"):
        gen_kw = max(inverter_kw*0.5, 3.0)
        circuits.append((f"Generator Backup ({gen_kw:.1f} kW)", gen_kw*1000, v, 15, phase, 2.0))

    results = []
    for label, pw, vv, lm, ph, vd_pct in circuits:
        r = size_cable(pw, vv, lm, phase=ph, pf=pf,
                       install_method=install_method, ambient_c=ambient_c,
                       max_vd_pct=vd_pct)
        r["circuit"] = label
        results.append(r)
    return results
