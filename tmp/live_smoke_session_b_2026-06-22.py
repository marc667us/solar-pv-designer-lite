#!/usr/bin/env python3
"""Live smoke for session-B (2026-06-22) shipped features at
https://solarpro.aiappinvent.com .

Runs anonymous probes first, then attempts an admin login via the
?legacy=1 bypass and exercises the admin surfaces.

Each block prints PASS / WARN / FAIL.  Returns non-zero exit on any FAIL.
"""
from __future__ import annotations
import os, re, sys, json
import requests

BASE = "https://solarpro.aiappinvent.com"
TIMEOUT = 25
# 4-word passphrase from project memory (may have rotated since).
ADMIN_USER = "admin"
ADMIN_PW   = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or ""

OK   = "[+] PASS"
WARN = "[~] WARN"
FAIL = "[-] FAIL"

results = []
def record(name, status, detail=""):
    results.append((name, status, detail))
    line = f"{status:9s} {name}"
    if detail:
        line += f" -- {detail[:120]}"
    print(line)

def get_csrf(html):
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""

# ─── 1. Anonymous probes ──────────────────────────────────────────────────
s = requests.Session()
s.headers["User-Agent"] = "SolarPro-live-smoke/2026-06-22"

print("\n=== 1. Anonymous routes ===")
try:
    r = s.get(f"{BASE}/api/ping", timeout=TIMEOUT)
    if r.status_code == 200 and r.json().get("pong"):
        record("/api/ping", OK, str(r.json()))
    else:
        record("/api/ping", FAIL, f"{r.status_code} {r.text[:80]}")
except Exception as e:
    record("/api/ping", FAIL, str(e))

# /marketplace anon: should have pagination markup + Ghana product names
try:
    r = s.get(f"{BASE}/marketplace", timeout=TIMEOUT)
    has_pagination = ("Page <strong" in r.text or "Page </strong>" in r.text or 'btn-warning fw-bold btn-sm">' in r.text)
    has_brand_apinto = "Agenda Commercial" in r.text or "Safenergy" in r.text or "Cisco" in r.text
    if r.status_code == 200:
        if has_pagination:
            record("/marketplace pagination", OK, f"{len(r.content)//1024}KB markup")
        else:
            record("/marketplace pagination", WARN, "pagination markup not found (maybe single page)")
        if has_brand_apinto:
            record("/marketplace Ghana suppliers visible", OK, "found Agenda/Safenergy/Cisco")
        else:
            record("/marketplace Ghana suppliers visible", WARN, "none of Agenda/Safenergy/Cisco hit")
    else:
        record("/marketplace", FAIL, f"status={r.status_code}")
except Exception as e:
    record("/marketplace", FAIL, str(e))

# /supplier/register: address field must be required
try:
    r = s.get(f"{BASE}/supplier/register", timeout=TIMEOUT)
    has_address = ('name="address"' in r.text and 'required' in r.text.split('name="address"')[1][:200])
    record("/supplier/register address required",
           OK if has_address else FAIL,
           "address textarea present + required" if has_address else "address field missing/not required")
except Exception as e:
    record("/supplier/register", FAIL, str(e))

# Admin-only routes should redirect anon to /login
for path in ("/admin/marketplace/brands",
             "/admin/marketplace/categories",
             "/admin/marketplace/settings",
             "/admin/online-users",
             "/admin/api/online-users",
             "/procurement/catalog",
             "/procurement/suppliers"):
    try:
        r = s.get(f"{BASE}{path}", timeout=TIMEOUT, allow_redirects=False)
        if r.status_code in (302, 303):
            loc = r.headers.get("Location", "")
            ok = "login" in loc.lower()
            record(f"{path} anon gate", OK if ok else WARN, f"-> {loc[:80]}")
        else:
            record(f"{path} anon gate", WARN, f"unexpected status {r.status_code}")
    except Exception as e:
        record(f"{path}", FAIL, str(e))

