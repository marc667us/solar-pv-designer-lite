"""Binary patch — register campaign_api blueprint inside web_app.py.

Identical pattern to patch_campaign_registration.py, but for the *backend*
API blueprint (campaign_api.py) — distinct from the static-file portal that
we previously removed. This one stays.

Idempotent: skips if the registration line is already present.
"""
from pathlib import Path

src = Path("web_app.py")
data = src.read_bytes()

MARKER = b"register_campaign_api(app)"
if MARKER in data:
    print("SKIP: register_campaign_api already in web_app.py")
    raise SystemExit(0)

INJECT = (
    b"\r\n"
    b"# === Campaign portal REST API (backs the GitHub Pages portal) ===\r\n"
    b"from campaign_api import register_campaign_api\r\n"
    b"register_campaign_api(app)\r\n"
    b"# === end campaign portal REST API ===\r\n"
    b"\r\n"
)

TARGET = b"@app.route("
pos = data.find(TARGET)
if pos < 0:
    raise SystemExit("FAIL: could not find @app.route( in web_app.py")

line_start = data.rfind(b"\r\n", 0, pos)
if line_start < 0:
    line_start = data.rfind(b"\n", 0, pos)
insert_at = line_start + 2 if data[line_start:line_start+2] == b"\r\n" else line_start + 1

data = data[:insert_at] + INJECT + data[insert_at:]
src.write_bytes(data)
print(f"OK: registration injected at byte {insert_at}")
