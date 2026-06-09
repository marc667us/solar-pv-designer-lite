"""
db_adapter.py — Postgres connection wrapper for SolarPro.

PHASE B1 (safe scaffold). Active ONLY when DATABASE_URL points at a
postgres:// or postgresql:// URL. When DATABASE_URL is unset, web_app.py's
get_db() takes the existing SQLite path and this module isn't imported.

Goal: make a psycopg2 connection look enough like sqlite3.Connection that
the existing 303 execute() call sites + 553 ? placeholders keep working
without per-site refactoring. The compatibility layer covers:

  - execute(sql, params): translates ? -> %s; returns a cursor whose rows
    behave like sqlite3.Row (support BOTH row['col'] AND row[0] access)
  - executescript(sql_text): splits multi-statement string and runs each
  - commit() / rollback() / close()
  - context manager: commit on success / rollback on exception
    (mirrors sqlite3 — does NOT auto-close on context exit, by design,
    so the existing patterns still work)

KNOWN LIMITATIONS (documented for next session):

  - The ?->%s translation uses str.replace which is naive: if a SQL string
    literal contains the character '?', it gets wrongly substituted. None
    of SolarPro's queries do today (audited 2026-06-09); revisit if SQL
    grows.
  - SQLite-specific syntax in the codebase WILL fail on Postgres:
      * AUTOINCREMENT (~15 occurrences in init_db CREATE TABLE blocks)
      * datetime('now'), date('now'), strftime() — Postgres equivalents differ
      * PRAGMA table_info() — Postgres uses information_schema
    These are NOT handled here; they're handled by skipping init_db's
    CREATE TABLE pass when on Postgres (migrations 001-004 build the
    schema instead) AND by a future migration of date/time queries.
    The dual-backend get_db() in web_app.py guards this.
  - Connection pooling: this adapter opens a fresh connection per get_db()
    call. Free-tier Postgres caps at ~25 simultaneous connections; under
    real load we'd need psycopg2.pool. For dev/beta-without-load, fine.
"""

from __future__ import annotations

import os


class _PgConnAdapter:
    """Wraps a psycopg2 connection so it works in the same idioms the
    SolarPro codebase uses against sqlite3. See module docstring for the
    compatibility contract."""

    def __init__(self, raw_conn):
        self._conn = raw_conn

    # ── DB-API compat ──────────────────────────────────────────────────

    def execute(self, sql, params=()):
        """Run SQL with ?-style placeholders. Returns a cursor whose rows
        support both row['col'] and row[0] (we use psycopg2's DictCursor).

        Why DictCursor (not RealDictCursor): DictCursor rows are list
        subclasses with dict-like access — they pass both subscript paths
        the codebase uses. RealDictCursor returns dict-only rows which
        would break any caller that does row[0].
        """
        import psycopg2.extras
        translated = sql.replace("?", "%s") if "?" in sql else sql
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(translated, params if params else None)
        return cur

    def executescript(self, sql_text):
        """Run a multi-statement SQL string. Postgres doesn't have
        executescript; we split on `;` boundaries. Comments must be
        on their own lines (we trim each statement)."""
        cur = self._conn.cursor()
        for raw_stmt in sql_text.split(';'):
            stmt = raw_stmt.strip()
            if not stmt:
                continue
            # Skip lone SQL-line comments (the codebase doesn't mix them
            # inline with statements, so this is safe)
            if stmt.startswith('--') and '\n' not in stmt:
                continue
            cur.execute(stmt)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    # ── Context manager — mirrors sqlite3.Connection behavior ──────────
    # sqlite3's __exit__ commits on success / rolls back on exception,
    # but does NOT close the connection. We do the same so existing
    # `with get_db() as c:` patterns work identically.

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        # NB: don't close — sqlite3 doesn't and we have callers that hold
        # the connection beyond the `with` block. Connections are GC'd
        # when the variable goes out of scope.


def open_postgres(database_url: str):
    """Open a psycopg2 connection from a postgres:// or postgresql:// URL
    and return a _PgConnAdapter wrapping it. Used by web_app.py's
    get_db() when DATABASE_URL is set."""
    import psycopg2
    # Normalize legacy postgres:// -> postgresql:// (psycopg2 wants the latter)
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    sslmode = os.environ.get("PGSSLMODE", "require")
    raw = psycopg2.connect(database_url, sslmode=sslmode)
    return _PgConnAdapter(raw)
