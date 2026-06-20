# patch_attach_add_library_item.py
# Phase 2: splice the +Add Library Item route + admin approval routes
# from new_boq_add_library_item_route.py into web_app.py.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
NEW_FILE = Path(__file__).with_name("new_boq_add_library_item_route.py")

data = TARGET.read_bytes()
new_code = NEW_FILE.read_text(encoding="utf-8")

if b"def boms_add_library_item" in data:
    print("Already spliced. No changes written.")
    raise SystemExit(0)

# Normalise to CRLF (file is CRLF-encoded).
new_code_crlf = new_code.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")

TARGET_ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(TARGET_ANCHOR)
assert pos > 0, "anchor not found"

data = data[:pos] + new_code_crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced {NEW_FILE.name} into web_app.py (+{len(new_code_crlf)} bytes)")
