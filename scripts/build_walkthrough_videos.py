"""Build real screen-capture walkthrough MP4s for the 3 SolarPro guides.

Replaces the legacy slideshow MP4s with actual Playwright recordings:
  - Real cursor (drawn by JS overlay because headless Chromium has no system cursor)
  - Real screen transitions (the page state actually changes as the cursor
    clicks)
  - edge-tts voice-over composited via FFmpeg

Inputs are the SHELL dicts at the top of this file — each lists the URLs
the recorder should visit and the voice-over script that plays in parallel.

Outputs into docs/:
  docs/guide_quick_walkthrough.mp4       (~30s, anonymous)
  docs/guide_full_user_walkthrough.mp4   (~60s, anonymous demo surfaces)
  docs/guide_technical_walkthrough.mp4   (~45s, public admin tour signals)

The new /support page surfaces these via the support_asset slug mechanism.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
DOCS = PROJECT / "docs"
BASE = "https://solarpro.aiappinvent.com"
VW, VH = 1280, 720

# Pretty SolarPro-branded cursor overlay drawn into the page itself so
# the recording captures a visible mouse. Chromium headless has no
# system cursor — we own it.
CURSOR_OVERLAY = r"""
(function(){
  if (window.__solarproCursorInstalled) return;
  window.__solarproCursorInstalled = true;
  const s = document.createElement('style');
  s.innerHTML = `
    #__sp_cursor {
      position: fixed; left: -100px; top: -100px;
      width: 22px; height: 22px; border-radius: 50%;
      background: radial-gradient(circle at 30% 30%, #fde68a, #fbbf24 55%, #d97706);
      box-shadow: 0 0 14px 4px rgba(251,191,36,.55),
                  0 0 2px 1px rgba(0,0,0,.35) inset;
      pointer-events: none; z-index: 2147483647;
      transition: left .25s cubic-bezier(.22,.61,.36,1),
                  top  .25s cubic-bezier(.22,.61,.36,1),
                  transform .12s ease;
    }
    #__sp_cursor.click { transform: scale(.7); background: #fef08a; }
    @keyframes __sp_ring { 0%{transform:scale(.3);opacity:.9} 100%{transform:scale(2.5);opacity:0} }
    .__sp_ring {
      position: fixed; width: 22px; height: 22px; border-radius: 50%;
      border: 2px solid #fbbf24; pointer-events: none; z-index: 2147483646;
      animation: __sp_ring .55s ease-out forwards;
    }
  `;
  document.documentElement.appendChild(s);
  const c = document.createElement('div');
  c.id = '__sp_cursor';
  document.documentElement.appendChild(c);
  function move(x, y){
    c.style.left = (x - 11) + 'px';
    c.style.top  = (y - 11) + 'px';
  }
  function click(x, y){
    c.classList.add('click');
    setTimeout(() => c.classList.remove('click'), 110);
    const r = document.createElement('div');
    r.className = '__sp_ring';
    r.style.left = (x - 11) + 'px';
    r.style.top  = (y - 11) + 'px';
    document.documentElement.appendChild(r);
    setTimeout(() => r.remove(), 600);
  }
  // Track every mousemove and synthetic click event Playwright fires.
  window.addEventListener('mousemove', e => move(e.clientX, e.clientY), true);
  window.addEventListener('mousedown', e => click(e.clientX, e.clientY), true);
})();
"""


def _move_cursor_smoothly(page, x, y, ms=350):
    """Drive Playwright's pointer in small steps so the overlay animates."""
    page.mouse.move(x, y, steps=20)
    page.wait_for_timeout(ms)


def _click_with_pause(page, selector, before_ms=400, after_ms=900):
    """Move the cursor onto a selector, click, give the page time to respond."""
    page.wait_for_selector(selector, timeout=10000)
    box = page.locator(selector).first.bounding_box()
    if not box:
        page.wait_for_timeout(after_ms)
        return
    cx = int(box["x"] + box["width"]  / 2)
    cy = int(box["y"] + box["height"] / 2)
    _move_cursor_smoothly(page, cx, cy)
    page.wait_for_timeout(before_ms)
    page.mouse.click(cx, cy)
    page.wait_for_timeout(after_ms)


