# patch_solarpro_report_header_splice.py
# Splice new_solarpro_report_header.py into web_app.py BEFORE the `if __name__`
# guard, so the four helpers are module-level globals available to the
# PDF / XLSX export routes.
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "web_app.py"
NEW = ROOT / "new_solarpro_report_header.py"

data = TARGET.read_bytes()
new_code = NEW.read_bytes()
# Normalise to CRLF for web_app.py
new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

MARKER = b"# === BEGIN: solarpro_report_header splice ==="
END_MARKER = b"# === END: solarpro_report_header splice ==="

if MARKER in data:
    print("Already spliced — replacing existing block")
    pre = data.split(MARKER, 1)[0]
    post = data.split(END_MARKER, 1)[1]
    block = MARKER + b"\r\n" + new_code_crlf + b"\r\n" + END_MARKER + b"\r\n"
    data = pre + block + post
else:
    GUARD = b'if __name__ == "__main__":'
    pos = data.rfind(GUARD)
    if pos < 0:
        raise SystemExit("Cannot find main guard in web_app.py")
    block = (
        MARKER + b"\r\n"
        + new_code_crlf + b"\r\n"
        + END_MARKER + b"\r\n\r\n"
    )
    data = data[:pos] + block + data[pos:]
    print("Inserted before main guard")

TARGET.write_bytes(data)
print("OK")
