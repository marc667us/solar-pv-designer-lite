import os, requests, re, sys, time

BASE     = os.environ.get("SOLARPRO_BASE", "https://solarpro.aiappinvent.com")
ADMIN_PW = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "")
if not ADMIN_PW:
    sys.exit("Set SOLARPRO_ADMIN_PASSWORD env var (admin login passphrase).")
s = requests.Session()

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

def safe(text, n=800):
    return text.encode('ascii','replace').decode('ascii')[:n]

# Login
print("Waking site...")
s.get(BASE + "/", timeout=60)
r = post(BASE + "/login", {"username": "admin", "password": ADMIN_PW})
print("Login:", r.status_code, r.url)
if "dashboard" not in r.url and "project" not in r.url:
    print("Login FAILED:", safe(r.text))
    sys.exit(1)

# Create project
TS = str(int(time.time()))[-5:]
r = post(BASE + "/project/new", {"name": f"ProcTest-{TS}", "client_name": "Test Client"})
pid = extract_pid(r.url)
print(f"Project ID: {pid}  URL: {r.url}")

# Location (with default BOQ rates)
loc = {
    "country": "Ghana", "region": "Greater Accra",
    "latitude": "5.6037", "longitude": "-0.187",
    "tariff_per_kwh": "1.9688", "tariff": "1.9688",
    "currency": "GHS", "symbol": "GHS",
    "funding_mode": "cash", "battery_chemistry": "LiFePO4", "chemistry": "LiFePO4",
    "peak_sun_hours": "5.5", "autonomy_days": "1", "autonomy": "1",
    "cost_usd_kwp": "750", "fx_usd_to_local": "15.5", "voltage": "48",
    "panel_wp": "400", "system_type": "off-grid", "phase": "single",
    "tilt_angle": "15", "azimuth": "0", "system_losses": "14",
    "inverter_eff": "95", "battery_dod": "80", "performance_ratio": "75",
    "supply_markup_pct": "8", "install_rate_pct": "15",
}
r = post(BASE + f"/project/{pid}/location", loc)
print("Location:", r.status_code, r.url)

# Loads
loads = {
    "load_name[]": ["LED Lights", "Fan", "Fridge"],
    "load_watt[]": ["10", "75", "150"],
    "load_qty[]":  ["4", "1", "1"],
    "load_hours[]": ["6", "8", "24"],
    "load_cat[]":  ["Lighting", "Cooling", "Appliances"],
    "load_df[]":   ["75", "65", "50"],
}
r = post(BASE + f"/project/{pid}/loads", loads)
print("Loads:", r.status_code, r.url)

# Results
r2 = s.get(BASE + f"/project/{pid}/results", timeout=30)
print("Results:", r2.status_code)

# Procurement
print(f"\nProcurement for project {pid}...")
r3 = s.get(BASE + f"/project/{pid}/procurement", timeout=30)
print("Procurement status:", r3.status_code)
if r3.status_code == 200:
    print("SUCCESS")
    print("Page length:", len(r3.text))
else:
    print("FAIL")
    # Save full response to file
    with open("proc_response.txt", "w", encoding="utf-8", errors="replace") as f:
        f.write(r3.text)
    print("Full response saved to proc_response.txt")
    # Print ASCII-safe snippet
    print(safe(r3.text, 1200))
