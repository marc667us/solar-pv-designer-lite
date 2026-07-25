"""Add `failed_logins_24h` to GET/POST /admin/ops/security/audit.

WHY: beta-monitor.yml has a brute-force detector that reads
`security_audit["failed_logins_24h"]` and alerts when the count climbs. That key
has NEVER been produced by the route, so `fl` was always None and the alert
could never fire -- on top of the separate GET/POST 405 that made the whole
probe error out. Fixing only the 405 would turn the probe green while the
alert stayed dead, which is worse than an obvious error.

Inputs:  web_app.py (bytes, CRLF + mojibake -- byte-spliced, never Edit-ed)
Output:  web_app.py with the new count inserted into the existing try/with block
         of admin_ops_security_audit(), reusing the SAME dialect-safe pattern as
         admin_operations() (web_app.py:12437-12444): cutoff computed in Python
         and bound as a param, because datetime('now', ...) is SQLite-only and
         500s on Postgres.

Syntax notes:
  - anchored on the `recent_payments` else-branch, which is unique to this route
  - `_table_exists` guard so a fresh DB without audit_logs degrades to 0, matching
    how the surrounding counts already degrade
  - idempotent: re-running is a no-op if the key is already present
"""

SRC = "web_app.py"

ANCHOR = (
    b"            else:\r\n"
    b"                results[\"recent_payments\"] = 0\r\n"
)

ADDITION = (
    b"            # Brute-force signal consumed by beta-monitor.yml. Dialect-safe\r\n"
    b"            # 24h window: compute the cutoff in Python and bind it, because\r\n"
    b"            # datetime('now', ...) is SQLite-only and raises UndefinedFunction\r\n"
    b"            # on Postgres (the bug that took out /admin/operations).\r\n"
    b"            if _table_exists(c, \"audit_logs\"):\r\n"
    b"                _since_24h = (datetime.utcnow() - timedelta(hours=24)).strftime(\"%Y-%m-%d %H:%M:%S\")\r\n"
    b"                results[\"failed_logins_24h\"] = c.execute(\r\n"
    b"                    \"SELECT COUNT(*) FROM audit_logs WHERE action='failed_login' \"\r\n"
    b"                    \"AND created_at >= ?\", (_since_24h,)\r\n"
    b"                ).fetchone()[0]\r\n"
    b"            else:\r\n"
    b"                results[\"failed_logins_24h\"] = 0\r\n"
)


def main():
    data = open(SRC, "rb").read()

    if b'results["failed_logins_24h"]' in data:
        print("SKIP: failed_logins_24h already present (idempotent no-op)")
        return

    n = data.count(ANCHOR)
    if n != 1:
        raise SystemExit(f"ABORT: anchor found {n} times, expected exactly 1")

    data = data.replace(ANCHOR, ANCHOR + ADDITION)
    open(SRC, "wb").write(data)
    print("OK: inserted failed_logins_24h into admin_ops_security_audit()")


if __name__ == "__main__":
    main()
