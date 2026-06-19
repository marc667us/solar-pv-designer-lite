"""
Broad probe — visit every authenticated page in the app (admin login) and
flag any 4xx / 5xx that aren't the expected "anon -> 302 login" pattern.

Goal: hunt the user's "still 500 and 404" complaint by enumerating every
@app.route that's safe to hit anonymously or as admin.

Excludes destructive POSTs.
"""
import os, sys, re, requests
from dotenv import load_dotenv
load_dotenv()

BASE = os.environ.get("BASE", "http://localhost:5000")
ADMIN = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("no admin password")

# Curated list — only GET routes, parametric routes filled with id=1 or
# safe defaults so we can hit them. Trailing comments describe the page.
ROUTES = [
    "/",
    "/dashboard",
    "/marketplace",
    "/marketplace?currency=GHS",
    "/marketplace?currency=USD",
    "/marketplace?cat=1",
    "/procurement-center",
    "/procurement-center?currency=USD",
    "/price-sheets",
    "/rfqs",
    "/rfqs/new",
    "/boms",
    "/boms/new",
    "/admin",
    "/admin/marketplace",
    "/admin/marketplace/pending",
    "/admin/marketplace/suppliers",
    "/admin/marketplace/products",
    "/admin/marketplace/staff",
    "/admin/installers",
    "/admin/users",
    "/admin/operations",
    "/admin/logs",
    "/installation-support",
    "/me",
    "/me/referrals",
    "/myproject",
    "/upgrade",
    "/forgot-password",
    "/terms",
    "/privacy",
    "/about",
    "/contact",
    "/installer/register",
    "/supplier/register",
    "/api/version",
    "/api/health",
    "/api/health/database",
    "/api/health/storage",
    "/api/ping",
]

s = requests.Session()
g = s.get(f"{BASE}/login", timeout=20)
csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', g.text)
csrf = csrf.group(1) if csrf else ""
r = s.post(f"{BASE}/login",
           data={"username": ADMIN, "password": PASS, "_csrf": csrf},
           allow_redirects=False, timeout=20)
assert r.status_code == 302, f"admin login failed on {BASE}: {r.status_code}"
print(f"[login OK] target={BASE}\n")

fails = []
for path in ROUTES:
    try:
        r = s.get(BASE + path, allow_redirects=False, timeout=20)
        st = r.status_code
        # 302 to /login means the route requires login and we are NOT
        # logged in there — shouldn't happen since we just logged in.
        # 302 to anywhere else is a normal redirect (e.g. /admin -> /dashboard).
        loc = r.headers.get("Location", "")
        flag = "PASS" if (200 <= st < 400 or st == 405) else "FAIL"
        if flag == "FAIL":
            fails.append((st, path, loc[:60]))
        print(f"  [{flag}] {st:>3}  {path:40}  {loc[:50]}")
    except Exception as e:
        fails.append((0, path, f"EXC {type(e).__name__}: {e}"))
        print(f"  [FAIL]   ?  {path:40}  EXC {type(e).__name__}: {e}")

print()
if fails:
    print(f"FAILURES ({len(fails)}):")
    for st, path, info in fails:
        print(f"  [{st}] {path}  ({info})")
    sys.exit(1)
print("ALL PAGES PASS")
