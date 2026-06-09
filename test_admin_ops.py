"""
Live smoke-test: every admin operations button on https://solarpro.aiappinvent.com
Logs in as admin, then hits each endpoint and reports pass/fail + response summary.
"""
import requests, json, sys, time

BASE    = "https://solarpro.aiappinvent.com"
USER    = "admin"
PASS    = "SolarAdmin2026!"

s = requests.Session()
s.headers.update({"User-Agent": "SolarPro-AdminTest/1.0"})

PASS_MARK = "\033[92m PASS\033[0m"
FAIL_MARK = "\033[91m FAIL\033[0m"
WARN_MARK = "\033[93m WARN\033[0m"
results   = []

def chk(label, method, path, data=None, expected_keys=(), ok_statuses=(200,), allow_unavailable=True):
    url = BASE + path
    try:
        t0 = time.time()
        if method == "GET":
            r = s.get(url, timeout=30, allow_redirects=False)
        else:
            payload = dict(data or {})
            payload["_csrf"] = csrf_token
            r = s.post(url, data=payload, timeout=60, allow_redirects=False)
        ms = round((time.time() - t0) * 1000)

        # Redirect to /login = not authed
        if r.status_code in (301, 302) and "/login" in r.headers.get("Location",""):
            results.append((label, "FAIL", f"403/redirect — not authenticated"))
            print(f"[{FAIL_MARK}] {label:<55} redirect to login")
            return None

        if r.status_code not in ok_statuses:
            results.append((label, "FAIL", f"HTTP {r.status_code}"))
            print(f"[{FAIL_MARK}] {label:<55} HTTP {r.status_code}")
            return None

        try:
            body = r.json()
        except Exception:
            # Non-JSON (e.g. file download, HTML) — just check 200
            results.append((label, "PASS", f"HTTP {r.status_code} non-JSON ({ms}ms)"))
            print(f"[{PASS_MARK}] {label:<55} HTTP {r.status_code} binary/HTML ({ms}ms)")
            return r

        status = body.get("status","")
        if allow_unavailable and status == "unavailable":
            results.append((label, "WARN", f"unavailable: {body.get('message','')}"))
            print(f"[{WARN_MARK}] {label:<55} unavailable — {body.get('message','')[:70]}")
            return body

        missing = [k for k in expected_keys if k not in body]
        if status in ("ok","connected") or (not missing and status not in ("error",)):
            results.append((label, "PASS", f"{status} ({ms}ms)"))
            print(f"[{PASS_MARK}] {label:<55} {status} ({ms}ms)  {_summary(body)}")
        elif status == "warning":
            results.append((label, "WARN", f"warning: {body.get('message','')[:60]}"))
            print(f"[{WARN_MARK}] {label:<55} warning — {body.get('message','')[:70]}")
        else:
            results.append((label, "FAIL", f"{status}: {body.get('message','')[:60]}"))
            print(f"[{FAIL_MARK}] {label:<55} {status}: {body.get('message','')[:70]}")
        return body
    except requests.exceptions.Timeout:
        results.append((label, "FAIL", "timeout"))
        print(f"[{FAIL_MARK}] {label:<55} TIMEOUT")
    except Exception as e:
        results.append((label, "FAIL", str(e)[:60]))
        print(f"[{FAIL_MARK}] {label:<55} {e}")
    return None

def _summary(body):
    parts = []
    for k in ("users","projects","latency_ms","db_size_kb","used_memory",
              "vulnerabilities_found","keys_deleted","total_requests","rps","count","message"):
        if k in body:
            v = body[k]
            if isinstance(v, str):
                v = v[:40]
            parts.append(f"{k}={v}")
    return " | ".join(parts[:4])

# ── 1. Login ─────────────────────────────────────────────────────────────────
print("\n" + "="*75)
print("  SolarPro Admin Operations — Live Endpoint Test")
print("="*75)
print(f"\n[1] Logging in as '{USER}'...")

login_page = s.get(BASE + "/login", timeout=10)
csrf_token = ""
for line in login_page.text.splitlines():
    if 'name="_csrf"' in line or "csrf" in line.lower():
        import re
        m = re.search(r'value=["\']([^"\']{10,})["\']', line)
        if m:
            csrf_token = m.group(1)
            break

r = s.post(BASE + "/login", data={"username": USER, "password": PASS, "_csrf": csrf_token},
           allow_redirects=True, timeout=10)
if "/dashboard" in r.url or "/admin" in r.url or r.url == BASE + "/":
    print(f"    Login OK — session established (url={r.url})")
elif "Invalid" in r.text or "incorrect" in r.text.lower():
    print("    Login FAILED — wrong credentials. Aborting.")
    sys.exit(1)
else:
    # Try fetching /admin to confirm auth
    test = s.get(BASE + "/admin", timeout=10, allow_redirects=False)
    if test.status_code == 200:
        print(f"    Login OK (admin page accessible)")
    else:
        print(f"    Login status unclear (url={r.url}, code={r.status_code}) — continuing anyway")