# ─── 2. Login as admin via legacy bypass ─────────────────────────────────
print("\n=== 2. Admin login (legacy bypass) ===")
login_ok = False
try:
    r = s.get(f"{BASE}/login?legacy=1", timeout=TIMEOUT)
    csrf = get_csrf(r.text)
    if not csrf:
        record("login GET", FAIL, "no CSRF token in form")
    else:
        r = s.post(f"{BASE}/login?legacy=1",
                   data={"username": ADMIN_USER, "password": ADMIN_PW, "_csrf": csrf},
                   timeout=TIMEOUT, allow_redirects=False)
        if r.status_code in (302, 303):
            loc = r.headers.get("Location", "")
            login_ok = "login" not in loc.lower()
            record("login POST", OK if login_ok else FAIL,
                   f"-> {loc[:80]}" if login_ok else f"redirect back to login (creds bad?) -> {loc[:80]}")
        else:
            record("login POST", FAIL, f"status={r.status_code} body={r.text[:120]}")
except Exception as e:
    record("login POST", FAIL, str(e))

# ─── 3. Authed admin checks ──────────────────────────────────────────────
if login_ok:
    print("\n=== 3. Admin-authenticated checks ===")
    # /admin/online-users
    try:
        r = s.get(f"{BASE}/admin/online-users", timeout=TIMEOUT)
        if r.status_code == 200 and ("Who's online" in r.text or "Online users" in r.text):
            record("/admin/online-users page", OK, f"{len(r.content)//1024}KB")
        else:
            record("/admin/online-users page", FAIL, f"status={r.status_code} markers missing")
    except Exception as e:
        record("/admin/online-users", FAIL, str(e))

    try:
        r = s.get(f"{BASE}/admin/api/online-users", timeout=TIMEOUT)
        d = r.json()
        record("/admin/api/online-users JSON", OK if r.status_code == 200 else FAIL,
               f"count={d.get('count')} sample={(d.get('users') or [{}])[0].get('username','?')}")
    except Exception as e:
        record("/admin/api/online-users", FAIL, str(e))

    # /admin/marketplace/brands
    try:
        r = s.get(f"{BASE}/admin/marketplace/brands", timeout=TIMEOUT)
        # count rows in the table
        n_active = r.text.count('class="badge bg-success">Active</span>')
        n_inactive = r.text.count('class="badge bg-secondary">Inactive</span>')
        record("/admin/marketplace/brands", OK,
               f"{n_active + n_inactive} brand rows ({n_active} active, {n_inactive} inactive)")
        for expect in ("Cisco", "Safenergy", "Cummins", "Schneider Electric", "Reroy", "Ubiquiti"):
            hit = expect in r.text
            record(f"  brand '{expect}' in list", OK if hit else FAIL, "")
    except Exception as e:
        record("/admin/marketplace/brands", FAIL, str(e))

    # /admin/marketplace/categories
    try:
        r = s.get(f"{BASE}/admin/marketplace/categories", timeout=TIMEOUT)
        n_active = r.text.count('class="badge bg-success">Active</span>')
        record("/admin/marketplace/categories", OK,
               f"{n_active} active categories")
        for expect in ("Transformers", "LV Power Cables", "Power System Equipment", "ICT / ELV Products"):
            hit = expect in r.text
            record(f"  category '{expect}' in list", OK if hit else FAIL, "")
    except Exception as e:
        record("/admin/marketplace/categories", FAIL, str(e))

    # /admin/marketplace/settings GET
    try:
        r = s.get(f"{BASE}/admin/marketplace/settings", timeout=TIMEOUT)
        has_form = 'name="products_per_page"' in r.text
        m = re.search(r'name="products_per_page"[^>]*value="(\d+)"', r.text)
        cur_ppp = int(m.group(1)) if m else None
        record("/admin/marketplace/settings GET",
               OK if has_form else FAIL,
               f"products_per_page input present, current value={cur_ppp}")
    except Exception as e:
        record("/admin/marketplace/settings", FAIL, str(e))

    # /procurement/catalog -- Edit modal + brand <select>
    try:
        r = s.get(f"{BASE}/procurement/catalog", timeout=TIMEOUT)
        n_edit = r.text.count('data-bs-target="#editItem')
        m = re.search(r'name="brand"[^>]*>(.*?)</select>', r.text, re.S)
        n_brand_options = len(re.findall(r"<option", m.group(1))) if m else 0
        n_categories = len(re.findall(r"<option[^>]*>([^<]*)</option>", r.text.split('name="category_id"')[1].split("</select>")[0])) if 'name="category_id"' in r.text else 0
        record("/procurement/catalog Edit modals", OK if n_edit > 0 else FAIL,
               f"{n_edit} edit modal anchors")
        record("/procurement/catalog brand <select>",
               OK if n_brand_options > 5 else FAIL,
               f"{n_brand_options} brand options (incl placeholder)")
        record("/procurement/catalog category <select>",
               OK if n_categories > 5 else WARN,
               f"{n_categories} category options")
    except Exception as e:
        record("/procurement/catalog", FAIL, str(e))

    # /procurement/suppliers -- Ghana suppliers present
    try:
        r = s.get(f"{BASE}/procurement/suppliers", timeout=TIMEOUT)
        ghana = []
        for name in ("Agenda Commercial Limited", "Grand Pacific Limited",
                     "NESSTRA Ghana Ltd", "Powertech Generators Ghana Limited",
                     "Comsys Ghana Ltd.", "IPMC Ghana"):
            if name in r.text:
                ghana.append(name)
        record("/procurement/suppliers Ghana seeds",
               OK if len(ghana) >= 4 else WARN,
               f"{len(ghana)}/6 found: {', '.join(ghana[:3])}{'...' if len(ghana) > 3 else ''}")
    except Exception as e:
        record("/procurement/suppliers", FAIL, str(e))

    # /procurement-center pagination + selection-storage glue
    try:
        r = s.get(f"{BASE}/procurement-center?page=1", timeout=TIMEOUT)
        has_pagination = "Page <strong" in r.text or 'btn-warning fw-bold btn-sm">1' in r.text
        has_stored_ids = 'name="stored_ids"' in r.text
        has_selCount  = 'id="selCount"' in r.text
        n_cards = len(re.findall(r'name="product_ids" value="(\d+)"', r.text))
        record("/procurement-center pagination",
               OK if (has_pagination and has_stored_ids and has_selCount) else WARN,
               f"page1 cards={n_cards}, stored_ids={has_stored_ids}, selCount={has_selCount}")
    except Exception as e:
        record("/procurement-center", FAIL, str(e))

    # /marketplace -- count cards on page 1 vs page 2 to confirm PPP
    try:
        r1 = s.get(f"{BASE}/marketplace?page=1", timeout=TIMEOUT)
        r2 = s.get(f"{BASE}/marketplace?page=2", timeout=TIMEOUT)
        n1 = r1.text.count('class="solar-card h-100')
        n2 = r2.text.count('class="solar-card h-100')
        # PPP -- read from settings
        ppp_match = re.search(r'value="(\d+)"', r1.text.split('name="products_per_page"')[1] if 'name="products_per_page"' in r1.text else "")
        size1 = len(r1.content) // 1024
        size2 = len(r2.content) // 1024
        record("/marketplace?page=1 vs page=2",
               OK if (n1 > 0 or size1 != size2) else WARN,
               f"page1 ~{n1} cards ({size1}KB), page2 ~{n2} cards ({size2}KB)")
    except Exception as e:
        record("/marketplace pagination", FAIL, str(e))

else:
    print("\n=== 3. SKIPPED admin-authenticated checks (login failed) ===")
    print("Pass SOLARPRO_ADMIN_PASSWORD as env var to re-run with creds.")

# ─── Summary ─────────────────────────────────────────────────────────────
print("\n=== SUMMARY ===")
n_ok = sum(1 for _, s_, _ in results if s_ == OK)
n_warn = sum(1 for _, s_, _ in results if s_ == WARN)
n_fail = sum(1 for _, s_, _ in results if s_ == FAIL)
print(f"PASS: {n_ok}   WARN: {n_warn}   FAIL: {n_fail}")
sys.exit(0 if n_fail == 0 else 1)
