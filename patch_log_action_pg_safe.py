#!/usr/bin/env python3
"""patch_log_action_pg_safe.py -- 2026-06-22.

_log_marketplace_action() does CREATE TABLE with SQLite-only syntax
(INTEGER PRIMARY KEY AUTOINCREMENT). On Postgres the CREATE errors,
rolls back the transaction, and the subsequent INSERT silently fails.
Result: live actions never land in marketplace_audit_log on Postgres.

Fix: wrap the CREATE in try/except so the INSERT still runs whether the
table existed or not (the schema bootstrap creates it with SERIAL on PG).
"""
from __future__ import annotations
import sys

PATH = "web_app.py"


def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    needle = (
        b"def _log_marketplace_action(action: str, target_kind: str, target_id: int, notes: str = \"\"):\r\n"
        b"    \"\"\"Lightweight audit logger \xe2\x80\x94 writes one row to marketplace_audit_log.\r\n"
        b"\r\n"
        b"    Idempotent table creation so this works even on the very first action.\"\"\"\r\n"
        b"    with get_db() as c:\r\n"
        b"        c.execute(\r\n"
        b"            \"\"\"\r\n"
        b"            CREATE TABLE IF NOT EXISTS marketplace_audit_log (\r\n"
        b"                id INTEGER PRIMARY KEY AUTOINCREMENT,\r\n"
        b"                user_id INTEGER NOT NULL,\r\n"
        b"                action TEXT NOT NULL,\r\n"
        b"                target_kind TEXT NOT NULL,\r\n"
        b"                target_id INTEGER NOT NULL,\r\n"
        b"                notes TEXT DEFAULT '',\r\n"
        b"                created_at TEXT DEFAULT CURRENT_TIMESTAMP\r\n"
        b"            )\r\n"
        b"            \"\"\"\r\n"
        b"        )\r\n"
        b"        c.execute(\r\n"
        b"            \"INSERT INTO marketplace_audit_log \"\r\n"
        b"            \"(user_id, action, target_kind, target_id, notes) \"\r\n"
        b"            \"VALUES (?, ?, ?, ?, ?)\",\r\n"
        b"            (session.get(\"user_id\", 0), action, target_kind, target_id, notes),\r\n"
        b"        )\r\n"
    )
    repl = (
        b"def _log_marketplace_action(action: str, target_kind: str, target_id: int, notes: str = \"\"):\r\n"
        b"    \"\"\"Lightweight audit logger \xe2\x80\x94 writes one row to marketplace_audit_log.\r\n"
        b"\r\n"
        b"    2026-06-22 (session C): CREATE wrapped in try/except so an engine\r\n"
        b"    that rejects the SQLite-flavoured DDL (Postgres complains about\r\n"
        b"    'INTEGER PRIMARY KEY AUTOINCREMENT') doesn't roll back the INSERT.\r\n"
        b"    The Postgres bootstrap creates the table with SERIAL separately.\"\"\"\r\n"
        b"    try:\r\n"
        b"        with get_db() as c:\r\n"
        b"            try:\r\n"
        b"                c.execute(\r\n"
        b"                    \"CREATE TABLE IF NOT EXISTS marketplace_audit_log (\"\r\n"
        b"                    \" id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,\"\r\n"
        b"                    \" action TEXT NOT NULL, target_kind TEXT NOT NULL,\"\r\n"
        b"                    \" target_id INTEGER NOT NULL, notes TEXT DEFAULT '',\"\r\n"
        b"                    \" created_at TEXT DEFAULT CURRENT_TIMESTAMP)\"\r\n"
        b"                )\r\n"
        b"            except Exception:\r\n"
        b"                pass  # table already exists or DDL flavour mismatch (Postgres uses SERIAL via the bootstrap)\r\n"
        b"        with get_db() as c:\r\n"
        b"            c.execute(\r\n"
        b"                \"INSERT INTO marketplace_audit_log \"\r\n"
        b"                \"(user_id, action, target_kind, target_id, notes) \"\r\n"
        b"                \"VALUES (?, ?, ?, ?, ?)\",\r\n"
        b"                (session.get(\"user_id\", 0), action, target_kind, target_id, notes),\r\n"
        b"            )\r\n"
        b"    except Exception as _e:\r\n"
        b"        try: app.logger.warning(\"_log_marketplace_action failed: %s\", _e)\r\n"
        b"        except Exception: pass\r\n"
    )
    if needle in data:
        data = data.replace(needle, repl, 1)
        print("(patch) _log_marketplace_action now Postgres-safe.")
    elif b"2026-06-22 (session C): CREATE wrapped in try/except" in data:
        print("(patch) already applied.")
        return
    else:
        print("(patch) needle NOT FOUND."); sys.exit(2)
    with open(PATH, "wb") as fh:
        fh.write(data)
    print(f"wrote {PATH}")


if __name__ == "__main__":
    main()
