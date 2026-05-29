import requests, re, sys, time

BASE = "https://solarpro.aiappinvent.com"
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

def chk(label, r, expect_pdf=False):
    ok = r.status_code == 200
    if expect_pdf:
        ok = ok and (r.headers.get("Content-Type","").startswith("application/pdf") or len(r.content) > 2000)
    sym = "OK  " if ok else "FAIL"
    print(f"  {sym} [{r.status_code}] {label}")
    return ok

# Login
s.get(BASE + "/", timeout=60)
r = post(BASE + "/login", {"username": "admin", "password": "SolarAdmin2026!"})
print("Login:", r.status_code, r.url)

# Create project
r = post(BASE + "/project/new", {"name": f"ReportTest-{int(time.time())%10000}", "client_name": "Test"})
pid = extract_pid(r.url)
print(f"Project: {pid}")

# Setup location
loc = {"country":"Ghana","region":"Greater Accra","tariff":"1.9688","currency":"GHS","symbol":"GHS",
       "funding_mode":"cash","chemistry":"LiFePO4","autonomy":"1","voltage":"48","panel_wp":"400",
       "system_type":"off-grid","phase":"single","tilt_angle":"15","azimuth":"0",
       "system_losses":"14","inverter_eff":"95","battery_dod":"80","performance_ratio":"75",
       "supply_markup_pct":"8","install_rate_pct":"15"}
r = post(BASE + f"/project/{pid}/location", loc)
r = post(BASE + f"/project/{pid}/loads", {
    "load_name[]":["LED Lights","Fan","Fridge"],
    "load_watt[]":["10","75","150"],"load_qty[]":["4","1","1"],
    "load_hours[]":["6","8","24"],"load_cat[]":["Lighting","Cooling","Appliances"],
    "load_df[]":["75","65","50"]})
r = s.get(BASE + f"/project/{pid}/results", timeout=30)
print(f"Results: {r.status_code}")
print()

print("=== Report Pages ===")
pages = [
    ("PV Report",       f"/project/{pid}/report/pv"),
    ("BOQ Report",      f"/project/{pid}/report/boq"),
    ("Cable Report",    f"/project/{pid}/report/cable"),
    ("Economic Report", f"/project/{pid}/report/economic"),
    ("Energy Report",   f"/project/{pid}/report/energy"),
    ("Installation",    f"/project/{pid}/report/installation"),
    ("Inspection",      f"/project/{pid}/report/inspection"),
    ("Proposal",        f"/project/{pid}/report/proposal"),
    ("Procurement",     f"/project/{pid}/procurement"),
]
for label, path in pages:
    r = s.get(BASE + path, timeout=30)
    chk(label, r)

print()
print("=== PDF Exports ===")
pdfs = [
    ("PV PDF",           f"/project/{pid}/report/pv/pdf"),
    ("BOQ PDF",          f"/project/{pid}/report/boq/pdf"),
    ("Cable PDF",        f"/project/{pid}/report/cable/pdf"),
    ("Economic PDF",     f"/project/{pid}/report/economic/pdf"),
    ("Energy PDF",       f"/project/{pid}/report/energy/pdf"),
    ("Installation PDF", f"/project/{pid}/report/installation/pdf"),
    ("Workplan PDF",     f"/project/{pid}/report/workplan/pdf"),
    ("Staffing PDF",     f"/project/{pid}/report/staffing/pdf"),
    ("Inspection PDF",   f"/project/{pid}/report/inspection/pdf"),
    ("Procurement PDF",  f"/project/{pid}/procurement/pdf"),
    ("Proposal PDF",     f"/project/{pid}/report/proposal/pdf"),
]
for label, path in pdfs:
    r = s.get(BASE + path, timeout=60)
    chk(label, r, expect_pdf=True)

print()
print("=== Email Page ===")
r = s.get(BASE + f"/project/{pid}/email", timeout=20)
chk("Email page", r)
count = r.text.count("export_pdf")
print(f"  PDF links on email page: {count} (expect 11+)")

print()
print("Done")
