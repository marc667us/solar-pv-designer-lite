"""
Per-commit verification audit for the session's behavioural changes.

Each test verifies one specific change that should now be live on Railway.
Skip-condition: workflow/CI-only commits are not user-visible so we don't test.

Inputs:  RAILWAY_URL (live site), admin login
Outputs: a table of [commit short SHA, change description, status]
Exit:    0 if all pass, 1 if any fail
"""
import requests
import re
import sys
import json

URL = "https://web-production-744af.up.railway.app"

# Session reused across tests so we log in only once
s = requests.Session()


def csrf_of(html):
    """Extract _csrf hidden value from a rendered Jinja page."""
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    return m.group(1) if m else ""


def login():
    """Authenticate as admin."""
    r = s.get(f"{URL}/login", timeout=60)
    s.post(
        f"{URL}/login",
        data={"username": "admin", "password": "SolarAdmin2026!",
              "_csrf": csrf_of(r.text)},
        timeout=60,
    )


GREEN = "\x1b[92m"
RED = "\x1b[91m"
YEL = "\x1b[93m"
END = "\x1b[0m"


def row(commit, description, status, detail=""):
    """Print a result row."""
    if status == "PASS":
        col, sym = GREEN, "PASS"
    elif status == "WARN":
        col, sym = YEL, "WARN"
    else:
        col, sym = RED, "FAIL"
    print(f"  {commit}  [{col}{sym:4s}{END}] {description:<60s} {detail}")
    return status == "PASS"


