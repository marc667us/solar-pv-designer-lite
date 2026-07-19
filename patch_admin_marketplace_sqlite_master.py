"""/admin/marketplace 500s on live: its table-EXISTS guard is itself SQLite-only.

EVIDENCE (live error_logs, read 2026-07-19):
    7 x /admin/marketplace [UndefinedTable] last seen 2026-07-18

This is the owner's "check market admin there is an issue there", and it is real:

    recent_actions = c.execute(
        "SELECT mal.* FROM marketplace_audit_log mal ...").fetchall() \\
        if c.execute("SELECT name FROM sqlite_master WHERE type='table' "
                     "AND name='marketplace_audit_log'").fetchone() else []

The code defends against a missing `marketplace_audit_log` by querying `sqlite_master` --
a SQLite system table that does not exist on Postgres. **The existence check is the thing that
raises.** Postgres answers UndefinedTable and the whole admin marketplace page 500s.

`db_adapter._translate_sqlite_to_postgres()` does NOT cover this: it rewrites datetime(),
strftime() and last_insert_rowid(), not `sqlite_master`. (Worth stating explicitly, because
earlier today I wrongly "fixed" a datetime() call the adapter already handled and had to
revert it. This one is genuinely unhandled -- verified against the adapter's actual rules.)

TWO CHANGES
-----------
1. `_table_exists()` becomes backend-aware. It previously ran the SQLite query inside a
   try/except and returned False on failure -- safe from crashing, but it means every feature
   guarded by it has been SILENTLY DISABLED on live rather than merely unavailable. Now it
   asks Postgres properly (to_regclass) so those features come back.

   It BRANCHES on the backend rather than trying SQLite-first-then-Postgres, because a failed
   statement poisons the surrounding Postgres transaction -- InFailedSqlTransaction appears in
   this very error log, so that is a demonstrated hazard here, not a theoretical one.

2. The inline raw query in `/admin/marketplace` is replaced by a call to that helper. Inlining
   a second copy of "does this table exist" is what allowed the two to diverge in the first
   place.

web_app.py is CRLF + mojibake, so this is a byte-level splice, never an Edit. Idempotent.
"""
SRC = "web_app.py"

# ── 1. make the surviving _table_exists backend-aware ────────────────────────────────────
OLD_HELPER = (
    b'def _table_exists(conn, table_name):\r\n'
    b'    """SQLite-specific helper: check if a table exists. Returns False on\r\n'
    b'    Postgres (where the caller should use information_schema). For the\r\n'
    b'    security report this is best-effort; missing audit_logs table just\r\n'
    b'    yields None for that field."""\r\n'
    b'    try:\r\n'
    b'        row = conn.execute(\r\n'
    b'            "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=?",\r\n'
    b'            (table_name,)\r\n'
    b'        ).fetchone()\r\n'
    b'        return row is not None\r\n'
    b'    except Exception:\r\n'
    b'        return False\r\n'
)

NEW_HELPER = (
    b'def _table_exists(conn, table_name):\r\n'
    b'    """Does `table_name` exist? Works on BOTH backends.\r\n'
    b'\r\n'
    b'    Input:  an open connection and a bare table name.\r\n'
    b'    Output: True/False. Never raises.\r\n'
    b'\r\n'
    b'    It used to query sqlite_master only and return False on any error. That did not\r\n'
    b'    crash, but it meant this returned False for EVERY table on Postgres -- so every\r\n'
    b'    feature guarded by it was silently switched off on live rather than merely\r\n'
    b'    unavailable. `db_adapter` does not translate sqlite_master (it covers datetime(),\r\n'
    b'    strftime() and last_insert_rowid()), so the dialect split has to be handled here.\r\n'
    b'\r\n'
    b'    BRANCHES on the backend rather than trying SQLite first and falling back: a failed\r\n'
    b'    statement poisons the surrounding Postgres transaction, and InFailedSqlTransaction\r\n'
    b'    already appears in this app\'s live error log. A probe that breaks the caller\'s\r\n'
    b'    transaction is worse than the missing feature it was checking for.\r\n'
    b'    """\r\n'
    b'    try:\r\n'
    b'        if _inbox_is_pg():\r\n'
    b'            row = conn.execute(\r\n'
    b'                "SELECT to_regclass(?)", ("public." + str(table_name),)).fetchone()\r\n'
    b'            return bool(row and row[0])\r\n'
    b'        row = conn.execute(\r\n'
    b'            "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=?",\r\n'
    b'            (table_name,)\r\n'
    b'        ).fetchone()\r\n'
    b'        return row is not None\r\n'
    b'    except Exception:\r\n'
    b'        return False\r\n'
)

# ── 2. stop /admin/marketplace inlining its own sqlite_master probe ───────────────────────
OLD_CALLSITE = (
    b'        ).fetchall() if c.execute(\r\n'
    b'            "SELECT name FROM sqlite_master WHERE type=\'table\' AND name=\'marketplace_audit_log\'"\r\n'
    b'        ).fetchone() else []\r\n'
)

NEW_CALLSITE = (
    b'        ).fetchall() if _table_exists(c, "marketplace_audit_log") else []\r\n'
)

MARKER = b"Does `table_name` exist? Works on BOTH backends."


def main():
    data = open(SRC, "rb").read()
    if MARKER in data:
        print("already patched -- nothing to do")
        return 0
    for name, blob in (("helper", OLD_HELPER), ("callsite", OLD_CALLSITE)):
        if data.count(blob) != 1:
            print(f"REFUSING: {name} expected 1 match, found {data.count(blob)}")
            return 1
    data = data.replace(OLD_HELPER, NEW_HELPER).replace(OLD_CALLSITE, NEW_CALLSITE)
    open(SRC, "wb").write(data)
    print("patched: _table_exists is backend-aware; /admin/marketplace uses it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
