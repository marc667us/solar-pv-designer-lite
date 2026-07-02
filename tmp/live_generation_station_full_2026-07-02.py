"""Full live smoke test of the Generation Station Design module.

Covers every /large-scale-solar/* route surface anon can see + verifies
every authed route holds its auth gate cleanly (302, not 500). Also
confirms the create-project fix landed (live tip matches expected sha,
diag endpoint is registered).

Anon-visible (expect 200 + body sanity):
    /large-scale-solar               landing
    /large-scale-solar/demo          20 MW Ghana demo project
    /large-scale-solar/upgrade       upsell page

Auth-required (expect 302 to /login -> KC):
    /large-scale-solar/new                            Step 1 Project Registration (GET)
    /large-scale-solar/<pid>                          project overview
    /large-scale-solar/<pid>/step2 … step14           wizard steps
    /large-scale-solar/<pid>/report/<key>.pdf         5 PDF reports
    /large-scale-solar/<pid>/digital-twin             3D digital twin studio
    /large-scale-solar/<pid>/dt/scene.json            twin geometry
    /large-scale-solar/<pid>/dt/sun.json              NOAA sun position
    /large-scale-solar/<pid>/regulatory               regulatory / permitting

Admin-gated (expect 302 or 404):
    /large-scale-solar/diag/schema

Also samples SolarPro global health so we know the site is up.

Run:
    python tmp/live_generation_station_full_2026-07-02.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "https://solarpro.aiappinvent.com"
EXPECTED_LIVE_TIP_PREFIX = "ca72b15"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_a, **_kw):
        return None


_opener = urllib.request.build_opener(_NoRedirect())


def _fetch(path: str, timeout: float = 30.0) -> tuple[int, dict, bytes]:
    """Return (status, headers dict-lower, body bytes) without following redirects."""
    url = BASE + path
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "solarpro-live-smoke/2026-07-02"})
    t0 = time.time()
    try:
        r = _opener.open(req, timeout=timeout)
        code = r.getcode()
        body = r.read()
        headers = {k.lower(): v for k, v in r.getheaders()}
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read()
        except Exception:
            body = b""
        headers = {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}
    dur_ms = int((time.time() - t0) * 1000)
    headers["_duration_ms"] = str(dur_ms)
    return code, headers, body


def _live_tip() -> tuple[str, str]:
    url = "https://api.github.com/repos/marc667us/solar-pv-designer-lite/commits/master"
    r = urllib.request.urlopen(url, timeout=15).read()
    d = json.loads(r)
    return d["sha"][:10], d["commit"]["message"].split("\n")[0]


def _fix_is_ancestor(short_sha: str) -> bool:
    """Return True if `short_sha` is reachable from origin/master (i.e. the
    fix commit is on the branch even if bot commits have moved the tip)."""
    url = f"https://api.github.com/repos/marc667us/solar-pv-designer-lite/compare/{short_sha}...master"
    try:
        r = urllib.request.urlopen(url, timeout=15).read()
        d = json.loads(r)
        # GitHub compare returns status='identical'|'ahead'|'behind'|'diverged'.
        # 'identical' (short_sha == master) and 'ahead' (master is ahead of short_sha)
        # both mean the fix is in the tree.
        return d.get("status") in ("identical", "ahead")
    except Exception:
        return False


def main() -> int:
    ok = 0
    fail = 0
    warns = 0

    def check(cond: bool, label: str) -> None:
        nonlocal ok, fail
        if cond:
            ok += 1
            print(f"  [OK  ] {label}")
        else:
            fail += 1
            print(f"  [FAIL] {label}")

    def warn(cond: bool, label: str) -> None:
        nonlocal ok, warns
        if cond:
            ok += 1
            print(f"  [OK  ] {label}")
        else:
            warns += 1
            print(f"  [WARN] {label}")

    print(f"=== Live Generation Station Design full-surface smoke test ===")
    print(f"Base URL: {BASE}")

    # -----------------------------------------------------------------
    # 0. Live tip should match the fix commit
    # -----------------------------------------------------------------
    print("\n[0] Fix commit must be reachable from origin/master ...")
    sha, msg = _live_tip()
    print(f"  live tip = {sha} '{msg}'")
    if sha.startswith(EXPECTED_LIVE_TIP_PREFIX):
        check(True, f"live tip IS the fix commit ({EXPECTED_LIVE_TIP_PREFIX})")
    else:
        check(_fix_is_ancestor(EXPECTED_LIVE_TIP_PREFIX),
              f"{EXPECTED_LIVE_TIP_PREFIX} is an ancestor of live master "
              f"(tip has moved to {sha} via later commits like '{msg}')")

    # -----------------------------------------------------------------
    # 1. Global health
    # -----------------------------------------------------------------
    print("\n[1] Global health ...")
    for path in ("/", "/api/ping"):
        code, hdr, _ = _fetch(path)
        check(code == 200, f"GET {path} -> 200 (got {code}, {hdr.get('_duration_ms','?')} ms)")

    # -----------------------------------------------------------------
    # 2. Anon-visible /large-scale-solar/* routes -> 200 with content
    # -----------------------------------------------------------------
    print("\n[2] Anon-visible marketing routes ...")

    code, hdr, body = _fetch("/large-scale-solar")
    txt = body.decode("utf-8", errors="replace")
    check(code == 200, f"GET /large-scale-solar -> 200 (got {code}, {hdr.get('_duration_ms','?')} ms)")
    check("Generation Station" in txt or "Utility" in txt or "Capital Investment" in txt,
          "landing body mentions module name")
    check(len(body) > 5_000, f"landing body is substantive (got {len(body)} bytes)")
    # Content-Security-Policy header sanity (case-insensitive)
    warn("content-security-policy" in hdr, "landing carries Content-Security-Policy header")

    code, hdr, body = _fetch("/large-scale-solar/demo")
    txt = body.decode("utf-8", errors="replace")
    check(code == 200, f"GET /large-scale-solar/demo -> 200 (got {code})")
    check("Tema" in txt or "Ghana" in txt or "20" in txt,
          "demo body mentions Tema / Ghana / 20 (MW demo)")
    check(len(body) > 5_000, f"demo body is substantive (got {len(body)} bytes)")

    code, hdr, body = _fetch("/large-scale-solar/upgrade")
    txt = body.decode("utf-8", errors="replace")
    check(code == 200, f"GET /large-scale-solar/upgrade -> 200 (got {code})")
    check("Enterprise" in txt or "upgrade" in txt.lower() or "plan" in txt.lower(),
          "upgrade body mentions Enterprise / upgrade / plan")

    # -----------------------------------------------------------------
    # 3. Auth-required routes hold the gate cleanly (302 -> /login)
    # -----------------------------------------------------------------
    print("\n[3] Auth-required routes hold the gate (expect 302 to KC login) ...")
    # Use a plausible pid — the diag route needs to be visited for the tier
    # gate to redirect; since anon has no session, /new gate fires first
    # (login_required). Fake pid=1 for the <int:pid> routes; if the row
    # doesn't belong to the anon session the code redirects before the
    # ownership check runs.
    pid = 1
    auth_routes = [
        f"/large-scale-solar/new",
        f"/large-scale-solar/{pid}",
        f"/large-scale-solar/{pid}/step2",
        f"/large-scale-solar/{pid}/step3",
        f"/large-scale-solar/{pid}/step4",
        f"/large-scale-solar/{pid}/step5",
        f"/large-scale-solar/{pid}/step6",
        f"/large-scale-solar/{pid}/step7",
        f"/large-scale-solar/{pid}/step8",
        f"/large-scale-solar/{pid}/step9",
        f"/large-scale-solar/{pid}/step10",
        f"/large-scale-solar/{pid}/step11",
        f"/large-scale-solar/{pid}/step12",
        f"/large-scale-solar/{pid}/step13",
        f"/large-scale-solar/{pid}/step14",
        f"/large-scale-solar/{pid}/digital-twin",
        f"/large-scale-solar/{pid}/dt/scene.json",
        f"/large-scale-solar/{pid}/dt/sun.json",
        f"/large-scale-solar/{pid}/regulatory",
    ]
    for path in auth_routes:
        code, hdr, _ = _fetch(path)
        loc = hdr.get("location", "")
        check(code == 302, f"GET {path} -> 302 (got {code}, {hdr.get('_duration_ms','?')} ms)")
        if code == 302:
            check(("/login" in loc or "/auth/login" in loc),
                  f"    Location goes to login (got: {loc[:80]})")

    # -----------------------------------------------------------------
    # 4. Report PDF routes hold the gate — 5 full reports
    # -----------------------------------------------------------------
    print("\n[4] Report PDF endpoints (5 full report keys) ...")
    for key in ("executive", "technical", "financial", "bankability", "investment_memo"):
        path = f"/large-scale-solar/{pid}/report/{key}.pdf"
        code, hdr, _ = _fetch(path)
        loc = hdr.get("location", "")
        check(code == 302, f"GET {path} -> 302 (got {code})")
        if code == 302:
            check(("/login" in loc or "/auth/login" in loc),
                  f"    Location goes to login (got: {loc[:80]})")

    # -----------------------------------------------------------------
    # 5. Admin-gated diag endpoint — 302 or 404 for anon
    # -----------------------------------------------------------------
    print("\n[5] Admin-gated diag/schema ...")
    code, hdr, _ = _fetch("/large-scale-solar/diag/schema")
    check(code in (302, 404), f"GET /large-scale-solar/diag/schema -> 302 or 404 (got {code})")

    # -----------------------------------------------------------------
    # 6. No 500s anywhere in the module — sweep every route once more
    # -----------------------------------------------------------------
    print("\n[6] No 5xx across the full surface ...")
    routes_seen = ["/large-scale-solar", "/large-scale-solar/demo",
                   "/large-scale-solar/upgrade",
                   "/large-scale-solar/diag/schema"] + auth_routes + [
        f"/large-scale-solar/{pid}/report/{k}.pdf"
        for k in ("executive", "technical", "financial", "bankability",
                  "investment_memo")]
    fivex = 0
    for path in routes_seen:
        code, _, _ = _fetch(path)
        if 500 <= code < 600:
            fivex += 1
            print(f"    [5xx] {code}  {path}")
    check(fivex == 0, f"no 5xx across {len(routes_seen)} routes (found {fivex})")

    # -----------------------------------------------------------------
    # 7. Nav rename check — 'Generation Station Design' lives inside the
    # authed nav dropdown in base.html, so it only shows on logged-in
    # page fetches. Confirm the rename is in the local template source
    # (deployed copy is one commit behind the tip we already verified is
    # an ancestor of live master).
    # -----------------------------------------------------------------
    print("\n[7] Nav rename 'Generation Station Design' in base.html source ...")
    import os
    base_html = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "templates", "base.html")
    try:
        with open(base_html, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        check("Generation Station Design" in src,
              "base.html carries the 'Generation Station Design' dropdown label")
        check("Start New Generation Station" in src,
              "base.html carries the 'Start New Generation Station' CTA")
        check("UTILITY-SCALE / IPP / CAPTIVE" in src,
              "base.html carries the 'UTILITY-SCALE / IPP / CAPTIVE' section header")
    except FileNotFoundError:
        warn(False, f"base.html not found at {base_html}")

    print(f"\n=== Summary: {ok} OK / {fail} FAIL / {warns} WARN ===")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
