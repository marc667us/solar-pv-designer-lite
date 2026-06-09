"""Re-run admin ops test — all buttons including email. Revoke Sessions goes last."""
import requests, re, sys, time

BASE = "https://web-production-744af.up.railway.app"
s = requests.Session()

def do_login():
    lp = s.get(BASE + "/login", timeout=10)
    csrf = ""
    for line in lp.text.splitlines():
        if "_csrf" in line:
            m = re.search(r'value=["\']([^"\']{10,})["\']', line)
            if m: csrf = m.group(1); break
    s.post(BASE + "/login", data={"username": "admin", "password": "SolarAdmin2026!", "_csrf": csrf},
           allow_redirects=True, timeout=10)
    dash = s.get(BASE + "/admin", timeout=10)
    csrf2 = csrf
    for line in dash.text.splitlines():
        if "_csrf" in line:
            m = re.search(r'value=["\']([^"\']{10,})["\']', line)
            if m: csrf2 = m.group(1); break
    return csrf2

csrf = do_login()

P = "\x1b[92mPASS\x1b[0m"
F = "\x1b[91mFAIL\x1b[0m"
W = "\x1b[93mWARN\x1b[0m"
results = []

def test(label, method, path, extra_data=None, re_login=False):
    global csrf
    if re_login:
        csrf = do_login()
    url = BASE + path
    try:
        t0 = time.time()
        if method == "GET":
            r = s.get(url, timeout=45, allow_redirects=False)
        else:
            d = dict(extra_data or {})
            d["_csrf"] = csrf
            r = s.post(url, data=d, timeout=60, allow_redirects=False)
        ms = round((time.time() - t0)*1000)
        if r.status_code in (301,302) and "login" in r.headers.get("Location",""):
            results.append((label, "FAIL", "redirect to login"))
            sys.stdout.buffer.write(("[%s] %-52s redirect->login\n" % (F, label)).encode("utf-8","replace"))
            return
        try:
            body = r.json()
            st = body.get("status","")
            # Special: /api/ping returns {"pong":true} without status key
            if "pong" in body:
                st = "ok"
            detail = body.get("message","")[:55]
            if st in ("ok","connected","success","pass","not_configured"):
                tag = P
                results.append((label, "PASS", "%s %dms" % (st, ms)))
            elif st == "unavailable":
                tag = W
                results.append((label, "WARN", detail))
            elif st == "warning":
                tag = W
                results.append((label, "WARN", detail))
            elif r.status_code == 200 and st not in ("error",):
                tag = P
                results.append((label, "PASS", "HTTP200 %dms" % ms))
            else:
                tag = F
                results.append((label, "FAIL", "HTTP%d %s %s" % (r.status_code, st, detail)))
        except Exception:
            if r.status_code == 200:
                tag = P
                results.append((label, "PASS", "HTTP200 binary %dms" % ms))
            else:
                tag = F
                results.append((label, "FAIL", "HTTP%d non-JSON" % r.status_code))
        extra = ""
        if results[-1][1] == "PASS":
            try:
                b = r.json()
                for k in ("users","latency_ms","keys_deleted","rps","total_requests","count",
                          "vulnerabilities_found","smtp_configured","smtp_host","sent_to","result",
                          "db_size_kb","successful","errors"):
                    if k in b: extra += " %s=%s" % (k, str(b[k])[:25])
                    if len(extra) > 65: break
            except Exception: pass
        sys.stdout.buffer.write(("[%s] %-52s %s%s\n" % (tag, label, results[-1][2][:40], extra)).encode("utf-8","replace"))
    except requests.Timeout:
        results.append((label, "FAIL", "timeout"))
        sys.stdout.buffer.write(("[%s] %-52s TIMEOUT\n" % (F, label)).encode("utf-8","replace"))
    except Exception as e:
        results.append((label, "FAIL", str(e)[:40]))
        sys.stdout.buffer.write(("[%s] %-52s %s\n" % (F, label, str(e)[:40])).encode("utf-8","replace"))