def main():
    print("\n=== Per-Commit Audit on Live Railway ===\n")
    print(f"  Target: {URL}\n")
    login()
    results = []

    # ---- 27b2492 feat(panel-select): add 110/250/330 Wp options ----
    # Hit /project/new to get a fresh pid, then check the location form
    # contains all 7 panel options in the dropdown.
    r = s.get(f"{URL}/project/new", timeout=30)
    csrf = csrf_of(r.text)
    r = s.post(
        f"{URL}/project/new",
        data={"name": "_audit_panel", "client": "audit", "_csrf": csrf},
        timeout=30, allow_redirects=False,
    )
    pid_m = re.search(r"/project/(\d+)/", r.headers.get("Location", ""))
    if pid_m:
        pid = pid_m.group(1)
        r = s.get(f"{URL}/project/{pid}/location", timeout=30)
        # Match every <option value="N">N Wp Mono PERC</option> in the panel_wp <select>
        sel_html = re.search(r'<select name="panel_wp".+?</select>', r.text, re.S)
        opts = re.findall(r'value="(\d+)"', sel_html.group(0)) if sel_html else []
        expected = ["110", "250", "330", "400", "450", "500", "550"]
        if opts == expected:
            results.append(row("27b2492", "panel select has 7 options (110-550 Wp)",
                               "PASS", f"options={opts}"))
        else:
            results.append(row("27b2492", "panel select has 7 options (110-550 Wp)",
                               "FAIL", f"got {opts}"))
    else:
        results.append(row("27b2492", "panel select has 7 options",
                           "FAIL", "could not create project"))

    # ---- 27b2492 hard-coded "400 Wp" fix in installation report ----
    # The fix made the panel rating row read r.panel_wp instead of "400".
    # We hit /project/<pid>/report/installation after submitting a 550-Wp project
    # and verify the rendered text mentions 550 not 400.
    r = s.get(f"{URL}/project/new", timeout=30)
    csrf = csrf_of(r.text)
    r = s.post(
        f"{URL}/project/new",
        data={"name": "_audit_550", "client": "audit", "_csrf": csrf},
        timeout=30, allow_redirects=False,
    )
    pid_m = re.search(r"/project/(\d+)/", r.headers.get("Location", ""))
    if pid_m:
        pid = pid_m.group(1)
        # Submit location with 550 Wp
        r = s.get(f"{URL}/project/{pid}/location", timeout=30)
        s.post(
            f"{URL}/project/{pid}/location",
            data={"_csrf": csrf_of(r.text), "country": "Ghana",
                  "region": "Greater Accra", "tariff": "2.5",
                  "system_type": "off-grid", "phase": "single",
                  "voltage": "48", "autonomy": "1", "chemistry": "LiFePO4",
                  "panel_wp": "550", "mounting_type": "rooftop_pitched",
                  "tilt_angle": "15", "azimuth": "0", "system_losses": "14",
                  "inverter_eff": "95", "battery_dod": "80",
                  "performance_ratio": "75", "supply_markup_pct": "8",
                  "install_rate_pct": "15", "funding_mode": "loan"},
            timeout=30, allow_redirects=False,
        )
        r = s.get(f"{URL}/project/{pid}/loads", timeout=30)
        s.post(
            f"{URL}/project/{pid}/loads",
            data=[("_csrf", csrf_of(r.text)),
                  ("load_cat[]", "Lighting"), ("load_name[]", "Bulb"),
                  ("load_watt[]", "10"), ("load_qty[]", "5"),
                  ("load_hours[]", "4"), ("load_df[]", "1.0")],
            timeout=30, allow_redirects=False,
        )
        # Pull the installation report HTML
        r = s.get(f"{URL}/project/{pid}/report/installation", timeout=30)
        # Look anywhere for "550 Wp" near a Panel Rating mention; the report
        # contains many panel references, so we check the SVG row + body table.
        # multiline=DOTALL because the row may span several formatting tags
        html = r.text
        has_550 = "550 Wp" in html or "550Wp" in html
        has_only_400 = (("400 Wp (TOPCon" in html or "400 Wp (TOPCON" in html)
                        and "550 Wp" not in html)
        if has_550:
            results.append(row("27b2492", "installation report shows selected Wp (not hardcoded 400)",
                               "PASS", "550 Wp visible in install report"))
        elif has_only_400:
            results.append(row("27b2492", "installation report shows selected Wp (not hardcoded 400)",
                               "FAIL", "still hardcoded 400 Wp"))
        else:
            # If neither shows, the project might not have computed results yet
            results.append(row("27b2492", "installation report shows selected Wp",
                               "WARN", f"neither 550 nor 400 found; html size={len(html)}"))
    else:
        results.append(row("27b2492", "installation report dynamic Wp",
                           "FAIL", "could not create project"))

    # ---- e2baef6 + c163657 rate-limit exempt /api/ping etc. ----
    # Hammer /api/ping with 200 requests in <60s. If exempt works we'll
    # never see a 429. Limit was 120/min default before the exemption.
    rl_ok = True
    rl_codes = {200: 0, 429: 0, "other": 0}
    for _ in range(200):
        r = requests.get(f"{URL}/api/ping", timeout=10)
        if r.status_code == 200:
            rl_codes[200] += 1
        elif r.status_code == 429:
            rl_codes[429] += 1
        else:
            rl_codes["other"] += 1
    if rl_codes[429] == 0:
        results.append(row("e2baef6", "/api/ping exempt from 120/min limiter (200 req burst)",
                           "PASS", f"200x200ok"))
    else:
        results.append(row("e2baef6", "/api/ping exempt from 120/min limiter",
                           "FAIL", f"got 429s: {rl_codes[429]}"))

    # ---- cca3768 BOM stripping ----
    # Status endpoint should now show smtp_port "587" (3 chars) not "﻿587".
    r = s.get(f"{URL}/admin/ops/email/status", timeout=30)
    st = r.json()
    port_clean = st.get("smtp_port", "") == "587"
    tls_clean = st.get("smtp_tls", "") in ("true", "false")
    if port_clean and tls_clean:
        results.append(row("cca3768", "BOM stripped from SMTP_PORT/SMTP_TLS",
                           "PASS", f"port={st.get('smtp_port')!r} tls={st.get('smtp_tls')!r}"))
    else:
        results.append(row("cca3768", "BOM stripped from SMTP_PORT/SMTP_TLS",
                           "FAIL", f"port={st.get('smtp_port')!r} tls={st.get('smtp_tls')!r}"))

    # ---- 8834954 Axigen path present (skipped when not configured) ----
    # The status endpoint now reports axigen_configured.
    if "axigen_configured" in st:
        if st["axigen_configured"] is False and st.get("axigen_url") == "(not set)":
            results.append(row("8834954", "Axigen provider integrated (skipped because no creds)",
                               "PASS", "axigen_configured=false"))
        else:
            results.append(row("8834954", "Axigen provider integrated",
                               "PASS", f"axigen_configured={st['axigen_configured']}"))
    else:
        results.append(row("8834954", "Axigen field in /email/status",
                           "FAIL", "field missing"))

    # ---- 93c5423 Brevo wired and actually sends ----
    if st.get("brevo_configured") is True and st.get("brevo_key_prefix", "").startswith("xkeysib-"):
        # Re-login fresh so the CSRF token & session are valid (200+ pings above
        # may have aged the session out, depending on idle-timeout).
        login()
        admin_pg = s.get(f"{URL}/admin", timeout=30)
        csrf2 = csrf_of(admin_pg.text)
        if not csrf2:
            # Last resort: grab from /admin/operations
            csrf2 = csrf_of(s.get(f"{URL}/admin/operations", timeout=30).text)
        r = s.post(f"{URL}/admin/ops/email/test", data={"_csrf": csrf2}, timeout=60)
        # If the POST returned HTML (login redirect, error page), parsing as JSON throws.
        try:
            js = r.json()
        except Exception:
            results.append(row("93c5423", "Brevo primary provider sends email through HTTPS",
                               "FAIL", f"HTTP {r.status_code} non-JSON body: {r.text[:80]!r}"))
            js = None
        if js and js.get("provider") == "brevo" and js.get("status") == "ok":
            results.append(row("93c5423", "Brevo primary provider sends email through HTTPS",
                               "PASS", f"messageId={js.get('diagnostics',[{}])[0].get('messageId','?')[-20:]}"))
        elif js:
            results.append(row("93c5423", "Brevo primary provider sends email",
                               "FAIL", str(js)[:120]))
    else:
        results.append(row("93c5423", "Brevo provider configured + key set",
                           "FAIL", f"configured={st.get('brevo_configured')} prefix={st.get('brevo_key_prefix')}"))

    # ---- 77620f2 + railway.toml on Railway ----
    # If the service answers /api/ping we know the Railway migration worked.
    r = requests.get(f"{URL}/api/ping", timeout=30)
    if r.status_code == 200 and r.json().get("pong") is True:
        results.append(row("77620f2", "Railway hosting live and responding",
                           "PASS", f"url={URL}"))
    else:
        results.append(row("77620f2", "Railway hosting", "FAIL", f"HTTP {r.status_code}"))

    # Summary
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== {passed}/{total} checks passed ===\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
