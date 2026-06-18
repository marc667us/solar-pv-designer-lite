"""Inject the marketplace BOM/BOQ routes into web_app.py."""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_marketplace_bom_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if (b"def boms_list" in src and b"def boms_view" in src
            and b"def boms_clone_to_rfq" in src):
        print("[skip] BOM routes already present")
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
    print("[ok] injected boms_list + boms_new + boms_view + boms_add_item + "
          "boms_delete_item + boms_add_from_marketplace + boms_clone_to_rfq + "
          "boms_boq")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
