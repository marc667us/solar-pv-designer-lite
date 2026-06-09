"""
Sales-readiness audit on the live Railway deployment.

Verifies every path a real prospect / customer would actually hit:
  1. Public landing pages load (no login required)
  2. New user can sign up via the public form
  3. Signed-up user can create a project end-to-end
  4. Reports + proposal render and download as PDF
  5. Paystack upgrade flow returns a real authorization URL
  6. Brevo sends a transactional email (already verified, but reconfirmed)

Inputs:
  BASE: live Railway URL (custom domain still pending cert)
Output:
  Pass/fail table per check + summary
Syntax notes:
  - requests.Session preserves cookies across the signup flow
  - re.search with non-greedy groups to pull csrf, location redirects, etc.
"""
import requests
import re
import sys
import time
import random

BASE = "https://web-production-744af.up.railway.app"


def csrf_of(html):
    """Pull _csrf hidden value from a Jinja page (tolerant of attribute order)."""
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else ""


PASS = "\x1b[92mPASS\x1b[0m"
FAIL = "\x1b[91mFAIL\x1b[0m"
WARN = "\x1b[93mWARN\x1b[0m"


def report(label, status, detail=""):
    print(f"  [{status}] {label:<55s} {detail}")


def main():
    results = []
    s = requests.Session()

    # ---- 1. Public landing page ----
    try:
        r = requests.get(BASE + "/", timeout=30)
        ok = r.status_code == 200 and len(r.text) > 1000
        report("Public landing page (/)", PASS if ok else FAIL,
               f"HTTP {r.status_code} bytes={len(r.text)}")
        results.append(ok)
    except Exception as e:
        report("Public landing page (/)", FAIL, str(e)[:60]); results.append(False)

    # ---- 2. Public assess page ----
    try:
        r = requests.get(BASE + "/assess", timeout=30)
        ok = r.status_code == 200
        report("Public assess form (/assess)", PASS if ok else FAIL, f"HTTP {r.status_code}")
        results.append(ok)
    except Exception as e:
        report("Public assess form (/assess)", FAIL, str(e)[:60]); results.append(False)

    # ---- 3. Public pricing/upgrade page ----
    try:
        r = requests.get(BASE + "/upgrade", timeout=30, allow_redirects=False)
        # /upgrade may redirect to /login if it's auth-only — both are valid states
        ok = r.status_code in (200, 302)
        loc = r.headers.get('Location', '')
        report("Pricing page (/upgrade)", PASS if ok else FAIL,
               f"HTTP {r.status_code} -> {loc[:40]}" if r.status_code == 302 else f"HTTP {r.status_code}")
        results.append(ok)
    except Exception as e:
        report("Pricing page (/upgrade)", FAIL, str(e)[:60]); results.append(False)

    # ---- 4. Register form available (route is /register not /signup) ----
    try:
        r = requests.get(BASE + "/register", timeout=30)
        has_form = '_csrf' in r.text and 'username' in r.text.lower()
        ok = r.status_code == 200 and has_form
        report("Register form renders + has CSRF", PASS if ok else FAIL,
               f"HTTP {r.status_code}")
        results.append(ok)
    except Exception as e:
        report("Register form", FAIL, str(e)[:60]); results.append(False)

    # ---- 5. New user registers end-to-end ----
    # Random username so we can re-run repeatedly without integrity errors
    uname = f"_audit_{int(time.time())}_{random.randint(100,999)}"
    pwd = "TestPass2026!"
    try:
        r = s.get(BASE + "/register", timeout=30)
        csrf = csrf_of(r.text)
        # Register POST fields per web_app.register():
        #   username, email, password, name, company, country, terms_agreed, _csrf
        r = s.post(BASE + "/register", data={
            "username": uname,
            "email": f"{uname}@audit.test",
            "password": pwd,
            "name": "Audit Customer",
            "company": "Audit Co.",
            "country": "Ghana",
            "terms_agreed": "on",        # required — registration fails without it
            "_csrf": csrf,
        }, timeout=30, allow_redirects=False)
        # Successful signup typically 302s to dashboard or shows the page with a flash msg
        if r.status_code in (301, 302):
            ok = True
            detail = f"302 -> {r.headers.get('Location','?')[:40]}"
        else:
            # Inline error or already-logged-in
            ok = "dashboard" in r.text.lower() or "logout" in r.text.lower()
            detail = f"HTTP {r.status_code} {'logged-in' if ok else 'form-error'}"
        report(f"Signup creates user '{uname}'", PASS if ok else FAIL, detail)
        results.append(ok)
    except Exception as e:
        report("Signup end-to-end", FAIL, str(e)[:60]); results.append(False)

    # ---- 6. Newly-signed-up user can create a project + reach results ----
    if results[-1]:
        try:
            r = s.get(BASE + "/project/new", timeout=30)
            csrf = csrf_of(r.text)
            r = s.post(BASE + "/project/new",
                       data={"name": "_audit_project", "client": "Audit",
                             "_csrf": csrf},
                       timeout=30, allow_redirects=False)
            pid_m = re.search(r"/project/(\d+)/", r.headers.get("Location", ""))
            if not pid_m:
                report("New-user project creation", FAIL, "no pid in redirect")
                results.append(False)
            else:
                pid = pid_m.group(1)
                # Submit location
                r = s.get(f"{BASE}/project/{pid}/location", timeout=30)
                s.post(f"{BASE}/project/{pid}/location", data={
                    "_csrf": csrf_of(r.text), "country": "Ghana",
                    "region": "Greater Accra", "tariff": "2.5",
                    "system_type": "off-grid", "phase": "single",
                    "voltage": "48", "autonomy": "1", "chemistry": "LiFePO4",
                    "panel_wp": "400", "mounting_type": "rooftop_pitched",
                    "tilt_angle": "15", "azimuth": "0", "system_losses": "14",
                    "inverter_eff": "95", "battery_dod": "80",
                    "performance_ratio": "75", "supply_markup_pct": "8",
                    "install_rate_pct": "15", "funding_mode": "loan",
                }, timeout=30, allow_redirects=False)
                # Submit loads → triggers calculation
                r = s.get(f"{BASE}/project/{pid}/loads", timeout=30)
                rr = s.post(f"{BASE}/project/{pid}/loads", data=[
                    ("_csrf", csrf_of(r.text)),
                    ("load_cat[]", "Lighting"), ("load_name[]", "Bulb"),
                    ("load_watt[]", "10"), ("load_qty[]", "5"),
                    ("load_hours[]", "4"), ("load_df[]", "1.0"),
                ], timeout=30, allow_redirects=False)
                ok = rr.status_code in (301, 302)
                report(f"New user runs full project flow (pid {pid})",
                       PASS if ok else FAIL, f"loads HTTP {rr.status_code}")
                results.append(ok)
        except Exception as e:
            report("New-user project flow", FAIL, str(e)[:80]); results.append(False)
    else:
        report("New-user project flow", WARN, "skipped (signup failed)")
        results.append(False)

    # ---- 7. Proposal PDF for that customer-created project ----
    if results[-1]:
        try:
            r = s.get(f"{BASE}/project/{pid}/report/proposal/pdf",
                      timeout=60, stream=True)
            head = r.raw.read(8) if r.raw else b""
            r.close()
            ok = r.status_code == 200 and head.startswith(b"%PDF")
            report("Proposal PDF downloads (customer)", PASS if ok else FAIL,
                   f"HTTP {r.status_code} ct={r.headers.get('Content-Type','')[:30]}")
            results.append(ok)
        except Exception as e:
            report("Proposal PDF", FAIL, str(e)[:60]); results.append(False)
    else:
        report("Proposal PDF (customer)", WARN, "skipped"); results.append(False)

    # ---- 8. Paystack init returns a real authorization URL ----
    if results[-2]:
        try:
            r = s.get(f"{BASE}/upgrade", timeout=30)
            up_csrf = csrf_of(r.text)
            # plan=professional triggers /paystack/initialize for $49 monthly
            r = s.post(f"{BASE}/paystack/initialize",
                       data={"_csrf": up_csrf, "plan": "professional",
                             "billing_cycle": "monthly"},
                       timeout=30, allow_redirects=False)
            body = r.text
            # Successful init either 302s to checkout.paystack.com or returns JSON with the URL
            if r.status_code in (301, 302) and "paystack" in r.headers.get("Location", "").lower():
                report("Paystack init returns authorization URL", PASS,
                       f"302 → {r.headers.get('Location','')[:50]}")
                results.append(True)
            elif "checkout.paystack.com" in body or "authorization_url" in body:
                report("Paystack init returns authorization URL", PASS,
                       "URL in body")
                results.append(True)
            else:
                report("Paystack init", FAIL,
                       f"HTTP {r.status_code} no paystack URL")
                results.append(False)
        except Exception as e:
            report("Paystack init", FAIL, str(e)[:60]); results.append(False)
    else:
        report("Paystack init", WARN, "skipped"); results.append(False)

    # ---- 9. Confirm Brevo email send still working (fresh session) ----
    try:
        s_admin = requests.Session()
        r = s_admin.get(BASE + "/login", timeout=30)
        s_admin.post(BASE + "/login", data={
            "username": "admin", "password": "SolarAdmin2026!",
            "_csrf": csrf_of(r.text)}, timeout=30)
        # Pull a fresh CSRF from /admin (the session-scoped one is from /login
        # and may be stale once the session was upgraded to authenticated).
        r = s_admin.get(BASE + "/admin", timeout=30)
        admin_csrf = csrf_of(r.text)
        r = s_admin.post(BASE + "/admin/ops/email/test",
                         data={"_csrf": admin_csrf}, timeout=60)
        try:
            js = r.json()
        except Exception:
            report("Brevo email send", FAIL,
                   f"HTTP {r.status_code} non-JSON: {r.text[:60]!r}")
            results.append(False)
            return
        ok = js.get("status") == "ok" and js.get("provider") == "brevo"
        report("Email via Brevo sends ok", PASS if ok else FAIL,
               f"{js.get('provider','?')}/{js.get('status','?')}")
        results.append(ok)
    except Exception as e:
        report("Brevo email send", FAIL, str(e)[:60]); results.append(False)

    passed = sum(1 for r in results if r)
    print(f"\n=== Sales readiness: {passed}/{len(results)} PASS ===")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
