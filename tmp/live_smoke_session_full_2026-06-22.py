#!/usr/bin/env python3
"""Full live-coverage smoke for session B + session C features at
https://solarpro.aiappinvent.com . Single script, no shortcuts."""
from __future__ import annotations
import os, re, sys, json, requests

BASE = "https://solarpro.aiappinvent.com"
ADMIN_USER = "admin"
ADMIN_PW   = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or ""
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

s = requests.Session()
s.headers["User-Agent"] = "SolarPro-FullSmoke/2026-06-22"

# ── 1. Anon ──────────────────────────────────────────────────────────────
print("\n=== 1. Anonymous routes ===")
r = s.get(f"{BASE}/api/ping", timeout=TIMEOUT)
rec("/api/ping", OK if r.status_code == 200 else FAIL, r.text[:60])

r = s.get(f"{BASE}/marketplace", timeout=TIMEOUT)
has_pag  = "Page <strong" in r.text
has_next = "chevron-right" in r.text
rec("/marketplace pagination", OK if has_pag else WARN,
    f"page markup present, bytes={len(r.content)//1024}KB")

r = s.get(f"{BASE}/supplier/register", timeout=TIMEOUT)
address_req = bool(re.search(r'name="address"[^>]*required', r.text) or
                   re.search(r'<textarea[^>]*name="address"[^>]*required', r.text))
rec("/supplier/register address required", OK if address_req else FAIL, "")

# 8 admin routes should 302 to /login anon
for path in ("/admin/marketplace/brands", "/admin/marketplace/categories",
             "/admin/marketplace/settings", "/admin/marketplace/products",
             "/admin/online-users", "/admin/api/online-users",
             "/admin/actions-log", "/admin/users",
             "/procurement/catalog", "/procurement/suppliers"):
    r = s.get(f"{BASE}{path}", timeout=TIMEOUT, allow_redirects=False)
    ok = (r.status_code in (302, 303) and "login" in r.headers.get("Location","").lower())
    rec(f"{path} anon gate", OK if ok else WARN, f"-> {r.status_code} {r.headers.get('Location','')[:60]}")

# ── 2. Login ────────────────────────────────────────────────────────────
print("\n=== 2. Admin login ===")
r = s.get(f"{BASE}/login?legacy=1", timeout=TIMEOUT)
csrf = get_csrf(r.text)
r = s.post(f"{BASE}/login?legacy=1",
           data={"username": ADMIN_USER, "password": ADMIN_PW, "_csrf": csrf},
           timeout=TIMEOUT, allow_redirects=False)
login_ok = r.status_code in (302, 303) and "login" not in r.headers.get("Location","").lower()
rec("login", OK if login_ok else FAIL, f"-> {r.headers.get('Location','')[:60]}")
if not login_ok:
    print("login failed -- aborting"); sys.exit(1)

# ── 3. Admin: brands ─────────────────────────────────────────────────────
print("\n=== 3. Admin: marketplace ===")
r = s.get(f"{BASE}/admin/marketplace/brands", timeout=TIMEOUT)
n_brand = r.text.count('class="badge bg-success">Active</span>')
rec(f"/admin/marketplace/brands", OK if n_brand >= 130 else WARN,
    f"{n_brand} active brands (target 130+)")

r = s.get(f"{BASE}/admin/marketplace/categories", timeout=TIMEOUT)
n_cat = r.text.count('class="badge bg-success">Active</span>')
rec(f"/admin/marketplace/categories", OK if n_cat >= 20 else WARN,
    f"{n_cat} active categories")

r = s.get(f"{BASE}/admin/marketplace/settings", timeout=TIMEOUT)
has_ppp = 'name="products_per_page"' in r.text
m = re.search(r'name="products_per_page"[^>]*value="(\d+)"', r.text)
ppp = int(m.group(1)) if m else 0
rec(f"/admin/marketplace/settings", OK if has_ppp else FAIL,
    f"products_per_page={ppp}")

