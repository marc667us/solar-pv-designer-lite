# patch_attach_data_v3.py
# Splice new_boq_data_v3.py after v2 (overrides Memshield -> Eaton in
# Section A, renames Section B -> FEEDERS AND SUBFEEDERS, attaches a
# section subheading on every section).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

if b"_BOQ_SECTION_SUBHEADINGS" in data:
    print("v3 already spliced.")
    raise SystemExit(0)

src = Path(__file__).with_name("new_boq_data_v3.py").read_text(encoding="utf-8")
crlf = src.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
ANCHOR = b'if __name__ == "__main__":'
pos = data.rfind(ANCHOR)
assert pos > 0
data = data[:pos] + crlf + b"\r\n\r\n" + data[pos:]
TARGET.write_bytes(data)
print(f"OK -- spliced v3 (+{len(crlf)} bytes)")
