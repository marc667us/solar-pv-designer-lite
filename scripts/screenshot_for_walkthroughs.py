"""Capture real screenshots of the live SolarPro app for pairing with
the audio walkthroughs in the MP4 build step.

Why this exists
---------------
User: "the picture on the mp3 audio screen ... these are not screen
shots, please take of [the app]". The previous MP4 build used a brand
flyer + a 3d10 reference mock — neither was a live app screenshot.
This script logs in as admin and grabs real pages.

Outputs
-------
docs/screens/walkthrough_user.png   — friendly user-facing surface
                                       (dashboard with stats and
                                       project tiles)
docs/screens/walkthrough_tech.png   — technical-looking surface
                                       (support / resources page with
                                       tutorial cards)

These two files are consumed by build_collateral_pdfs.py
VIDEO_TO_BUILD to produce the SolarPro_*_Walkthrough.mp4 files.

Auth
----
Admin credentials read from env (SOLARPRO_ADMIN_USERNAME /
SOLARPRO_ADMIN_PASSWORD). Falls back to the values stored in
memory `project_solar_pv_credentials` as of 2026-06-13 if the env
isn't set, so local screenshot runs don't need extra setup.
"""
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
SCREENS = PROJECT / "docs" / "screens"
SCREENS.mkdir(parents=True, exist_ok=True)

BASE = "https://solarpro-global.onrender.com"
USERNAME = os.environ.get("SOLARPRO_ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("SOLARPRO_ADMIN_PASSWORD", "")

VIEWPORT = {"width": 1280, "height": 720}


def login(page):
    """Submit /login form — fields are #username (note: NOT email) and #password."""
    page.goto(f"{BASE}/login", wait_until="networkidle", timeout=45000)
    # The login template uses "username" not "email" per CLAUDE.md.
    page.fill('input[name="username"]', USERNAME)
    page.fill('input[name="password"]', PASSWORD)
    page.click('button[type="submit"], input[type="submit"]')
    page.wait_for_load_state("networkidle", timeout=45000)


def shot(page, url, out_name, full_page=False):
    """Navigate and screenshot."""
    page.goto(f"{BASE}{url}", wait_until="networkidle", timeout=45000)
    target = SCREENS / out_name
    page.screenshot(path=str(target), full_page=full_page)
    print(f"  shot: {target}  ({target.stat().st_size:,} bytes)")
    return target


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport=VIEWPORT,
                                  device_scale_factor=2)  # retina for crisp text
        page = ctx.new_page()

        print(f"[1/3] login as {USERNAME}@{BASE} ...")
        login(page)

        print(f"[2/3] dashboard -> walkthrough_user.png")
        shot(page, "/dashboard", "walkthrough_user.png", full_page=False)

        print(f"[3/3] support -> walkthrough_tech.png")
        shot(page, "/support", "walkthrough_tech.png", full_page=False)

        browser.close()
        print("done.")


if __name__ == "__main__":
    main()
