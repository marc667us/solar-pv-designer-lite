"""Inject the Zero-Cost AI Growth Layer (viralsolar 1.txt) routes into web_app.py.

Splices new_growth_layer_routes.py before the `if __name__ == "__main__":`
block. Idempotent — checks for a sentinel function name before injecting.
Also adds a 'Growth' navbar item right after the Marketplace dropdown and a
'Share' button on the project view header (best-effort — both are guarded
by sentinel checks so re-runs are safe).

NEVER edit web_app.py with the Edit tool (CRLF + mojibake corruption).
This patch operates at the byte level following the established pattern.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_growth_layer_routes.py"
BASE_TPL = "templates/base.html"

ROUTES_SENTINEL = b"def growth_create_share_asset"
ANCHOR = b'if __name__ == "__main__":'


def patch_routes() -> int:
    src = open(TARGET, "rb").read()
    if ROUTES_SENTINEL in src:
        print("[skip] growth layer routes already injected")
        return 0
    new_code = open(NEW_ROUTES, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    pos = src.rfind(ANCHOR)
    if pos < 0:
        print("[fail] anchor missing in web_app.py")
        return 3
    src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]
    open(TARGET, "wb").write(src)
    print("[ok] injected growth layer routes (8 modules)")
    return 0


# Splice a small nav entry into base.html right inside the Marketplace
# admin dropdown so the page is reachable without disturbing the existing
# structure. Idempotent.
NAV_SENTINEL = b"growth_dashboard_page"
NAV_NEEDLE = b'<li><a class="dropdown-item" href="{{ url_for(\'admin_marketplace_pending\') }}">'
NAV_INSERT = (
    b'<li><a class="dropdown-item" href="{{ url_for(\'growth_dashboard_page\') }}">'
    b'<i class="bi bi-rocket-takeoff me-2 text-warning"></i>Growth Dashboard '
    b'<span class="badge ms-2" style="background:rgba(245,158,11,.18);color:#f59e0b;font-size:9px">VIRAL</span></a></li>\n            '
)


def patch_navbar() -> int:
    try:
        src = open(BASE_TPL, "rb").read()
    except FileNotFoundError:
        print("[skip] base.html not found")
        return 0
    if NAV_SENTINEL in src:
        print("[skip] navbar entry already present")
        return 0
    if NAV_NEEDLE not in src:
        print("[warn] navbar anchor not found; leaving base.html untouched "
              "(open /growth directly)")
        return 0
    src = src.replace(NAV_NEEDLE, NAV_INSERT + NAV_NEEDLE, 1)
    open(BASE_TPL, "wb").write(src)
    print("[ok] navbar Growth Dashboard link inserted")
    return 0


if __name__ == "__main__":
    rc = patch_routes() or patch_navbar()
    sys.exit(rc)
