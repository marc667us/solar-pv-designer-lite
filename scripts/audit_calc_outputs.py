"""
P0 — numeric outputs audit (resume queue priority 1).

Hand-calc 5kWp residential rooftop Greater Accra against the seven engine
functions, A/B vs app output, surface any discrepancy.

Run from project root:  python scripts/audit_calc_outputs.py
"""

from __future__ import annotations
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Skip Flask app init noise during import — we only need the calc fns.
os.environ.setdefault("SKIP_WEB_INIT", "1")

# Import calc functions directly from web_app + helpers.
from config.global_solar_data import temp_derating
from calculation.ac_cable_sizing import size_all_cables

# web_app imports a lot at module-load; isolate the calc fns we need.
import importlib.util
spec = importlib.util.spec_from_file_location("web_app", os.path.join(ROOT, "web_app.py"))
# Don't actually load — too heavy. Instead pull the fns via exec on the relevant lines.
# Simpler: import directly. If it explodes, we'll work around.
import web_app  # noqa: E402

calc_loads     = web_app.calc_loads
calc_pv        = web_app.calc_pv
calc_battery   = web_app.calc_battery
calc_mppt      = web_app.calc_mppt
calc_inverter  = web_app.calc_inverter
calc_boq       = web_app.calc_boq
calc_economics = web_app.calc_economics
BATTERY_CHEMISTRY = web_app.BATTERY_CHEMISTRY


# ── Reporter ─────────────────────────────────────────────────────────────────

passes, fails = [], []
def check(label, expected, actual, tol=0.01):
    delta = abs(actual - expected) if isinstance(expected, (int, float)) else None
    ok = (actual == expected) if delta is None else (delta <= tol * max(1, abs(expected)))
    rec = (label, expected, actual, delta, ok)
    (passes if ok else fails).append(rec)
    flag = "PASS" if ok else "FAIL"
    extra = f"  (delta={delta:.4g})" if delta is not None else ""
    print(f"  [{flag}] {label}: expected {expected!r}, got {actual!r}{extra}")


# ── Test case: 5kWp Greater Accra rooftop residential ────────────────────────

print("\n" + "=" * 72)
print(" 5kWp Greater Accra residential — hand-calc vs engine")
print("=" * 72)

DAILY_KWH = 18.0   # consumption matched to 5kWp at 5h PSH, 75% sys_eff
PSH       = 5.0
TEMP_C    = 28.0
PANEL_WP  = 400
SYS_EFF   = 0.75
AUTONOMY  = 1
PEAK_KW   = 3.5
TARIFF    = 1.9688   # GHS/kWh Residential Standard
CURRENCY  = "GHS"
SYMBOL    = "GHS"  # use ASCII for cross-codec terminals; engine accepts any string
COST_USD_KWP = 850
FX_USD    = 15.0     # rough 2026 GHS/USD


# ── temp_derating ──────────────────────────────────────────────────────────
print("\n[temp_derating]")
expected_td = max(0.88, 1.0 - max(0.0, (TEMP_C - 25.0) * 0.004))
check("temp_derating(28)", expected_td, temp_derating(TEMP_C))


# ── calc_loads ─────────────────────────────────────────────────────────────
print("\n[calc_loads]")
loads_sample = [
    {"wattage": 100, "quantity": 10, "hours": 5,  "category": "Lighting"},     # 0.75 DF
    {"wattage": 1500, "quantity": 1, "hours": 4,  "category": "Cooling"},      # 0.65 DF
    {"wattage": 150,  "quantity": 1, "hours": 16, "category": "Electronics"},  # 0.70 DF
]
# Hand: (100*10*5*0.75 + 1500*1*4*0.65 + 150*1*16*0.70) / 1000
#     = (3750 + 3900 + 1680) / 1000 = 9.33
expected_loads = round((100*10*5*0.75 + 1500*1*4*0.65 + 150*1*16*0.70) / 1000, 3)
check("calc_loads(mixed)", expected_loads, calc_loads(loads_sample))


