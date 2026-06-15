"""Inject the Site Inspection Form routes into web_app.py.

Project rule: NEVER use Edit on web_app.py because of CRLF + mojibake;
use byte-patching via separate routes file. Mirrors the pattern in
patch_shading_report_routes.py.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_inspection_form_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if not src:
        print("[fail] empty target")
        return 2

    if b"def inspection_form" in src and b"def inspection_upload_serve" in src:
        print("[skip] inspection-form routes already present")
        return 0

    new_code = open(NEW_ROUTES, "rb").read()
    # Normalise to CRLF to match web_app.py line endings.
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    ANCHOR = b'if __name__ == "__main__":'
    pos = src.rfind(ANCHOR)
    if pos < 0:
        print("[fail] could not find __main__ block to inject before")
        return 3
    src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]
    open(TARGET, "wb").write(src)
    print("[ok] injected inspection_form + inspection_upload_serve "
          "+ inspection_upload_delete routes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
