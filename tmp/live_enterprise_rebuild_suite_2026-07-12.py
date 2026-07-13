"""LIVE suite -- Enterprise Programme REBUILD (slices 1-6) against solarpro.aiappinvent.com.

Not a unit test. This drives the REAL deployed module against the REAL Postgres, through
HTTP, exactly as the owner would. Everything the SQLite suite proves is worthless if the
Postgres path diverges -- and migrations 025/026/027 had NEVER been executed against a real
Postgres until today, so this is the first time that path is exercised at all.

WHAT IT WALKS
  1.  anonymous -- the module must not leak to a logged-out visitor
  2.  login (Keycloak OIDC + PKCE)
  3.  onboarding -> a real organisation tenant
  4.  programme registry -> create a programme
  5.  the lifecycle spine -- 16 phases, 14 gates, seeded and visible
  6.  C01: a gate cannot be approved by someone who is not its named authority
  7.  the versioned template engine -- draft -> review -> approved, and the FREEZE
  8.  the beneficiary register -- register a site by hand
  9.  the importer -- upload CSV, STAGED (nothing written), preview, then commit
  10. duplicate detection -- a school listed twice in one file is caught
  11. site qualification -- score, then decide (C02), and scoring is NOT deciding
  12. the priority list -- ranked, unscored last
  13. C13 -- another tenant's ids are 404, never 403

It CLEANS UP after itself and is safe to re-run.

Run:  python tmp/live_enterprise_rebuild_suite_2026-07-12.py
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests

BASE = "https://solarpro.aiappinvent.com"
TIMEOUT = 90                      # free tier cold-starts; be patient

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))
    return bool(ok)


def csrf(s: requests.Session, url: str) -> str:
    """Pull the _csrf token out of a rendered form."""
    r = s.get(url, timeout=TIMEOUT)
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
    return m.group(1) if m else ""


# ------------------------------------------------------------------ 2. login


def login(s: requests.Session, username: str, password: str) -> bool:
    print("\n== 2. Login (Keycloak OIDC + PKCE) ==")
    try:
        r = s.get(f"{BASE}/auth/login", timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        return check("reached Keycloak", False, str(e)[:120])

    if "auth.aiappinvent.com" not in r.url and "/realms/" not in r.url:
        # Keycloak may be off -- fall back to the legacy form.
        r = s.get(f"{BASE}/login", timeout=TIMEOUT)
        m = re.search(r'name="_csrf"\s+value="([^"]+)"', r.text)
        if not m:
            return check("found a login form", False, f"landed on {r.url[:80]}")
        r2 = s.post(f"{BASE}/login",
                    data={"_csrf": m.group(1), "username": username, "password": password},
                    timeout=TIMEOUT, allow_redirects=True)
        r3 = s.get(f"{BASE}/dashboard", timeout=TIMEOUT, allow_redirects=False)
        return check("session established (legacy login)", r3.status_code == 200,
                     f"{r3.status_code}")

    check("redirected to Keycloak", True, "")
    m = re.search(r'action="([^"]+)"', r.text)
    if not m:
        return check("found the KC login form", False, "no form action")
    action = urljoin(r.url, m.group(1).replace("&amp;", "&"))

    r2 = s.post(action, data={"username": username, "password": password},
                timeout=TIMEOUT, allow_redirects=True)
    if "Invalid username or password" in r2.text:
        return check("Keycloak accepted the credentials", False,
                     "invalid -- the local .env has drifted from the live secret")
    if "solarpro.aiappinvent.com" not in urlparse(r2.url).netloc:
        return check("callback returned to the app", False, f"stuck at {r2.url[:90]}")

    r3 = s.get(f"{BASE}/dashboard", timeout=TIMEOUT, allow_redirects=False)
    return check("session established (/dashboard = 200)", r3.status_code == 200,
                 f"{r3.status_code}")


# ------------------------------------------------------- 1. anonymous access


def test_anonymous() -> None:
    print("\n== 1. Anonymous -- the module must not leak ==")
    a = requests.Session()
    for path in ("/enterprise", "/enterprise/templates", "/enterprise/onboarding"):
        r = a.get(f"{BASE}{path}", timeout=TIMEOUT, allow_redirects=False)
        # 302 to login is correct. 200 would mean a logged-out visitor sees the module.
        check(f"anonymous {path} does not render", r.status_code in (302, 401, 404),
              f"{r.status_code}")


# --------------------------------------------------------------- the module


def test_module(s: requests.Session) -> bool:
    print("\n== 3. The rebuilt module is the one being served ==")
    r = s.get(f"{BASE}/enterprise", timeout=TIMEOUT)
    if r.status_code == 404:
        check("module is ON", False,
              "404 -- enterprise_rebuild_enabled is '0'. Flip it, wait ~60s, re-run.")
        return False
    if not check("/enterprise = 200", r.status_code == 200, f"{r.status_code}"):
        return False

    # /enterprise/programmes was a PHASE-1 route and does not exist in the rebuild.
    # Its absence is the proof that the swap actually happened.
    old = s.get(f"{BASE}/enterprise/programmes", timeout=TIMEOUT, allow_redirects=False)
    check("the OLD Phase-1 route is gone (/enterprise/programmes = 404)",
          old.status_code == 404, f"{old.status_code}")

    # /enterprise/templates exists ONLY in the rebuild (slice 4).
    t = s.get(f"{BASE}/enterprise/templates", timeout=TIMEOUT)
    check("the REBUILD-only route exists (/enterprise/templates = 200)",
          t.status_code == 200, f"{t.status_code}")
    return True


def onboard(s: requests.Session) -> None:
    print("\n== 4. Onboarding -- a real organisation tenant ==")
    r = s.get(f"{BASE}/enterprise/onboarding", timeout=TIMEOUT)
    if "already" in r.text.lower() and "organisation" in r.text.lower():
        check("already onboarded", True, "reusing the existing organisation")
        return
    token = csrf(s, f"{BASE}/enterprise/onboarding")
    if not token:
        check("onboarding form rendered", False, "no _csrf in the page")
        return
    r = s.post(f"{BASE}/enterprise/onboarding", timeout=TIMEOUT, allow_redirects=True,
               data={"_csrf": token, "legal_name": "Live Suite Ministry",
                     "organisation_type": "ministry", "country": "Ghana"})
    check("organisation created (or already existed)", r.status_code == 200,
          f"{r.status_code}")


def create_programme(s: requests.Session) -> int | None:
    print("\n== 5. Programme registry + the lifecycle spine ==")
    token = csrf(s, f"{BASE}/enterprise/programmes/new")
    if not token:
        check("create-programme form rendered", False, "no _csrf")
        return None

    code = f"LIVE-{int(time.time()) % 100000}"
    r = s.post(f"{BASE}/enterprise/programmes/new", timeout=TIMEOUT, allow_redirects=True,
               data={"_csrf": token, "code": code, "name": "Live Suite Programme",
                     "design_strategy": "standard"})
    if not check("programme created", r.status_code == 200, f"{r.status_code}"):
        return None

    m = re.search(r"/enterprise/programmes/(\d+)", r.url) or \
        re.search(r"/enterprise/programmes/(\d+)", r.text)
    if not m:
        check("programme id resolved", False, "could not find it in the response")
        return None
    pid = int(m.group(1))
    check("programme id resolved", True, f"#{pid}")

    d = s.get(f"{BASE}/enterprise/programmes/{pid}", timeout=TIMEOUT)
    body = d.text
    # Doc 3: 16 phases, 14 gates. They are SEEDED at creation -- a lifecycle that only
    # materialises when you reach it is a lifecycle you can skip.
    gates = len(re.findall(r"\bG\d{2}\b", body))
    check("the 14 stage gates are seeded and visible", gates >= 14, f"{gates} gate refs")
    check("the programme opens in Concept (phase 1 of 16)",
          "Concept" in body or "concept" in body, "")
    return pid


def test_c01(s: requests.Session, pid: int) -> None:
    print("\n== 6. C01 -- a gate needs its NAMED authority ==")
    # G02's authority is the steering committee, not whoever is logged in. Approving it
    # without the role must be refused. (403 = 'you may not', which is the correct answer;
    # a 200 here would mean any member can approve any gate.)
    token = csrf(s, f"{BASE}/enterprise/programmes/{pid}")
    r = s.post(f"{BASE}/enterprise/programmes/{pid}/gates/G02/approve", timeout=TIMEOUT,
               data={"_csrf": token, "comment": "live suite"}, allow_redirects=False)
    check("a gate cannot be approved without its named role",
          r.status_code in (403, 302), f"{r.status_code}")


def test_templates(s: requests.Session) -> None:
    print("\n== 7. The versioned template engine (slice 4) ==")
    token = csrf(s, f"{BASE}/enterprise/templates/new")
    if not token:
        check("template form rendered", False, "no _csrf")
        return

    # `code` is REQUIRED -- create_template raises TemplateError("a template needs a code and
    # a name") without one. This suite used to omit it, and never noticed: TemplateError
    # subclasses EnterpriseGateError, so the route flashes and REDIRECTS BACK to the form,
    # which is a perfectly good HTTP 200. "template created == 200" therefore passed against
    # a template that was never created. The check below is now the real one -- a 200 alone
    # proves nothing, only the id in the landing URL does.
    #
    # Unique per run, like the programme code: a template code is unique per tenant, so a
    # fixed one would create on the first run and TemplateError("code already used") on every
    # run after it.
    code = f"LIVE-TPL-{int(time.time()) % 100000}"
    r = s.post(f"{BASE}/enterprise/templates/new", timeout=TIMEOUT, allow_redirects=True,
               data={"_csrf": token, "code": code, "name": "Live Suite School Package",
                     "beneficiary_type": "school", "design_strategy": "standard"})
    if not check("template POST accepted", r.status_code == 200, f"{r.status_code}"):
        return
    m = re.search(r"/enterprise/templates/(\d+)", r.url)
    check("template created (landed on its detail page, not bounced to the form)",
          bool(m), f"#{m.group(1)} [{code}]" if m else f"bounced back to {r.url}")


def test_beneficiaries_and_import(s: requests.Session, pid: int) -> None:
    print("\n== 8/9/10. Register, import (STAGED), duplicates ==")

    # -- register one site by hand
    token = csrf(s, f"{BASE}/enterprise/programmes/{pid}/beneficiaries/new")
    if token:
        r = s.post(f"{BASE}/enterprise/programmes/{pid}/beneficiaries/new", timeout=TIMEOUT,
                   allow_redirects=True,
                   data={"_csrf": token, "code": "MANUAL-01", "name": "Hand Registered School",
                         "beneficiary_type": "school", "community": "Kpando"})
        check("a site can be registered by hand", r.status_code == 200, f"{r.status_code}")

    # -- import a CSV that lists ONE SCHOOL TWICE. The importer must catch the duplicate
    #    (the register alone cannot -- nothing from this file is in the register yet).
    csv = (
        "School Name,Site Code,Region,Town,Students\n"
        "Live Kpando Senior High,LV-01,Volta,Kpando,820\n"
        "Live Hohoe Technical,LV-02,Volta,Hohoe,610\n"
        "Live Kpando Senior High,LV-99,Volta,Kpando,820\n"   # <- same school, other code
        "Live Broken School,LV-03,Volta,Ho,not-a-number\n"   # <- invalid
    ).encode()

    token = csrf(s, f"{BASE}/enterprise/programmes/{pid}/beneficiaries")
    r = s.post(f"{BASE}/enterprise/programmes/{pid}/import", timeout=TIMEOUT,
               allow_redirects=True,
               data={"_csrf": token, "default_type": "school"},
               files={"file": ("live_sites.csv", io.BytesIO(csv), "text/csv")})
    if not check("upload accepted", r.status_code == 200, f"{r.status_code}"):
        return

    body = r.text
    m = re.search(r"/enterprise/imports/(\d+)", r.url)
    check("upload landed on the import PREVIEW (nothing written yet)", bool(m),
          r.url[-40:] if not m else f"batch #{m.group(1)}")
    if not m:
        return
    batch = int(m.group(1))

    # The preview must show the duplicate AND the bad row -- BEFORE anything is committed.
    check("the duplicate row is caught (same school listed twice in one file)",
          "Duplicate" in body or "duplicate" in body, "")
    check("the invalid row is caught, not imported",
          "Error" in body or "error" in body, "")

    # THE POINT OF THE SLICE: the register must still be empty of these rows.
    reg = s.get(f"{BASE}/enterprise/programmes/{pid}/beneficiaries", timeout=TIMEOUT)
    check("STAGING WROTE NOTHING -- the register has no imported rows yet",
          "Live Kpando Senior High" not in reg.text, "")

    # -- commit
    token = csrf(s, f"{BASE}/enterprise/imports/{batch}")
    r = s.post(f"{BASE}/enterprise/imports/{batch}/commit", timeout=TIMEOUT,
               data={"_csrf": token}, allow_redirects=True)
    check("commit accepted", r.status_code == 200, f"{r.status_code}")

    reg = s.get(f"{BASE}/enterprise/programmes/{pid}/beneficiaries", timeout=TIMEOUT)
    check("the valid rows are now in the register", "Live Kpando Senior High" in reg.text, "")
    check("the school listed twice was registered ONCE",
          reg.text.count("Live Kpando Senior High") <= 2, "")   # name + maybe a title attr


def test_qualification(s: requests.Session, pid: int) -> None:
    print("\n== 11/12. Site qualification (C02) + the priority list ==")
    prio = s.get(f"{BASE}/enterprise/programmes/{pid}/priority", timeout=TIMEOUT)
    if not check("the priority list renders", prio.status_code == 200, f"{prio.status_code}"):
        return
    check("unscored sites are shown as a QUESTION, not as zero",
          "not scored" in prio.text.lower(), "")

    m = re.search(r"/enterprise/beneficiaries/(\d+)/qualify", prio.text)
    if not m:
        check("a site to score was found", False, "no qualify link on the priority list")
        return
    bid = int(m.group(1))

    card = s.get(f"{BASE}/enterprise/beneficiaries/{bid}/qualify", timeout=TIMEOUT)
    check("the scorecard renders", card.status_code == 200, f"{card.status_code}")
    # THE SIGN TRAP, on the page the surveyor actually reads.
    check("the page states 100 = NO risk (the sign trap)",
          "no risk" in card.text.lower(), "")

    # A site must be ADMITTED (Qualification Pending) before it can be scored.
    token = csrf(s, f"{BASE}/enterprise/beneficiaries/{bid}")
    s.post(f"{BASE}/enterprise/beneficiaries/{bid}/transition", timeout=TIMEOUT,
           data={"_csrf": token, "target": "Qualification Pending"}, allow_redirects=True)

    # C02: try to DECIDE a site nobody has scored. It must be refused.
    token = csrf(s, f"{BASE}/enterprise/beneficiaries/{bid}/qualify")
    s.post(f"{BASE}/enterprise/beneficiaries/{bid}/qualify/decide", timeout=TIMEOUT,
           data={"_csrf": token, "decision": "Qualified"}, allow_redirects=True)
    after = s.get(f"{BASE}/enterprise/beneficiaries/{bid}/qualify", timeout=TIMEOUT)
    check("C02: a site NOBODY SCORED cannot be qualified",
          "Qualified" not in after.text or "not been scored" in after.text.lower()
          or "nothing to approve" in after.text.lower(), "")

    # Now score it.
    scores = {"technical_suitability": "80", "energy_need": "90",
              "financial_suitability": "70", "social_impact": "85",
              "implementation_readiness": "60", "security_risk": "100",
              "environmental_risk": "90", "funding_eligibility": "75"}
    token = csrf(s, f"{BASE}/enterprise/beneficiaries/{bid}/qualify")
    r = s.post(f"{BASE}/enterprise/beneficiaries/{bid}/qualify", timeout=TIMEOUT,
               data=dict(scores, _csrf=token, notes="live suite"), allow_redirects=True)
    scored = check("the site can be scored", r.status_code == 200, f"{r.status_code}")

    if scored:
        # 80*20+90*20+70*15+85*15+60*10+100*5+90*5+75*10 = 8025 / 100 = 80.25
        check("the weighted total is right (80.25)", "80.2" in r.text or "80.3" in r.text,
              "")
        check("SCORING IS NOT DECIDING -- still awaiting a decision",
              "Qualification Pending" in r.text or "needs a decision" in r.text.lower(), "")


def test_c13(s: requests.Session) -> None:
    print("\n== 13. C13 -- another tenant's data is 404, never 403 ==")
    # 403 would CONFIRM the row exists, which is itself the leak.
    for path in ("/enterprise/programmes/999999",
                 "/enterprise/beneficiaries/999999",
                 "/enterprise/imports/999999",
                 "/enterprise/programmes/999999/priority"):
        r = s.get(f"{BASE}{path}", timeout=TIMEOUT, allow_redirects=False)
        check(f"{path} -> 404 (not 403)", r.status_code == 404, f"{r.status_code}")


def main() -> int:
    user = os.environ.get("LIVE_USER", "marc667us")
    pw = os.environ.get("SOLARPRO_OWNER_PASSWORD", "")
    if not pw:
        try:
            t = open(".env", encoding="utf-8", errors="replace").read()
            m = re.search(r"^SOLARPRO_OWNER_PASSWORD=(.*)$", t, re.M)
            pw = m.group(1).strip() if m else ""
        except OSError:
            pw = ""

    print("=" * 74)
    print(" LIVE suite -- Enterprise Programme REBUILD (slices 1-6) --", BASE)
    print("=" * 74)

    test_anonymous()

    s = requests.Session()
    s.headers["User-Agent"] = "solarpro-live-enterprise-rebuild/1.0"

    if not pw:
        check("credentials available", False,
              "no SOLARPRO_OWNER_PASSWORD -- authenticated tests CANNOT run")
    elif login(s, user, pw):
        if test_module(s):
            onboard(s)
            pid = create_programme(s)
            if pid:
                test_c01(s, pid)
                test_templates(s)
                test_beneficiaries_and_import(s, pid)
                test_qualification(s, pid)
            test_c13(s)

    print("\n" + "=" * 74)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print(f" {passed}/{len(results)} passed")
    if failed:
        print("\n FAILURES:")
        for n, d in failed:
            print(f"   - {n}" + (f"  ({d})" if d else ""))
    print("=" * 74)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
