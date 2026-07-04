# -*- coding: utf-8 -*-
"""Focused regression for the Codex MED finding (2026-07-03):
tracker plants must NOT pay for both fixed-tilt racking AND tracker racking.

Fix under test: _ci_solar_derived_terms now exposes fixed_mount_kwp /
fixed_pile_count / fixed_clamps that collapse to 0 when the plant is a tracker,
and the Bill-2 Fixed-Tilt Structure catalog rows reference those keys. So:
  - fixed-tilt plant  -> 4 fixed-tilt rows present, 0 tracker rows
  - tracker plant     -> 0 fixed-tilt rows,          4 tracker rows
Pure test: no DB, calls the row/derived helpers directly. Imports the ACTIVE
new_capital_investment_routes.py."""
import os, sys
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")

import new_capital_investment_routes as ci

fails = []
def ck(n, c, e=''):
    print(("PASS" if c else "FAIL"), "-", n, e)
    if not c: fails.append(n)

# A realistic 20 MWp sizing blob (what size_utility_pv() emits, minus mounting).
base_sz = {
    "n_modules": 36000, "dc_kwp_actual": 20000.0, "kwp": 20000.0,
    "kwp_input": 20000.0, "n_central_inv": 4, "strings": 1500,
    "combiners": 60, "dc_cable_m_est": 45000.0, "ac_cable_m_est": 6000.0,
    "pile_count": 18000,
}

FIXED_SECTION = "Fixed-Tilt Structure"
TRACKER_SECTION = "Tracker (optional)"

def count_section(rows, section):
    return sum(1 for r in rows if r["section"] == section)

# --- Fixed-tilt plant (no mounting => not a tracker) ---
sz_fixed = dict(base_sz)  # mounting absent -> fixed tilt
d_fixed = ci._ci_solar_derived_terms(sz_fixed)
rows_fixed = ci._ci_solar_boq_rows(sz_fixed)
ck("fixed: fixed_mount_kwp is full dc kWp", d_fixed["fixed_mount_kwp"] == 20000.0, d_fixed["fixed_mount_kwp"])
ck("fixed: fixed_pile_count non-zero", d_fixed["fixed_pile_count"] == 18000, d_fixed["fixed_pile_count"])
ck("fixed: fixed_clamps non-zero", d_fixed["fixed_clamps"] == 36000, d_fixed["fixed_clamps"])
ck("fixed: tracker_kwp zero", d_fixed["tracker_kwp"] == 0.0, d_fixed["tracker_kwp"])
ck("fixed: 4 fixed-tilt rows present", count_section(rows_fixed, FIXED_SECTION) == 4, count_section(rows_fixed, FIXED_SECTION))
ck("fixed: 0 tracker rows present", count_section(rows_fixed, TRACKER_SECTION) == 0, count_section(rows_fixed, TRACKER_SECTION))

# --- Tracker plant (single_axis) ---
sz_trk = dict(base_sz); sz_trk["mounting"] = "single_axis"
d_trk = ci._ci_solar_derived_terms(sz_trk)
rows_trk = ci._ci_solar_boq_rows(sz_trk)
ck("tracker: fixed_mount_kwp ZEROED", d_trk["fixed_mount_kwp"] == 0.0, d_trk["fixed_mount_kwp"])
ck("tracker: fixed_pile_count ZEROED", d_trk["fixed_pile_count"] == 0, d_trk["fixed_pile_count"])
ck("tracker: fixed_clamps ZEROED", d_trk["fixed_clamps"] == 0, d_trk["fixed_clamps"])
ck("tracker: tracker_kwp non-zero", d_trk["tracker_kwp"] == 20000.0, d_trk["tracker_kwp"])
ck("tracker: 0 fixed-tilt rows (no double-count)", count_section(rows_trk, FIXED_SECTION) == 0, count_section(rows_trk, FIXED_SECTION))
ck("tracker: 4 tracker rows present", count_section(rows_trk, TRACKER_SECTION) == 4, count_section(rows_trk, TRACKER_SECTION))

# --- mounting_type alias also gates (dual_axis) ---
sz_dual = dict(base_sz); sz_dual["mounting_type"] = "dual_axis"
rows_dual = ci._ci_solar_boq_rows(sz_dual)
ck("dual_axis: 0 fixed-tilt rows", count_section(rows_dual, FIXED_SECTION) == 0, count_section(rows_dual, FIXED_SECTION))
ck("dual_axis: 4 tracker rows", count_section(rows_dual, TRACKER_SECTION) == 4, count_section(rows_dual, TRACKER_SECTION))

# --- Structural: neither plant double-pays; both cover exactly one mounting family ---
mount_rows_fixed = count_section(rows_fixed, FIXED_SECTION) + count_section(rows_fixed, TRACKER_SECTION)
mount_rows_trk = count_section(rows_trk, FIXED_SECTION) + count_section(rows_trk, TRACKER_SECTION)
ck("fixed plant total mounting rows == 4 (one family)", mount_rows_fixed == 4, mount_rows_fixed)
ck("tracker plant total mounting rows == 4 (one family)", mount_rows_trk == 4, mount_rows_trk)

print("=== TRACKER DOUBLE-COUNT:", "ALL PASS" if not fails else "FAIL "+str(fails), "===")
sys.exit(1 if fails else 0)