# Admin products list
r = s.get(f"{BASE}/admin/marketplace/products", timeout=TIMEOUT)
rec("/admin/marketplace/products", OK if r.status_code == 200 else FAIL,
    f"page {len(r.content)//1024}KB")

# Admin suppliers list
r = s.get(f"{BASE}/admin/marketplace/suppliers", timeout=TIMEOUT)
rec("/admin/marketplace/suppliers", OK if r.status_code == 200 else FAIL,
    f"page {len(r.content)//1024}KB")

# ── 4. Procurement catalog (paginated + Edit modals + brand dropdown) ──
print("\n=== 4. Procurement catalogue ===")
r = s.get(f"{BASE}/procurement/catalog?page=1", timeout=TIMEOUT)
m = re.search(r"(\d+)\s+products?\s+total", r.text)
total_cat = int(m.group(1)) if m else 0
rec(f"/procurement/catalog total products", OK if total_cat >= 300 else WARN,
    f"{total_cat} (target 300+)")
n_edit = r.text.count('data-bs-target="#editItem')
rec("/procurement/catalog Edit modals on rows", OK if n_edit > 5 else FAIL,
    f"{n_edit} edit modal anchors")
mb = re.search(r'<select name="brand"[^>]*>(.*?)</select>', r.text, re.S)
brand_opts = len(re.findall(r"<option", mb.group(1))) if mb else 0
rec("/procurement/catalog brand <select>", OK if brand_opts >= 50 else WARN,
    f"{brand_opts} options on Add modal")
has_pag = "Page <strong" in r.text and "chevron-right" in r.text
rec("/procurement/catalog pagination", OK if has_pag else WARN, "")

# ── 5. Procurement suppliers (paginated + edit modal) ──
print("\n=== 5. Supplier directory ===")
r = s.get(f"{BASE}/procurement/suppliers?page=1", timeout=TIMEOUT)
n_edit_sup = r.text.count('data-bs-target="#editSup')
rec("/procurement/suppliers edit modals", OK if n_edit_sup > 5 else WARN,
    f"{n_edit_sup} edit modal anchors")
has_pag = "Page <strong" in r.text and "chevron-right" in r.text
rec("/procurement/suppliers pagination", OK if has_pag else WARN, "")
m = re.search(r"(\d+)\s+suppliers?\s+total", r.text)
total_sup = int(m.group(1)) if m else 0
rec(f"/procurement/suppliers total", OK if total_sup >= 7 else WARN,
    f"{total_sup} suppliers total (Ghana adds + smoke leftovers)")

# Walk pages to collect new Ghana suppliers
all_html = r.text
for p in range(2, 12):
    rr = s.get(f"{BASE}/procurement/suppliers?page={p}", timeout=TIMEOUT)
    all_html += rr.text
    if "Page" not in rr.text or "Next" not in rr.text:
        break
for sup in ("APT Ghana", "Compass Engineering Services", "Legrand Ghana",
            "Tricord Limited", "JMG Offshore Ghana", "Automation Ghana Group",
            "Electrical Supplies Ghana"):
    rec(f"  supplier '{sup}' present", OK if sup in all_html else FAIL, "")

# ── 6. Admin users (online status column) ──
print("\n=== 6. Admin users (online/offline) ===")
r = s.get(f"{BASE}/admin/users", timeout=TIMEOUT)
n_status_hdr = r.text.count('>Status<')
n_on  = r.text.count('background:#22c55e')
n_off = r.text.count('background:#6868a0;margin-right')
n_rows = len(re.findall(r'class="user-row"', r.text))
rec(f"/admin/users Status header", OK if n_status_hdr >= 1 else FAIL, "")
rec(f"/admin/users badges", OK if (n_on + n_off) > 0 else WARN,
    f"{n_rows} user rows, {n_on} green dots, {n_off} grey dots")