# Refresh CSRF token from dashboard
dash = s.get(BASE + "/admin", timeout=10)
for line in dash.text.splitlines():
    if 'name="_csrf"' in line or ('csrf' in line.lower() and 'value=' in line):
        import re
        m = re.search(r'value=["\']([^"\']{10,})["\']', line)
        if m:
            csrf_token = m.group(1)
            break

print(f"    CSRF token: {csrf_token[:20]}..." if csrf_token else "    CSRF token not found — POST calls may fail")
print()

# ── 2. Public endpoints ──────────────────────────────────────────────────────
print("[2] Public endpoints")
chk("/api/ping                          ", "GET",  "/api/ping",           expected_keys=("pong",))
chk("/api/health                        ", "GET",  "/api/health",         expected_keys=("status",))
chk("/api/health/database               ", "GET",  "/api/health/database",expected_keys=("status",))
chk("/api/health/redis                  ", "GET",  "/api/health/redis",   expected_keys=("status",))
chk("/api/health/queue                  ", "GET",  "/api/health/queue",   expected_keys=("status",))
chk("/api/health/ai                     ", "GET",  "/api/health/ai",      expected_keys=("status",))
chk("/api/health/storage                ", "GET",  "/api/health/storage", expected_keys=("status",))
print()

# ── 3. Ping buttons ──────────────────────────────────────────────────────────
print("[3] Ping buttons (admin-protected)")
chk("/admin/ops/ping/frontend           ", "GET",  "/admin/ops/ping/frontend",  expected_keys=("status",))
chk("/admin/ops/ping/backend            ", "GET",  "/admin/ops/ping/backend",   expected_keys=("status",))
chk("/admin/ops/ping/redis              ", "GET",  "/admin/ops/ping/redis",     expected_keys=("status",))
chk("/admin/ops/ping/database           ", "GET",  "/admin/ops/ping/database",  expected_keys=("status",))
print()

# ── 4. Security / RLS ────────────────────────────────────────────────────────
print("[4] Security & RLS buttons")
chk("/admin/ops/db/rls-check            ", "GET",  "/admin/ops/db/rls-check",              expected_keys=("status",))
chk("/admin/ops/security/tenant-iso     ", "GET",  "/admin/ops/security/tenant-isolation", expected_keys=("status",))
chk("/admin/ops/security/audit          ", "POST", "/admin/ops/security/audit",            expected_keys=("status",))
chk("/admin/ops/security/sessions       ", "GET",  "/admin/ops/security/sessions",         expected_keys=("status",))
print()

# ── 5. Logs ──────────────────────────────────────────────────────────────────
print("[5] Log viewer buttons")
chk("/admin/ops/logs/view (app)         ", "GET",  "/admin/ops/logs/view?type=app",     expected_keys=("status",))
chk("/admin/ops/logs/view (error)       ", "GET",  "/admin/ops/logs/view?type=error",   expected_keys=("status",))
chk("/admin/ops/logs/audit              ", "GET",  "/admin/ops/logs/audit",             expected_keys=("status",))
print()

# ── 6. System tools ──────────────────────────────────────────────────────────
print("[6] System tools")
chk("/admin/ops/system/pip-audit        ", "POST", "/admin/ops/system/pip-audit", expected_keys=("status",))
chk("/admin/ops/system/load-test        ", "POST", "/admin/ops/system/load-test", expected_keys=("status",))
print()

# ── 7. Cache / Queue ─────────────────────────────────────────────────────────
print("[7] Cache & queue")
chk("/admin/ops/cache/clear             ", "POST", "/admin/ops/cache/clear",   expected_keys=("status",))
chk("/admin/ops/queue/restart           ", "POST", "/admin/ops/queue/restart", expected_keys=("status",))
print()

# ── 8. DB operations ─────────────────────────────────────────────────────────
print("[8] Database operations")
chk("/admin/ops/db/vacuum               ", "POST", "/admin/ops/db/vacuum", expected_keys=("status",))
print()

# ── 9. Backup ────────────────────────────────────────────────────────────────
print("[9] Backup")
chk("/admin/ops/backup/run              ", "POST", "/admin/ops/backup/run",      expected_keys=("status",))
chk("/admin/ops/backup/download         ", "GET",  "/admin/ops/backup/download", ok_statuses=(200,404))
print()

# ── Summary ──────────────────────────────────────────────────────────────────
passed   = sum(1 for _,s,_ in results if s == "PASS")
warned   = sum(1 for _,s,_ in results if s == "WARN")
failed   = sum(1 for _,s,_ in results if s == "FAIL")
total    = len(results)
print("="*75)
print(f"  RESULTS: {passed}/{total} PASS   {warned} WARN   {failed} FAIL")
print("="*75)
if failed:
    print("\nFailed endpoints:")
    for lbl, st, msg in results:
        if st == "FAIL":
            print(f"  ✗ {lbl.strip():<50} {msg}")
if warned:
    print("\nWarnings (unavailable services — expected on Render free tier):")
    for lbl, st, msg in results:
        if st == "WARN":
            print(f"  ⚠ {lbl.strip():<50} {msg[:70]}")
print()
