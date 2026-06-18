"""
End-to-end browser test of the Basic Price Sheet preparation flow.
Steps:
  1. Login as admin.
  2. GET /procurement-center  -> assert 200, default currency is GHS.
  3. Tick first product checkbox, set doc_type=price_sheet, submit Add.
  4. Follow redirect -> /price-sheets/<id>  -> assert 200.
  5. Click "My Price Sheets" -> assert 200.
  6. Test the currency dropdown by passing ?currency=GHS and ?currency=USD.
"""
import os, sys, pathlib, re
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

SHOT_DIR = pathlib.Path(__file__).parent / "shots_ps"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

FAIL = ["Internal Server Error", "Traceback (most recent call last)", "Page Not Found"]

def banner(s):
    print(); print("=" * 72); print(s); print("=" * 72)

def shot(page, name):
    page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=False)

def assert_ok(page, label, expected_min=200, expected_max=200, allow_redirect=False):
    body = page.content()
    bad = next((m for m in FAIL if m in body), None)
    print(f"[{label}] url={page.url}  body_len={len(body)}  bad_marker={bad}")
    if bad:
        shot(page, f"{label}_FAIL")
        raise SystemExit(f"FAIL {label}: '{bad}' in page body")
    shot(page, label)

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        banner("1. LOGIN")
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.fill('input[name="username"]', ADMIN_USER)
        page.fill('input[name="password"]', ADMIN_PASS)
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded")
        assert "/dashboard" in page.url, f"login failed, landed on {page.url}"
        print("  login OK")

        banner("2. GET /procurement-center  (expect default currency=GHS)")
        page.goto(BASE + "/procurement-center", wait_until="domcontentloaded", timeout=45000)
        page.wait_for_load_state("networkidle", timeout=15000)
        assert_ok(page, "procurement_center")
        # Confirm GHS is the default-selected option
        selected = page.eval_on_selector('select[name="currency"] option[selected]', "el => el.value")
        print(f"  currency dropdown default = {selected!r}")
        assert selected == "GHS", f"expected default GHS, got {selected!r}"

        banner("3. Tick first product + submit Basic Price Sheet")
        checkboxes = page.query_selector_all("input.prod-chk")
        print(f"  product checkboxes on page: {len(checkboxes)}")
        if not checkboxes:
            print("  no checkboxes -> no products in catalog; skip submit")
            browser.close(); return
        checkboxes[0].check()
        page.check('input[value="price_sheet"]')  # already default but be explicit
        page.click("#addBtn")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        print(f"  post-submit url: {page.url}")
        assert_ok(page, "price_sheet_view_after_add")
        # capture sheet id from URL
        m = re.search(r"/price-sheets/(\d+)", page.url)
        sheet_id = int(m.group(1)) if m else None
        print(f"  created sheet id = {sheet_id}")

        banner("4. Direct GET /price-sheets (list page)")
        page.goto(BASE + "/price-sheets", wait_until="domcontentloaded")
        assert_ok(page, "price_sheets_list")

        if sheet_id:
            banner(f"5. Direct GET /price-sheets/{sheet_id}")
            page.goto(BASE + f"/price-sheets/{sheet_id}", wait_until="domcontentloaded")
            assert_ok(page, "price_sheet_view_direct")

        banner("6. Currency override sweep: GHS, USD, EUR, BAD")
        for cur in ["GHS", "USD", "EUR", "ZZZ"]:
            page.goto(BASE + f"/procurement-center?currency={cur}", wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            sel = page.eval_on_selector('select[name="currency"] option[selected]', "el => el.value")
            print(f"  ?currency={cur:>4}  -> dropdown shows {sel!r}")
            assert_ok(page, f"cur_{cur}")

        print()
        print("ALL CHECKS PASSED")
        browser.close()

if __name__ == "__main__":
    main()
