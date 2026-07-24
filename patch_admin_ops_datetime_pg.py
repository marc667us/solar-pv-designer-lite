# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# WHAT: makes the Admin Operations Center's 24h failed-login count dialect-safe.
# WHY:  `datetime('now', '-24 hours')` is a SQLite-only function. On live
#       Postgres it raises `UndefinedFunction: function datetime(...) does not
#       exist`, which 500s the ENTIRE /admin/operations page (observed 8x in
#       error_logs, last 2026-07-24). That is the "operation does not exist"
#       error reported from the opcenter.
# HOW:  compute the cutoff timestamp in Python and bind it as a `?` param.
#       Works identically on SQLite and Postgres; no DB-specific date function.
#
# INPUT:  web_app.py (bytes)
# OUTPUT: web_app.py rewritten in place; asserts the anchor is unique and that
#         the result byte-compiles.

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

OLD = (
    b'failed_logins = c.execute(\r\n'
    b'            "SELECT COUNT(*) FROM audit_logs WHERE action=\'failed_login\' "\r\n'
    b'            "AND created_at >= datetime(\'now\', \'-24 hours\')"\r\n'
    b'        ).fetchone()[0] if _table_exists(c, "audit_logs") else 0'
)

NEW = (
    b'# Dialect-safe 24h window: compute the cutoff in Python and bind it as a\r\n'
    b'        # param. datetime(\'now\', ...) is SQLite-only and 500s on Postgres\r\n'
    b'        # (UndefinedFunction), which was breaking the whole Ops Center page.\r\n'
    b'        _since_24h = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")\r\n'
    b'        failed_logins = c.execute(\r\n'
    b'            "SELECT COUNT(*) FROM audit_logs WHERE action=\'failed_login\' "\r\n'
    b'            "AND created_at >= ?", (_since_24h,)\r\n'
    b'        ).fetchone()[0] if _table_exists(c, "audit_logs") else 0'
)

n = data.count(OLD)
assert n == 1, f"expected exactly 1 match for OLD block, found {n}"

data = data.replace(OLD, NEW)
open(PATH, "wb").write(data)

py_compile.compile(PATH, doraise=True)
print("OK: patched admin_operations 24h window to be dialect-safe; byte-compiles clean.")
