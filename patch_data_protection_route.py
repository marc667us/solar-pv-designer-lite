"""
Splice a /data-protection GET route into web_app.py right after the
existing /privacy route. Idempotent: re-running detects an existing
mount via the unique target marker string.

Pattern A byte-patch (per the project CLAUDE.md rule that forbids the
Edit tool on web_app.py; the file has CRLF + Windows-1252 mojibake the
Edit tool routinely corrupts).
"""
from pathlib import Path

WEB = Path('web_app.py')
data = WEB.read_bytes()

ANCHOR = (
    b'@app.route("/privacy")\r\n'
    b'def privacy():\r\n'
    b'    return render_template("privacy.html")\r\n'
)
MARKER = b'@app.route("/data-protection")'

if MARKER in data:
    print('already patched - /data-protection route already present')
    raise SystemExit(0)

if ANCHOR not in data:
    raise SystemExit(
        'anchor not found - /privacy route may have moved; '
        'open web_app.py around line 10347 and re-derive the anchor bytes'
    )

INSERT = (
    b'\r\n'
    b'@app.route("/data-protection")\r\n'
    b'def data_protection():\r\n'
    b'    return render_template("data_protection.html")\r\n'
)

# Insert AFTER the privacy route block (right before the next
# section comment so the new route lives in the same '-- Legal Pages --'
# cluster).
idx = data.index(ANCHOR) + len(ANCHOR)
new = data[:idx] + INSERT + data[idx:]
WEB.write_bytes(new)
print(f'patched: web_app.py grew by {len(new) - len(data)} bytes')
print(f'new file size: {len(new):,} bytes')