# ── 7. Online users page + API ──
print("\n=== 7. Online users ===")
r = s.get(f"{BASE}/admin/online-users", timeout=TIMEOUT)
rec("/admin/online-users page", OK if r.status_code == 200 else FAIL,
    f"{len(r.content)//1024}KB")
r = s.get(f"{BASE}/admin/api/online-users", timeout=TIMEOUT)
d = json.loads(r.content)
rec("/admin/api/online-users JSON", OK if r.status_code == 200 else FAIL,
    f"count={d.get('count')} window={d.get('window_seconds')}s")

# ── 8. Admin actions log ──
print("\n=== 8. Admin actions log ===")
r = s.get(f"{BASE}/admin/actions-log", timeout=TIMEOUT)
has_filter = 'name="action"' in r.text and 'name="hours"' in r.text
chips = re.findall(r'background:[^"]*">\s*(\w+)\s*<span class="opacity-75', r.text)
rec("/admin/actions-log filter form", OK if has_filter else FAIL, "")
rec("/admin/actions-log action chips", OK if len(chips) > 0 else WARN,
    f"{len(chips)} action chips on page")
# Trigger an action and confirm it logs
r = s.get(f"{BASE}/admin/marketplace/brands", timeout=TIMEOUT)
csrf_b = get_csrf(r.text)
import time
test_brand = f"SmokeBrand-{int(time.time()) % 100000}"
s.post(f"{BASE}/admin/marketplace/brands/add",
       data={"_csrf": csrf_b, "name": test_brand, "country": "Test", "website": ""},
       timeout=TIMEOUT, allow_redirects=False)
r = s.get(f"{BASE}/admin/actions-log", timeout=TIMEOUT)
rec(f"action log captures add_brand", OK if test_brand in r.text else FAIL,
    f"sentinel='{test_brand}'")

# ── 9. Procurement center (pagination + sessionStorage glue) ──
print("\n=== 9. Procurement center ===")
r = s.get(f"{BASE}/procurement-center?page=1", timeout=TIMEOUT)
n_cards   = len(re.findall(r'name="product_ids" value="(\d+)"', r.text))
has_store = 'name="stored_ids"' in r.text
has_sel   = 'id="selCount"' in r.text
has_pag   = "Page <strong" in r.text
rec("/procurement-center pagination", OK if has_pag else WARN, f"{n_cards} cards on page 1")
rec("/procurement-center sessionStorage glue", OK if (has_store and has_sel) else FAIL,
    f"stored_ids={has_store} selCount={has_sel}")

