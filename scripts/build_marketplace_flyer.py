"""Build two marketplace launch flyers (1080x1080 square + 1200x628 rectangle).

Uses Pillow only — no qrcode dep. Both flyers carry:
  * 'FREE TO BROWSE' pill (top)
  * Main heading: 'Electrical Pricing Marketplace'
  * 4 bullets: live supplier prices · 20+ categories · BOM builder · BOQ export
  * Big URL: solarpro.aiappinvent.com/marketplace

Theme matches solar's gold/dark brand. Output land in
docs/marketplace_launch/ alongside the markdown copy.

Usage: python scripts/build_marketplace_flyer.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "marketplace_launch"

# Solar brand palette
BG_DARK = (15, 15, 34)         # #0f0f22
BG_PANEL = (26, 16, 48)        # #1a1030
GOLD = (245, 158, 11)          # #f59e0b
GOLD_DIM = (180, 117, 9)
ORANGE = (234, 88, 12)
TEXT = (226, 226, 240)
MUTED = (144, 144, 192)
GREEN = (34, 197, 94)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Pick a font that's likely available on Windows."""
    candidates_bold = [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    candidates_regular = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    for path in (candidates_bold if bold else candidates_regular):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_panel(draw: ImageDraw.ImageDraw, x0: int, y0: int,
                    x1: int, y1: int) -> None:
    """Vertical gradient inside the panel — dark navy → dark purple → dark navy."""
    h = y1 - y0
    for i in range(h):
        t = i / max(1, h - 1)
        # Blend through panel + back
        if t < 0.5:
            f = t * 2
            r = int(BG_DARK[0] + (BG_PANEL[0] - BG_DARK[0]) * f)
            g = int(BG_DARK[1] + (BG_PANEL[1] - BG_DARK[1]) * f)
            b = int(BG_DARK[2] + (BG_PANEL[2] - BG_DARK[2]) * f)
        else:
            f = (t - 0.5) * 2
            r = int(BG_PANEL[0] + (BG_DARK[0] - BG_PANEL[0]) * f)
            g = int(BG_PANEL[1] + (BG_DARK[1] - BG_PANEL[1]) * f)
            b = int(BG_PANEL[2] + (BG_DARK[2] - BG_PANEL[2]) * f)
        draw.line([(x0, y0 + i), (x1, y0 + i)], fill=(r, g, b))


def _draw_lightning_bolt(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                          size: int) -> None:
    s = size
    pts = [
        (cx - s // 3, cy - s // 2),
        (cx + s // 6, cy - s // 6),
        (cx - s // 8, cy - s // 6),
        (cx + s // 3, cy + s // 2),
        (cx - s // 6, cy + s // 6),
        (cx + s // 8, cy + s // 6),
    ]
    draw.polygon(pts, fill=GOLD, outline=GOLD_DIM)


def _draw_pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str,
               font: ImageFont.FreeTypeFont, fg, bg) -> int:
    pad_x, pad_y = 18, 8
    tw = draw.textlength(text, font=font)
    w, h = int(tw + pad_x * 2), font.size + pad_y * 2
    radius = h // 2
    draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=fg)
    return w


def _draw_bullet(draw: ImageDraw.ImageDraw, x: int, y: int, text: str,
                 font: ImageFont.FreeTypeFont) -> None:
    bullet_x = x + 8
    draw.ellipse(
        [bullet_x - 5, y + font.size // 3, bullet_x + 5, y + font.size // 3 + 10],
        fill=GOLD,
    )
    draw.text((x + 28, y), text, font=font, fill=TEXT)


def build_square_1080() -> Path:
    W = H = 1080
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)
    _gradient_panel(draw, 0, 0, W, H)

    # Glow ring top-right
    for r in range(420, 0, -20):
        alpha = max(0, 25 - (420 - r) // 16)
        if alpha <= 0:
            break
        glow = (GOLD[0], GOLD[1], GOLD[2])
        # Approximate halo with thin concentric arcs
        draw.ellipse([W - r - 60, -r + 80, W + r - 60, r + 80],
                     outline=glow, width=1)

    # Lightning bolt mark
    _draw_lightning_bolt(draw, 110, 130, 96)

    # SolarPro logotype
    draw.text((180, 90), "SolarPro",
              font=_font(40, bold=True), fill=TEXT)
    draw.text((180, 140), "Global", font=_font(28), fill=MUTED)

    # Pills
    f_pill = _font(22, bold=True)
    px = 90
    pw = _draw_pill(draw, px, 240, "FREE TO BROWSE", f_pill,
                    fg=(0, 0, 0), bg=GOLD)
    _draw_pill(draw, px + pw + 12, 240, "ELECTRICAL PRICING", f_pill,
               fg=GOLD, bg=(0, 0, 0))

    # Heading
    draw.text((90, 320),  "Electrical Pricing", font=_font(72, bold=True), fill=TEXT)
    draw.text((90, 400),  "Marketplace.",       font=_font(72, bold=True), fill=GOLD)

    # Sub
    draw.text((90, 510),
              "Live supplier prices. Build a BOQ in minutes.",
              font=_font(28), fill=MUTED)

    # Bullets
    f_b = _font(28, bold=True)
    bullets = [
        "Live prices across 20+ electrical categories",
        "Transformers, cables, switchgear, sockets...",
        "BOM builder with labour + profit + VAT markups",
        "Export Excel and PDF in one click",
    ]
    for i, b in enumerate(bullets):
        _draw_bullet(draw, 90, 600 + i * 56, b, f_b)

    # URL panel
    url_y = 880
    draw.rounded_rectangle([60, url_y, W - 60, url_y + 110], radius=24,
                           fill=(0, 0, 0), outline=GOLD, width=3)
    draw.text((90, url_y + 24), "Browse free:",
              font=_font(22, bold=True), fill=MUTED)
    draw.text((90, url_y + 54), "solarpro.aiappinvent.com/marketplace",
              font=_font(34, bold=True), fill=GOLD)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "marketplace_flyer_1080x1080.png"
    img.save(out, format="PNG", optimize=True)
    return out


def build_rect_1200x628() -> Path:
    W, H = 1200, 628
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)
    _gradient_panel(draw, 0, 0, W, H)

    # Brand mark
    _draw_lightning_bolt(draw, 90, 90, 70)
    draw.text((150, 60),  "SolarPro Global",
              font=_font(34, bold=True), fill=TEXT)
    draw.text((150, 102), "solarpro.aiappinvent.com",
              font=_font(18), fill=MUTED)

    # Pill
    _draw_pill(draw, 70, 180, "FREE TO BROWSE", _font(20, bold=True),
               fg=(0, 0, 0), bg=GOLD)

    # Heading
    draw.text((70, 230), "Electrical Pricing Marketplace",
              font=_font(60, bold=True), fill=TEXT)
    draw.text((70, 312), "Live supplier prices in one place.",
              font=_font(28), fill=GOLD)

    # Bullets
    f_b = _font(22, bold=True)
    bullets = [
        "20+ electrical categories",
        "BOM with labour + profit + VAT",
        "Excel + PDF export",
        "RFQs to verified suppliers",
    ]
    for i, b in enumerate(bullets):
        _draw_bullet(draw, 70, 380 + i * 38, b, f_b)

    # URL panel
    draw.rounded_rectangle([700, 380, W - 60, 560], radius=24,
                           fill=(0, 0, 0), outline=GOLD, width=3)
    draw.text((730, 410), "Browse free:",
              font=_font(20, bold=True), fill=MUTED)
    draw.text((730, 444), "solarpro.aiappinvent.com",
              font=_font(28, bold=True), fill=GOLD)
    draw.text((730, 484), "/marketplace",
              font=_font(28, bold=True), fill=GOLD)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "marketplace_flyer_1200x628.png"
    img.save(out, format="PNG", optimize=True)
    return out


if __name__ == "__main__":
    p1 = build_square_1080()
    p2 = build_rect_1200x628()
    print(f"wrote {p1}")
    print(f"wrote {p2}")
