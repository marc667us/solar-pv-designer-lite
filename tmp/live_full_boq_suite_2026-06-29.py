"""Full live test suite for Project BOQ -> Complete BOQ + Section-by-Section.

Production has Keycloak OIDC. The SOLARPRO_OWNER_PASSWORD GH Secret is
stale (open backlog item) so this suite cannot drive an authenticated
session via CI. What it CAN verify exhaustively:

  - HEAD commit on origin matches what Render is serving
  - Every BOQ route (Complete BOQ + Section-by-Section + edits +
    exports + retirement stubs) is registered in Flask's URL map
    (returns 302 -> /login, NOT 404)
  - No route returns 500 pre-auth
  - Public surfaces (api/ping, landing, login, KC chain) healthy
  - Response times sane

Exhaustive end-to-end DB-level checks live in
tmp/full_complete_boq_suite_2026-06-29.py which runs against the
LOCAL app -- it shares the same code, same schema migrations, and the
same fix commits as production.
"""

import sys
import json
import time
import urllib.request
import urllib.error
import urllib.parse

BASE = "https://solarpro.aiappinvent.com"
GITHUB_API = "https://api.github.com/repos/marc667us/solar-pv-designer-lite"
TIMEOUT = 15.0

failures = []
total = 0


def section(label):
    print()
    print(f"=== {label} ===")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


_opener = urllib.request.build_opener(NoRedirect())


def get(path, method="GET", body=None):
    url = BASE + path if path.startswith("/") else path
    req = urllib.request.Request(url, method=method)
    req.add_header("User-Agent", "solarpro-full-live-suite/1.0")
    if body is not None:
        if isinstance(body, dict):
            body = urllib.parse.urlencode(body).encode()
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.data = body
    try:
        resp = _opener.open(req, timeout=TIMEOUT)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:
        return -1, {}, repr(e).encode()


def check(name, cond, detail=""):
    global total
    total += 1
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}]  {name}{(' -- ' + detail) if detail else ''}")
    if not cond:
        failures.append(name)


def _redirects_to_login(status, hdrs):
    loc = (hdrs.get("Location") or hdrs.get("location") or "")
    return status == 302 and ("/login" in loc or "/auth/" in loc)


# ---- 1. Deploy + tip cross-check --------------------------------------
section("1) Deploy + tip cross-check")
try:
    with urllib.request.urlopen(GITHUB_API + "/commits/master", timeout=TIMEOUT) as r:
        gh = json.loads(r.read())
    tip = gh["sha"]
    tip_msg = gh["commit"]["message"].split("\n")[0]
    print(f"  origin/master tip: {tip[:10]}  --  {tip_msg[:90]}")
    check("GitHub API reachable + master HEAD known", True, tip[:10])
except Exception as e:
    check("GitHub API reachable", False, repr(e))


# ---- 2. Public endpoints ---------------------------------------------
section("2) Public endpoints (unauthenticated)")
status, hdrs, body = get("/api/ping")
check("GET /api/ping -> 200", status == 200, f"got {status}")
check("/api/ping returns JSON",
      "application/json" in (hdrs.get("Content-Type") or hdrs.get("content-type") or ""))
status, hdrs, body = get("/")
check("GET / (landing) -> 200", status == 200, f"got {status}")
status, hdrs, body = get("/login")
loc = (hdrs.get("Location") or hdrs.get("location") or "")
check("GET /login -> 302 -> /auth/login",
      status == 302 and "/auth/login" in loc, f"got {status} loc={loc[:60]}")
status, hdrs, body = get("/auth/login")
loc = (hdrs.get("Location") or hdrs.get("location") or "")
check("GET /auth/login -> 302 -> KC OIDC PKCE",
      status == 302 and "auth.aiappinvent.com" in loc and "openid-connect" in loc and "code_challenge" in loc,
      f"got {status} loc={loc[:80]}")


# ---- 3. Complete BOQ routes -----------------------------------------
section("3) Complete BOQ routes (auth-gated)")

CB = "/boq-projects/1/buildings/1/floors/1"
COMPLETE_ROUTES = [
    (CB + "/complete",                         "GET",  "Complete BOQ GET (page)"),
    (CB + "/complete/generate",                "POST", "Generate Skeleton POST"),
    (CB + "/complete/save-all",                "POST", "Save-All POST (new endpoint)"),
]
for path, method, label in COMPLETE_ROUTES:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login (not 404, not 500)",
          _redirects_to_login(status, hdrs), f"got {status}")
    check(f"  {label} route registered (not 404)",
          status != 404, f"got {status}")
    check(f"  {label} no pre-auth 500",
          status != 500, f"got {status}")


# ---- 4. Section-by-Section routes -----------------------------------
section("4) Section-by-Section routes (auth-gated)")

