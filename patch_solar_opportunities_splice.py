# patch_solar_opportunities_splice.py
from pathlib import Path

ROOT = Path(__file__).parent
TARGET = ROOT / "web_app.py"
NEW = ROOT / "new_solar_opportunities.py"

data = TARGET.read_bytes()
new_code = NEW.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

MARKER = b"# === BEGIN: solar_opportunities splice ==="
END = b"# === END: solar_opportunities splice ==="

if MARKER in data:
    pre = data.split(MARKER, 1)[0]
    post = data.split(END, 1)[1]
    block = MARKER + b"\r\n" + new_code + b"\r\n" + END + b"\r\n"
    data = pre + block + post
    print("Replaced existing block")
else:
    GUARD = b'if __name__ == "__main__":'
    pos = data.rfind(GUARD)
    block = MARKER + b"\r\n" + new_code + b"\r\n" + END + b"\r\n\r\n"
    data = data[:pos] + block + data[pos:]
    print("Inserted")

TARGET.write_bytes(data)
print("OK")
