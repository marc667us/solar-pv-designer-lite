# -*- coding: utf-8 -*-
"""
Live smoke for the Step 8 Finance -> BOQ linkage deploy.

Authed end-to-end generation is not automatable on live (KC OIDC PKCE login),
so this proves the deploy is clean and the Step 8 route gates safely:
  * /api/version reports the new commit,
  * /api/health is ok,
  * GET + POST /large-scale-solar/<pid>/step8 gate to /login (302), NOT 500.
Run: python tmp/live_step8_finance_2026-07-02.py
"""
import sys
import urllib.request
import urllib.error

BASE = "https://solarpro.aiappinvent.com"
EXPECT_COMMIT = "2a70953"
FAIL = []


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do NOT follow redirects - a protected route returns 302 -> /login and
    following that into the cross-domain KC OIDC chain would mask the gate."""
    def redirect_request(self, *a, **k):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def get(path, method="GET"):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("User-Agent", "solarpro-live-smoke/step8")
    try:
        r = _OPENER.open(req, timeout=30)
        return r.status, r.read(4000).decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        # 302/401/403 land here with _NoRedirect - that IS the gate.
        loc = e.headers.get("Location", "") if e.headers else ""
        return e.code, "LOCATION=" + loc, path
    except Exception as e:
        return 0, f"ERR {e}", path


def main():
    st, body, _ = get("/api/version")
    print(f"/api/version -> {st}: {body[:200]}")
    check(st == 200, "/api/version 200")
    check(EXPECT_COMMIT in body, f"/api/version reports {EXPECT_COMMIT}")

    st, body, _ = get("/api/health")
    check(st == 200, f"/api/health 200 (got {st})")

    # Step 8 must GATE (302 -> /login), never 500. Redirects are NOT followed.
    for method in ("GET", "POST"):
        st, body, url = get("/large-scale-solar/1/step8", method=method)
        print(f"step8 {method} -> {st} {body[:80]}")
        check(st in (302, 303, 401, 403),
              f"step8 {method} gates to auth (got {st})")
        check("login" in body.lower() or st in (401, 403),
              f"step8 {method} redirects to /login")

    print()
    if FAIL:
        print(f"RESULT: {len(FAIL)} FAILED")
        for m in FAIL:
            print("  - " + m)
        sys.exit(1)
    print("RESULT: ALL PASS")


if __name__ == "__main__":
    main()
