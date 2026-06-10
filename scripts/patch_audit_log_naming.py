"""
Session B / B6 — rename `audit_log` (singular) -> `audit_logs` (plural) in
web_app.py so the SELECT sites match the writes (lines 1769/1780 already
INSERT into `audit_logs` plural).

Why byte-patch: web_app.py is CRLF + mojibake; the Edit tool would
introduce curly quotes. Direct byte replace is the safe path per CLAUDE.md.

The 4 occurrences are all SQL string literals + 1 user-facing message:

  1. web_app.py:10202  SELECT COUNT(*) FROM audit_log  WHERE action='failed_login'
  2. web_app.py:10204  _table_exists(c, "audit_log")
  3. web_app.py:10777  SELECT id, action, user_id, ... FROM audit_log ORDER BY id DESC
  4. web_app.py:10786  "No audit_log table yet. Activates after PostgreSQL migration."

The comment at line 5903 ("We intentionally skip audit_log so forensic
trail survives") is left alone — it's prose, not a SQL identifier.

Behavior impact: today both SELECTs return early via except/_table_exists
because `audit_log` doesn't exist on either backend. After the rename
they target `audit_logs` which DOES exist; the SELECTs still gracefully
degrade (action='failed_login' mismatches the actual 'login_failed'
writes; column list at 10777 lacks resource/status). Observable behavior
unchanged.
"""
from __future__ import annotations
import os, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web_app.py")

# (old_bytes, new_bytes, expected_count). Each replacement is uniquely
# anchored in the surrounding bytes so we cannot mis-match.
PATCHES = [
    (
        b"SELECT COUNT(*) FROM audit_log WHERE action='failed_login' ",
        b"SELECT COUNT(*) FROM audit_logs WHERE action='failed_login' ",
        1,
    ),
    (
        b'_table_exists(c, "audit_log")',
        b'_table_exists(c, "audit_logs")',
        1,
    ),
    (
        b"SELECT id, action, user_id, resource, status, created_at FROM audit_log ORDER BY id DESC LIMIT 100",
        b"SELECT id, action, user_id, resource, status, created_at FROM audit_logs ORDER BY id DESC LIMIT 100",
        1,
    ),
    (
        b'"No audit_log table yet. Activates after PostgreSQL migration."',
        b'"No audit_logs table yet. Activates after PostgreSQL migration."',
        1,
    ),
]


def main() -> int:
    data = open(TARGET, "rb").read()
    for old, new, expected in PATCHES:
        n = data.count(old)
        if n != expected:
            print(f"ERROR: pattern {old[:60]!r}... matched {n}× (expected {expected})",
                  file=sys.stderr)
            return 2
        data = data.replace(old, new, expected)
    open(TARGET, "wb").write(data)
    print(f"OK applied {len(PATCHES)} patches to web_app.py")
    # Sanity: count surviving singular vs plural.
    leftover = data.count(b"audit_log ") + data.count(b'audit_log"') + data.count(b"audit_log'")
    plural = data.count(b"audit_logs")
    print(f"audit_log (singular tokens, incl. comment): {leftover}, audit_logs: {plural}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