def _hover_smoothly(page, selector, hold_ms=900):
    page.wait_for_selector(selector, timeout=10000)
    box = page.locator(selector).first.bounding_box()
    if not box:
        return
    cx = int(box["x"] + box["width"]  / 2)
    cy = int(box["y"] + box["height"] / 2)
    _move_cursor_smoothly(page, cx, cy)
    page.wait_for_timeout(hold_ms)


# ── Shell dicts — what each walkthrough does ─────────────────────────────────

def shell_quick(page):
    """30-second tour of /bill-check (anonymous)."""
    page.goto(f"{BASE}/bill-check", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(1500)
    # Hover the chip row to point out building-type selection
    for sel in ['[data-bc-type="home"]', '[data-bc-type="lifeline"]',
                '[data-bc-type="shop"]', '[data-bc-type="slt"]']:
        _hover_smoothly(page, sel, hold_ms=600)
    # Type a real bill amount so the outcome cards animate
    page.locator("#bcLandingBillNum").click()
    page.wait_for_timeout(300)
    page.locator("#bcLandingBillNum").fill("")
    for ch in "6800":
        page.keyboard.type(ch, delay=110)
    page.wait_for_timeout(800)
    # Drag the slider
    slider = page.locator("#bcLandingBill").bounding_box()
    if slider:
        sx = int(slider["x"] + 60)
        sy = int(slider["y"] + slider["height"] / 2)
        page.mouse.move(sx, sy, steps=10)
        page.mouse.down()
        page.mouse.move(int(slider["x"] + slider["width"] * 0.45), sy, steps=30)
        page.wait_for_timeout(400)
        page.mouse.move(int(slider["x"] + slider["width"] * 0.78), sy, steps=30)
        page.mouse.up()
        page.wait_for_timeout(800)
    # Scroll down to show the step row + FAQ
    page.evaluate("window.scrollTo({top: 600, behavior:'smooth'})")
    page.wait_for_timeout(1400)
    page.evaluate("window.scrollTo({top: 1200, behavior:'smooth'})")
    page.wait_for_timeout(1400)
    page.evaluate("window.scrollTo({top: 0, behavior:'smooth'})")
    page.wait_for_timeout(1200)


def shell_full_user(page):
    """60-second tour: homepage → marketplace → bill-check → guides (all anon)."""
    page.goto(f"{BASE}/", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(1500)
    # Hover the bill-check magnet
    try:
        _hover_smoothly(page, 'a[href*="bill-check"]', hold_ms=1100)
    except Exception:
        pass
    # Jump to /marketplace
    page.goto(f"{BASE}/marketplace?country=GH", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(1400)
    # Hover the country picker
    try:
        _hover_smoothly(page, 'select[name="country"]', hold_ms=900)
    except Exception:
        pass
    # Scroll down a bit so a compliance badge becomes visible
    page.evaluate("window.scrollTo({top: 600, behavior:'smooth'})")
    page.wait_for_timeout(1200)
    page.evaluate("window.scrollTo({top: 1200, behavior:'smooth'})")
    page.wait_for_timeout(1200)
    # Jump to /bill-check
    page.goto(f"{BASE}/bill-check", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(1200)
    page.locator("#bcLandingBillNum").click()
    page.locator("#bcLandingBillNum").fill("")
    for ch in "9500":
        page.keyboard.type(ch, delay=80)
    page.wait_for_timeout(900)
    # Then jump to /guides/quick to introduce the guide library
    page.goto(f"{BASE}/guides/quick", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(1500)
    page.evaluate("window.scrollTo({top: 500, behavior:'smooth'})")
    page.wait_for_timeout(1200)


def shell_technical(page):
    """45-second tour: technical guide → architecture sections."""
    page.goto(f"{BASE}/guides/technical", wait_until="domcontentloaded")
    page.evaluate(CURSOR_OVERLAY)
    page.wait_for_timeout(2000)
    # Scroll through the technical guide showing each section
    for top in (400, 1200, 2200, 3000, 3800):
        page.evaluate(f"window.scrollTo({{top: {top}, behavior:'smooth'}})")
        page.wait_for_timeout(1400)
    # Bounce back to the top
    page.evaluate("window.scrollTo({top: 0, behavior:'smooth'})")
    page.wait_for_timeout(1500)


# Voice-over per walkthrough — composited via edge-tts + ffmpeg
NARRATIONS = {
    "quick": (
        "SolarPro's Check My Bill tool. Anonymous, free, takes about a minute. "
        "Drop your monthly Ghana bill in, pick your customer category, and we'll "
        "show you exactly how much of that bill could repay a solar loan. "
        "The outcome cards update live as you drag the slider, "
        "so you can test different amounts in seconds."
    ),
    "full_user": (
        "Welcome to SolarPro Design. From the homepage, you can check your bill, "
        "browse the marketplace, or start a free assessment. "
        "The marketplace lists hundreds of products with per-country compliance "
        "badges so you know what's legal to install in your region. "
        "Run a quick bill check, then read the Quick Start guide to learn the rest."
    ),
    "technical": (
        "The Technical Guide covers SolarPro's architecture: the single-file Flask app, "
        "the sizing engine flow from loads through results, the marketplace schema, "
        "the country compliance model, the Growth layer with seven share-card types, "
        "and the AI stack. Use this as the reference for any integration or extension."
    ),
}

SHELLS = [
    ("quick",     "guide_quick_walkthrough.mp4",     shell_quick),
    ("full_user", "guide_full_user_walkthrough.mp4", shell_full_user),
    ("technical", "guide_technical_walkthrough.mp4", shell_technical),
]


def _ffmpeg_bin():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


async def _synth_voice(text: str, mp3_path: Path):
    import edge_tts
    voice = "en-US-AriaNeural"
    com = edge_tts.Communicate(text, voice, rate="-2%")
    await com.save(str(mp3_path))


def _record_session(shell_fn, webm_dir: Path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ])
        ctx = browser.new_context(
            viewport={"width": VW, "height": VH},
            record_video_dir=str(webm_dir),
            record_video_size={"width": VW, "height": VH},
        )
        page = ctx.new_page()
        # Reinstall the cursor overlay on every navigation
        page.add_init_script(CURSOR_OVERLAY)
        try:
            shell_fn(page)
        finally:
            ctx.close()  # flushes the .webm
            browser.close()
    webms = sorted(webm_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not webms:
        raise RuntimeError("Playwright produced no .webm")
    return webms[0]


def _mux_to_mp4(webm: Path, mp3: Path, mp4_out: Path):
    """Composite webm video + mp3 narration into a single MP4."""
    ff = _ffmpeg_bin()
    cmd = [
        ff, "-y",
        "-i", str(webm),
        "-i", str(mp3),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",  # cap at the shorter of (video, audio) — keeps file tight
        "-movflags", "+faststart",
        str(mp4_out),
    ]
    print("  ffmpeg:", " ".join(cmd[:4]), "... -> ", mp4_out.name)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr[-2000:])
        raise RuntimeError(f"ffmpeg mux failed for {mp4_out.name}")


def main(*targets):
    """Pass target slugs to limit which walkthroughs build; default = all."""
    if not targets:
        targets = tuple(s[0] for s in SHELLS)
    DOCS.mkdir(exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="sp_walkthrough_"))
    print(f"workdir: {workdir}\n")
    for slug, mp4_name, shell_fn in SHELLS:
        if slug not in targets:
            continue
        print(f"=== building {mp4_name} ===")
        webm_dir = workdir / slug
        webm_dir.mkdir(parents=True, exist_ok=True)
        # 1. Synthesise the narration first so it overlays cleanly.
        mp3 = workdir / f"{slug}.mp3"
        asyncio.run(_synth_voice(NARRATIONS[slug], mp3))
        print(f"  voice MP3: {mp3.stat().st_size} bytes")
        # 2. Record the Playwright session.
        webm = _record_session(shell_fn, webm_dir)
        print(f"  Playwright WebM: {webm.name} {webm.stat().st_size} bytes")
        # 3. Mux into a single MP4 in docs/.
        mp4 = DOCS / mp4_name
        _mux_to_mp4(webm, mp3, mp4)
        print(f"  -> {mp4} ({mp4.stat().st_size} bytes)\n")
    print("done.")


if __name__ == "__main__":
    main(*sys.argv[1:])
