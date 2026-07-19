"""/admin/operations used SQLite-only date arithmetic, so it 500s on live Postgres.

FOUND 2026-07-19 while hunting the owner's "check market admin there is an issue there".

    SELECT COUNT(*) FROM audit_logs WHERE action='failed_login'
      AND created_at >= datetime('now', '-24 hours')

`datetime(text, text)` is a SQLite function. Postgres has no such function and raises

    function datetime(unknown, unknown) does not exist

so the whole Admin Operations page returns 500 on live. It passes locally because the dev
database is SQLite -- the failure only exists where it matters, which is why a local smoke
test of every admin GET returned 200 across the board.

WHY THIS ONE SLIPPED THROUGH: the codebase already knows about this incompatibility and
handles it correctly in three other places -- a try/except PG-then-SQLite fallback at the
error_logs count, an if/else at the admin_notifications dedupe, and an `_inbox_is_pg()`
ternary in the SOC correlation. This single call site was simply never converted. One
unguarded query among three guarded ones is drift, not a design decision.

The guard is `_inbox_is_pg()` (defined later in the file, which is fine -- names resolve when
the handler runs, not when it is defined). Reusing it rather than adding a fourth way to ask
"is this Postgres": a second detector eventually disagrees with the first, which is the exact
failure mode that produced four separate faults earlier today.

web_app.py is CRLF + mojibake, so this is a byte-level splice, never an Edit. Idempotent.
"""
SRC = "web_app.py"

OLD = (
    b'            "SELECT COUNT(*) FROM audit_logs WHERE action=\'failed_login\' "\r\n'
    b'            "AND created_at >= datetime(\'now\', \'-24 hours\')"\r\n'
)

NEW = (
    b'            "SELECT COUNT(*) FROM audit_logs WHERE action=\'failed_login\' "\r\n'
    b'            # datetime() is SQLite-only; Postgres raises "function datetime(unknown,\r\n'
    b'            # unknown) does not exist" and this whole page 500s on live. Three other\r\n'
    b'            # call sites in this file already branch on the backend -- this one never\r\n'
    b'            # did. Same helper as those, so there is one answer to "is this Postgres".\r\n'
    b'            + ("AND created_at >= (NOW() - INTERVAL \'24 hours\')"\r\n'
    b'               if _inbox_is_pg() else\r\n'
    b'               "AND created_at >= datetime(\'now\', \'-24 hours\')")\r\n'
)

MARKER = b"datetime() is SQLite-only; Postgres raises"


def main():
    data = open(SRC, "rb").read()
    if MARKER in data:
        print("already patched -- nothing to do")
        return 0
    if data.count(OLD) != 1:
        print(f"REFUSING: expected exactly 1 match, found {data.count(OLD)}")
        return 1
    open(SRC, "wb").write(data.replace(OLD, NEW))
    print("patched: /admin/operations failed-login count now branches on the backend")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
