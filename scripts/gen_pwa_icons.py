"""Generate square PWA icons for SolarPro (on-brand solar mark).

Produces, into static/icons/:
    icon-192.png            192x192  (standard)
    icon-512.png            512x512  (standard)
    icon-maskable-512.png   512x512  (content inside the center ~80% safe zone,
                                       full-bleed background so an OS mask never
                                       clips the mark -- purpose "maskable")

Drawn with Pillow at 4x then downsampled for clean anti-aliased edges. No SVG
renderer needed (cairosvg is not installed). Brand: dark bg #0f1020, amber sun
#f59e0b (the app theme-color). Re-runnable; overwrites the PNGs.
"""

import math
import os

from PIL import Image, ImageDraw

BG = (15, 16, 32)          # #0f1020 -- app dark theme
AMBER = (245, 158, 11)     # #f59e0b -- theme-color
AMBER_HI = (251, 191, 36)  # #fbbf24 -- highlight

OUT = os.path.join(os.path.dirname(__file__), "..", "static", "icons")


def _draw(size, safe=1.0):
    """Draw one icon at `size` px. `safe` (<=1.0) shrinks the mark toward the
    centre for maskable icons (leaves a padding ring the OS mask can eat)."""
    S = size * 4                      # supersample
    img = Image.new("RGB", (S, S), BG)
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    # Overall mark radius (disc + rays reach). For maskable, keep within ~80%.
    reach = (S * 0.42) * safe
    disc_r = reach * 0.52
    ray_in = disc_r * 1.18
    ray_out = reach

    # Rays: 12 tapered spokes.
    n = 12
    for i in range(n):
        a = (i / n) * 2 * math.pi
        # a small angular half-width for the tapered ray
        hw = math.radians(6)
        p_out = (cx + ray_out * math.cos(a), cy + ray_out * math.sin(a))
        p_l = (cx + ray_in * math.cos(a - hw), cy + ray_in * math.sin(a - hw))
        p_r = (cx + ray_in * math.cos(a + hw), cy + ray_in * math.sin(a + hw))
        d.polygon([p_out, p_l, p_r], fill=AMBER)

    # Sun disc (amber with a slightly brighter inner highlight).
    d.ellipse([cx - disc_r, cy - disc_r, cx + disc_r, cy + disc_r], fill=AMBER)
    hi_r = disc_r * 0.62
    d.ellipse([cx - hi_r, cy - hi_r, cx + hi_r, cy + hi_r], fill=AMBER_HI)

    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    _draw(192).save(os.path.join(OUT, "icon-192.png"))
    _draw(512).save(os.path.join(OUT, "icon-512.png"))
    _draw(512, safe=0.80).save(os.path.join(OUT, "icon-maskable-512.png"))
    print("OK: wrote icon-192.png, icon-512.png, icon-maskable-512.png to static/icons/")


if __name__ == "__main__":
    main()