# ── calc_pv ────────────────────────────────────────────────────────────────
print("\n[calc_pv]")
# Hand:
#   td  = 0.988
#   eff = 0.75 * 0.988 = 0.741
#   pv_kw = 18 / (5 * 0.741) = 18 / 3.705 = 4.858
#   num_panels = ceil(4858/400) = ceil(12.146) = 13
td_h  = expected_td
eff_h = SYS_EFF * td_h
pv_kw_h = round(DAILY_KWH / (PSH * eff_h), 3)
num_p_h = math.ceil(pv_kw_h * 1000 / PANEL_WP)
pv_kw, num_p, td_r, pv_kw_base = calc_pv(DAILY_KWH, PSH, TEMP_C, PANEL_WP, SYS_EFF)
check("calc_pv pv_kw",      pv_kw_h, pv_kw)
check("calc_pv num_panels", num_p_h, num_p)
check("calc_pv td",         round(td_h, 4), td_r)
# With default shading_factor=1.0, pv_kw_corrected == pv_kw_base.
check("calc_pv pv_kw_base", pv_kw_h, pv_kw_base)


# ── calc_battery ───────────────────────────────────────────────────────────
print("\n[calc_battery]")
# Hand: dod=0.90 eff=0.96; required = 18 / (0.9*0.96) = 18/0.864 = 20.833
#   For sizes_kwh=[5.12,10.24,13.5,15.36,20.48,30.72] and MAX_RATIO=2.0:
#   Iterate and pick best score.
required = DAILY_KWH / (0.90 * 0.96)
SIZES = BATTERY_CHEMISTRY["LiFePO4"]["sizes_kwh"]
best = None
for size in SIZES:
    n = max(1, math.ceil(required / size))
    total = n * size
    if n == 1 and total > required * 2.0 and size != SIZES[0]:
        continue
    score = n * 1000 + (total - required)
    if best is None or score < best[0]:
        best = (score, n, size, total)
_, n_h, unit_h, total_h = best
total_r, n_r, unit_r = calc_battery(DAILY_KWH, AUTONOMY, "LiFePO4")
check("calc_battery total_kwh", round(total_h, 1), total_r)
check("calc_battery n_units",   n_h,             n_r)
check("calc_battery unit_kwh",  unit_h,          unit_r)


# ── calc_inverter ──────────────────────────────────────────────────────────
print("\n[calc_inverter]")
# from_energy = 18 * 0.30 * 1.25 = 6.75; max(6.75, 3.5) = 6.75; next standard >= 6.75 = 8.0
from_energy = DAILY_KWH * 0.30 * 1.25
inv_h = max(from_energy, PEAK_KW * 1.0)
for std in [3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 50.0, 100.0]:
    if std >= inv_h:
        inv_h_std = std
        break
check("calc_inverter (kW)", inv_h_std, calc_inverter(DAILY_KWH, PEAK_KW))


# ── calc_mppt ──────────────────────────────────────────────────────────────
print("\n[calc_mppt]")
# i_max = (pv_kw * 1000) / 48 * 1.25; pick first standard size >= i_max
PV_KW_FIX = pv_kw  # use what engine produced
i_max_h = (PV_KW_FIX * 1000) / 48 * 1.25
mppt_h = None
for s in [20, 30, 40, 50, 60, 80, 100, 120, 150, 200]:
    if s >= i_max_h:
        mppt_h = s
        break
if mppt_h is None:
    mppt_h = math.ceil(i_max_h / 10) * 10
check("calc_mppt (A)", mppt_h, calc_mppt(PV_KW_FIX, 48))