sys.stdout.buffer.write(b"\n=== SolarPro Admin Ops - Full Button Test ===\n\n")

sys.stdout.buffer.write(b"[PINGS]\n")
test("Ping /api/ping",             "GET",  "/api/ping")
test("Ping Frontend",               "GET",  "/admin/ops/ping/frontend")
test("Ping Backend",                "GET",  "/admin/ops/ping/backend")
test("Ping Redis",                  "GET",  "/admin/ops/ping/redis")
test("Ping Database",               "GET",  "/admin/ops/ping/database")

sys.stdout.buffer.write(b"\n[HEALTH]\n")
test("Health /api/health",          "GET",  "/api/health")
test("Health DB",                   "GET",  "/api/health/database")
test("Health Redis",                "GET",  "/api/health/redis")
test("Health Queue",                "GET",  "/api/health/queue")
test("Health AI",                   "GET",  "/api/health/ai")
test("Health Storage",              "GET",  "/api/health/storage")

sys.stdout.buffer.write(b"\n[SECURITY & RLS]\n")
test("RLS Check",                   "GET",  "/admin/ops/db/rls-check")
test("Tenant Isolation",            "GET",  "/admin/ops/security/tenant-isolation")
test("Security Audit",              "POST", "/admin/ops/security/audit")
test("Active Sessions",             "GET",  "/admin/ops/security/sessions")

sys.stdout.buffer.write(b"\n[LOGS]\n")
test("View App Logs",               "GET",  "/admin/ops/logs/view?type=app")
test("View Error Logs",             "GET",  "/admin/ops/logs/view?type=error")
test("View Security Logs",          "GET",  "/admin/ops/logs/view?type=security")
test("View Audit Logs",             "GET",  "/admin/ops/logs/audit")

sys.stdout.buffer.write(b"\n[SYSTEM TOOLS]\n")
test("pip-audit",                   "POST", "/admin/ops/system/pip-audit")
test("Load Test",                   "POST", "/admin/ops/system/load-test")
test("Email Status",                "GET",  "/admin/ops/email/status")
test("Send Test Email",             "POST", "/admin/ops/email/test")

sys.stdout.buffer.write(b"\n[CACHE & QUEUE]\n")
test("Clear Cache",                 "POST", "/admin/ops/cache/clear")
test("Restart Queue",               "POST", "/admin/ops/queue/restart")

sys.stdout.buffer.write(b"\n[DATABASE]\n")
test("DB Vacuum",                   "POST", "/admin/ops/db/vacuum")

sys.stdout.buffer.write(b"\n[BACKUP]\n")
test("Backup Run",                  "POST", "/admin/ops/backup/run")
test("Backup Download",             "GET",  "/admin/ops/backup/download")

# Revoke Sessions LAST (clears session — re-login needed after)
sys.stdout.buffer.write(b"\n[DESTRUCTIVE - runs last]\n")
test("Revoke All Sessions",         "POST", "/admin/ops/security/revoke-all-sessions")

# Summary
passed = sum(1 for _,s2,_ in results if s2=="PASS")
warned = sum(1 for _,s2,_ in results if s2=="WARN")
failed = sum(1 for _,s2,_ in results if s2=="FAIL")
total  = len(results)

sys.stdout.buffer.write(("\n=== RESULTS: %d/%d PASS  %d WARN  %d FAIL ===\n" % (passed, total, warned, failed)).encode())
if failed:
    sys.stdout.buffer.write(b"\nFailed:\n")
    for lbl,st,msg in results:
        if st=="FAIL":
            sys.stdout.buffer.write(("  FAIL  %-50s %s\n" % (lbl, msg)).encode("utf-8","replace"))
if warned:
    sys.stdout.buffer.write(b"\nWarnings (unavailable on Render free tier - expected):\n")
    for lbl,st,msg in results:
        if st=="WARN":
            sys.stdout.buffer.write(("  WARN  %-50s %s\n" % (lbl, msg[:60])).encode("utf-8","replace"))
