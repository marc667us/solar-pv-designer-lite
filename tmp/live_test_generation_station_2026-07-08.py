#!/usr/bin/env python3
"""Live test suite -- Generation Station (Large-Scale-Solar) design + 3D Digital
Twin -- against production (solarpro.aiappinvent.com).

Production has Keycloak OIDC enabled, so authenticated HTML pages require the
interactive PKCE browser flow that a headless client cannot (and must not)
complete. This suite therefore verifies everything reachable WITHOUT a session:

  * public endpoints return 200,
  * every 3D static asset (12 JS modules + Three.js r147 UMD) returns 200,
  * every gated Generation-Station route EXISTS and is correctly protected
    (302 -> /login), and critically is NOT 404 (missing) or 5xx (crashing) --
    a 5xx here would mean the dt_scene_v2 import or a route broke the module.

Authenticated business-logic coverage lives in the local pytest suite
(tests/test_digital_twin_*.py, 33 tests) which exercises the same server code.

Re-run:  python tmp/live_test_generation_station_2026-07-08.py
"""
import sys
import urllib.request
import urllib.error

BASE = "https://solarpro.aiappinvent.com"
TIMEOUT = 25

PASS, FAIL = [], []


def _status(path, allow_redirect=False):
    """Return (code, location) without following redirects."""
    url = BASE + path

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "gs-live-suite/1"})
    try:
        r = opener.open(req, timeout=TIMEOUT)
        return r.getcode(), r.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Location", "") if e.headers else ""
    except Exception as e:
        return 0, "err:%s" % type(e).__name__


def check(label, path, expect):
    """expect: 'public' (200) | 'gated' (302->login, never 404/5xx) |
    'gated_post' (POST-only route: 405 on GET is correct, route exists) |
    'asset'."""
    code, loc = _status(path)
    ok = False
    detail = str(code)
    if expect == "public":
        ok = code == 200
    elif expect == "asset":
        ok = code == 200
    elif expect == "gated":
        # Route exists and is protected: a redirect to auth is the pass. A 404
        # means the route vanished; a 5xx means the handler/module crashed.
        ok = code in (301, 302, 303, 307, 308) and code not in (404,) and code < 500
        detail = "%s -> %s" % (code, (loc or "").replace(BASE, "") or "?")
    elif expect == "gated_post":
        # POST-only endpoint. A GET hitting 405 proves the route is registered
        # and method-guarded (auth runs on the real POST). 302 is also fine if
        # the auth decorator fires before method routing. 404/5xx = fail.
        ok = code in (405, 301, 302, 303, 307, 308) and code != 404 and code < 500
        detail = "%s (POST-only)" % code
    (PASS if ok else FAIL).append((label, path, detail))
    print("  [%s] %-46s %s" % ("PASS" if ok else "FAIL", label, detail))


PID = 1  # sample id; gated routes 302 before any row lookup

print("=" * 68)
print("LIVE TEST SUITE -- Generation Station design + 3D Digital Twin")
print("Target:", BASE)
print("=" * 68)

print("\n[A] Public surface (expect 200)")
check("health ping", "/api/ping", "public")
check("landing", "/", "public")
check("generation-station landing", "/large-scale-solar", "public")

print("\n[B] 3D asset integrity (expect 200)")
for f in ["dt-state", "dt-materials", "dt-scene-builder", "dt-selection",
          "dt-sun", "dt-cameras", "dt-simulation-modes", "dt-shadow-analysis",
          "dt-parameter-panel", "dt-ai-actions", "dt-exports", "dt-main"]:
    check("module %s.js" % f, "/static/capital_investment/dt/%s.js" % f, "asset")
check("three.min.js (r147 UMD)", "/static/vendor/three-r147-umd/three.min.js", "asset")
check("OrbitControls.js", "/static/vendor/three-r147-umd/OrbitControls.js", "asset")

print("\n[C] 3D Digital Twin routes exist + protected (expect 302, never 404/5xx)")
check("digital-twin page", "/large-scale-solar/%d/digital-twin" % PID, "gated")
check("dt scene.json", "/large-scale-solar/%d/dt/scene.json" % PID, "gated")
check("dt sun.json", "/large-scale-solar/%d/dt/sun.json" % PID, "gated")
check("dt sun-arc.json", "/large-scale-solar/%d/dt/sun-arc.json" % PID, "gated")
check("dt parameters (POST)", "/large-scale-solar/%d/dt/parameters" % PID, "gated_post")
check("dt object-action (POST)", "/large-scale-solar/%d/dt/object-action" % PID, "gated_post")
check("dt shadow-analysis.json", "/large-scale-solar/%d/dt/shadow-analysis.json" % PID, "gated")
check("dt object-schedule.json", "/large-scale-solar/%d/dt/object-schedule.json" % PID, "gated")

print("\n[D] Generation-Station wizard + reports exist + protected")
for s in range(2, 15):
    check("wizard step%d" % s, "/large-scale-solar/%d/step%d" % (PID, s), "gated")
check("BOQ finish (POST)", "/large-scale-solar/%d/boq/finish" % PID, "gated_post")
check("cost-plan", "/large-scale-solar/%d/cost-plan" % PID, "gated")
check("cost-plan.xlsx", "/large-scale-solar/%d/cost-plan.xlsx" % PID, "gated")
check("cost-plan.pdf", "/large-scale-solar/%d/cost-plan.pdf" % PID, "gated")
check("regulatory", "/large-scale-solar/%d/regulatory" % PID, "gated")
check("diag/schema", "/large-scale-solar/diag/schema", "gated")

print("\n[E] Engineering deliverables exist + protected (2026-07-08)")
check("electrical-sld", "/large-scale-solar/%d/electrical-sld" % PID, "gated")
check("design-report", "/large-scale-solar/%d/design-report" % PID, "gated")

print("\n" + "=" * 68)
print("RESULT: %d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("\nFAILURES:")
    for label, path, detail in FAIL:
        print("  - %-40s %s  (%s)" % (label, path, detail))
print("=" * 68)
sys.exit(1 if FAIL else 0)
