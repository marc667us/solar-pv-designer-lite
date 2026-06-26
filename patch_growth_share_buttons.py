"""Add a 'Share' button to the Results page export bar AND to each
report_*.html action bar. All edits are byte-level, sentinel-guarded, and
idempotent. Use ONLY this script — do NOT hand-edit results.html or the
report templates."""
from __future__ import annotations
import os, sys
from pathlib import Path

ROOT = Path(__file__).parent

SHARE_SENTINEL = b'data-growth-share="1"'   # appears in every injection

# ─── 1) Results page (main hub) ────────────────────────────────────────────
RESULTS = ROOT / "templates" / "results.html"
RESULTS_ANCHOR = b'<!-- \xe2\x94\x80\xe2\x94\x80 Reports \xe2\x94\x80\xe2\x94\x80'  # "── Reports ──"
RESULTS_INSERT = (
    b'<!-- Growth Layer: Share -->\r\n'
    b'<div class="d-flex align-items-center gap-2 p-3 rounded mb-3 no-print"\r\n'
    b'     style="background:#f59e0b08;border:1px solid #f59e0b44" data-growth-share="1">\r\n'
    b'  <i class="bi bi-share-fill" style="color:#f59e0b;font-size:18px;flex-shrink:0"></i>\r\n'
    b'  <div class="small flex-grow-1" style="color:#f0d28a">\r\n'
    b'    <strong style="color:#f59e0b">Share this design</strong>\r\n'
    b'    \xe2\x80\x94 generate a beautiful card with savings, payback, and a QR-coded share link.\r\n'
    b'  </div>\r\n'
    b'  <a href="{{ url_for(\'growth_share_composer\', pid=project.id) }}"\r\n'
    b'     class="btn btn-sm fw-bold"\r\n'
    b'     style="background:#f59e0b;color:#0f0f22;border:0">\r\n'
    b'    <i class="bi bi-share-fill me-1"></i>Share\r\n'
    b'  </a>\r\n'
    b'</div>\r\n\r\n'
)


def patch_results() -> bool:
    if not RESULTS.exists():
        print(f"[skip] {RESULTS} not found")
        return False
    src = RESULTS.read_bytes()
    if SHARE_SENTINEL in src:
        print(f"[skip] {RESULTS.name} already has Share strip")
        return False
    if RESULTS_ANCHOR not in src:
        print(f"[warn] {RESULTS.name} anchor (Reports section header) missing — leaving untouched")
        return False
    new = src.replace(RESULTS_ANCHOR, RESULTS_INSERT + RESULTS_ANCHOR, 1)
    RESULTS.write_bytes(new)
    print(f"[ok]   {RESULTS.name} Share strip inserted")
    return True


# ─── 2) report_*.html action bars ──────────────────────────────────────────
# Each report template has a Print button as the last item in its action bar.
# We splice a Share button RIGHT BEFORE the Print button.
PRINT_NEEDLES = [
    # Most common shape: btn-outline-secondary class first
    b'<button onclick="window.print()" class="btn btn-outline-secondary btn-sm">',
    # A few variants
    b'<button onclick="window.print()" class="btn btn-sm btn-outline-secondary">',
    # report_proposal.html uses .btn-solar
    b'<button onclick="window.print()" class="btn btn-solar btn-sm">',
    # report_shading.html uses type="button" prefix + btn-outline-info
    b'<button type="button" onclick="window.print()" class="btn btn-sm btn-outline-info">',
]

REPORT_SHARE_BUTTON = (
    b'<a href="{{ url_for(\'growth_share_composer\', pid=project.id) }}" '
    b'class="btn btn-sm" data-growth-share="1" '
    b'style="background:#f59e0b;color:#0f0f22;border:0;font-weight:700" '
    b'title="Share this report as a card">'
    b'<i class="bi bi-share-fill me-1"></i>Share</a>\r\n    '
)


def patch_report(path: Path) -> bool:
    src = path.read_bytes()
    if SHARE_SENTINEL in src:
        return False  # already done
    for needle in PRINT_NEEDLES:
        if needle in src:
            new = src.replace(needle, REPORT_SHARE_BUTTON + needle, 1)
            path.write_bytes(new)
            return True
    return False


def patch_reports() -> int:
    n_ok = 0; n_skip = 0
    for p in sorted((ROOT / "templates").glob("report_*.html")):
        # Skip the drawings template — it's a sub-template that doesn't carry
        # an action bar of its own.
        if p.name.endswith("_drawings.html"):
            continue
        if patch_report(p):
            print(f"[ok]   {p.name} Share button inserted")
            n_ok += 1
        else:
            print(f"[skip] {p.name} (already has Share button OR Print needle missing)")
            n_skip += 1
    return 0


if __name__ == "__main__":
    patch_results()
    patch_reports()
    sys.exit(0)
