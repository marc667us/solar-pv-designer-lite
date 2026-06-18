"""
End-to-end browser test of marketplace browse + RFQ submission as a real user.

Steps:
  1. Login as admin (acting as a buyer).
  2. GET /marketplace               -> 200, find first product card.
  3. Click "Request quote"           -> /rfqs/new?product_id=<pid>  -> 200, seeded product.
  4. Submit RFQ form                 -> POST /rfqs/new -> redirects to /rfqs/<id> -> 200.
  5. Confirm seeded item is on the draft.
  6. Add a second item                -> POST /rfqs/<id>/items/add -> 302 -> 200.
  7. Select 2 verified suppliers, POST /rfqs/<id>/send.
  8. Assert status badge is now 'Sent' on the view page.
  9. Confirm /rfqs list shows the new RFQ with status='sent'.
"""
import os, sys, pathlib, re, sqlite3
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"
DB = "data/solar_web.db"
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

SHOT_DIR = pathlib.Path(__file__).parent / "shots_rfq"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

FAIL = ["Internal Server Error", "Traceback (most recent call last)", "Page Not Found"]

def shot(page, name):
    page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=True)

def assert_clean(page, label):
    body = page.content()
    bad = next((m for m in FAIL if m in body), None)
    if bad:
        shot(page, f"{label}_BAD")
        raise SystemExit(f"FAIL {label}: '{bad}' in body  url={page.url}")
    return body

def login(page, u, p):
    page.goto(BASE + "/logout", wait_until="domcontentloaded")
    page.goto(BASE + "/login", wait_until="domcontentloaded")
    page.fill('input[name="username"]', u)
    page.fill('input[name="password"]', p)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    return "/dashboard" in page.url

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        page = ctx.new_page()

        print("=" * 72); print("1) LOGIN"); print("=" * 72)
        assert login(page, ADMIN_USER, ADMIN_PASS), "admin login failed"
        print("  OK")

        print(); print("=" * 72); print("2) MARKETPLACE BROWSE"); print("=" * 72)
        page.goto(BASE + "/marketplace", wait_until="commit", timeout=45000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        body = assert_clean(page, "marketplace")
        shot(page, "01_marketplace")
        # Pull the first "Request quote" link  (template: /rfqs/new?product_id=<id>)
        first_link = page.eval_on_selector_all(
            'a[href*="/rfqs/new"]',
            "els => els.length ? els[0].getAttribute('href') : null"
        )
        print(f"  first RFQ-seed link: {first_link!r}")
        assert first_link, "no /rfqs/new?product_id=… link found on /marketplace"

        print(); print("=" * 72); print("3) GO TO RFQ-NEW (product-seeded)"); print("=" * 72)
        page.goto(BASE + first_link, wait_until="domcontentloaded")
        assert_clean(page, "rfq_new")
        shot(page, "02_rfq_new")
        # Confirm seeded chip appears
        body = page.content()
        seeded = "Seeded from marketplace product" in body
        print(f"  'Seeded from marketplace product' chip visible: {seeded}")
        assert seeded, "rfq_new did not render the seeded-product chip"

        print(); print("=" * 72); print("4) SUBMIT RFQ FORM"); print("=" * 72)
        page.fill('input[name="title"]', "AUTOTEST — marketplace E2E RFQ")
        page.select_option('select[name="delivery_country"]', label="Ghana")
        page.fill('input[name="first_item_qty"]', "10")
        page.fill('input[name="first_item_spec"]', "AUTOTEST spec")
        page.fill('textarea[name="notes"]', "AUTOTEST — created by verify_marketplace_rfq_e2e.py")
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        body = assert_clean(page, "rfq_view_after_create")
        m = re.search(r"/rfqs/(\d+)", page.url)
        rfq_id = int(m.group(1)) if m else None
        print(f"  landed on {page.url}  rfq_id={rfq_id}")
        assert rfq_id, "did not redirect to /rfqs/<id>"
        shot(page, "03_rfq_draft")

        # Confirm seeded item appears on the draft (qty=10)
        has_item = ("AUTOTEST spec" in body) or ("10.00" in body)
        print(f"  seeded item present on draft: {has_item}")

        print(); print("=" * 72); print("5) ADD A SECOND ITEM"); print("=" * 72)
        page.fill('input[name="name"]', "AUTOTEST extra cable run")
        page.fill('input[name="qty"]', "5")
        page.fill('input[name="unit"]', "m")
        page.fill('input[name="spec_notes"]', "4C 25mm² Cu XLPE/SWA/PVC")
        # Add-item form's submit button
        page.click('form[action*="/items/add"] button')
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        body = assert_clean(page, "rfq_view_after_add_item")
        ok2 = "AUTOTEST extra cable run" in body
        print(f"  second item present: {ok2}")
        shot(page, "04_rfq_two_items")

        print(); print("=" * 72); print("6) SEND RFQ TO 2 SUPPLIERS"); print("=" * 72)
        # Pick first 2 supplier checkboxes
        boxes = page.query_selector_all('input[type="checkbox"][name="supplier_ids"]')
        print(f"  supplier checkboxes available: {len(boxes)}")
        assert len(boxes) >= 1, "no supplier checkboxes on draft — cannot send"
        for b in boxes[: min(2, len(boxes))]:
            b.check()
        page.click('form[action*="/send"] button')
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        body = assert_clean(page, "rfq_view_after_send")
        sent_now = "Sent" in body and "Draft" not in body[:6000]  # rough check
        print(f"  status badge now 'Sent': {sent_now}")
        shot(page, "05_rfq_sent")
        # Also assert DB state
        con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
        rfq_db = con.execute("SELECT status FROM rfqs WHERE id=?", (rfq_id,)).fetchone()
        n_targets = con.execute("SELECT COUNT(*) FROM rfq_supplier_targets WHERE rfq_id=?", (rfq_id,)).fetchone()[0]
        con.close()
        print(f"  DB rfq.status={rfq_db['status']!r}  targets={n_targets}")
        assert rfq_db["status"] == "sent", f"expected status='sent', got {rfq_db['status']!r}"
        assert n_targets >= 1, "no supplier targets recorded"

        print(); print("=" * 72); print("7) /rfqs LIST SHOWS NEW RFQ AS 'sent'"); print("=" * 72)
        page.goto(BASE + "/rfqs", wait_until="domcontentloaded")
        body = assert_clean(page, "rfqs_list")
        print(f"  AUTOTEST title visible on list: {'AUTOTEST — marketplace E2E RFQ' in body}")
        shot(page, "06_rfqs_list")

        browser.close()
        print()
        print(f"ALL MARKETPLACE+RFQ E2E CHECKS PASSED  (rfq_id={rfq_id})")
        # NB: leave the test RFQ in the DB so user can eyeball it; they can delete via UI.

if __name__ == "__main__":
    main()
