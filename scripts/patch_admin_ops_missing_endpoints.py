"""
Add the 7 admin-ops endpoints that the Ops Center JS calls but that
don't yet exist on the backend (all returned 404):

  GET  /admin/ops/ping/queue       — queue subsystem status
  GET  /admin/ops/ping/ai          — AI providers status
  GET  /admin/ops/ping/storage     — disk space status
  GET  /admin/ops/security/report  — downloadable security report (JSON)
  GET  /admin/ops/db/report        — downloadable DB health report (JSON)
  GET  /admin/ops/health/report    — downloadable full health report (JSON)
  POST /admin/ops/logs/archive     — archive old logs and return summary

Pattern mirrors existing admin_ops_ping_database / admin_ops_logs_view
handlers. All require @admin_required (login + admin gate).

Why a binary patch: web_app.py is CRLF + Windows-1252 mojibake. Edit
introduces curly quotes. We append the new routes BEFORE the
`if __name__ == "__main__":` block at end-of-file (CLAUDE.md Pattern B).
"""
from pathlib import Path
import sys

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

# Read the new routes from a sibling file to avoid b'''...''' triple-quote pitfalls.
SRC = Path(__file__).parent.parent / "new_admin_ops_routes.py"
new_code = SRC.read_bytes()
# Normalize to CRLF to match web_app.py
new_code = new_code.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')

# Idempotency check: if any of the new endpoint paths are already in web_app.py
# we treat as already applied.
SENTINEL = b'def admin_ops_ping_queue('
if SENTINEL in data:
    print("[skip] new routes already present in web_app.py")
    sys.exit(0)

# Anchor: insert right before the `if __name__ == "__main__":` block.
TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
if pos == -1:
    print("[abort] could not find `if __name__ == \"__main__\":` anchor")
    sys.exit(2)

data = data[:pos] + new_code + b'\r\n\r\n' + data[pos:]

# Sanity: still CRLF only
crlf = data.count(b'\r\n')
lf   = data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}")
    sys.exit(3)

bak = WEB.with_suffix(WEB.suffix + ".bak_admin_ops_endpoints")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written")

WEB.write_bytes(data)
print(f"[write]  web_app.py: {orig_size} -> {len(data)} bytes (CRLF preserved)")
print(f"[ok]     7 new admin-ops endpoints inserted")
