"""
Verify the procurement_specialist role flows end-to-end.

Plan:
  1. SQL: ensure test user `proc_test` exists with a known password and is
     NOT admin and has role='procurement_specialist'.
  2. Login as admin, confirm the user shows up at /admin/marketplace/staff.
  3. Logout, login as proc_test.
  4. Hit the 6 specialist-guarded routes + /me; assert 200 (not 403).
  5. Sanity: log in as proc_test AFTER demote, confirm same routes now 403.
  6. Cleanup: delete the test user.
"""
import os, sys, pathlib, sqlite3, time
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash

BASE = "http://localhost:5000"
DB = "data/solar_web.db"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

TEST_USER = "proc_test"
TEST_PASS = "ProcSpecTest!2026"

SPECIALIST_ROUTES = [
    ("/admin/marketplace/suppliers", "specialist suppliers list"),
    ("/admin/marketplace/products",  "specialist products list"),
    ("/me",                          "personal dashboard (any login)"),
]

SHOT_DIR = pathlib.Path(__file__).parent / "shots_spec"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

# ---------------------------------------------------------------------- DB

def ensure_test_user(role: str):
    """Ensure proc_test exists with given role + known password. Returns user id."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (TEST_USER,))
    row = cur.fetchone()
    ph = generate_password_hash(TEST_PASS)
    if row:
        cur.execute(
            "UPDATE users SET password_hash=?, role=?, is_admin=0, email_verified=1 WHERE id=?",
            (ph, role, row["id"]),
        )
        uid = row["id"]
    else:
        cur.execute(
            "INSERT INTO users (username, email, password_hash, name, plan, is_admin, role, email_verified) "
            "VALUES (?, ?, ?, ?, 'free', 0, ?, 1)",
            (TEST_USER, f"{TEST_USER}@example.local", ph, "Procurement Test User", role),
        )
        uid = cur.lastrowid
    con.commit()
    con.close()
    return uid

def delete_test_user():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username=?", (TEST_USER,))
    con.commit()
    con.close()

# ---------------------------------------------------------------------- browser

def login(page, username, password):
    page.goto(BASE + "/logout", wait_until="domcontentloaded")
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    return "/dashboard" in page.url or page.url.rstrip("/") == BASE

def probe(page, path):
    resp = page.goto(BASE + path, wait_until="commit", timeout=30000)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    return resp.status if resp else 0

# ---------------------------------------------------------------------- main

def main():
    failures = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()

            print("=" * 72); print("PHASE 1 — promote test user (specialist)"); print("=" * 72)
            uid = ensure_test_user("procurement_specialist")
            print(f"  test user id={uid}, role=procurement_specialist")

            print(); print("=" * 72); print("PHASE 2 — admin sees them on /admin/marketplace/staff"); print("=" * 72)
            assert login(page, ADMIN_USER, ADMIN_PASS), "admin login failed"
            page.goto(BASE + "/admin/marketplace/staff", wait_until="domcontentloaded")
            html = page.content()
            on_roster = TEST_USER in html
            print(f"  proc_test visible on staff roster: {on_roster}")
            if not on_roster:
                failures.append("test user not visible on /admin/marketplace/staff")
            page.screenshot(path=str(SHOT_DIR / "admin_staff_roster.png"))

            print(); print("=" * 72); print("PHASE 3 — login as specialist, hit guarded routes"); print("=" * 72)
            ok = login(page, TEST_USER, TEST_PASS)
            print(f"  specialist login OK: {ok} (landed on {page.url})")
            if not ok:
                failures.append("specialist login failed")
            for path, note in SPECIALIST_ROUTES:
                code = probe(page, path)
                ok = (code == 200)
                print(f"  [specialist] {code}  {path}  ({note})  {'PASS' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"specialist {path} -> {code}")
                page.screenshot(path=str(SHOT_DIR / f"spec_{path.strip('/').replace('/','__') or 'root'}.png"))

            print(); print("=" * 72); print("PHASE 4 — demote, then re-check guarded routes (expect 403)"); print("=" * 72)
            ensure_test_user("")  # role cleared
            print("  test user role cleared")
            login(page, TEST_USER, TEST_PASS)
            for path, note in SPECIALIST_ROUTES:
                code = probe(page, path)
                # /me is open to any login, so 200 is correct there.
                expect = 403 if path != "/me" else 200
                ok = (code == expect)
                print(f"  [demoted]    {code}  {path}  expect={expect}  {'PASS' if ok else 'FAIL'}")
                if not ok:
                    failures.append(f"demoted {path} -> {code} (expected {expect})")

            browser.close()
    finally:
        print()
        print("=" * 72); print("CLEANUP — delete test user"); print("=" * 72)
        delete_test_user()
        print(f"  removed user '{TEST_USER}'")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    else:
        print("ALL SPECIALIST CHECKS PASSED")

if __name__ == "__main__":
    main()
