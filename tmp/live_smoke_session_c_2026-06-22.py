#!/usr/bin/env python3
"""Live smoke for session-C library expansion at solarpro.aiappinvent.com."""
from __future__ import annotations
import os, re, sys, requests

BASE = "https://solarpro.aiappinvent.com"
ADMIN_USER = "admin"
ADMIN_PW   = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or "marble-willow-poppy-river"
TIMEOUT = 30

OK, WARN, FAIL = "[+] PASS", "[~] WARN", "[-] FAIL"
results = []
def rec(name, status, detail=""):
    results.append((name, status))
    line = f"{status:9s} {name}"
    if detail: line += f" -- {detail[:140]}"
    print(line)

def get_csrf(html):
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""

# 1. Anon probes
print("\n=== 1. Anonymous routes ===")
s = requests.Session()
s.headers["User-Agent"] = "SolarPro-live-smoke-C/2026-06-22"
r = s.get(f"{BASE}/api/ping", timeout=TIMEOUT)
rec("/api/ping", OK if r.status_code == 200 else FAIL, r.text[:80])

# /marketplace — expanded products
r = s.get(f"{BASE}/marketplace", timeout=TIMEOUT)
# Total products text "Showing N of M products" or scan for product names
new_products = [
    "13A Twin Socket with USB",
    "10kW Hybrid Inverter",
    "550W Mono-PERC PV Module",
    "Copper-bonded Earth Rod 16mm x 3m",
    "32-channel NVR",
    "Lightning Air Terminal",
    "4MP IP Dome Camera (PoE)",
    "BMS DDC Controller",
    "PVC Trunking 50x50mm",
    "10mm² Cu PVC Cable",
]
n_hits = sum(1 for p in new_products if p in r.text)
rec(f"/marketplace new products visible",
    OK if n_hits >= 5 else WARN,
    f"{n_hits}/{len(new_products)} new product names found, page {len(r.content)//1024}KB")

# 2. Login
print("\n=== 2. Admin login ===")
r = s.get(f"{BASE}/login?legacy=1", timeout=TIMEOUT)
csrf = get_csrf(r.text)
r = s.post(f"{BASE}/login?legacy=1",
           data={"username": ADMIN_USER, "password": ADMIN_PW, "_csrf": csrf},
           timeout=TIMEOUT, allow_redirects=False)
login_ok = r.status_code in (302, 303) and "login" not in r.headers.get("Location", "").lower()
rec("login", OK if login_ok else FAIL, f"-> {r.headers.get('Location', '')[:80]}")
if not login_ok:
    print("\nSummary: aborting (login failed)")
    sys.exit(1)

# 3. Authed checks
print("\n=== 3. Admin-authenticated checks ===")
# Brands count
r = s.get(f"{BASE}/admin/marketplace/brands", timeout=TIMEOUT)
n_active = r.text.count('class="badge bg-success">Active</span>')
rec(f"/admin/marketplace/brands", OK if n_active >= 100 else WARN,
    f"{n_active} active brands (expect 130+)")

for expect in ("Marshall-Tufflex", "Gewiss", "Furse", "DEHN", "K2 Systems",
               "Hikvision", "Dahua", "Aruba", "Yealink", "ZKTeco",
               "Suprema", "Socomec", "Lapp", "Staubli", "Q CELLS",
               "Trina", "GoodWe", "Solis"):
    hit = expect in r.text
    rec(f"  brand '{expect}' in list", OK if hit else FAIL, "")

# Procurement suppliers — new Ghana additions
r = s.get(f"{BASE}/procurement/suppliers?page=1", timeout=TIMEOUT)
# Also need to walk pages since pagination is on
all_html = r.text
m = re.search(r"of\s+<strong[^>]*>(\d+)</strong>", r.text)
total_pages = int(m.group(1)) if m else 1
if total_pages > 1:
    for p in range(2, min(total_pages, 8) + 1):
        rr = s.get(f"{BASE}/procurement/suppliers?page={p}", timeout=TIMEOUT)
        all_html += rr.text

for sup in ("APT Ghana", "Compass Engineering Services", "Legrand Ghana",
            "Tricord Limited", "JMG Offshore Ghana", "Automation Ghana Group",
            "Electrical Supplies Ghana"):
    hit = sup in all_html
    rec(f"  new supplier '{sup}'", OK if hit else FAIL, "")

