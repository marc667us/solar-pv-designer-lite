"""Wire the platform-wide Share modal into base.html (navbar button +
modal include) AND landing.html (hero CTA button). All injections are
byte-level, sentinel-guarded, and idempotent.
"""
from __future__ import annotations
from pathlib import Path
import sys

ROOT    = Path(__file__).parent
BASE    = ROOT / "templates" / "base.html"
LANDING = ROOT / "templates" / "landing.html"

SENTINEL = b'data-platform-share="1"'

# ─── 1) base.html — include the modal partial right before </body> ─────────
# Find the closing </body> tag and insert the include + a small JS hook above it.
BASE_BODY_NEEDLE = b"</body>"
BASE_MODAL_INCLUDE = (
    b'\r\n<!-- Growth Layer: site-wide Share-SolarPro modal -->\r\n'
    b'{% include "growth/_platform_share_modal.html" ignore missing %}\r\n'
)

# ─── 1b) base.html — navbar Share button (logged-in side) ──────────────────
# Place it right BEFORE the Dashboard link so it's the first item in the
# right-side cluster. The needle is the comment immediately above the
# Dashboard nav-item.
BASE_NAV_AUTH_NEEDLE = (
    b'{# Helper macro \xe2\x80\x94 marks nav-link active when on matching endpoint #}'
)
BASE_NAV_AUTH_INSERT = (
    b'<li class="nav-item">\r\n'
    b'          <a class="nav-link" href="#" data-bs-toggle="modal"\r\n'
    b'             data-bs-target="#platformShareModal" data-platform-share="1"\r\n'
    b'             title="Share SolarPro with a colleague">\r\n'
    b'            <i class="bi bi-megaphone-fill me-1 text-warning"></i>Share\r\n'
    b'          </a>\r\n'
    b'        </li>\r\n\r\n'
    b'        '
)

# ─── 1c) base.html — navbar Share button (anonymous side) ──────────────────
# The anon branch ends right before {% endif %}. Find the anon Marketplace
# link's closing </li> and insert a Share <li> AFTER it.
BASE_NAV_ANON_NEEDLE = b'<i class="bi bi-bag-check-fill me-1 text-warning"></i>Marketplace'
# We'll splice AFTER the closing </li> of that block. To be safe and not
# disturb structure, we add the Share item INSIDE the anon block by
# appending after the marketplace link's closing tag. Use a unique anchor:
BASE_NAV_ANON_ANCHOR = (
    b'<span class="badge ms-1" style="background:rgba(34,197,94,.18);'
    b'color:#22c55e;font-size:9px;font-weight:700">FREE</span>\r\n'
    b'          </a>\r\n'
    b'        </li>'
)
BASE_NAV_ANON_INSERT_AFTER = (
    b'<span class="badge ms-1" style="background:rgba(34,197,94,.18);'
    b'color:#22c55e;font-size:9px;font-weight:700">FREE</span>\r\n'
    b'          </a>\r\n'
    b'        </li>\r\n'
    b'        <li class="nav-item">\r\n'
    b'          <a class="nav-link" href="#" data-bs-toggle="modal"\r\n'
    b'             data-bs-target="#platformShareModal" data-platform-share="1"\r\n'
    b'             title="Share SolarPro">\r\n'
    b'            <i class="bi bi-megaphone-fill me-1 text-warning"></i>Share\r\n'
    b'          </a>\r\n'
    b'        </li>'
)

# ─── 2) landing.html — hero CTA Share button ───────────────────────────────
# Insert next to the existing "Free Site Assessment" button block (after its
# closing </a>) so users see three CTAs side-by-side in the hero.
LANDING_NEEDLE = (
    b'<i class="bi bi-clipboard2-check-fill me-2"></i>Free Site Assessment\r\n'
    b'    </a>'
)
LANDING_INSERT_AFTER = (
    b'<i class="bi bi-clipboard2-check-fill me-2"></i>Free Site Assessment\r\n'
    b'    </a>\r\n'
    b'    <button type="button" class="btn btn-lg px-4 fw-bold pulse-cta"\r\n'
    b'            data-bs-toggle="modal" data-bs-target="#platformShareModal"\r\n'
    b'            data-platform-share="1"\r\n'
    b'            style="background:linear-gradient(135deg,#1877F2,#0a66c2);border:none;color:#fff">\r\n'
    b'      <i class="bi bi-megaphone-fill me-2"></i>Share Platform\r\n'
    b'    </button>'
)
# Also try the LF variant in case landing.html has LF newlines from a prior edit
LANDING_NEEDLE_LF = LANDING_NEEDLE.replace(b"\r\n", b"\n")
LANDING_INSERT_AFTER_LF = LANDING_INSERT_AFTER.replace(b"\r\n", b"\n")


def patch_base() -> int:
    if not BASE.exists():
        print("[fail] base.html not found"); return 1
    src = BASE.read_bytes()
    n = 0
    # (a) modal include
    if SENTINEL in src and b'platformShareModal' in src:
        print("[skip] base.html already wired")
    else:
        if BASE_BODY_NEEDLE not in src:
            print("[warn] base.html </body> not found — modal include skipped")
        else:
            src = src.replace(BASE_BODY_NEEDLE,
                              BASE_MODAL_INCLUDE + BASE_BODY_NEEDLE, 1)
            n += 1
            print("[ok]   base.html modal include inserted")
        # (b) navbar Share — logged-in
        if BASE_NAV_AUTH_NEEDLE in src:
            src = src.replace(BASE_NAV_AUTH_NEEDLE,
                              BASE_NAV_AUTH_INSERT + BASE_NAV_AUTH_NEEDLE, 1)
            n += 1
            print("[ok]   base.html nav Share button (logged-in) inserted")
        else:
            print("[warn] base.html logged-in nav anchor not found")
        # (c) navbar Share — anonymous
        if BASE_NAV_ANON_ANCHOR in src and src.count(BASE_NAV_ANON_INSERT_AFTER) == 0:
            src = src.replace(BASE_NAV_ANON_ANCHOR,
                              BASE_NAV_ANON_INSERT_AFTER, 1)
            n += 1
            print("[ok]   base.html nav Share button (anonymous) inserted")
        else:
            print("[warn] base.html anonymous nav anchor not found (or already done)")
    BASE.write_bytes(src)
    return 0


def patch_landing() -> int:
    if not LANDING.exists():
        print("[skip] landing.html not found"); return 0
    src = LANDING.read_bytes()
    if b'data-platform-share="1"' in src:
        print("[skip] landing.html already has Share Platform CTA"); return 0
    if LANDING_NEEDLE in src:
        src = src.replace(LANDING_NEEDLE, LANDING_INSERT_AFTER, 1)
        LANDING.write_bytes(src)
        print("[ok]   landing.html hero CTA inserted (CRLF)")
        return 0
    if LANDING_NEEDLE_LF in src:
        src = src.replace(LANDING_NEEDLE_LF, LANDING_INSERT_AFTER_LF, 1)
        LANDING.write_bytes(src)
        print("[ok]   landing.html hero CTA inserted (LF)")
        return 0
    print("[warn] landing.html hero anchor not found")
    return 0


if __name__ == "__main__":
    rc = patch_base() or patch_landing()
    sys.exit(rc)
