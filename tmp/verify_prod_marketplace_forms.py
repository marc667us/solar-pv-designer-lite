"""
Audit ALL form submissions on the production marketplace surfaces.

Target: https://solarpro.aiappinvent.com (or override via env BASE).
Logs in as admin, walks each form, submits with valid data, records the HTTP
status of the response. Any 4xx/5xx is flagged.
"""
import os, sys, pathlib, re
from dotenv import load_dotenv
load_dotenv()
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "https://solarpro.aiappinvent.com")
ADMIN_USER = os.environ.get("SOLARPRO_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("SOLARPRO_ADMIN_PASSWORD") or sys.exit("SOLARPRO_ADMIN_PASSWORD not set")

SHOT_DIR = pathlib.Path(__file__).parent / "shots_prod_forms"
SHOT_DIR.mkdir(exist_ok=True)
for f in SHOT_DIR.glob("*.png"):
    f.unlink()

results = []  # (label, status_code, note)

def record(label, status, note=""):
    results.append((label, status, note))
    flag = "PASS" if 200 <= status < 400 else "FAIL"
    print(f"  [{flag}] {status}  {label}  {note}")

def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=30000)
    page.fill('input[name="username"]', ADMIN_USER)
    page.fill('input[name="password"]', ADMIN_PASS)
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded")
    return "/dashboard" in page.url

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900},
                                   user_agent="solarpro-form-auditor/1.0")
        page = ctx.new_page()

        # Capture every navigation/HTTP status so we can audit redirects/4xx.
        nav_status = {"last": None}
        def on_response(r):
            if r.frame == page.main_frame and r.request.is_navigation_request():
                nav_status["last"] = (r.url, r.status)
        page.on("response", on_response)

        print("=" * 72); print(f"PROD form audit  target={BASE}"); print("=" * 72)
        if not login(page):
            sys.exit("login failed — wrong password?")
        print("  login OK"); print()

        # ── GET checks first (we want each surface to render before we POST) ─
        print("[A] anon-or-authed GETs on marketplace surfaces")
        for path, note in [
            ("/marketplace", "anon catalog"),
            ("/procurement-center", "Slice 9 picker"),
            ("/price-sheets", "price-sheets list"),
            ("/rfqs", "RFQ list"),
            ("/rfqs/new", "RFQ form"),
            ("/boms", "BOMs list"),
            ("/admin/marketplace", "admin landing"),
            ("/admin/marketplace/pending", "verification queue"),
            ("/admin/marketplace/suppliers", "supplier admin"),
            ("/admin/marketplace/products", "product admin"),
            ("/admin/marketplace/staff", "staff admin"),
            ("/installation-support", "tech-support dashboard"),
        ]:
            try:
                resp = page.goto(BASE + path, wait_until="commit", timeout=45000)
                record(path, resp.status if resp else 0, note)
            except Exception as e:
                record(path, 0, f"EXCEPTION: {type(e).__name__}")

        print()
        print("[B] POST: create an RFQ end-to-end via the buyer flow")
        # First grab a product to seed
        page.goto(BASE + "/marketplace", wait_until="domcontentloaded", timeout=45000)
        first_link = page.eval_on_selector_all(
            'a[href*="/rfqs/new"]',
            "els => els.length ? els[0].getAttribute('href') : null"
        )
        print(f"  first RFQ-seed link: {first_link}")
        if not first_link:
            record("MISSING: /marketplace -> Request-quote link", 0, "no /rfqs/new?product_id link found")
        else:
            page.goto(BASE + first_link, wait_until="domcontentloaded", timeout=30000)
            page.fill('input[name="title"]', "AUTOTEST PROD RFQ")
            try:
                page.select_option('select[name="delivery_country"]', label="Ghana")
            except Exception:
                pass
            page.fill('input[name="first_item_qty"]', "1")
            page.fill('input[name="first_item_spec"]', "AUTOTEST")
            nav_status["last"] = None
            page.click('button[type="submit"]')
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            last = nav_status["last"] or (page.url, 0)
            record("POST /rfqs/new", last[1], f"-> {last[0]}")
            m = re.search(r"/rfqs/(\d+)", page.url)
            rfq_id = int(m.group(1)) if m else None
            print(f"  rfq_id = {rfq_id}")

            if rfq_id:
                # Add a second item
                page.fill('input[name="name"]', "AUTOTEST extra item")
                page.fill('input[name="qty"]', "2")
                page.fill('input[name="unit"]', "No.")
                nav_status["last"] = None
                page.click('form[action*="/items/add"] button')
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                last = nav_status["last"] or (page.url, 0)
                record(f"POST /rfqs/{rfq_id}/items/add", last[1], f"-> {last[0]}")

                # Send to 1 supplier
                boxes = page.query_selector_all('input[type="checkbox"][name="supplier_ids"]')
                if boxes:
                    boxes[0].check()
                    nav_status["last"] = None
                    page.click('form[action*="/send"] button')
                    page.wait_for_load_state("domcontentloaded", timeout=20000)
                    last = nav_status["last"] or (page.url, 0)
                    record(f"POST /rfqs/{rfq_id}/send", last[1], f"-> {last[0]}")
                else:
                    record(f"POST /rfqs/{rfq_id}/send", 0, "no supplier checkboxes")

        print()
        print("[C] POST: procurement-center add → Basic Price Sheet")
        page.goto(BASE + "/procurement-center", wait_until="domcontentloaded", timeout=45000)
        boxes = page.query_selector_all("input.prod-chk")
        print(f"  catalog checkboxes: {len(boxes)}")
        if boxes:
            boxes[0].check()
            nav_status["last"] = None
            page.click("#addBtn")
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            last = nav_status["last"] or (page.url, 0)
            record("POST /procurement-center/add", last[1], f"-> {last[0]}")
        else:
            record("POST /procurement-center/add", 0, "no products on /procurement-center")

        browser.close()

    # ── Summary
    print()
    print("=" * 72); print("SUMMARY"); print("=" * 72)
    bad = [(l,s,n) for (l,s,n) in results if not (200 <= s < 400)]
    print(f"{len(results)-len(bad)}/{len(results)} PASS,  {len(bad)} FAIL/ERROR")
    if bad:
        print()
        print("Failures:")
        for l,s,n in bad:
            print(f"  [{s}] {l}  ({n})")
        sys.exit(1)

if __name__ == "__main__":
    main()
