"""
Phase B1-safe: refactor get_db() to dispatch on DATABASE_URL.

WHEN DATABASE_URL IS UNSET: behavior is byte-identical to today (SQLite path).
WHEN DATABASE_URL starts with postgres:// or postgresql://: returns a
   _PgConnAdapter (defined in db_adapter.py) wrapping a psycopg2 connection.

This is intentionally a *scaffolding* change. The Postgres path can't be
exercised by the existing tests (no DATABASE_URL fixture) and is gated so
production keeps working until tomorrow's cutover wires DATABASE_URL.

Why a binary patch: web_app.py is CRLF + Windows-1252 mojibake. Edit-tool
curly quotes corrupt the file. Idempotent.
"""
import sys
from pathlib import Path

WEB = Path(__file__).parent.parent / "web_app.py"
data = WEB.read_bytes()
orig_size = len(data)

P1_OLD = (
    b'def get_db():\r\n'
    b'    conn = sqlite3.connect(DB_PATH)\r\n'
    b'    conn.row_factory = sqlite3.Row\r\n'
    b'    return conn\r\n'
)
P1_NEW = (
    b'def get_db():\r\n'
    b'    # Phase B1: dual-backend dispatch on DATABASE_URL. When unset (today),\r\n'
    b'    # behavior is byte-identical to the original SQLite path.\r\n'
    b'    _db_url = os.environ.get("DATABASE_URL", "")\r\n'
    b'    if _db_url.startswith(("postgres://", "postgresql://")):\r\n'
    b'        import db_adapter\r\n'
    b'        return db_adapter.open_postgres(_db_url)\r\n'
    b'    conn = sqlite3.connect(DB_PATH)\r\n'
    b'    conn.row_factory = sqlite3.Row\r\n'
    b'    return conn\r\n'
)

if P1_OLD in data:
    data = data.replace(P1_OLD, P1_NEW, 1)
    print("[patch] get_db dispatch added")
elif P1_NEW in data:
    print("[skip] already applied")
    sys.exit(0)
else:
    print("[abort] anchor not found — get_db() may have been refactored already")
    sys.exit(2)

# Sanity: still CRLF
crlf = data.count(b'\r\n')
lf   = data.count(b'\n') - crlf
if lf != 0:
    print(f"[abort] bare LFs present after patch: {lf}")
    sys.exit(3)

bak = WEB.with_suffix(WEB.suffix + ".bak_get_db_dual")
if not bak.exists():
    bak.write_bytes(WEB.read_bytes())
    print(f"[backup] {bak.name} written")
WEB.write_bytes(data)
print(f"[write]  web_app.py: {orig_size} -> {len(data)} bytes (CRLF preserved)")
