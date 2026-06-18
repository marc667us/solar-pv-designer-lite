"""Inject the marketplace supplier self-service routes into web_app.py.

Project rule: NEVER use Edit on web_app.py because of CRLF + mojibake;
use byte-patching via a separate routes file.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_marketplace_supplier_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if not src:
        print("[fail] empty target")
        return 2

    if (b"def supplier_register" in src and b"def supplier_dashboard" in src
            and b"def supplier_product_add" in src):
        print("[skip] supplier self-service routes already present")
        return 0

    new_code = open(NEW_ROUTES, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    ANCHOR = b'if __name__ == "__main__":'
    pos = src.rfind(ANCHOR)
    if pos < 0:
        print("[fail] could not find __main__ block")
        return 3
    src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]
    open(TARGET, "wb").write(src)
    print("[ok] injected supplier_register + supplier_dashboard + "
          "supplier_products + supplier_product_add + helpers")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
