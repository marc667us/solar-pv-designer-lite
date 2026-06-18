"""Hotfix the live deploy — make all `_ensure_*` marketplace helpers safe on
Postgres by routing them through `_ensure_marketplace_schema_postgres()`
when DATABASE_URL is set, and otherwise running the existing SQLite-only
DDL bodies.

Without this patch, the live /marketplace and /supplier/register endpoints
500 because:
  - `c.executescript(...)` doesn't exist on the psycopg2-wrapped connection.
  - `INTEGER PRIMARY KEY AUTOINCREMENT` is invalid Postgres syntax.

Idempotent: re-running is safe — checks for the postgres-init function's
presence before re-injecting.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
NEW_INIT = "new_marketplace_postgres_init.py"


def patch() -> int:
    src = open(TARGET, "rb").read()
    if b"def _ensure_marketplace_schema_postgres" in src:
        print("[skip] postgres-init already present")
        return 0

    new_code = open(NEW_INIT, "rb").read()
    new_code_crlf = new_code.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    ANCHOR = b'if __name__ == "__main__":'
    pos = src.rfind(ANCHOR)
    if pos < 0:
        print("[fail] could not find __main__ anchor")
        return 3
    src = src[:pos] + new_code_crlf + b"\r\n\r\n" + src[pos:]

    # Now wrap each `_ensure_*` helper body so it short-circuits to the
    # postgres bootstrap when DATABASE_URL is set. We do this by inserting
    # one short-circuit line right after each `def _ensure_*():` line.
    helpers = [
        b"def _ensure_marketplace_tables():\r\n",
        b"def _ensure_supplier_schema():\r\n",
        b"def _ensure_rfq_tables():\r\n",
        b"def _ensure_bom_tables():\r\n",
    ]
    short_circuit = (
        b"    if bool(os.environ.get(\"DATABASE_URL\")):\r\n"
        b"        _ensure_marketplace_schema_postgres()\r\n"
        b"        return\r\n"
    )
    inserted = 0
    for h in helpers:
        idx = src.find(h)
        if idx < 0:
            print(f"[warn] helper not found: {h.decode()!r}")
            continue
        # Insert the short-circuit AFTER the def line. Some helpers start
        # with a docstring or comment; we insert immediately, so the
        # docstring becomes unreachable as an expression but still parses.
        # Simpler: insert right after the def line, before the body.
        end_of_def = idx + len(h)
        src = src[:end_of_def] + short_circuit + src[end_of_def:]
        inserted += 1

    open(TARGET, "wb").write(src)
    print(f"[ok] injected postgres-init; short-circuited {inserted}/4 helpers")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
