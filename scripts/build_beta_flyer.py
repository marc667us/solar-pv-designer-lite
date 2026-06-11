"""Beta-launch flyer generator for FB / IG / LinkedIn.

Produces two PNG sizes from the live landing-page copy:
  - docs/SolarPro_Beta_Flyer_1080.png      1080x1080  IG feed, FB feed
  - docs/SolarPro_Beta_Flyer_1200x628.png  1200x628   LinkedIn, FB link preview

Brand: dark navy bg, solar-gold accents, white display text.
Run: python scripts/build_beta_flyer.py
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs"
OUT_DIR.mkdir(exist_ok=True)

# ── Brand palette (matches templates/landing.html + base.html) ────────────────
BG          = (10, 10, 20)        # near-black navy
BG_DEEP     = (6, 6, 14)
CARD_BG     = (15, 15, 34)
BORDER      = (30, 30, 58)
GOLD        = (245, 158, 11)
GOLD_LIGHT  = (251, 191, 36)
GOLD_SOFT_A = (245, 158, 11, 40)  # ~16% opacity for badge fills
TEXT        = (242, 242, 253)
MUTED       = (140, 140, 184)
GREEN_GO    = (34, 197, 94)       # "live" indicator dot

# Windows fonts (verified present on this box)
F_ARIAL_BLACK = "C:/Windows/Fonts/ariblk.ttf"
F_ARIAL_BOLD  = "C:/Windows/Fonts/arialbd.ttf"
F_ARIAL       = "C:/Windows/Fonts/arial.ttf"
# arial.ttf exists; ariblk may not — fall back to bold if missing.
import os
if not os.path.exists(F_ARIAL_BLACK):
    F_ARIAL_BLACK = F_ARIAL_BOLD


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    """Simple top->bottom gradient."""
    img = Image.new("RGB", (w, h), top)
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
        )
    # Stretch single column across width — much faster than per-pixel fill
    col = img.crop((0, 0, 1, h))
    return col.resize((w, h), Image.NEAREST)


def radial_glow(w: int, h: int, cx: int, cy: int, radius: int, color_rgba: tuple) -> Image.Image:
    """Soft radial glow blob for hero accent."""
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    steps = 40
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        alpha = int(color_rgba[3] * (1 - i / steps) ** 2)
        d.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(color_rgba[0], color_rgba[1], color_rgba[2], alpha),
        )
    return glow


def rounded_rect(draw: ImageDraw.ImageDraw, xy, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def measure(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont) -> tuple:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ── Square 1080×1080 (IG / FB feed) ───────────────────────────────────────────
def build_square():
    W, H = 1080, 1080
    base = vertical_gradient(W, H, BG_DEEP, BG).convert("RGBA")
    glow = radial_glow(W, H, W // 2, 0, 700, (245, 158, 11, 90))
    img = Image.alpha_composite(base, glow)
    d = ImageDraw.Draw(img)

    # Hero badge — gold pill at top
    badge_text = "● BETA LIVE  ·  GLOBAL PLATFORM  ·  FREE TO START"
    badge_f = font(F_ARIAL_BOLD, 22)
    bw, bh = measure(d, badge_text, badge_f)
    bx0 = (W - bw) // 2 - 24
    by0 = 90
    rounded_rect(d, (bx0, by0, bx0 + bw + 48, by0 + bh + 24), 28,
                 fill=(245, 158, 11, 38), outline=GOLD, width=2)
    d.text((bx0 + 24, by0 + 12), badge_text, font=badge_f, fill=GOLD_LIGHT)

    # Headline — 3 lines, big bold. Use font.size for stable line-height
    # (Pillow's textbbox ignores descender space when text has none).
    h1 = "Find Solar Tenders."
    h2 = "Design the System."
    h3 = "Win the Contract."
    h_size = 84
    h_f = font(F_ARIAL_BLACK, h_size)
    h_line = int(h_size * 1.08)   # consistent leading
    y = 210
    for line in (h1, h2, h3):
        lw, _ = measure(d, line, h_f)
        d.text(((W - lw) // 2, y), line, font=h_f, fill=TEXT)
        y += h_line

    # Subhead — explicit gap below headline
    y += 36
    sub = "Automatically find live solar RFPs across 22+ countries —"
    sub2 = "then generate full engineering design, BOQ & proposal in 30 minutes."
    s_f = font(F_ARIAL, 26)
    for line in (sub, sub2):
        lw, _ = measure(d, line, s_f)
        d.text(((W - lw) // 2, y), line, font=s_f, fill=MUTED)
        y += 36
    y += 16

    # Three value tiles
    tiles = [
        ("RFP RADAR",   "22+ countries scanned\nfor live solar tenders"),
        ("AUTO-DESIGN", "PV, battery, inverter,\ncable sizing in minutes"),
        ("PROPOSAL",    "Bankable BOQ + financial\nproposal — one click"),
    ]
    tile_y = y + 8
    tile_w, tile_h = 290, 170
    gap = 24
    total_w = tile_w * 3 + gap * 2
    tile_x0 = (W - total_w) // 2

    title_f = font(F_ARIAL_BOLD, 22)
    body_f  = font(F_ARIAL, 19)
    for i, (title, body) in enumerate(tiles):
        x = tile_x0 + i * (tile_w + gap)
        rounded_rect(d, (x, tile_y, x + tile_w, tile_y + tile_h), 16,
                     fill=CARD_BG, outline=BORDER, width=1)
        # Gold dot
        d.ellipse((x + 22, tile_y + 22, x + 36, tile_y + 36), fill=GOLD)
        d.text((x + 22, tile_y + 50), title, font=title_f, fill=GOLD_LIGHT)
        for li, bl in enumerate(body.split("\n")):
            d.text((x + 22, tile_y + 86 + li * 26), bl, font=body_f, fill=TEXT)

    # CTA — gold filled rounded button
    cta_text = "Start Free — 14 Day Trial — No Card"
    cta_f = font(F_ARIAL_BOLD, 32)
    cw, ch = measure(d, cta_text, cta_f)
    cx0 = (W - (cw + 80)) // 2
    cy0 = tile_y + tile_h + 38
    rounded_rect(d, (cx0, cy0, cx0 + cw + 80, cy0 + ch + 30), 32, fill=GOLD)
    d.text((cx0 + 40, cy0 + 15), cta_text, font=cta_f, fill=BG_DEEP)

    # URL
    url = "solarpro.aiappinvent.com"
    url_f = font(F_ARIAL_BOLD, 30)
    uw, uh = measure(d, url, url_f)
    d.text(((W - uw) // 2, cy0 + ch + 90), url, font=url_f, fill=TEXT)

    # Brand mark — bottom
    brand = "SolarPro Global"
    bf = font(F_ARIAL_BOLD, 22)
    bw2, bh2 = measure(d, brand, bf)
    d.text(((W - bw2) // 2, H - 70), brand, font=bf, fill=MUTED)

    out = OUT_DIR / "SolarPro_Beta_Flyer_1080.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")


# ── Wide 1200×628 (LinkedIn / FB link preview) ────────────────────────────────
def build_wide():
    W, H = 1200, 628
    base = vertical_gradient(W, H, BG_DEEP, BG).convert("RGBA")
    glow = radial_glow(W, H, W // 4, -40, 500, (245, 158, 11, 80))
    img = Image.alpha_composite(base, glow)
    d = ImageDraw.Draw(img)

    # Left column — badge + headline + subhead
    L_PAD = 60
    badge_text = "● BETA LIVE · GLOBAL"
    badge_f = font(F_ARIAL_BOLD, 18)
    bw, bh = measure(d, badge_text, badge_f)
    by0 = 60
    rounded_rect(d, (L_PAD, by0, L_PAD + bw + 36, by0 + bh + 18), 22,
                 fill=(245, 158, 11, 38), outline=GOLD, width=2)
    d.text((L_PAD + 18, by0 + 9), badge_text, font=badge_f, fill=GOLD_LIGHT)

    # Headline
    h_lines = ["Find Solar Tenders.", "Design the System.", "Win the Contract."]
    h_f = font(F_ARIAL_BLACK, 56)
    y = 130
    for line in h_lines:
        d.text((L_PAD, y), line, font=h_f, fill=TEXT)
        _, lh = measure(d, line, h_f)
        y += lh + 4

    # Subhead
    sub = "Live RFPs across 22+ countries. Engineering design,"
    sub2 = "BOQ & bankable proposal — in 30 minutes."
    s_f = font(F_ARIAL, 22)
    for line in (sub, sub2):
        d.text((L_PAD, y + 14), line, font=s_f, fill=MUTED)
        _, lh = measure(d, line, s_f)
        y += lh + 4

    # Right column — CTA card
    R_X = 720
    card_y = 80
    card_w, card_h = 420, 470
    rounded_rect(d, (R_X, card_y, R_X + card_w, card_y + card_h), 22,
                 fill=CARD_BG, outline=BORDER, width=2)

    # Card header — gold dot + label
    d.ellipse((R_X + 28, card_y + 32, R_X + 44, card_y + 48), fill=GOLD)
    label_f = font(F_ARIAL_BOLD, 16)
    d.text((R_X + 56, card_y + 32), "BETA · NO CARD NEEDED", font=label_f, fill=GOLD_LIGHT)

    # Card title
    title_f = font(F_ARIAL_BLACK, 34)
    d.text((R_X + 28, card_y + 78), "Start Free.", font=title_f, fill=TEXT)
    d.text((R_X + 28, card_y + 120), "14 Day Trial.", font=title_f, fill=TEXT)

    # Card body — value bullets
    body_f = font(F_ARIAL, 18)
    bullets = [
        "Live tender + RFP feed",
        "Auto PV / battery / inverter sizing",
        "BOQ + financial proposal",
        "BS 7671 / IEC 60364 compliant",
    ]
    by = card_y + 200
    for b in bullets:
        d.text((R_X + 28, by), "•", font=body_f, fill=GOLD)
        d.text((R_X + 50, by), b, font=body_f, fill=TEXT)
        by += 32

    # CTA pill at bottom of card
    cta = "solarpro.aiappinvent.com"
    cta_f = font(F_ARIAL_BOLD, 22)
    cw, ch = measure(d, cta, cta_f)
    cx0 = R_X + (card_w - (cw + 40)) // 2
    cy0 = card_y + card_h - 70
    rounded_rect(d, (cx0, cy0, cx0 + cw + 40, cy0 + ch + 22), 26, fill=GOLD)
    d.text((cx0 + 20, cy0 + 10), cta, font=cta_f, fill=BG_DEEP)

    # Brand mark — bottom left
    brand = "SolarPro Global"
    bf = font(F_ARIAL_BOLD, 18)
    d.text((L_PAD, H - 50), brand, font=bf, fill=MUTED)

    out = OUT_DIR / "SolarPro_Beta_Flyer_1200x628.png"
    img.convert("RGB").save(out, "PNG", optimize=True)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    build_square()
    build_wide()
