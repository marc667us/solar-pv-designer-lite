"""
Live end-to-end test of the referral program on the Railway-hosted SolarPro.

Tests, in order:
  1.  /referrals (admin login)            -> renders, code shown
  2.  /r/<admin_code>                     -> 302 + cookie set
  3.  New visitor lands on /r/<code>      -> cookie carried into /register
  4.  Register completes                  -> 302 to dashboard, user created
  5.  Admin /referrals signups stat       -> increments by 1
  6.  Recent referrals table              -> shows the new user row
  7.  New user has own code              -> different from admin's
  8.  /r/<bad_code> with invalid code     -> still works, just no real referrer
  9.  ?ref=<code> query param (no /r/)    -> base.html JS cookie capture
  10. Signup with invalid ref cookie      -> succeeds, no referred_by

Inputs:  BASE Railway URL, admin credentials
Output:  PASS/FAIL per check + summary
"""
import requests
import re
import sys
import time
import random

BASE = "https://web-production-744af.up.railway.app"
GREEN = "\x1b[92m"
RED = "\x1b[91m"
END = "\x1b[0m"
PASS = f"{GREEN}PASS{END}"
FAIL = f"{RED}FAIL{END}"


def csrf_of(html):
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else ""


def report(label, ok, detail=""):
    print(f"  [{PASS if ok else FAIL}] {label:<55s} {detail}")
    return ok


def admin_session():
    """Return a logged-in admin session."""
    s = requests.Session()
    r = s.get(f"{BASE}/login", timeout=30)
    s.post(f"{BASE}/login",
           data={"username": "admin", "password": "SolarAdmin2026!",
                 "_csrf": csrf_of(r.text)}, timeout=30)
    return s


def main():
    results = []
    admin = admin_session()

    # 1. Admin /referrals renders + has a referral code in the page
    r = admin.get(f"{BASE}/referrals", timeout=30)
    code_m = re.search(r'monospace[^>]*>([A-Z0-9]+)<', r.text)
    admin_code = code_m.group(1) if code_m else None
    results.append(report("1. /referrals renders for admin + code visible",
                          r.status_code == 200 and admin_code is not None,
                          f"HTTP {r.status_code} code={admin_code}"))

    # Pull baseline signup count from the same page so we can verify a +1 later
    base_m = re.search(r'class="v blue">(\d+)', r.text)
    baseline_signups = int(base_m.group(1)) if base_m else 0

    # 2. /r/<admin_code> returns 302 + ref_code cookie
    visitor1 = requests.Session()
    r = visitor1.get(f"{BASE}/r/{admin_code}", timeout=30, allow_redirects=False)
    cookie_set = ("ref_code" in r.headers.get("Set-Cookie", ""))
    results.append(report("2. /r/<code> sets cookie + 302 redirect",
                          r.status_code == 302 and cookie_set,
                          f"HTTP {r.status_code} cookie_set={cookie_set}"))

    # 3. Visitor session keeps cookie when they hit /register
    r = visitor1.get(f"{BASE}/register", timeout=30)
    has_ref = "ref_code" in str(visitor1.cookies)
    results.append(report("3. Cookie survives navigation to /register",
                          has_ref, f"cookies={list(visitor1.cookies.keys())}"))

    # 4. Visitor registers, gets 302 to dashboard
    uname1 = f"reflive1_{int(time.time())}_{random.randint(100,999)}"
    csrf = csrf_of(r.text)
    r = visitor1.post(f"{BASE}/register", data={
        "username": uname1, "email": f"{uname1}@audit.x",
        "password": "TestPass2026!", "name": "Live Ref 1",
        "company": "Test", "country": "Ghana",
        "terms_agreed": "on", "_csrf": csrf
    }, timeout=30, allow_redirects=False)
    results.append(report("4. New visitor signup via /r/ flow succeeds",
                          r.status_code in (301, 302),
                          f"HTTP {r.status_code} -> {r.headers.get('Location','?')[:30]}"))

    # 5. Admin signup count incremented
    time.sleep(1)
    r = admin.get(f"{BASE}/referrals", timeout=30)
    new_m = re.search(r'class="v blue">(\d+)', r.text)
    new_signups = int(new_m.group(1)) if new_m else baseline_signups
    results.append(report(f"5. Admin signup stat went from {baseline_signups} -> ?",
                          new_signups > baseline_signups,
                          f"now {new_signups}"))

    # 6. The newly-registered username appears in the recent table
    found_in_recent = uname1 in r.text
    results.append(report("6. New user appears in 'Recent referrals' table",
                          found_in_recent, f"found={found_in_recent}"))

    # 7. The new user has their own code (different from admin's)
    r = visitor1.get(f"{BASE}/referrals", timeout=30)
    own_m = re.search(r'monospace[^>]*>([A-Z0-9]+)<', r.text)
    own_code = own_m.group(1) if own_m else None
    different = own_code is not None and own_code != admin_code
    results.append(report("7. New user has unique own code != admin's",
                          different, f"new={own_code} admin={admin_code}"))

    # 8. Invalid /r/<garbage> still returns 302 to landing (graceful no-op)
    junk = requests.Session()
    r = junk.get(f"{BASE}/r/THISCODE_DOES_NOT_EXIST_ZZZ", timeout=30, allow_redirects=False)
    results.append(report("8. Invalid /r/<code> still 302s to landing",
                          r.status_code == 302,
                          f"HTTP {r.status_code}"))

    # 9. ?ref=<code> on landing should set cookie via base.html JS.
    # JS runs only in a browser, so we can't fully test it here without a headless
    # browser. We verify the JS is present in the page source instead.
    r = requests.get(f"{BASE}/?ref={admin_code}", timeout=30)
    js_present = "REF_COOKIE_CAPTURE_v1" in r.text
    results.append(report("9. base.html injects ref-cookie JS on every page",
                          js_present, f"sigil_found={js_present}"))

    # 10. Signup with a never-existed cookie value succeeds with no referred_by
    visitor2 = requests.Session()
    visitor2.cookies.set("ref_code", "BADGARBA",
                         domain="web-production-744af.up.railway.app", path="/")
    r = visitor2.get(f"{BASE}/register", timeout=30)
    csrf = csrf_of(r.text)
    uname2 = f"reflive2_{int(time.time())}_{random.randint(100,999)}"
    r = visitor2.post(f"{BASE}/register", data={
        "username": uname2, "email": f"{uname2}@audit.x",
        "password": "TestPass2026!", "name": "Bad Ref",
        "company": "Test", "country": "Ghana",
        "terms_agreed": "on", "_csrf": csrf
    }, timeout=30, allow_redirects=False)
    # Should succeed; we can't check referred_by directly without admin DB query
    results.append(report("10. Signup with invalid ref cookie succeeds (graceful)",
                          r.status_code in (301, 302),
                          f"HTTP {r.status_code}"))

    passed = sum(1 for r in results if r)
    print(f"\n=== Referral live tests: {passed}/{len(results)} PASS ===")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
