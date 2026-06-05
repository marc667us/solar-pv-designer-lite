"""
Binary patch — register the campaign portal blueprint inside web_app.py.

Why a patch script?
-------------------
CLAUDE.md warns that web_app.py has CRLF + mojibake; the Edit tool can introduce
Unicode curly quotes. Binary I/O preserves the file exactly.

What it does
------------
1. Reads web_app.py (CRLF preserved).
2. Skips if the registration is already there (idempotent).
3. Finds the FIRST `@app.route(` decorator and inserts BEFORE it:
     from campaign_blueprint import register_campaign
     register_campaign(app)
4. Writes the file back.

Inputs:   web_app.py (in cwd)
Outputs:  web_app.py (patched in place); prints OK/SKIP.
"""
from pathlib import Path

src = Path("web_app.py")
data = src.read_bytes()

MARKER = b"register_campaign(app)"
if MARKER in data:
    print("SKIP: register_campaign(app) already in web_app.py")
    raise SystemExit(0)

INJECT = (
    b"\r\n"
    b"# === Campaign portal (intranet sales app) ===\r\n"
    b"from campaign_blueprint import register_campaign\r\n"
    b"register_campaign(app)\r\n"
    b"# === end campaign portal ===\r\n"
    b"\r\n"
)

# Insert just before the very first `@app.route(` decorator
TARGET = b"@app.route("
pos = data.find(TARGET)
if pos < 0:
    raise SystemExit("FAIL: could not find @app.route( in web_app.py")

# Back up to start of the line containing the decorator
line_start = data.rfind(b"\r\n", 0, pos)
if line_start < 0:
    line_start = data.rfind(b"\n", 0, pos)
insert_at = line_start + 2 if data[line_start:line_start+2] == b"\r\n" else line_start + 1

data = data[:insert_at] + INJECT + data[insert_at:]
src.write_bytes(data)
print(f"OK: registration injected at byte {insert_at}")
