"""Live smoke test against solarpro.aiappinvent.com after the 2026-06-19
catalogue session. Exercises every piece this session shipped + the
critical 500 / 404 regressions.

Sections:
  A. Anonymous public pages
  B. Logged-in (marc667us) navigation
  C. Marketplace -> BOM / RFQ / Procurement flows (the lastrowid fix)
  D. Catalogue taxonomy verification (new categories visible live)
  E. BOQ Compliance Review panel
"""

import os
import urllib.request, urllib.parse, urllib.error, http.cookiejar, re, sys, json

BASE = "https://solarpro.aiappinvent.com"
USERNAME = "marc667us"
PASSWORD = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    mark = "OK " if cond else "XX "
    print(f"  {mark} {name}{(' -- ' + detail) if detail else ''}")
    return cond


def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def get(opener, path):
    try:
        r = opener.open(BASE + path, timeout=30)
        return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def post(opener, path, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, method="POST")
    try:
        r = opener.open(req, timeout=30)
        return r.status, r.read(), r.url
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.url


def csrf_from(body):
    m = re.search(rb'name="_csrf" value="([^"]+)"', body)
    return m.group(1).decode() if m else ""


def login(opener):
    _, body = get(opener, "/login")
    csrf = csrf_from(body)
    status, _, _ = post(opener, "/login", {"_csrf": csrf, "username": USERNAME, "password": PASSWORD})
    return status in (200, 302)


# ── A. Anonymous public ──────────────────────────────────────────────────
print("\n=== A. Anonymous public pages ===")
op = make_opener()
status, body = get(op, "/api/version")
data = json.loads(body)
check("version endpoint reports session HEAD", data.get("commit", "").startswith("86130a5"), data.get("commit", ""))

status, body = get(op, "/marketplace")
check("/marketplace returns 200 anonymously", status == 200, str(status))
check("Power System Equipment chip rendered", b"Power System Equipment" in body)
n_cat_headers = len(re.findall(rb'fw-black mb-0 me-2 text-warning', body))
check("category section headers >= 10", n_cat_headers >= 10, f"{n_cat_headers} headers")

# Power System Equipment category id is dynamic on Postgres (SERIAL).
# Discover it from the chip link in the landing page.
_, body = get(op, "/marketplace")
m = re.search(rb'href="/marketplace\?cat=(\d+)[^"]*"[^>]*>\s*<i[^>]+></i>\s*Power System Equipment', body)
ps_cat = m.group(1).decode() if m else ""
check("Power System Equipment chip carries a real cat id", bool(ps_cat), f"cat={ps_cat}")

status, body = get(op, f"/marketplace?cat={ps_cat}&sub=Generators")
check(f"subcategory drilldown ?cat={ps_cat}&sub=Generators -> 200", status == 200)
check("Cummins genset visible under Generators", b"Cummins" in body)

# Bare category filter (the % escape bug)
status, _ = get(op, f"/marketplace?cat={ps_cat}")
check(f"/marketplace?cat={ps_cat} (was IndexError) -> 200", status == 200)

status, body = get(op, "/marketplace/product/13")
check("/marketplace/product/13 (transformer) -> 200", status == 200)

# ── B. Logged-in nav ─────────────────────────────────────────────────────
print("\n=== B. Logged-in (marc667us) navigation ===")
op = make_opener()
ok = login(op)
check("login as marc667us", ok)

status, body = get(op, "/dashboard")
check("/dashboard -> 200", status == 200)

status, body = get(op, "/procurement-center")
check("/procurement-center -> 200", status == 200)
n_cat_headers = len(re.findall(rb'fw-black mb-0 me-2 text-warning', body))
check("procurement-center groups by category (>=10 headers)", n_cat_headers >= 10, f"{n_cat_headers}")

# ── C. /boms/None bug regression (the live 500 fix) ──────────────────────
print("\n=== C. Marketplace -> BOM / RFQ / Procurement (lastrowid fix) ===")
_, body = get(op, "/marketplace")
csrf = csrf_from(body)

# C1. POST /boms/add-product/<id> -- the bug that returned /boms/None -> 404.
# Pick a live product id that exists in production (1 is JinkoSolar PV module).
status, body, final_url = post(op, "/boms/add-product/1", {"_csrf": csrf})
# Expect redirect to /boms/<int> not /boms/None.
m = re.search(r"/boms/(\d+)$", final_url)
check("POST /boms/add-product/1 lands on /boms/<int>", bool(m), f"final URL: {final_url}")
if m:
    bom_id = int(m.group(1))
    status, body = get(op, f"/boms/{bom_id}")
    check(f"GET /boms/{bom_id} -> 200", status == 200)
    # C2. BOQ view -- the new compliance panel
    status, body = get(op, f"/boms/{bom_id}/boq")
    check(f"GET /boms/{bom_id}/boq -> 200", status == 200)
    check("BOQ has the Compliance Review panel", b"Compliance Review" in body)

# C3. /rfqs/new?product_id=13 -- form must render the seed line
status, body = get(op, "/rfqs/new?product_id=13")
check("GET /rfqs/new?product_id=13 -> 200", status == 200)

# C4. Procurement Center add -- creates a price sheet for product 1.
_, body = get(op, "/procurement-center")
csrf = csrf_from(body)
status, body, final_url = post(op, "/procurement-center/add", {
    "_csrf": csrf, "doc_type": "price_sheet", "currency": "GHS", "product_ids": "1",
})
m = re.search(r"/price-sheets/(\d+)$", final_url)
check("POST /procurement-center/add (price_sheet) -> /price-sheets/<int>",
      bool(m), f"final URL: {final_url}")

# C5. Same for bom -- different code path, same lastrowid risk.
_, body = get(op, "/procurement-center")
csrf = csrf_from(body)
status, body, final_url = post(op, "/procurement-center/add", {
    "_csrf": csrf, "doc_type": "bom", "currency": "GHS", "product_ids": "1",
})
m = re.search(r"/boms/(\d+)$", final_url)
check("POST /procurement-center/add (bom) -> /boms/<int>",
      bool(m), f"final URL: {final_url}")

# ── D. Catalogue verification ────────────────────────────────────────────
print("\n=== D. New taxonomy live ===")
status, body = get(op, "/marketplace")
for cat in [b"Power System Equipment", b"Voltage Regulators / AVR", b"Plastic Trunking",
            b"Steel Square Boxes", b"Earthing Materials"]:
    check(f"category visible: {cat.decode()}", cat in body)

# ── Summary ──────────────────────────────────────────────────────────────
print("\n=== SUMMARY ===")
n_pass = sum(1 for s, *_ in results if s == "PASS")
n_fail = sum(1 for s, *_ in results if s == "FAIL")
print(f"{n_pass}/{len(results)} passed")
for s, n, d in results:
    if s == "FAIL":
        print(f"  FAIL: {n}  ({d})")

sys.exit(0 if n_fail == 0 else 1)
