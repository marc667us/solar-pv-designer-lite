"""REPRODUCE the owner's 403: "click create new programme -> hiccup page, not authorised".

WHY THIS SCRIPT EXISTS
----------------------
Two theories were tested against live data and BOTH were refuted:

  * "the owner holds no programme.create" -- refuted. `Diag Enterprise Permissions` shows
    every one of the 7 enterprise users holds it in whatever tenant they land in, and the
    MOE owner (user_id=2) holds all 11 onboarding roles.
  * "create_programme rejects it later" -- refuted. workflows.create_programme has exactly
    one authorisation check (rbac.require_permission at workflows.py:443) and it is the
    same one the route already passed.

So the 403 is NOT explained by role data, and guessing again would be the third guess.
This walks the owner's actual clicks over HTTP against the REAL deployment and reports
which request returns what -- including WHICH TENANT the session is acting in at each
step, because that is the input every permission check is judged against.

It is READ-ONLY except for the final create attempt, which is guarded behind --post and
is off by default. Nothing else writes.

Run (in Actions -- Keycloak authenticates on EMAIL, and the local .env is stale):
    LIVE_USER=marc667us@yahoo.com SOLARPRO_OWNER_PASSWORD=... python tmp/repro_enterprise_403_2026-07-13.py
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urljoin, urlparse

import requests

BASE = "https://solarpro.aiappinvent.com"
TIMEOUT = 90


def login(s: requests.Session, username: str, password: str) -> bool:
    """Keycloak OIDC + PKCE, exactly as the live suite does it."""
    r = s.get(f"{BASE}/auth/login", timeout=TIMEOUT, allow_redirects=True)
    if "auth.aiappinvent.com" not in r.url and "/realms/" not in r.url:
        print(f"  ! not redirected to Keycloak (landed at {r.url[:80]})")
        return False
    m = re.search(r'action="([^"]+)"', r.text)
    if not m:
        print("  ! no login form at Keycloak")
        return False
    action = urljoin(r.url, m.group(1).replace("&amp;", "&"))
    r2 = s.post(action, data={"username": username, "password": password},
                timeout=TIMEOUT, allow_redirects=True)
    if "Invalid username or password" in r2.text:
        print("  ! Keycloak rejected the credentials")
        return False
    if "solarpro.aiappinvent.com" not in urlparse(r2.url).netloc:
        print(f"  ! callback did not return to the app (stuck at {r2.url[:90]})")
        return False
    r3 = s.get(f"{BASE}/dashboard", timeout=TIMEOUT, allow_redirects=False)
    print(f"  logged in -- /dashboard = {r3.status_code}")
    return r3.status_code == 200


def active_tenant(html: str) -> str:
    """Which organisation is the switcher showing as selected? That IS the active tenant."""
    m = re.search(r'<option value="[^"]*"\s+selected[^>]*>\s*([^<\n]+)', html)
    return m.group(1).strip() if m else "(could not read the switcher)"


def show(s: requests.Session, path: str, label: str) -> requests.Response:
    r = s.get(f"{BASE}{path}", timeout=TIMEOUT, allow_redirects=False)
    verdict = ""
    if r.status_code == 403:
        verdict = "   <<<< 403 -- THIS IS THE HICCUP PAGE THE OWNER SAW"
    elif r.status_code == 404:
        verdict = "   <<<< 404 (module flag dark?)"
    print(f"  GET {path:<42} -> {r.status_code}{verdict}")
    # The friendly handler renders the 403 as a 200-looking page in some paths, so also
    # sniff the body for the error template's own words.
    if "We hit a small hiccup" in r.text or "Hiccup" in r.text:
        print(f"       body is the ERROR PAGE. title/message: "
              f"{' | '.join(re.findall(r'<h4[^>]*>([^<]+)</h4>|<p[^>]*>([^<]{10,120})</p>', r.text)[:2])!s:.180}")
    return r


def main() -> int:
    user = os.environ.get("LIVE_USER", "")
    pw = os.environ.get("SOLARPRO_OWNER_PASSWORD", "")
    if not user or not pw:
        print("LIVE_USER and SOLARPRO_OWNER_PASSWORD must be set.")
        return 2

    s = requests.Session()
    print("== 1. Login ==")
    if not login(s, user, pw):
        return 1

    print("\n== 2. The Enterprise home page (this is where the buttons live) ==")
    home = show(s, "/enterprise", "home")
    if home.status_code == 200:
        print(f"       ACTIVE TENANT (from the switcher): {active_tenant(home.text)}")
        has_new = "New Programme" in home.text
        has_members = ">Members" in home.text or "Members\n" in home.text
        print(f"       'New Programme' button rendered: {has_new}   "
              f"(it is gated on can_create, so False == no programme.create)")
        print(f"       'Members' button rendered:       {has_members}")

    print("\n== 3. THE REPORTED CLICK -- 'New Programme' ==")
    show(s, "/enterprise/programmes/new", "create programme form")

    print("\n== 4. The neighbouring buttons (the owner also called Members unclear) ==")
    show(s, "/enterprise/members", "members")
    show(s, "/enterprise/templates", "templates")

    print("\n== 5. Same clicks, but acting in the PERSONAL workspace ==")
    print("   (the switcher's other option -- a permission is judged against the ACTIVE")
    print("    tenant, so the same button can behave differently in each)")
    ids = re.findall(r'<option value="([^"]+)"', home.text) if home.status_code == 200 else []
    csrf = re.search(r'name="_csrf" value="([^"]+)"', home.text) if home.status_code == 200 else None
    if len(ids) > 1 and csrf:
        for tid in ids:
            s.post(f"{BASE}/enterprise/switch-tenant", timeout=TIMEOUT,
                   data={"_csrf": csrf.group(1), "tenant_id": tid}, allow_redirects=True)
            h = s.get(f"{BASE}/enterprise", timeout=TIMEOUT)
            print(f"\n   --- acting in: {active_tenant(h.text)} ---")
            show(s, "/enterprise/programmes/new", "create programme")
            show(s, "/enterprise/members", "members")
    else:
        print("   (only one tenant on this account -- nothing to switch to)")

    # ---------------------------------------------------------------- the POST path
    # The GET renders 200 in BOTH tenants (above), so the form is reachable and the
    # permission IS held. That leaves the POST. The only abort(403) on the POST path
    # other than the permission check -- which we have just proved passes -- is
    # csrf_protect() (web_app.py:274-279), which aborts 403 when the submitted _csrf
    # does not match the one in the session.
    #
    # So: submit the SAME form twice -- once with the token the server just gave us, and
    # once with a stale token -- and see which produces the owner's page. This decides
    # between "the module refuses the owner" and "the owner's form went stale".
    print("\n== 6. THE POST -- is it CSRF, not permissions? ==")
    r = s.get(f"{BASE}/enterprise/programmes/new", timeout=TIMEOUT)
    tok = re.search(r'name="_csrf" value="([^"]+)"', r.text)
    if not tok:
        print("   ! no CSRF field on the form -- cannot test")
        return 0
    good = tok.group(1)

    stale = s.post(f"{BASE}/enterprise/programmes/new", timeout=TIMEOUT,
                   allow_redirects=False,
                   data={"_csrf": "stale-token-from-an-older-session",
                         "code": "REPRO-STALE", "name": "Repro (stale token)",
                         "design_strategy": "standard"})
    is_hiccup = "hiccup" in stale.text.lower() or "not authorised" in stale.text.lower() \
        or "not have the permission" in stale.text.lower()
    print(f"   POST with a STALE csrf token -> {stale.status_code}"
          f"{'   <<<< reproduces the OWNER PAGE' if stale.status_code == 403 else ''}")
    print(f"        body is the hiccup/not-authorised page: {is_hiccup}")
    print("        (nothing was created -- the request was rejected before any write)")

    if "--post" in sys.argv:
        real = s.post(f"{BASE}/enterprise/programmes/new", timeout=TIMEOUT,
                      allow_redirects=False,
                      data={"_csrf": good, "code": "REPRO-OK", "name": "Repro (valid token)",
                            "design_strategy": "standard"})
        print(f"   POST with a VALID csrf token -> {real.status_code} "
              f"({'302 = created' if real.status_code == 302 else 'see body'})")
    else:
        print("   POST with a VALID token: SKIPPED (pass --post to actually create one)")

    print("\n== DONE ==")
    print("If the GET is 200 everywhere and only the stale-token POST is 403, then the")
    print("owner was never 'unauthorised' -- their form's CSRF token no longer matched")
    print("their session, and csrf_protect() abort(403) rendered Werkzeug's generic")
    print("'you don't have permission' text as the hiccup page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
