"""Apply Codex Slice 5 high-severity fix to the already-injected web_app.py.

Codex Slice 5 finding: /boms/add-product/<int:pid> was a state-mutating GET
with no CSRF protection. A third-party page could trigger insertion via
<img src="...">, silently adding products to a logged-in user's BOM.

Fix: convert to POST-only + call csrf_protect() at the top of the handler.
The marketplace template now renders a tiny <form method="POST"> per card.

Idempotent — skips if already applied.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = (
    b'@app.route("/boms/add-product/<int:pid>")\r\n'
    b'@login_required\r\n'
    b'def boms_add_from_marketplace(pid):\r\n'
    b'    """One-click "Add to BOM" from a marketplace product card.\r\n'
    b'\r\n'
    b'    Picks the user\'s most-recently-updated draft BOM and appends the product;\r\n'
    b'    if no draft exists, creates a fresh BOM titled with today\'s date. Then\r\n'
    b'    redirects to /boms/<id>."""\r\n'
    b'    _ensure_bom_tables()\r\n'
)

NEW = (
    b'@app.route("/boms/add-product/<int:pid>", methods=["POST"])\r\n'
    b'@login_required\r\n'
    b'def boms_add_from_marketplace(pid):\r\n'
    b'    """One-click "Add to BOM" from a marketplace product card.\r\n'
    b'\r\n'
    b'    POST-only with CSRF protection \xe2\x80\x94 a state-mutating endpoint must not be\r\n'
    b'    a GET (Codex finding: a third-party page could trigger insertion via\r\n'
    b'    <img src=...> on a logged-in user). The marketplace template renders\r\n'
    b'    this as a tiny <form method="POST"> per card.\r\n'
    b'\r\n'
    b'    Picks the user\'s most-recently-updated draft BOM and appends the product;\r\n'
    b'    if no draft exists, creates a fresh BOM titled with today\'s date. Then\r\n'
    b'    redirects to /boms/<id>."""\r\n'
    b'    csrf_protect()\r\n'
    b'    _ensure_bom_tables()\r\n'
)


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b'methods=["POST"])\r\n@login_required\r\ndef boms_add_from_marketplace' in src:
        print("[skip] POST + csrf_protect already present")
        return 0
    if OLD not in src:
        print("[fail] pre-fix block not found — line endings may have drifted")
        return 4
    src = src.replace(OLD, NEW)
    open(TARGET, "wb").write(src)
    print("[ok] /boms/add-product/<pid> converted to POST + csrf_protect()")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