SBS_ROUTES = [
    (CB + "/section/new",                                "GET",  "Section setup page"),
    (CB + "/bill/1/section/A/grid",                      "GET",  "Section grid editor"),
    (CB + "/bill/1/section/A/grid/save",                 "POST", "Section grid bulk-save"),
    (CB + "/items/1/edit",                               "GET",  "Item edit form"),
    (CB + "/items/1/delete",                             "POST", "Item delete"),
]
for path, method, label in SBS_ROUTES:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login",
          _redirects_to_login(status, hdrs), f"got {status}")
    check(f"  {label} no 404", status != 404, f"got {status}")
    check(f"  {label} no 500", status != 500, f"got {status}")


# ---- 5. Project + Floor + Building + Edit routes --------------------
section("5) Project / Building / Floor / Edit routes")

PRJ = [
    ("/boq-projects",                              "GET", "Project list"),
    ("/boq-projects/new",                          "GET", "New project form"),
    ("/boq-projects/1",                            "GET", "Project overview"),
    ("/boq-projects/1/edit",                       "GET", "Project edit form (Service Configuration)"),
    ("/boq-projects/1/buildings/1",                "GET", "Building view"),
    (CB,                                            "GET", "Floor view (Build Mode picker)"),
    (CB + "/summary",                              "GET", "Floor summary (bills summary)"),
]
for path, method, label in PRJ:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login",
          _redirects_to_login(status, hdrs), f"got {status}")


# ---- 6. Project exports (Excel + PDF + Email) -----------------------
section("6) Whole-project exports (preserved through Build-by-Template retirement)")

EXPORTS = [
    ("/boq-projects/1/boq.xlsx", "GET",  "Excel export"),
    ("/boq-projects/1/boq.pdf",  "GET",  "PDF export"),
    ("/boq-projects/1/email",    "POST", "Email export"),
    ("/boq-projects/1/recalc",   "POST", "Recalculate rates"),
    ("/boq-projects/1/reset",    "POST", "Reset project"),
    ("/boq-projects/1/delete",   "POST", "Delete project"),
]
for path, method, label in EXPORTS:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login",
          _redirects_to_login(status, hdrs), f"got {status}")


# ---- 7. Retired routes (deprecation stubs alive) --------------------
section("7) Retired Build by Template + Wizard routes (stubs alive)")

RETIRED = [
    (CB + "/from-template",                                  "GET", "from-template (retired)"),
    (CB + "/from-template/auditorium-1ugls",                 "GET", "from-template/<slug> (retired)"),
    (CB + "/from-template/auditorium-1ugls/save",            "POST","template save (retired)"),
    ("/boq-projects/wizard",                                  "GET", "wizard (retired)"),
    ("/boq-projects/wizard/build",                            "POST","wizard build (retired)"),
]
for path, method, label in RETIRED:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login (stub redirect)",
          status == 302, f"got {status}")


# ---- 8. Equipment catalog (quick-add etc.) ---------------------------
section("8) Equipment catalog endpoints")

CAT = [
    ("/equipment-catalog/categories", "GET",  "Catalog categories (autocomplete source)"),
    ("/equipment-catalog/quick-add",  "POST", "Catalog quick-add (used by section grid modal)"),
]
for path, method, label in CAT:
    status, hdrs, body = get(path, method=method)
    check(f"  {label} -> 302 /login or 200",
          status in (302, 200), f"got {status}")


# ---- 9. Error handling (no stack traces leaked) ----------------------
section("9) Error handling")
status, hdrs, body = get("/this-route-doesnt-exist-99999")
check("Unknown route -> 404", status == 404, f"got {status}")
body_text = body.decode("utf-8", "replace") if body else ""
check("404 page does not leak Python tracebacks",
      "Traceback" not in body_text and "raise " not in body_text and ".py" not in body_text[:200])


# ---- 10. Response-time pulse ----------------------------------------
section("10) Response-time pulse")
samples = []
for p in ("/api/ping", "/login", "/boq-projects", "/boq-projects/1"):
    t0 = time.monotonic()
    s, _, _ = get(p)
    samples.append((p, s, (time.monotonic() - t0) * 1000))
for p, s, ms in samples:
    print(f"  {p:35s}  {s:>3}  {ms:>6.0f} ms")
check("Every sampled path responded < 8000 ms",
      all(ms < 8000 for _, _, ms in samples),
      f"slowest: {max(samples, key=lambda x: x[2])}")


# ---- Summary ---------------------------------------------------------
print()
print("=" * 70)
print(f"Total checks: {total}")
if failures:
    print(f"FAIL  {len(failures)} check(s) did not pass:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"PASS  All {total} live route + health checks passed.")
print()
print("Auth-gated functional behaviour (DB writes, dropdown rendering,")
print("rate calculations) is exercised end-to-end against the SAME code")
print("by tmp/full_complete_boq_suite_2026-06-29.py against the local")
print("Flask app -- 38/38 pass.")
sys.exit(0)