# Procurement catalog -- count products + sample new line items
r = s.get(f"{BASE}/procurement/catalog?page=1", timeout=TIMEOUT)
m = re.search(r"(\d+)\s+products?\s+total", r.text)
total_cat = int(m.group(1)) if m else 0
rec(f"/procurement/catalog total products",
    OK if total_cat >= 250 else WARN,
    f"{total_cat} products total (expect 300+)")

# BOQ template picker -- check master-reference-library card
# Need a BOQ project to view it. The picker URL requires pid/bid/fid.
# Just check the template module data via the template list helper isn't trivial,
# instead probe the template directly:
# (we'll create a project to walk into the picker)
csrf2 = get_csrf(s.get(f"{BASE}/boq-projects/new", timeout=TIMEOUT).text)
r = s.post(f"{BASE}/boq-projects/new", data={
    "_csrf": csrf2, "project_name": "LiveSmoke-C", "client_name": "Auto", "location": "Accra",
    "project_type": "single_building",
    "services": ["internal_electrical","fire_alarm","ip_cctv","bms","ip_pa","it_network",
                 "lightning_protection","earthing_bonding","nurse_call","power_supply_lighting"],
}, allow_redirects=False, timeout=TIMEOUT)
pid_m = re.search(r"/boq-projects/(\d+)", r.headers.get("Location", ""))
pid = int(pid_m.group(1)) if pid_m else 0
if pid:
    csrf3 = get_csrf(s.get(f"{BASE}/boq-projects/{pid}/buildings/new", timeout=TIMEOUT).text)
    r = s.post(f"{BASE}/boq-projects/{pid}/buildings/new", data={
        "_csrf": csrf3, "building_name": "Block A", "primary_purpose": "commercial",
        "purpose_subtype": "Office", "building_area": "800", "number_of_floors": "2",
    }, allow_redirects=False, timeout=TIMEOUT)
    bid_m = re.search(r"/buildings/(\d+)", r.headers.get("Location", ""))
    bid = int(bid_m.group(1)) if bid_m else 0
    if bid:
        # Find floor id from picker page
        r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}", timeout=TIMEOUT)
        fid_m = re.search(r"/floors/(\d+)", r.text)
        fid = int(fid_m.group(1)) if fid_m else 0
        if fid:
            r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}/floors/{fid}/from-template",
                      timeout=TIMEOUT)
            has_mr = "Master Reference Library" in r.text
            rec("BOQ template picker shows Master Reference Library",
                OK if has_mr else FAIL, "")
            # Try to load the master template view to count lines
            if has_mr:
                r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}/floors/{fid}/from-template/master-reference-library",
                          timeout=TIMEOUT)
                n_rows = r.text.count('class="boq-tpl-row"')
                rec(f"  master template renders rows",
                    OK if n_rows >= 100 else WARN,
                    f"{n_rows} row(s)")
                has_bills = sum(1 for b in (
                    "PRELIMINARIES","CONTAINMENT","WIRING AND CABLES","WIRING ACCESSORIES",
                    "LED LIGHTING","DISTRIBUTION BOARDS","MAIN EQUIPMENT","EARTHING",
                    "SOLAR PV","ICT","CCTV","BMS","TESTING") if b in r.text)
                rec(f"  master template bill banners",
                    OK if has_bills >= 11 else WARN,
                    f"{has_bills}/13 bill banners present")

# Online users
r = s.get(f"{BASE}/admin/api/online-users", timeout=TIMEOUT)
import json
d = json.loads(r.data if hasattr(r, "data") else r.content)
rec("/admin/api/online-users", OK if r.status_code == 200 else FAIL,
    f"count={d.get('count')}")

# Summary
print("\n=== SUMMARY ===")
n_ok = sum(1 for _, s_ in results if s_ == OK)
n_w  = sum(1 for _, s_ in results if s_ == WARN)
n_f  = sum(1 for _, s_ in results if s_ == FAIL)
print(f"PASS: {n_ok}   WARN: {n_w}   FAIL: {n_f}")
sys.exit(0 if n_f == 0 else 1)
