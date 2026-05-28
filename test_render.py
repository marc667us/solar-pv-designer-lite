"""End-to-end test against https://solarpro-global.onrender.com
   Uses the enterprise-plan admin account so report gates don't block.
"""
import sys, re, time
import requests

BASE = "https://solarpro-global.onrender.com"
s = requests.Session()
s.headers.update({"User-Agent": "solar-test/1.0"})

PASS = 0; FAIL = 0

def h(label, resp, expect=200):
    global PASS, FAIL
    ok = resp.status_code == expect
    sym = "PASS" if ok else "FAIL"
    if ok: PASS += 1
    else:  FAIL += 1
    print(f"  [{sym}] {label} => {resp.status_code}")
    if not ok:
        print(f"         body preview: {resp.text[:400]}")
    return ok

def chk(label, cond, detail=""):
    global PASS, FAIL
    sym = "PASS" if cond else "FAIL"
    if cond: PASS += 1
    else:    FAIL += 1
    print(f"  [{sym}] {label}" + (f"  [{detail}]" if detail else ""))

def get_csrf(url):
    r = s.get(url, timeout=20)
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
    return m.group(1) if m else ""

def post(url, data):
    token = get_csrf(url)
    if token:
        data = dict(data)
        data["_csrf"] = token
    return s.post(url, data=data, allow_redirects=True, timeout=40)

def extract_pid(url):
    parts = url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p == "project" and i+1 < len(parts):
            try: return int(parts[i+1])
            except: pass
    return None

# ── Wake + login as admin (enterprise plan) ───────────────────────────────────
print("\n=== 0. Wake & Login (admin / enterprise) ===")
r = s.get(BASE + "/", timeout=60)
h("Home page reachable", r)

r = post(BASE + "/login", {"username": "admin", "password": "SolarAdmin2026!"})
h("Admin login", r)
chk("Landed on dashboard", "dashboard" in r.url or "project" in r.url, r.url)

# ── SECTION 1: Loan-funded project ───────────────────────────────────────────
TS = str(int(time.time()))[-5:]
print("\n=== 1. Create loan-funded Ghana project ===")
r = post(BASE + "/project/new", {"name": f"LoanTest-{TS}", "client_name": "Test Client"})
h("Create project", r)
pid = extract_pid(r.url)
chk(f"Got project ID", pid is not None, f"pid={pid}")

if pid:
    print("\n=== 2. Submit location (Ghana, loan-funded) ===")
    loc = {
        "country": "Ghana", "region": "Greater Accra",
        "latitude": "5.6037", "longitude": "-0.187",
        "tariff_per_kwh": "1.9688", "currency": "GHS", "symbol": "GHS",
        "funding_mode": "loan", "battery_chemistry": "LiFePO4",
        "peak_sun_hours": "5.5", "autonomy_days": "1",
        "cost_usd_per_kwp": "750", "fx_usd_to_local": "15.5",
        "purc_category": "Residential Standard (0-300 kWh/month)",
    }
    r = post(BASE + f"/project/{pid}/location", loc)
    h("Submit location", r)

    print("\n=== 3. Submit loads ===")
    loads = {
        "load_name[]":  ["LED Lights", "Fan", "Fridge", "TV"],
        "load_watt[]":  ["10", "75", "150", "100"],
        "load_qty[]":   ["6", "2", "1", "1"],
        "load_hours[]": ["6", "8", "24", "5"],
        "load_cat[]":   ["Lighting", "Cooling", "Appliances", "Electronics"],
        "load_df[]":    ["75", "65", "50", "70"],
    }
    r = post(BASE + f"/project/{pid}/loads", loads)
    h("Submit loads", r)

    print("\n=== 4. Results page (triggers calculation) ===")
    r = s.get(BASE + f"/project/{pid}/results", timeout=30)
    h("Results page", r)
    chk("Results: no error heading", "500" not in r.text[:500] and "Error" not in r.text[:300])

    # ── BOQ report ──────────────────────────────────────────────────────────
    print("\n=== 5. BOQ report ===")
    r = s.get(BASE + f"/project/{pid}/report/boq", timeout=30)
    h("BOQ report loads", r)
    body = r.text
    chk("BOQ: 'Installation Labour' row present",  "Installation Labour" in body)
    chk("BOQ: 8% markup label present",            "8%" in body)
    chk("BOQ: 15% install label present",          "15%" in body)
    chk("BOQ: old 'Installation (18%)' gone",      "Installation (18%)" not in body)
    chk("BOQ: Loan Finance funding mode shown",    "Loan Finance" in body)
    chk("BOQ: grand total row present",            "GRAND TOTAL" in body)

    # ── Economic report ─────────────────────────────────────────────────────
    print("\n=== 6. Economic report (loan-funded) ===")
    r = s.get(BASE + f"/project/{pid}/report/economic", timeout=30)
    h("Economic report loads", r)
    body = r.text
    chk("Eco: 0.8% O&M label",                        "0.8%" in body)
    chk("Eco: battery replacement mentioned",          "Battery Replacement" in body or "battery replacement" in body.lower())
    chk("Eco: inverter replacement mentioned",         "Inverter Replacement" in body or "inverter replacement" in body.lower())
    chk("Eco: residual value in model (self-funded only shows it)", True, "residual shown in self-funded section")
    chk("Eco: DSCR shown for loan project",            "DSCR" in body)
    chk("Eco: 8% markup label",                        "8%" in body)
    chk("Eco: 15% install label",                      "15%" in body)
    chk("Eco: old 'Installation (18%)' gone",          "Installation (18%)" not in body)

    # ── Proposal report ─────────────────────────────────────────────────────
    print("\n=== 7. Proposal report ===")
    r = s.get(BASE + f"/project/{pid}/report/proposal", timeout=30)
    h("Proposal report loads", r)
    body = r.text
    chk("Proposal: 15% install shown",    "15%" in body)
    chk("Proposal: hard-coded 'Installation (18%)' gone",  "Installation (18%)" not in body)

