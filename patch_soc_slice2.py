"""Splice new_soc_slice2.py into web_app.py before the __main__ tail.
Byte-level, CRLF-aware, idempotent (ADR-0001). Run: python patch_soc_slice2.py
"""

SENTINEL = b"def soc_orchestrate"
TARGET = b'if __name__ == "__main__":'


def main():
    data = open("web_app.py", "rb").read()
    if SENTINEL in data:
        print("[skip] SOC Slice 2 already spliced into web_app.py")
        return
    new_code = open("new_soc_slice2.py", "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    pos = data.rfind(TARGET)
    if pos == -1:
        raise SystemExit("[fail] could not find __main__ tail in web_app.py")
    patched = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    open("web_app.py", "wb").write(patched)
    print("[ok] spliced new_soc_slice2.py (%d bytes)" % len(new_code_crlf))


if __name__ == "__main__":
    main()
