"""Inject the marketplace RFQ workflow routes into web_app.py."""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_ROUTES = "new_marketplace_rfq_routes.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if (b"def rfqs_list" in src and b"def rfqs_view" in src
            and b"def supplier_rfqs_respond" in src):
        print("[skip] RFQ routes already present")
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
    print("[ok] injected rfqs_list + rfqs_new + rfqs_view + rfqs_add_item + "
          "rfqs_delete_item + rfqs_send + rfqs_award + rfqs_cancel + "
          "supplier_rfqs_inbox + supplier_rfqs_respond")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