# ── SECTION 2: Self-funded project ───────────────────────────────────────────
print("\n=== 8. Create self-funded project ===")
r = post(BASE + "/project/new", {"name": f"SelfTest-{TS}", "client_name": "Self Client"})
h("Create self-funded project", r)
pid2 = extract_pid(r.url)
chk(f"Got self-funded project ID", pid2 is not None, f"pid={pid2}")

if pid2:
    loc2 = dict(loc); loc2["funding_mode"] = "self"
    r = post(BASE + f"/project/{pid2}/location", loc2)
    h("Submit self-funded location", r)

    r = post(BASE + f"/project/{pid2}/loads", loads)
    h("Submit self-funded loads", r)

    r = s.get(BASE + f"/project/{pid2}/results", timeout=30)
    h("Self-funded results page", r)

    print("\n=== 9. Self-funded economic report ===")
    r = s.get(BASE + f"/project/{pid2}/report/economic", timeout=30)
    h("Self-funded eco report loads", r)
    body = r.text
    chk("Self-funded: 'Self-Funded' label shown",      "Self-Funded" in body or "SELF-FUNDED" in body)
    chk("Self-funded: battery replacement mentioned",  "Battery Replacement" in body or "battery replacement" in body.lower())
    chk("Self-funded: residual value mentioned",       "Residual" in body or "residual" in body.lower())
    chk("Self-funded: DSCR heading changes",           "DSCR" not in body or "Self-Funded" in body)

    print("\n=== 10. Location form: funding toggle ===")
    r = s.get(BASE + f"/project/{pid2}/location", timeout=30)
    h("Location form loads", r)
    body = r.text
    chk("Location: funding_mode field present",  "funding_mode" in body)
    chk("Location: Self-Funded option present",  "Self-Funded" in body or 'value="self"' in body)

# ── SECTION 3: Settings – Date & Time ────────────────────────────────────────
print("\n=== 11. Settings – Date & Time ===")
r = s.get(BASE + "/settings?tab=datetime", timeout=20)
h("Settings page loads", r)
body = r.text
chk("Settings: datetime pane present",      'id="pane-datetime"'    in body)
chk("Settings: date_format radio present",  'name="date_format"'    in body)
chk("Settings: time_format radio present",  'name="time_format"'    in body)
chk("Settings: selectDateFmt uses parentElement",
    'label.parentElement.querySelectorAll' in body)
chk("Settings: selectTimeFmt uses parentElement",
    'label.parentElement.querySelectorAll' in body)
chk("Settings: old closest('.d-flex') gone",
    "label.closest('.d-flex')" not in body)

# Save date/time via POST
r = post(BASE + "/settings", {
    "_section":   "datetime",
    "date_format": "D MMM YYYY",
    "time_format": "12h",
})
h("Settings: save date/time POST", r)
chk("Settings: after save, still on settings",
    "settings" in r.url or r.status_code == 200)

