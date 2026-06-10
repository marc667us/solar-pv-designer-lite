"""
Live test of report exports + view pages.

Goal:
- Seed a fresh project (location + loads -> results computed), then hit every
  /report/* HTML view AND every /report/*/pdf + /export/* download.
- Pass = HTTP 200 and Content-Type matches expected (text/html for views,
  application/pdf or application/vnd.openxmlformats-* / text/csv for downloads).

Inputs:
- SOLARPRO_BASE        (default https://solarpro.aiappinvent.com)
- SOLARPRO_ADMIN_PASSWORD (required)

Outputs:
- one line per endpoint with status + content-type + length
- summary count at the end

Syntax notes:
- HEAD requests skip body download — fast and enough to verify content-type
- requests.Session keeps cookies so /report/* see us as logged in
"""
import os
import requests
import re
import sys
import time

BASE     = os.environ.get("SOLARPRO_BASE", "https://solarpro.aiappinvent.com")
ADMIN_PW = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "")
if not ADMIN_PW:
    sys.exit("Set SOLARPRO_ADMIN_PASSWORD env var (admin login passphrase).")


def csrf_of(html):
    """Extract _csrf hidden value (either attribute order)."""
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']_csrf["\']', html)
    return m.group(1) if m else ""


def post(s, url, data):
    """POST with auto-injected CSRF token from the GET of the same url."""
    token = csrf_of(s.get(url, timeout=20).text)
    data = dict(data)
    if token:
        data["_csrf"] = token
    return s.post(url, data=data, allow_redirects=True, timeout=40)


def extract_pid(url):
    parts = url.rstrip("/").split("/")
    for i, p in enumerate(parts):
        if p == "project" and i + 1 < len(parts):
            try: return int(parts[i + 1])
            except: pass
    return None


def login(s):
    """POST /login as admin."""
    s.get(BASE + "/", timeout=60)
    post(s, BASE + "/login", {"username": "admin", "password": ADMIN_PW})


def seed_project(s):
    """Create a project, set location, submit loads, fetch results. Returns pid."""
    r = post(s, BASE + "/project/new", {"name": f"ExportTest-{int(time.time())%10000}", "client_name": "Test"})
    pid = extract_pid(r.url)
    if pid is None:
        sys.exit(f"could not create project; landed at {r.url}")
    post(s, BASE + f"/project/{pid}/location", {
        "country":"Ghana","region":"Greater Accra","tariff":"1.9688","currency":"GHS","symbol":"GHS",
        "funding_mode":"cash","chemistry":"LiFePO4","autonomy":"1","voltage":"48","panel_wp":"400",
        "system_type":"off-grid","phase":"single","tilt_angle":"15","azimuth":"0",
        "system_losses":"14","inverter_eff":"95","battery_dod":"80","performance_ratio":"75",
        "supply_markup_pct":"8","install_rate_pct":"15",
    })
    post(s, BASE + f"/project/{pid}/loads", {
        "load_name[]":["LED Lights","Fan","Fridge"],
        "load_watt[]":["10","75","150"], "load_qty[]":["4","1","1"],
        "load_hours[]":["6","8","24"], "load_cat[]":["Lighting","Cooling","Appliances"],
        "load_df[]":["75","65","50"],
    })
    s.get(BASE + f"/project/{pid}/results", timeout=30)
    return pid


def main():
    s = requests.Session()
    print("login...", end="", flush=True)
    login(s)
    print(" ok")
    print("seeding project...", end="", flush=True)
    pid = seed_project(s)
    print(f" pid={pid}\n")

    # (label, path, expected substring of content-type) — built from the seeded pid
    paths = [
        # HTML view reports
        ("VIEW Inspection",    f"/project/{pid}/report/inspection",            "text/html"),
        ("VIEW PV",            f"/project/{pid}/report/pv",                    "text/html"),
        ("VIEW BOQ",           f"/project/{pid}/report/boq",                   "text/html"),
        ("VIEW Cable",         f"/project/{pid}/report/cable",                 "text/html"),
        ("VIEW Economic",      f"/project/{pid}/report/economic",              "text/html"),
        ("VIEW Installation",  f"/project/{pid}/report/installation",          "text/html"),
        ("VIEW Install Draw",  f"/project/{pid}/report/installation/drawings", "text/html"),
        ("VIEW Proposal",      f"/project/{pid}/report/proposal",              "text/html"),
        ("VIEW Energy",        f"/project/{pid}/report/energy",                "text/html"),
        # PDF downloads
        ("PDF Inspection",     f"/project/{pid}/report/inspection/pdf",        "application/pdf"),
        ("PDF PV",             f"/project/{pid}/report/pv/pdf",                "application/pdf"),
        ("PDF BOQ",            f"/project/{pid}/report/boq/pdf",               "application/pdf"),
        ("PDF Cable",          f"/project/{pid}/report/cable/pdf",             "application/pdf"),
        ("PDF Economic",       f"/project/{pid}/report/economic/pdf",          "application/pdf"),
        ("PDF Energy",         f"/project/{pid}/report/energy/pdf",            "application/pdf"),
        ("PDF Installation",   f"/project/{pid}/report/installation/pdf",      "application/pdf"),
        ("PDF Workplan",       f"/project/{pid}/report/workplan/pdf",          "application/pdf"),
        ("PDF Staffing",       f"/project/{pid}/report/staffing/pdf",          "application/pdf"),
        ("PDF Proposal",       f"/project/{pid}/report/proposal/pdf",          "application/pdf"),
        # Other exports
        ("EXP Excel",          f"/project/{pid}/export/excel",                 "spreadsheet"),
        ("EXP CSV",            f"/project/{pid}/export/csv",                   "text/csv"),
        ("EXP Docx",           f"/project/{pid}/export/docx",                  "word"),
    ]
    P = "\x1b[92mPASS\x1b[0m"
    F = "\x1b[91mFAIL\x1b[0m"
    passed = 0
    failed = []
    for label, path, ctype_match in paths:
        try:
            r = s.get(f"{BASE}{path}", timeout=60, allow_redirects=False, stream=True)
            ct = r.headers.get("Content-Type", "").lower()
            length = r.headers.get("Content-Length", "?")
            # for the content body we only need a small chunk to confirm it's not a Flask error
            body_head = r.raw.read(512) if r.raw else b""
            r.close()
            # accept 200 with matching content-type OR 200 if content starts with PDF magic
            ok = r.status_code == 200 and (ctype_match in ct or (ctype_match == "application/pdf" and body_head.startswith(b"%PDF")))
            tag = P if ok else F
            sys.stdout.buffer.write(
                (f"[{tag}] {label:<24}  HTTP {r.status_code}  ct={ct[:35]:<35} len={length}\n").encode("utf-8", "replace")
            )
            if ok:
                passed += 1
            else:
                # capture first bit of body for diagnosis
                snippet = body_head[:200].decode("utf-8", "replace")
                failed.append((label, path, r.status_code, ct, snippet))
        except Exception as e:
            sys.stdout.buffer.write((f"[{F}] {label:<24}  EXCEPTION: {e}\n").encode("utf-8", "replace"))
            failed.append((label, path, "EXC", str(e), ""))
    print(f"\n=== RESULTS: {passed}/{len(paths)} PASS  {len(failed)} FAIL ===\n")
    if failed:
        print("Failures:")
        for label, path, status, ct_or_err, body in failed:
            print(f"  {label}  {path}")
            print(f"    status={status}  ct/err={ct_or_err}")
            if body:
                print(f"    body: {body[:160]!r}")


if __name__ == "__main__":
    main()
