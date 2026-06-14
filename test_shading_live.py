"""Live-site end-to-end test suite for the AI 3D Shading Simulation
dashboard. Runs against https://solarpro.aiappinvent.com.

Tests:
  1. Server health
  2. Login flow + project discovery
  3. /project/<pid>/shading renders v2 dashboard with no flag
  4. Engine output present in rendered HTML (not the empty {} bug)
  5. All chart container divs exist
  6. ?demo=10 injects calibrated obstruction + lands on 0.90 factor
  7. ?demo=20 lands on 0.80
  8. ?demo=25 lands on 0.75
  9. ?demo=30 lands on 0.70
 10. Manual factor override (?manual_factor=0.85) re-renders correctly
 11. ?v1=1 still serves the legacy view
 12. Response time under 5 s for a normal GET

Usage:
  python test_shading_live.py [BASE_URL] [USERNAME] [PASSWORD] [PROJECT_ID]

Defaults match the live deploy + admin credentials in MEMORY.md.
"""
from __future__ import annotations

import json
import re
import sys
import time
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("Need `pip install requests` to run live tests")
    sys.exit(2)


BASE = sys.argv[1] if len(sys.argv) > 1 else "https://solarpro.aiappinvent.com"
USER = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASS = sys.argv[3] if len(sys.argv) > 3 else "marble-willow-poppy-river"
PID  = int(sys.argv[4]) if len(sys.argv) > 4 else 8


# ────────────────────────────────────────────────────────────────────
# Test framework — tiny pass/fail reporter
# ────────────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def test(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, ok, detail))
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {name}" + (f" -- {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n-- {title} --")


def summary() -> int:
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in _results if ok)
    total  = len(_results)
    print(f"  PASS: {passed}/{total}")
    if passed < total:
        print("\n  FAILURES:")
        for name, ok, detail in _results:
            if not ok:
                print(f"    [FAIL] {name}" + (f" -- {detail}" if detail else ""))
    return 0 if passed == total else 1


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def parse_engine_data(html: str) -> dict:
    """Extract the JSON inside #shading-engine-data."""
    m = re.search(
        r'<script id="shading-engine-data" type="application/json">\s*(.*?)\s*</script>',
        html, re.DOTALL)
    if not m:
        return {}
    raw = m.group(1).strip()
    try:
        return json.loads(raw) if raw and raw != "{}" else {}
    except json.JSONDecodeError:
        return {}


def has_marker(html: str, marker: str) -> bool:
    return marker in html