# ── calc_boq ───────────────────────────────────────────────────────────────
print("\n[calc_boq]")
try:
    # calc_boq returns (rows, grand) — rows is the line-item list, grand is total.
    rows, boq_total = calc_boq(
        num_panels=num_p_h, num_bat=n_h, inv_kw=inv_h_std, pv_kw=pv_kw_h,
        bat_kwh=total_h, unit_bat_kwh=unit_h, chemistry="LiFePO4",
        mppt_a=100, cost_usd_kwp=COST_USD_KWP, fx_usd=FX_USD)
    # Sanity: total should be in (10_000, 200_000) GHS for a 5kWp residential.
    # Per session memo: 5kWp Ghana boq was GHS 58,650 after cost_usd_kwp 980->850.
    plausible = 10_000 <= boq_total <= 200_000
    check("calc_boq total_local plausible (10k-200k GHS)", True, plausible)
    print(f"     total_local = GHS {boq_total:,.2f}")
    print(f"     line items  = {len(rows)}")
except Exception as e:
    fails.append(("calc_boq raised", "no raise", str(e), None, False))
    print(f"  [FAIL] calc_boq raised: {e}")
    import traceback; traceback.print_exc()


# ── size_all_cables ────────────────────────────────────────────────────────
print("\n[size_all_cables]")
cables = size_all_cables(inverter_kw=inv_h_std, pv_kw=pv_kw_h,
                         system_type="hybrid", phase="single", ambient_c=TEMP_C)
# hybrid + single => 5 circuits: inv->DB, Main, Sub, Grid, Generator backup
check("size_all_cables circuit count", 5, len(cables))
for c in cables:
    if c.get("cable_size_mm2", 0) <= 0 or c.get("breaker_a", 0) <= 0:
        fails.append((f"cable {c.get('circuit')} bad sizing", ">0", c, None, False))
        print(f"  [FAIL] {c.get('circuit')}: size={c.get('cable_size_mm2')} breaker={c.get('breaker_a')}")
    else:
        print(f"  [OK]   {c.get('circuit'):<40} sz={c['cable_size_mm2']} mm² brk={c['breaker_a']} A vd={c.get('vd_percent', '?')}%")


# ── calc_economics ─────────────────────────────────────────────────────────
print("\n[calc_economics]")
try:
    econ = calc_economics(
        pv_kw=pv_kw_h, num_panels=num_p_h, bat_kwh=total_h, num_bat=n_h,
        inv_kw=inv_h_std, daily_kwh=DAILY_KWH, tariff=TARIFF,
        currency=CURRENCY, symbol=SYMBOL, cost_usd_kwp=COST_USD_KWP,
        fx_usd=FX_USD, autonomy=AUTONOMY, chemistry="LiFePO4",
        funding_mode="loan", install_rate_pct=15)
    # Engine returns `irr_pct` (already × 100) not `irr`. None on degenerate inputs.
    irr_pct = econ.get("irr_pct")
    payback = econ.get("payback", 999)
    npv     = econ.get("npv", -1)
    plausible_payback = 3 <= payback <= 10
    plausible_irr     = irr_pct is not None and 5 <= irr_pct <= 40
    plausible_npv     = npv > 0
    check("calc_economics payback in 3-10 yr", True, plausible_payback)
    check("calc_economics IRR_pct in 5-40%",   True, plausible_irr)
    check("calc_economics NPV positive",       True, plausible_npv)
    print(f"     payback     = {payback:.2f} yr")
    print(f"     IRR_pct     = {irr_pct if irr_pct is None else f'{irr_pct:.1f}'}%")
    print(f"     NPV         = {SYMBOL} {npv:,.0f}")
    print(f"     CAPEX       = {SYMBOL} {econ.get('total_local'):,.0f}")
    print(f"     bankability = {econ.get('bankability', '?')}")
except Exception as e:
    fails.append(("calc_economics raised", "no raise", str(e), None, False))
    print(f"  [FAIL] calc_economics raised: {e}")
    import traceback; traceback.print_exc()


# ── Summary ────────────────────────────────────────────────────────────────
print("\n" + "=" * 72)
print(f" SUMMARY: {len(passes)} PASS, {len(fails)} FAIL")
print("=" * 72)
if fails:
    print("\nFAILURES:")
    for label, expected, actual, delta, _ in fails:
        d = f" (delta={delta:.4g})" if delta is not None else ""
        print(f"  - {label}: expected={expected!r}, got={actual!r}{d}")
    sys.exit(1)
sys.exit(0)
