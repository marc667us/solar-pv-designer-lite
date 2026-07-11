"""Splice new_tutorial_admin.py into web_app.py before the __main__ tail.
Byte-level, CRLF-aware, idempotent (ADR-0001). Run: python patch_tutorial_admin.py
"""

SENTINEL = b"def _ensure_tutorial_schema"
TARGET = b'if __name__ == "__main__":'


def main():
    data = open("web_app.py", "rb").read()
    if SENTINEL in data:
        print("[skip] Tutorial admin slice already spliced into web_app.py")
        return
    new_code = open("new_tutorial_admin.py", "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    pos = data.rfind(TARGET)
    if pos == -1:
        raise SystemExit("[fail] could not find __main__ tail in web_app.py")
    patched = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    open("web_app.py", "wb").write(patched)
    print("[ok] spliced new_tutorial_admin.py (%d bytes)" % len(new_code_crlf))


if __name__ == "__main__":
    main()
