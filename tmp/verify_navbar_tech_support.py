"""
Verify the 'Installation Support' navbar link visibility:
  * admin            -> visible
  * technical_support -> visible
  * no-role user     -> hidden
  * anonymous        -> hidden (whole left nav reverts to single Marketplace link)
"""
import os, sys, sqlite3
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash

BASE = "http://localhost:5000"
DB = "data/solar_web.db"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

TEST_USER = "nav_test"
TEST_PASS = "NavTest!2026"

def ensure_user(role: str):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (TEST_USER,))
    row = cur.fetchone()
    ph = generate_password_hash(TEST_PASS)
    if row:
        cur.execute("UPDATE users SET password_hash=?, role=?, is_admin=0, email_verified=1 WHERE id=?",
                    (ph, role, row["id"]))
    else:
        cur.execute("INSERT INTO users (username, email, password_hash, name, plan, is_admin, role, email_verified) "
                    "VALUES (?,?,?,?,'free',0,?,1)",
                    (TEST_USER, f"{TEST_USER}@example.local", ph, "Nav Test", role))
    con.commit(); con.close()

def delete_user():
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username=?", (TEST_USER,))
    con.commit(); con.close()

def login(page, u, p):
    page.goto(BASE + "/logout", wait_until="domcontentloaded")
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.fill('input[name="username"]', u)
    page.fill('input[name="password"]', p)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    return "/dashboard" in page.url or page.url.rstrip("/") == BASE

def has_link(page):
    page.goto(BASE + "/dashboard", wait_until="domcontentloaded")
    body = page.content()
    return "Installation Support" in body

def has_link_anon(page):
    page.goto(BASE + "/logout", wait_until="domcontentloaded")
    page.goto(BASE + "/", wait_until="domcontentloaded")
    body = page.content()
    return "Installation Support" in body

def main():
    fails = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1366, "height": 900})
            page = ctx.new_page()

            print("=== anon ===")
            v = has_link_anon(page)
            print(f"  link visible to anonymous: {v}  (expect False)")
            if v: fails.append("link visible to anonymous")

            print("=== admin ===")
            assert login(page, ADMIN_USER, ADMIN_PASS), "admin login failed"
            v = has_link(page)
            print(f"  link visible to admin: {v}  (expect True)")
            if not v: fails.append("link hidden from admin")

            print("=== no-role user ===")
            ensure_user("")
            assert login(page, TEST_USER, TEST_PASS), "no-role login failed"
            v = has_link(page)
            print(f"  link visible to no-role user: {v}  (expect False)")
            if v: fails.append("link visible to no-role user")

            print("=== technical_support user ===")
            ensure_user("technical_support")
            assert login(page, TEST_USER, TEST_PASS), "tech-support login failed"
            v = has_link(page)
            print(f"  link visible to technical_support: {v}  (expect True)")
            if not v: fails.append("link hidden from tech_support")

            print("=== procurement_specialist user (sanity — should NOT see it) ===")
            ensure_user("procurement_specialist")
            assert login(page, TEST_USER, TEST_PASS), "proc-spec login failed"
            v = has_link(page)
            print(f"  link visible to procurement_specialist: {v}  (expect False)")
            if v: fails.append("link leaked to procurement_specialist")

            browser.close()
    finally:
        delete_user()

    print()
    if fails:
        print("FAILURES:", fails); sys.exit(1)
    print("ALL NAVBAR VISIBILITY CHECKS PASSED")

if __name__ == "__main__":
    main()
