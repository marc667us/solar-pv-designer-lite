"""
Smoke test the 4 new admin-ops endpoints under a real admin login.

Verifies:
  - login as admin succeeds
  - each endpoint returns HTTP 200
  - each download endpoint sets Content-Disposition: attachment
  - JSON endpoints return valid JSON with expected keys
  - logs/archive (POST) returns a JSON status

Exit 0 on PASS, non-zero on FAIL.
"""
import json
import os
import re
import sys

import requests

BASE = os.environ.get("SMOKE_BASE", "http://localhost:5000")
ADMIN_USER = "admin"
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "robin-grain-aware-prairie")


def get_csrf(s, path="/login"):
    r = s.get(BASE + path, timeout=10)
    m = re.search(r'name="_csrf" value="([^"]+)"', r.text)
    return m.group(1) if m else ""


def login(s):
    csrf = get_csrf(s)
    r = s.post(BASE + "/login", data={
        "_csrf": csrf, "username": ADMIN_USER, "password": ADMIN_PASS,
    }, allow_redirects=True, timeout=15)
    if r.status_code != 200 or "/login" in r.url:
        print(f"FAIL: login redirected to {r.url} (HTTP {r.status_code})")
        sys.exit(2)
    # Pull dashboard to confirm session is alive
    r = s.get(BASE + "/admin", allow_redirects=False, timeout=10)
    if r.status_code != 200:
        print(f"FAIL: /admin returned {r.status_code} after login (expected 200)")
        sys.exit(3)
    print(f"  login OK as {ADMIN_USER!r}")


def check_download_json(s, path, must_contain_keys):
    print(f"\n[check] GET {path}")
    r = s.get(BASE + path, allow_redirects=False, timeout=15)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  FAIL: expected 200, got {r.status_code}")
        return False
    cd = r.headers.get("Content-Disposition", "")
    ct = r.headers.get("Content-Type", "")
    print(f"  Content-Type:        {ct!r}")
    print(f"  Content-Disposition: {cd!r}")
    if "attachment" not in cd.lower():
        print(f"  FAIL: Content-Disposition missing 'attachment'")
        return False
    if "json" not in ct.lower():
        print(f"  FAIL: Content-Type missing 'json'")
        return False
    try:
        body = r.json()
    except Exception as e:
        print(f"  FAIL: response body not valid JSON: {e}")
        return False
    missing = [k for k in must_contain_keys if k not in body]
    if missing:
        print(f"  FAIL: JSON missing keys: {missing}")
        return False
    print(f"  body keys: {list(body.keys())}")
    print(f"  PASS")
    return True


def check_archive_post(s):
    print(f"\n[check] POST /admin/ops/logs/archive")
    csrf = get_csrf(s, "/admin/operations")
    r = s.post(BASE + "/admin/ops/logs/archive",
               headers={"X-CSRF-Token": csrf},
               data={"_csrf": csrf}, timeout=15)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  FAIL: expected 200, got {r.status_code}; body: {r.text[:200]}")
        return False
    try:
        body = r.json()
    except Exception as e:
        print(f"  FAIL: not JSON: {e}; body: {r.text[:200]}")
        return False
    print(f"  body: {json.dumps(body, indent=2)[:400]}")
    if body.get("status") not in ("ok", "warn", "partial"):
        print(f"  FAIL: status not ok/warn/partial: {body.get('status')!r}")
        return False
    print(f"  PASS")
    return True


def main():
    s = requests.Session()
    print(f"smoke base: {BASE}")
    login(s)
    results = [
        check_download_json(s, "/admin/ops/security/report",
                            ["generated_at", "report_type", "checks"]),
        check_download_json(s, "/admin/ops/db/report",
                            ["generated_at", "report_type", "backend", "checks"]),
        check_download_json(s, "/admin/ops/health/report",
                            ["generated_at", "report_type", "subsystems"]),
        check_archive_post(s),
    ]
    print()
    print(f"=== Summary: {sum(results)}/{len(results)} passed ===")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
