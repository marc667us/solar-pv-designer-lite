"""
Live test of report exports + view pages.

Goal:
- For an existing computed project (pid=7 from the panel test above), hit every
  /report/* HTML view AND every /report/*/pdf + /export/* download.
- Pass = HTTP 200 and Content-Type matches expected (text/html for views,
  application/pdf or application/vnd.openxmlformats-* / text/csv for downloads).

Inputs:
- BASE: live URL
- admin login
- pid: an existing pid with results saved

Outputs:
- one line per endpoint with status + content-type + length
- summary count at the end

Syntax notes:
- HEAD requests skip body download — fast and enough to verify content-type
- requests.Session keeps cookies so /report/* see us as logged in
"""
import requests
import re
import sys

BASE = "https://web-production-744af.up.railway.app"
PID = 7  # last project from the panel test


def csrf_of(html):
    """Extract _csrf hidden value (either attribute order)."""
    m = re.search(r'name=["\']_csrf["\']\s+value=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'value=["\']([^"\']+)["\']\s+name=["\']_csrf["\']', html)
    return m.group(1) if m else ""


def login(s):
    """POST /login as admin."""
    r = s.get(f"{BASE}/login", timeout=20)
    s.post(
        f"{BASE}/login",
        data={"username": "admin", "password": "SolarAdmin2026!", "_csrf": csrf_of(r.text)},
        timeout=20,
    )


# (label, path, expected substring of content-type)
PATHS = [
    # HTML view reports
    ("VIEW Inspection",    f"/project/{PID}/report/inspection",            "text/html"),
    ("VIEW PV",            f"/project/{PID}/report/pv",                    "text/html"),
    ("VIEW BOQ",           f"/project/{PID}/report/boq",                   "text/html"),
    ("VIEW Cable",         f"/project/{PID}/report/cable",                 "text/html"),
    ("VIEW Economic",      f"/project/{PID}/report/economic",              "text/html"),
    ("VIEW Installation",  f"/project/{PID}/report/installation",          "text/html"),
    ("VIEW Install Draw",  f"/project/{PID}/report/installation/drawings", "text/html"),
    ("VIEW Proposal",      f"/project/{PID}/report/proposal",              "text/html"),
    ("VIEW Energy",        f"/project/{PID}/report/energy",                "text/html"),
    # PDF downloads
    ("PDF Inspection",     f"/project/{PID}/report/inspection/pdf",        "application/pdf"),
    ("PDF PV",             f"/project/{PID}/report/pv/pdf",                "application/pdf"),
    ("PDF BOQ",            f"/project/{PID}/report/boq/pdf",               "application/pdf"),
    ("PDF Cable",          f"/project/{PID}/report/cable/pdf",             "application/pdf"),
    ("PDF Economic",       f"/project/{PID}/report/economic/pdf",          "application/pdf"),
    ("PDF Energy",         f"/project/{PID}/report/energy/pdf",            "application/pdf"),
    ("PDF Installation",   f"/project/{PID}/report/installation/pdf",      "application/pdf"),
    ("PDF Workplan",       f"/project/{PID}/report/workplan/pdf",          "application/pdf"),
    ("PDF Staffing",       f"/project/{PID}/report/staffing/pdf",          "application/pdf"),
    ("PDF Proposal",       f"/project/{PID}/report/proposal/pdf",          "application/pdf"),
    # Other exports
    ("EXP Excel",          f"/project/{PID}/export/excel",                 "spreadsheet"),
    ("EXP CSV",            f"/project/{PID}/export/csv",                   "text/csv"),
    ("EXP Docx",           f"/project/{PID}/export/docx",                  "word"),
]


def main():
    s = requests.Session()
    print("login...", end="", flush=True)
    login(s)
    print(" ok\n")
    P = "\x1b[92mPASS\x1b[0m"
    F = "\x1b[91mFAIL\x1b[0m"
    passed = 0
    failed = []
    for label, path, ctype_match in PATHS:
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
    print(f"\n=== RESULTS: {passed}/{len(PATHS)} PASS  {len(failed)} FAIL ===\n")
    if failed:
        print("Failures:")
        for label, path, status, ct_or_err, body in failed:
            print(f"  {label}  {path}")
            print(f"    status={status}  ct/err={ct_or_err}")
            if body:
                print(f"    body: {body[:160]!r}")


if __name__ == "__main__":
    main()
