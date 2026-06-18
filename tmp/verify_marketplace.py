"""
Browser verification of marketplace + procurement routes after the 2026-06-18 restart.
Drives Chromium via Playwright; logs in as admin; visits every marketplace route;
reports HTTP status + whether the page rendered (no 500 page detected).
"""
import os, sys, pathlib

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

# (path, requires_login, expected_status_min, expected_status_max, note)
ANON_ROUTES = [
    ("/marketplace", 200, 200, "public catalog"),
]
AUTH_ROUTES = [
    ("/procurement-center",          200, 200, "Slice 9 product picker"),
    ("/price-sheets",                200, 200, "Slice 9 price sheets list"),
    ("/supplier/dashboard",          403, 403, "supplier portal (admin gets 403 — correct RBAC)"),
    ("/admin/marketplace",           200, 200, "Slice 3 verification landing"),
    ("/admin/marketplace/pending",   200, 200, "Slice 3 verification queue"),
    ("/admin/marketplace/suppliers", 200, 200, "supplier admin"),
    ("/admin/marketplace/products",  200, 200, "product admin"),
    ("/admin/marketplace/staff",     200, 200, "staff admin"),
    ("/rfqs",                        200, 200, "Slice 4 RFQ list"),
    ("/boms",                        200, 200, "Slice 5 BOM list"),
]

SHOT_DIR = pathlib.Path(__file__).parent / "shots"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

FAIL_MARKERS = [
    "Internal Server Error",
    "The server encountered an unexpected internal server error",
    "Traceback (most recent call last)",
]

def safe_name(p):
    return p.strip("/").replace("/", "__") or "root"

def check(page, path, lo, hi, note):
    resp = page.goto(BASE + path, wait_until="commit", timeout=45000)
    status = resp.status if resp else 0
    # Give the HTML body a moment to actually arrive after the headers.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    body = page.content()
    bad = next((m for m in FAIL_MARKERS if m in body), None)
    shot = SHOT_DIR / f"{safe_name(path)}.png"
    page.screenshot(path=str(shot), full_page=False)
    ok = (lo <= status <= hi) and (bad is None)
    return ok, status, bad, shot

def main():
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        # Anon routes first (fresh context).
        for path, lo, hi, note in ANON_ROUTES:
            ok, st, bad, shot = check(page, path, lo, hi, note)
            results.append(("anon", path, ok, st, bad, shot, note))

        # Login.
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.fill('input[name="username"]', ADMIN_USER)
        page.fill('input[name="password"]', ADMIN_PASS)
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        logged_in = "/dashboard" in page.url or page.url.rstrip("/") == BASE
        print(f"[login] post-login URL: {page.url}  logged_in={logged_in}")

        if not logged_in:
            print("[login] FAILED — aborting auth route checks")
            for path, lo, hi, note in AUTH_ROUTES:
                results.append(("auth", path, False, 0, "login failed", None, note))
        else:
            for path, lo, hi, note in AUTH_ROUTES:
                ok, st, bad, shot = check(page, path, lo, hi, note)
                results.append(("auth", path, ok, st, bad, shot, note))

        browser.close()

    print()
    print(f"{'scope':5} {'status':>6}  {'path':40}  result   note")
    print("-" * 100)
    passed = failed = 0
    for scope, path, ok, st, bad, shot, note in results:
        flag = "PASS" if ok else "FAIL"
        passed += int(ok); failed += int(not ok)
        marker = f"  [{bad}]" if bad else ""
        print(f"{scope:5} {st:>6}  {path:40}  {flag}    {note}{marker}")
    print("-" * 100)
    print(f"Total: {passed} pass, {failed} fail, screenshots in {SHOT_DIR}")
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
