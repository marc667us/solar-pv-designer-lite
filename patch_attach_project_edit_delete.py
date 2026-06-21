# patch_attach_project_edit_delete.py
# Splice Edit / Delete / Start-all-over routes for BOQ projects.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b"def boq_project_edit" in data and b"def boq_project_reset" in data:
    print("Already spliced.")
    raise SystemExit(0)

src = Path(__file__).with_name("new_boq_project_edit_delete_routes.py").read_text(encoding="utf-8")
crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0
data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced project edit/delete/reset (+{len(crlf)} bytes)")
