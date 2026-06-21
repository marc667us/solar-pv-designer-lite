# patch_attach_price_sheet_exports.py
from pathlib import Path
TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()
if b"def price_sheet_xlsx" in data:
    print("Already spliced.")
    raise SystemExit(0)
src = Path(__file__).with_name("new_price_sheet_export_routes.py").read_text(encoding="utf-8")
crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
pos = data.rfind(b'if __name__ == "__main__":')
assert pos > 0
data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced price sheet exports (+{len(crlf)} bytes)")
