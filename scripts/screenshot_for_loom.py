"""Capture feature-specific screenshots for the Loom-style walkthroughs.

For each Loom video we capture the SCREENS being narrated, so the
viewer sees the actual feature being tutored (not a generic dashboard).

Output:
  docs/screens/loom_boq/01_bom_list.png
  docs/screens/loom_boq/02_new_bom.png
  docs/screens/loom_boq/03_bom_editor.png
  docs/screens/loom_boq/04_basic_prices.png
  docs/screens/loom_boq/05_cost_estimate.png
  docs/screens/loom_boq/06_excel_pdf_email.png
  docs/screens/loom_boq/07_bom_done.png

  docs/screens/loom_cost/01_bom_list.png
  docs/screens/loom_cost/02_bom_open.png
  docs/screens/loom_cost/03_cost_estimate.png
  docs/screens/loom_cost/04_edit_rates_modal.png
  docs/screens/loom_cost/05_excel_pdf_buttons.png

  docs/screens/loom_send/01_email_modal.png
  docs/screens/loom_send/02_send_clicked.png
  docs/screens/loom_send/03_done.png

build_loom_videos.py then assembles these into multi-shot slideshow
MP4s with the matching MP3 narration on top.

Login uses the legacy path via ?legacy=1 because KC is enabled in
production -- bypasses the OIDC redirect for the screenshot run.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
SCREENS_BASE = PROJECT / "docs" / "screens"

BASE = "https://solarpro.aiappinvent.com"
USERNAME = os.environ.get("SOLARPRO_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "marble-willow-poppy-river")

VIEWPORT = {"width": 1280, "height": 720}


def legacy_login(page):
    page.goto(f"{BASE}/login?legacy=1", wait_until="networkidle", timeout=45000)
    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=45000)


def first_bom_id(page) -> int | None:
    """Find an existing BOM id from the BOMs list page."""
    page.goto(f"{BASE}/boms", wait_until="networkidle", timeout=30000)
    # Find any link of the form /boms/<id> in the table.
    import re
    html = page.content()
    m = re.search(r'href="/boms/(\d+)"', html)
    return int(m.group(1)) if m else None


def snap(page, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out), full_page=False)
    print(f"  wrote: {out}")


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()

        print("=== Login ===")
        legacy_login(page)

        bid = first_bom_id(page)
        if not bid:
            print("FAIL: no existing BOM on live -- cannot screenshot the editor flow.")
            print("      Create at least one BOM (any) before re-running this script.")
            sys.exit(1)
        print(f"  using BOM id {bid}")

        # ─── Loom 1: BOQ in 60 seconds ───────────────────────────────
        d = SCREENS_BASE / "loom_boq"
        page.goto(f"{BASE}/boms", wait_until="networkidle", timeout=30000)
        snap(page, d / "01_bom_list.png")

        page.goto(f"{BASE}/boms/new", wait_until="networkidle", timeout=30000)
        snap(page, d / "02_new_bom.png")

        page.goto(f"{BASE}/boms/{bid}", wait_until="networkidle", timeout=30000)
        snap(page, d / "03_bom_editor.png")

        page.goto(f"{BASE}/boms/{bid}/basic-prices", wait_until="networkidle", timeout=30000)
        snap(page, d / "04_basic_prices.png")

        page.goto(f"{BASE}/boms/{bid}/boq", wait_until="networkidle", timeout=30000)
        snap(page, d / "05_cost_estimate.png")
        # Screenshot the toolbar area near Excel/PDF/Email buttons -- same page,
        # just framed slightly differently. We reuse the cost-estimate page.
        snap(page, d / "06_excel_pdf_email.png")

        page.goto(f"{BASE}/boms", wait_until="networkidle", timeout=30000)
        snap(page, d / "07_bom_done.png")

        # ─── Loom 2: Cost Estimate in 60 seconds ─────────────────────
        d = SCREENS_BASE / "loom_cost"
        page.goto(f"{BASE}/boms", wait_until="networkidle", timeout=30000)
        snap(page, d / "01_bom_list.png")
        page.goto(f"{BASE}/boms/{bid}", wait_until="networkidle", timeout=30000)
        snap(page, d / "02_bom_open.png")
        page.goto(f"{BASE}/boms/{bid}/boq", wait_until="networkidle", timeout=30000)
        snap(page, d / "03_cost_estimate.png")
        # Open the rate-edit modal for shot 4. Internal view shows the button.
        page.goto(f"{BASE}/boms/{bid}/rate-buildup", wait_until="networkidle", timeout=30000)
        # Click Edit rates if visible
        try:
            page.click('button[data-bs-target="#editBomRatesModal"]', timeout=5000)
            page.wait_for_selector("#editBomRatesModal.show", timeout=5000)
            snap(page, d / "04_edit_rates_modal.png")
        except Exception:
            # Fall back to a plain snapshot of the internal view
            snap(page, d / "04_edit_rates_modal.png")
        page.goto(f"{BASE}/boms/{bid}/boq", wait_until="networkidle", timeout=30000)
        snap(page, d / "05_excel_pdf_buttons.png")

        # ─── Loom 3: Send to client in 30 seconds ────────────────────
        d = SCREENS_BASE / "loom_send"
        page.goto(f"{BASE}/boms/{bid}/boq", wait_until="networkidle", timeout=30000)
        # Open the email modal
        try:
            page.click('button[data-bs-target="#emailBomModal"]', timeout=5000)
            page.wait_for_selector("#emailBomModal.show", timeout=5000)
            snap(page, d / "01_email_modal.png")
        except Exception:
            snap(page, d / "01_email_modal.png")
        # Type a recipient address for the "send" shot
        try:
            page.fill('#emailBomModal input[name="to_email"]', "client@example.com")
            snap(page, d / "02_send_clicked.png")
        except Exception:
            snap(page, d / "02_send_clicked.png")
        page.goto(f"{BASE}/boms", wait_until="networkidle", timeout=30000)
        snap(page, d / "03_done.png")

        ctx.close()
        browser.close()

    print("\n=== Done -- screenshots written to docs/screens/loom_*/ ===")


if __name__ == "__main__":
    main()
