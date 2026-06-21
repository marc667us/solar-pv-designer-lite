# patch_attach_data_v4.py
# Splice new_boq_data_v4.py after v3.
# Adds EARTHING AND EARTH LEADS section to every Bill 2 + tweaks
# WIRING OF POINTS subheading.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b'"EARTHING AND EARTH LEADS"' in data and b"_EARTHING_SUBHEADING" in data:
    print("v4 already spliced.")
    raise SystemExit(0)

src = Path(__file__).with_name("new_boq_data_v4.py").read_text(encoding="utf-8")
crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0
data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced v4 (+{len(crlf)} bytes)")