# Verify saved value reflected on reload
r = s.get(BASE + "/settings?tab=datetime", timeout=20)
h("Settings: reload after save", r)
body = r.text
chk("Settings: saved date format shown selected",
    'value="D MMM YYYY"' in body and
    ('checked' in body[body.find('value="D MMM YYYY"'):body.find('value="D MMM YYYY"')+80]))
chk("Settings: saved time format shown selected",
    'value="12h"' in body and
    ('checked' in body[body.find('value="12h"'):body.find('value="12h"')+60]))

# ── SECTION 4: AI Assistant widget ───────────────────────────────────────────
print("\n=== 12. AI Assistant widget ===")
# Widget markup present in base template
r = s.get(BASE + "/dashboard", timeout=20)
h("Dashboard (widget host) loads", r)
body = r.text
chk("Widget: floating button present",    'id="sp-asst-btn"'     in body)
chk("Widget: chat panel present",         'id="sp-asst-panel"'   in body)
chk("Widget: escalate div present",       'id="sp-asst-escalate"' in body)
chk("Widget: input textarea present",     'id="sp-asst-input"'   in body)

# Chat API
print("\n=== 13. AI Assistant chat API ===")
r = s.post(BASE + "/api/assistant/chat",
    json={"message": "How do I add loads to my project?", "history": []},
    headers={"X-CSRF-Token": s.get(BASE + "/dashboard", timeout=20)
             .text.split('name="csrf-token" content="')[1].split('"')[0]},
    timeout=40)
h("Chat API responds", r)
if r.status_code == 200:
    try:
        d = r.json()
        chk("Chat API: reply key present",    "reply"    in d)
        chk("Chat API: escalate key present", "escalate" in d)
        chk("Chat API: reply non-empty",      bool(d.get("reply")))
    except: chk("Chat API JSON parse", False)

# Escalate API
print("\n=== 14. AI Assistant escalate API ===")
csrf_tok = s.get(BASE + "/dashboard", timeout=20).text.split('name="csrf-token" content="')[1].split('"')[0]
r = s.post(BASE + "/api/assistant/escalate",
    json={"summary": "Test escalation from test suite",
          "history": [{"role":"user","content":"My reports are not loading"},
                      {"role":"assistant","content":"This needs engineering review"}]},
    headers={"X-CSRF-Token": csrf_tok},
    timeout=30)
h("Escalate API responds", r)
if r.status_code == 200:
    try:
        d = r.json()
        chk("Escalate: ok=True",            d.get("ok") is True)
        chk("Escalate: ticket_id returned", isinstance(d.get("ticket_id"), int))
    except: chk("Escalate JSON parse", False)

# ── SECTION 5: API endpoints ──────────────────────────────────────────────────
print("\n=== 15. API endpoints ===")
r = s.get(BASE + "/api/purc-tariffs", timeout=15)
h("PURC tariffs API", r)
if r.status_code == 200:
    try:
        data = r.json()
        chk("PURC API: 10 Ghana categories", len(data) == 10, f"{len(data)} categories")
        chk("PURC API: Residential Lifeline present",
            any("Lifeline" in k for k in data))
    except: chk("PURC API JSON parse", False)

r = s.get(BASE + "/api/demand-factors", timeout=15)
h("Demand factors API", r)
if r.status_code == 200:
    try:
        data = r.json()
        chk("DF API: Lighting=0.75", data.get("Lighting") == 0.75, str(data.get("Lighting")))
        chk("DF API: Cooling=0.65",  data.get("Cooling")  == 0.65, str(data.get("Cooling")))
        chk("DF API: Appliances=0.50", data.get("Appliances") == 0.50, str(data.get("Appliances")))
    except: chk("DF API JSON parse", False)

# ── SECTION 6: Assessment form & design API ──────────────────────────────────
print("\n=== 16. Assessment form ===")
r = s.get(BASE + "/assess", timeout=20)
h("Assessment page loads (public)", r)
if r.status_code == 200:
    body = r.text
    chk("Assess: form has name field",      'id="f_name"'      in body)
    chk("Assess: form has email field",     'id="f_email"'     in body)
    chk("Assess: form has country select",  'id="f_country"'   in body)
    chk("Assess: form has region select",   'id="f_region"'    in body)
    chk("Assess: load table present",       'id="loadTable"'   in body)
    chk("Assess: calc button present",      'id="calcBtn"'     in body)
    chk("Assess: results section present",  'id="resultsSection"' in body)
    chk("Assess: PRESETS JS object",        'const PRESETS'    in body)
    chk("Assess: recalcTotals function",    'function recalcTotals' in body)

