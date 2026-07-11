"""Splice new_soc_slice0.py into web_app.py just before the
`if __name__ == "__main__":` tail.

web_app.py is CRLF + mojibake and must never be Edit-ed directly (ADR-0001),
so this reads both files as bytes, normalises the new block to CRLF, and inserts
it. Idempotent: a sentinel marker prevents a second insertion.

Run:  python patch_soc_slice0.py
"""

SENTINEL = b"AI-SOC \xe2\x80\x94 Slice 0"  # em-dash in the module banner (utf-8)
SENTINEL_ASCII = b"def admin_soc_kill_switch"  # backstop marker, encoding-proof

TARGET = b'if __name__ == "__main__":'


def main():
    data = open("web_app.py", "rb").read()

    if SENTINEL in data or SENTINEL_ASCII in data:
        print("[skip] SOC Slice 0 already spliced into web_app.py")
        return

    new_code = open("new_soc_slice0.py", "rb").read()
    # Normalise to LF then to CRLF so the inserted block matches web_app.py.
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

    pos = data.rfind(TARGET)
    if pos == -1:
        raise SystemExit("[fail] could not find `if __name__ == \"__main__\":` in web_app.py")

    patched = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
    open("web_app.py", "wb").write(patched)
    print("[ok] spliced new_soc_slice0.py (%d bytes) before __main__ tail" % len(new_code_crlf))


if __name__ == "__main__":
    main()
