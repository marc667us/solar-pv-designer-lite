# patch_attach_section_meta.py
# Splice the per-section heading + instructions route into web_app.py.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_section_meta_route.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

if b"def boq_section_meta_save" in data:
    print("Section meta route already spliced.")
    raise SystemExit(0)

new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0, "anchor not found"
data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced section meta route (+{len(new_code_crlf)} bytes).")
