# -*- coding: utf-8 -*-
"""LIVE post-deploy check of the two-BOQ Generation-Station rework
(solarpro.aiappinvent.com, commit 23cdc6f). KC PKCE login as owner, create ONE
test project, walk steps 3-9, then verify: two BOQ links on the overview, the 5
new report PDFs, cost-plan.xlsx, Finish-BOQ-pricing, and /boq-projects isolation.
Single login attempt (no retry) to avoid KC lockout."""
import re, sys, html, requests

BASE = "https://solarpro.aiappinvent.com"
KC_USER, KC_PASS = "marc667us@yahoo.com", "ember-lantern-cedar-river"
s = requests.Session(); s.headers["User-Agent"] = "TwoBOQ-LiveCheck/1.0"
fails = []
def ck(n, c, e=""):
    print(("PASS" if c else "FAIL"), "-", n, ("" if c else f"[{e}]"))
    if not c: fails.append(n)
def csrf(t):
    m = re.search(r'name="_csrf"\s+value="([^"]*)"', t); return m.group(1) if m else ""

# --- KC login ---
r = s.get(f"{BASE}/auth/login", timeout=30)
m = re.search(r'action="([^"]+login-actions/authenticate[^"]*)"', r.text)
if not m:
    print("FATAL: no KC form"); sys.exit(2)
r2 = s.post(html.unescape(m.group(1)),
            data={"username": KC_USER, "password": KC_PASS, "credentialId": ""},
            timeout=30, headers={"Content-Type": "application/x-www-form-urlencoded"})
if "Invalid username or password" in r2.text or "Invalid email" in r2.text:
    print("FATAL: KC rejected creds"); sys.exit(3)
ck("KC login accepted", "/auth/login" not in r2.url and "login-actions/authenticate" not in r2.text, r2.url)

def get(p): return s.get(f"{BASE}{p}", timeout=120)
def spost(step, data):
    tok = csrf(get(f"/large-scale-solar/{{}}".format('new') if step=='new' else f"/large-scale-solar/{pid}/{step}").text)
    d = dict(data); d["_csrf"] = tok
    tgt = f"{BASE}/large-scale-solar/new" if step=='new' else f"{BASE}/large-scale-solar/{pid}/{step}"
    return s.post(tgt, data=d, timeout=120, allow_redirects=False)

# --- create + walk ---
tok = csrf(get("/large-scale-solar/new").text)
r = s.post(f"{BASE}/large-scale-solar/new", data={"_csrf": tok,
    "project_name": "LIVE TWO-BOQ CHECK - Generation Station (delete me)",
    "project_type": "utility_scale", "country": "Ghana", "region": "Greater Accra",
    "district": "Tema", "target_mwp": "20", "currency": "GHS",
    "project_status": "concept", "design_standard": "IEC", "tax_regime": "standard"},
    timeout=30, allow_redirects=False)
m = re.search(r"/large-scale-solar/(\d+)", r.headers.get("Location", ""))
pid = int(m.group(1)) if m else None
ck("project created", pid is not None, r.headers.get("Location"))
if not pid: print("passes so far; aborting"); sys.exit(4)
print("live pid =", pid)

spost("step3", {"terrain": "flat", "slope": "lt_3", "soil": "loam", "flood_risk": "low",
    "wind_zone": "z2_medium", "seismic_zone": "zone_1", "access": "paved",
    "water": "borehole", "land_area_ha": "50"})
spost("step4", {"buildings": ["control_room", "om_building", "security_gate", "battery_room",
    "inverter_room", "switchgear_bldg", "transformer_bldg", "scada_bldg"],
    "external_works": ["pv_field", "fence"]})
spost("step5", {"technologies": ["scada", "string_mon", "bms"]})
spost("step6", {"services": ["internal_installation", "power_supply", "fire_alarm", "earthing"]})
spost("step7", {"module_tech": "mono_topcon", "module_wp": "600", "mounting": "single_axis",
    "inverter_type": "central", "kwp": "20000", "dc_ac_ratio": "1.2", "tilt_deg": "10",
    "azimuth_deg": "180", "psh_daily": "5.4", "performance_ratio": "0.78",
    "availability_pct": "98", "annual_degradation_pct": "0.5", "project_life_yr": "25"})
spost("step8", {"tariff_local_per_kwh": "1.5", "fx_local_per_usd": "12", "revenue_model": "ppa",
    "project_life_yr": "25", "discount_rate_pct": "10", "debt_ratio_pct": "70",
    "debt_rate_pct": "10", "debt_tenor_yr": "12", "tax_rate_pct": "25", "monte_carlo_runs": "0"})
r = spost("step9", {})
ck("step9 generate redirects (no 500)", r.status_code in (302, 303), r.status_code)

# --- overview shows BOTH BOQs ---
ov = get(f"/large-scale-solar/{pid}").text
ck("overview shows Facilities BOQ link", "Facilities &amp; Technology BOQ" in ov or "Facilities & Technology BOQ" in ov, "missing")
ck("overview shows Solar Farm 20MWp BOQ link", "Solar Farm 20MWp BOQ" in ov, "missing")
ck("overview shows Finish BOQ pricing button", "Finish BOQ pricing" in ov, "missing")

# --- Finish BOQ pricing (prices deferred facility floors + solar) ---
ftok = csrf(ov)
rf = s.post(f"{BASE}/large-scale-solar/{pid}/boq/finish", data={"_csrf": ftok},
            timeout=180, allow_redirects=False)
ck("finish BOQ pricing redirects", rf.status_code in (302, 303), rf.status_code)

# --- 5 new reports render valid PDFs ---
for key in ("wiring", "single_line", "energy_impact", "economic_impact", "implementation_plan"):
    rr = get(f"/large-scale-solar/{pid}/report/{key}.pdf")
    ck(f"report {key}.pdf valid", rr.status_code == 200 and rr.content[:4] == b"%PDF",
       f"{rr.status_code} {rr.content[:8]}")

# --- cost-plan.xlsx (includes solar + service sheets) ---
rx = get(f"/large-scale-solar/{pid}/cost-plan.xlsx")
ck("cost-plan.xlsx valid zip", rx.status_code == 200 and rx.content[:2] == b"PK", rx.status_code)

# --- isolation on /boq-projects ---
d = get("/boq-projects").text
c = get("/boq-projects?scope=capital").text
ck("default /boq-projects hides Solar Farm 20MWp BOQ", "Solar Farm 20MWp" not in d, "leaked")
ck("scope=capital shows capital BOQs", ("Solar Farm 20MWp" in c) or ("Facilities" in c), "missing")

print("=== LIVE TWO-BOQ CHECK:", "ALL PASS" if not fails else "FAIL " + str(fails), "=== pid", pid)
sys.exit(1 if fails else 0)
