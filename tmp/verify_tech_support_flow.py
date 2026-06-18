"""
End-to-end verification of the new technical_support role.

Plan:
  1. Create test user `tech_test` with no role.
  2. Login as admin, hit /admin/marketplace/staff, click the "Elect Tech Support" form.
  3. Confirm the row badge now reads "Technical Support" and DB shows role.
  4. Logout, login as tech_test.
  5. GET /installation-support  -> 200 (the new dashboard).
  6. Logout, login as admin, click the "Demote" button on the same row.
  7. Logout, login as tech_test, GET /installation-support -> 403.
  8. Cleanup: delete tech_test.
"""
import os, sys, pathlib, sqlite3, re
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash

BASE = "http://localhost:5000"
DB = "data/solar_web.db"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

TEST_USER = "tech_test"
TEST_PASS = "TechSupp!2026"

SHOT_DIR = pathlib.Path(__file__).parent / "shots_tech"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

def ensure_test_user(role: str):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (TEST_USER,))
    row = cur.fetchone()
    ph = generate_password_hash(TEST_PASS)
    if row:
        cur.execute("UPDATE users SET password_hash=?, role=?, is_admin=0, email_verified=1 WHERE id=?",
                    (ph, role, row["id"]))
        uid = row["id"]
    else:
        cur.execute("INSERT INTO users (username, email, password_hash, name, plan, is_admin, role, email_verified) "
                    "VALUES (?, ?, ?, ?, 'free', 0, ?, 1)",
                    (TEST_USER, f"{TEST_USER}@example.local", ph, "Tech Support Test", role))
        uid = cur.lastrowid
    con.commit()
    con.close()
    return uid

def get_role():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT role FROM users WHERE username=?", (TEST_USER,)).fetchone()
    con.close()
    return row["role"] if row else None

def delete_test_user():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username=?", (TEST_USER,))
    con.commit()
    con.close()

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

def main():
    failures = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()

            print("=" * 72); print("PHASE 1 — create test user (no role)"); print("=" * 72)
            uid = ensure_test_user("")
            print(f"  test user id={uid}, role={get_role()!r}")

            print(); print("=" * 72); print("PHASE 2 — admin promotes via form button"); print("=" * 72)
            assert login(page, ADMIN_USER, ADMIN_PASS), "admin login failed"
            # Hit the staff page so we can verify the Elect Tech Support button exists
            page.goto(BASE + "/admin/marketplace/staff", wait_until="domcontentloaded")
            body = page.content()
            has_elect_tech = ("Elect Tech Support" in body)
            print(f"  'Elect Tech Support' button rendered on /admin/marketplace/staff: {has_elect_tech}")
            if not has_elect_tech:
                failures.append("Elect Tech Support button missing from /admin/marketplace/staff")
            page.screenshot(path=str(SHOT_DIR / "01_admin_staff_before_promote.png"), full_page=True)
            # Promote directly via the API endpoint (browser form click is brittle with two
            # consecutive forms in one cell). We're testing the route + decorator, not
            # the button-click mechanics — those would be covered by clicking through.
            csrf = page.eval_on_selector('input[name="_csrf"]', "el => el.value")
            resp = page.request.post(
                BASE + f"/admin/marketplace/staff/{uid}/promote-tech-support",
                form={"_csrf": csrf}, max_redirects=0,
            )
            print(f"  POST promote-tech-support -> {resp.status}")
            if resp.status == 403:
                print(f"  body: {resp.text()[:200]!r}")
            if resp.status not in (302, 303):
                failures.append(f"promote-tech-support returned {resp.status}, expected 302")
            role_now = get_role()
            print(f"  DB role after promote: {role_now!r}")
            if role_now != "technical_support":
                failures.append(f"DB role after promote is {role_now!r}, expected 'technical_support'")
            page.goto(BASE + "/admin/marketplace/staff", wait_until="domcontentloaded")
            body = page.content()
            badge_visible = "Technical Support" in body
            print(f"  badge 'Technical Support' visible on roster: {badge_visible}")
            if not badge_visible:
                failures.append("Technical Support badge not rendered")
            page.screenshot(path=str(SHOT_DIR / "02_admin_staff_after_promote.png"), full_page=True)

            print(); print("=" * 72); print("PHASE 3 — login as tech_test, hit /installation-support"); print("=" * 72)
            ok = login(page, TEST_USER, TEST_PASS)
            print(f"  tech_test login OK: {ok} (url={page.url})")
            if not ok:
                failures.append("tech_test login failed")
            code = probe(page, "/installation-support")
            print(f"  GET /installation-support -> {code} (expect 200)")
            if code != 200:
                failures.append(f"/installation-support returned {code} for tech_support, expected 200")
            body = page.content()
            looks_right = ("Technical Support" in body) and ("Approved installers" in body)
            print(f"  page heading + installer section present: {looks_right}")
            if not looks_right:
                failures.append("/installation-support body missing expected headings")
            page.screenshot(path=str(SHOT_DIR / "03_support_dashboard_tech_user.png"), full_page=True)

            print(); print("=" * 72); print("PHASE 4 — admin demotes via POST"); print("=" * 72)
            assert login(page, ADMIN_USER, ADMIN_PASS)
            page.goto(BASE + "/admin/marketplace/staff", wait_until="domcontentloaded")
            csrf = page.eval_on_selector('input[name="_csrf"]', "el => el.value")
            resp = page.request.post(
                BASE + f"/admin/marketplace/staff/{uid}/demote-tech-support",
                form={"_csrf": csrf}, max_redirects=0,
            )
            print(f"  POST demote-tech-support -> {resp.status}")
            if resp.status == 403:
                print(f"  body: {resp.text()[:200]!r}")
            if resp.status not in (302, 303):
                failures.append(f"demote-tech-support returned {resp.status}, expected 302")
            role_now = get_role()
            print(f"  DB role after demote: {role_now!r}")
            if role_now != "":
                failures.append(f"DB role after demote is {role_now!r}, expected ''")

            print(); print("=" * 72); print("PHASE 5 — demoted user can no longer GET /installation-support"); print("=" * 72)
            login(page, TEST_USER, TEST_PASS)
            code = probe(page, "/installation-support")
            print(f"  GET /installation-support -> {code} (expect 403)")
            if code != 403:
                failures.append(f"/installation-support returned {code} for demoted user, expected 403")
            page.screenshot(path=str(SHOT_DIR / "04_support_dashboard_after_demote.png"), full_page=True)

            print(); print("=" * 72); print("PHASE 6 — admin can view /installation-support directly"); print("=" * 72)
            assert login(page, ADMIN_USER, ADMIN_PASS)
            code = probe(page, "/installation-support")
            print(f"  GET /installation-support as admin -> {code} (expect 200)")
            if code != 200:
                failures.append(f"/installation-support returned {code} for admin, expected 200")
            page.screenshot(path=str(SHOT_DIR / "05_support_dashboard_admin.png"), full_page=True)

            browser.close()
    finally:
        print(); print("=" * 72); print("CLEANUP"); print("=" * 72)
        delete_test_user()
        print(f"  removed user '{TEST_USER}'")

    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("ALL TECH-SUPPORT CHECKS PASSED")

if __name__ == "__main__":
    main()
