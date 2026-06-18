"""Inject /procurement-center + Basic Price Sheet routes into web_app.py."""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_marketplace_procurement_center_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if (b"def procurement_center" in src and b"def price_sheet_view" in src
            and b"def procurement_center_add" in src):
        print("[skip] procurement center routes already present")
        return 0
    new_code = open(NEW_ROUTES, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    ANCHOR = b'if __name__ == "__main__":'
    pos = src.rfind(ANCHOR)
    if pos < 0:
        print("[fail] anchor missing")
        return 3
    src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]
    open(TARGET, "wb").write(src)
    print("[ok] injected procurement_center + add + price sheet routes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
