# patch_attach_boq_hierarchy.py
# Phase 3: splice the BOQ hierarchy routes from new_boq_hierarchy_routes.py
# into web_app.py (before `if __name__ == "__main__":`).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_hierarchy_routes.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

if b"def boq_projects_list" in data:
    print("Already spliced. No changes written.")
    raise SystemExit(0)

new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")

TARGET_ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(TARGET_ANCHOR)
assert pos > 0, "anchor not found"

data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced {NEW_FILE.name} (+{len(new_code_crlf)} bytes)")
