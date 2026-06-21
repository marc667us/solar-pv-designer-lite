# patch_attach_template_picker.py
# Splice the template picker + checkbox + exports routes into web_app.py.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_template_picker_routes.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

if b"def boq_template_picker" in data:
    print("Template picker routes already spliced.")
    raise SystemExit(0)

new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0, "anchor not found"
data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced template picker (+{len(new_code_crlf)} bytes).")