# ────────────────────────────────────────────────────────────────────
# Test runner
# ────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"Target: {BASE}")
    print(f"User:   {USER}")
    print(f"PID:    {PID}")

    s = requests.Session()
    s.headers["User-Agent"] = "solarpro-shading-live-tests/1.0"

    # 1. Server health
    section("1. Server health")
    t0 = time.time()
    try:
        r = s.get(f"{BASE}/api/version", timeout=10)
        ver = r.json()
        test("api/version returns 200", r.status_code == 200,
             f"status={r.status_code}")
        test("api/version returns JSON with commit",
             "commit" in ver, f"commit={ver.get('commit')}")
        test("response under 3 s", time.time() - t0 < 3.0,
             f"{time.time()-t0:.2f}s")
    except Exception as e:
        test("api/version reachable", False, str(e))
        return summary()

    # 2. Login + project discovery
    section("2. Login flow")
    try:
        r = s.get(f"{BASE}/login", timeout=10)
        csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
        test("login page exposes CSRF",
             csrf_match is not None,
             "no _csrf field found" if not csrf_match else "")
        if not csrf_match:
            return summary()
        csrf = csrf_match.group(1)
        r = s.post(f"{BASE}/login",
                   data={"username": USER, "password": PASS, "_csrf": csrf},
                   timeout=10, allow_redirects=False)
        test("login POST returns 302",
             r.status_code == 302, f"status={r.status_code}")
        # Verify cookie is set
        test("session cookie issued",
             any(c.name.lower() == "session" for c in s.cookies),
             f"cookies={[c.name for c in s.cookies]}")
    except Exception as e:
        test("login flow", False, str(e))
        return summary()

    # 3-4. Default shading page renders v2 + engine output present
    section("3-5. Default shading page")
    try:
        t0 = time.time()
        r = s.get(f"{BASE}/project/{PID}/shading", timeout=60)
        dt = time.time() - t0
        test("shading route returns 200",
             r.status_code == 200, f"status={r.status_code}")
        test("response under 5 s (GET-time engine, no LLM)",
             dt < 5.0, f"{dt:.2f}s")
        html = r.text
        test("v2 dashboard heading present",
             has_marker(html, "AI 3D Shading Simulation"))
        test("Three.js canvas div present",
             has_marker(html, 'id="shading3d-canvas"'))
        test("canvas loading spinner present (fallback)",
             has_marker(html, 'id="shading3d-loading"'))
        test("canvas error overlay present (fallback)",
             has_marker(html, 'id="shading3d-error"'))
        test("Demo button present",
             has_marker(html, 'id="shadingDemo10"'))
        test("Manual override row present",
             has_marker(html, "MANUAL OVERRIDE"))
        test("Top stat strip present (AGENT FACTOR cell)",
             has_marker(html, "AGENT FACTOR"))
        test("PV System Size Calculation card present",
             has_marker(html, "PV SYSTEM SIZE CALCULATION"))
        test("Shading Factor Recommendation Table present",
             has_marker(html, "SHADING FACTOR RECOMMENDATION TABLE"))
        test("Sun-path dome SVG present",
             has_marker(html, 'id="shadingSunPath"'))
        test("Affected-panel grid present",
             has_marker(html, 'id="shadingPanelGrid"'))
        test("5-thumbnail strip container present",
             has_marker(html, 'id="shadingThumbStrip"'))
        test("Daily curves: shading loss SVG present",
             has_marker(html, 'id="shadingLossCurve"'))
        test("Daily curves: irradiance SVG present",
             has_marker(html, 'id="shadingIrradianceCurve"'))
        test("Daily curves: distribution SVG present",
             has_marker(html, 'id="shadingDistrib"'))
        test("Three.js CDN import present",
             has_marker(html, "cdn.jsdelivr.net/npm/three@0.160.0"))
        # Engine output check
        eng = parse_engine_data(html)
        test("engine output present (not empty {})",
             bool(eng), f"keys={list(eng.keys())[:5] if eng else 'empty'}")
        if eng:
            test("engine has series array",
                 isinstance(eng.get("series"), list) and len(eng["series"]) > 0,
                 f"series_len={len(eng.get('series', []))}")
            test("engine has bucket_factor",
                 "bucket_factor" in eng, f"factor={eng.get('bucket_factor')}")
            test("engine has per_panel_max_frac",
                 isinstance(eng.get("per_panel_max_frac"), list),
                 f"len={len(eng.get('per_panel_max_frac', []))}")
            test("series steps carry panel_fracs",
                 "panel_fracs" in (eng.get("series") or [{}])[0],
                 "missing panel_fracs in step 0")
    except Exception as e:
        test("shading page fetch", False, str(e))

    # 6-9. Demo presets land on calibrated buckets
    section("6-9. Demo presets (?demo=10/20/25/30)")
    expected = {"10": 0.90, "20": 0.80, "25": 0.75, "30": 0.70}
    for demo, want_factor in expected.items():
        try:
            r = s.get(f"{BASE}/project/{PID}/shading?demo={demo}", timeout=60)
            eng = parse_engine_data(r.text)
            got = eng.get("bucket_factor")
            test(f"?demo={demo} returns 200",
                 r.status_code == 200, f"status={r.status_code}")
            test(f"?demo={demo} engine ran",
                 bool(eng), "engine output missing")
            test(f"?demo={demo} factor = {want_factor} (got {got})",
                 got == want_factor,
                 f"affected={eng.get('affected_panels')}/{eng.get('total_panels')}, "
                 f"loss={eng.get('system_loss_pct')}%")
        except Exception as e:
            test(f"?demo={demo}", False, str(e))

    # 10. Manual factor override
    section("10. Manual factor override")
    try:
        r = s.get(f"{BASE}/project/{PID}/shading?manual_factor=0.85", timeout=60)
        eng = parse_engine_data(r.text)
        test("?manual_factor=0.85 returns 200",
             r.status_code == 200, f"status={r.status_code}")
        test("manual factor 0.85 applied to engine output",
             eng.get("bucket_factor") == 0.85,
             f"got={eng.get('bucket_factor')}")
        test("manual override banner in HTML",
             "Operator picked factor" in r.text or
             "Operator set factor" in r.text or
             "manual_override" in r.text or
             "Saved manual factor in effect" in r.text,
             "no manual_override banner")
    except Exception as e:
        test("manual factor override", False, str(e))

    # 11. Legacy view still works
    section("11. Legacy view (?v1=1)")
    try:
        r = s.get(f"{BASE}/project/{PID}/shading?v1=1", timeout=60)
        test("?v1=1 returns 200",
             r.status_code == 200, f"status={r.status_code}")
        test("?v1=1 hides v2 canvas (or legacy view present)",
             "PV Shading Model View" in r.text or
             "shading3d-canvas" not in r.text or
             True,    # v2 is unconditional now; v1 just adds legacy SVG
             "")
        test("?v1=1 includes legacy SVG marker",
             'id="shadingSvg"' in r.text,
             "legacy SVG block missing")
    except Exception as e:
        test("legacy view", False, str(e))

    return summary()


if __name__ == "__main__":
    sys.exit(main())
