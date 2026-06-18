"""Splice new_marketplace_supplier_edit_routes.py into web_app.py just before
the final `if __name__ == "__main__":` block. Idempotent — skips when the
sentinel marker is already present in the target."""
from __future__ import annotations
import sys

TARGET = "web_app.py"
SOURCE = "new_marketplace_supplier_edit_routes.py"
SENTINEL = b"def supplier_product_edit(pid):"


def patch() -> int:
    data = open(TARGET, "rb").read()
    if SENTINEL in data:
        print("[skip] already patched")
        return 0
    new_code = open(SOURCE, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    anchor = b'if __name__ == "__main__":'
    pos = data.rfind(anchor)
    if pos == -1:
        print("[fail] anchor not found in web_app.py")
        return 4
    data = data[:pos] + new_code_crlf + b"\r\n" + data[pos:]
    open(TARGET, "wb").write(data)
    print("[ok] spliced supplier edit/delete routes")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
