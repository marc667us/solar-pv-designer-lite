# patch_attach_product_link_finder.py
# Splice the product link finder agent + routes.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b"def _find_links_for" in data:
    print("Already spliced.")
    raise SystemExit(0)

src = Path(__file__).with_name("new_product_link_finder.py").read_text(encoding="utf-8")
crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0
data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced product link finder (+{len(crlf)} bytes)")