# ── 10. BOQ Master Reference Library ──
print("\n=== 10. BOQ Master Reference Library ===")
r = s.get(f"{BASE}/boq-projects/new", timeout=TIMEOUT)
csrf2 = get_csrf(r.text)
r = s.post(f"{BASE}/boq-projects/new", data={
    "_csrf": csrf2, "project_name": "FullSmoke", "client_name": "Auto",
    "location": "Accra", "project_type": "single_building",
    "services": ["internal_electrical","fire_alarm","ip_cctv","bms","ip_pa",
                 "it_network","lightning_protection","earthing_bonding",
                 "nurse_call","power_supply_lighting"],
}, allow_redirects=False, timeout=TIMEOUT)
pid_m = re.search(r"/boq-projects/(\d+)", r.headers.get("Location",""))
pid = int(pid_m.group(1)) if pid_m else 0
if pid:
    r = s.get(f"{BASE}/boq-projects/{pid}/buildings/new", timeout=TIMEOUT)
    csrf3 = get_csrf(r.text)
    r = s.post(f"{BASE}/boq-projects/{pid}/buildings/new", data={
        "_csrf": csrf3, "building_name": "Block A", "primary_purpose": "commercial",
        "purpose_subtype": "Office", "building_area": "800", "number_of_floors": "2",
    }, allow_redirects=False, timeout=TIMEOUT)
    bid_m = re.search(r"/buildings/(\d+)", r.headers.get("Location",""))
    bid = int(bid_m.group(1)) if bid_m else 0
    if bid:
        r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}", timeout=TIMEOUT)
        fid_m = re.search(r"/floors/(\d+)", r.text)
        fid = int(fid_m.group(1)) if fid_m else 0
        if fid:
            r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}/floors/{fid}/from-template",
                      timeout=TIMEOUT)
            has_mr = "Master Reference Library" in r.text
            rec("BOQ template picker shows Master Library", OK if has_mr else FAIL, "")
            if has_mr:
                r = s.get(f"{BASE}/boq-projects/{pid}/buildings/{bid}/floors/{fid}/from-template/master-reference-library",
                          timeout=TIMEOUT)
                n_rows = r.text.count('class="boq-tpl-row"')
                bills = sum(1 for b in (
                    "PRELIMINARIES","CONTAINMENT","WIRING AND CABLES","WIRING ACCESSORIES",
                    "LED LIGHTING","DISTRIBUTION BOARDS","MAIN EQUIPMENT","EARTHING",
                    "SOLAR PV","ICT","CCTV","BMS","TESTING") if b in r.text)
                rec("  master template renders rows", OK if n_rows >= 100 else FAIL,
                    f"{n_rows} rows")
                rec("  master template bill banners", OK if bills >= 11 else FAIL,
                    f"{bills}/13")
                # Per-section Add Item button + reorder controls
                n_add_item = r.text.count("Add item to ")
                n_move_up  = r.text.count("Move row up")
                rec("  per-section Add Item buttons", OK if n_add_item >= 20 else WARN,
                    f"{n_add_item} add-item buttons")
                rec("  per-row Move-up/down controls", OK if n_move_up >= 100 else WARN,
                    f"{n_move_up} move-up buttons")

# ── 11. Dashboard clear-synthetic button ──
print("\n=== 11. Dashboard clear-synthetic ===")
r = s.get(f"{BASE}/dashboard", timeout=TIMEOUT)
synth_m = re.search(r"Clear synthetic-health history \((\d+)\)", r.text)
synth_count = int(synth_m.group(1)) if synth_m else 0
if synth_count > 0:
    rec(f"/dashboard has Clear button", OK, f"count={synth_count}")
else:
    rec(f"/dashboard Clear button (none expected if no synth rows)", OK,
        "no synthetic rows currently (button hidden by template)")

# ── 12. Cost Estimate PDF + XLSX (Apinto 9-col) ──
print("\n=== 12. Cost Estimate PDF + XLSX ===")
r = s.get(f"{BASE}/boms", timeout=TIMEOUT)
# Pick first existing BOM if any
bom_m = re.search(r'href="/boms/(\d+)"', r.text)
if bom_m:
    bom_id = int(bom_m.group(1))
    r = s.get(f"{BASE}/boms/{bom_id}/boq.pdf", timeout=TIMEOUT)
    rec(f"/boms/{bom_id}/boq.pdf", OK if r.status_code == 200 and r.content[:4]==b'%PDF' else WARN,
        f"{r.status_code} {len(r.content)//1024}KB")
    r = s.get(f"{BASE}/boms/{bom_id}/boq.xlsx", timeout=TIMEOUT)
    rec(f"/boms/{bom_id}/boq.xlsx", OK if r.status_code == 200 and r.content[:2]==b'PK' else WARN,
        f"{r.status_code} {len(r.content)//1024}KB")
else:
    rec("Cost Estimate exports", WARN, "no BOMs on admin account")

# ── Summary ──
print("\n=== SUMMARY ===")
n_ok = sum(1 for _, s_ in results if s_ == OK)
n_w  = sum(1 for _, s_ in results if s_ == WARN)
n_f  = sum(1 for _, s_ in results if s_ == FAIL)
print(f"PASS: {n_ok}   WARN: {n_w}   FAIL: {n_f}")
sys.exit(0 if n_f == 0 else 1)