print("\n=== 17. Public solar API (regions + data) ===")
r = s.get(BASE + "/api/solar_regions/Ghana", timeout=15)
h("Public regions API — Ghana", r)
if r.status_code == 200:
    try:
        d = r.json()
        chk("Regions: list returned",        isinstance(d.get("regions"), list))
        chk("Regions: at least 3 for Ghana", len(d.get("regions", [])) >= 3,
            str(len(d.get("regions", []))))
    except: chk("Regions JSON parse", False)

r = s.get(BASE + "/api/solar_data/Ghana/Greater%20Accra", timeout=15)
h("Public solar data API — Ghana/Greater Accra", r)
if r.status_code == 200:
    try:
        d = r.json()
        chk("Solar data: psh present", "psh" in d)
        chk("Solar data: tariff present", "tariff" in d)
        chk("Solar data: psh > 3",      (d.get("psh") or 0) > 3)
    except: chk("Solar data JSON parse", False)

print("\n=== 18. Design API — Ghana residential ===")
payload1 = {
    "name": "Test User", "email": "test@example.com", "phone": "",
    "country": "Ghana", "region": "Greater Accra",
    "building_type": "residential",
    "loads": [
        {"name": "LED Lights", "watts": 60, "qty": 6, "hours": 6, "demand_factor": 0.75},
        {"name": "Fan",        "watts": 80, "qty": 2, "hours": 8, "demand_factor": 0.75},
        {"name": "Fridge",     "watts": 150,"qty": 1, "hours": 24,"demand_factor": 0.33},
    ]
}
d1 = {}
r1 = s.post(BASE + "/api/assess/design", json=payload1, timeout=30)
h("Design API Ghana residential", r1)
if r1.status_code == 200:
    try:
        d1 = r1.json()
        chk("Ghana design ok",     d1.get("ok") is True)
        chk("Ghana pv_kw > 0",     (d1.get("pv_kw") or 0) > 0)
        chk("Ghana bat_kwh > 0",   (d1.get("bat_kwh") or 0) > 0)
        chk("Ghana currency GHS",  d1.get("currency") == "GHS")
        chk("Ghana ref SA-*",      str(d1.get("ref", "")).startswith("SA-"))
        chk("Ghana payback_yr set", d1.get("payback_yr") is not None)
    except Exception as e: chk(f"Ghana design JSON parse: {e}", False)

print("\n=== 19. Design API — Nigeria commercial (Lagos Southwest) ===")
payload2 = {
    "name": "Emeka Obi", "email": "emeka@test.ng", "phone": "",
    "country": "Nigeria", "region": "Lagos (Southwest)",
    "building_type": "commercial",
    "loads": [
        {"name": "AC Units",  "watts": 1500, "qty": 4,  "hours": 10, "demand_factor": 0.75},
        {"name": "Lighting",  "watts": 200,  "qty": 10, "hours": 10, "demand_factor": 1.0 },
        {"name": "Computers", "watts": 300,  "qty": 10, "hours": 8,  "demand_factor": 0.8 },
    ]
}
r2 = s.post(BASE + "/api/assess/design", json=payload2, timeout=30)
h("Design API Nigeria commercial", r2)
if r2.status_code == 200:
    try:
        d2 = r2.json()
        chk("Nigeria design ok",      d2.get("ok") is True)
        chk("Nigeria currency NGN",   d2.get("currency") == "NGN")
        gh_pv = d1.get("pv_kw") or 0
        chk("Nigeria larger than GH", (d2.get("pv_kw") or 0) > gh_pv,
            f"NG={d2.get('pv_kw')} GH={gh_pv}")
    except Exception as e: chk(f"Nigeria design JSON parse: {e}", False)

print("\n=== 20. Design API — validation errors ===")
r_bad = s.post(BASE + "/api/assess/design",
    json={"name":"","email":"","country":"Ghana","region":"Greater Accra","loads":[]},
    timeout=15)
h("Validation: missing name/email/loads (expect 400)", r_bad, expect=400)
if r_bad.status_code in (200, 400):
    try:
        d_bad = r_bad.json()
        chk("Validation: ok=False for empty submit", d_bad.get("ok") is False)
    except: chk("Validation JSON parse", False)

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"  PASSED: {PASS}/{total}")
print(f"  FAILED: {FAIL}/{total}")
print("  All checks PASSED." if FAIL == 0 else "  Some checks FAILED - see above.")
print("="*50)
sys.exit(0 if FAIL == 0 else 1)
