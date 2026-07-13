"""Every module's ensure_schema() must execute NOTHING when the backend is Postgres.

Why this test exists
--------------------
The SQLite mirrors in this package exist so the test suite has a schema to run against.
On Postgres the migrations own the schema, so each ensure_schema() is meant to be a no-op.

Slice 6.6 shipped a `documents.ensure_schema` that guarded Postgres by ASSUMING
`PRAGMA table_info` would raise there:

    try:
        have = {r[1] for r in c.execute("PRAGMA table_info(...)").fetchall()}
    except Exception:
        return                  # "Postgres: PRAGMA is not a thing"

It is. `db_adapter._translate_sqlite_to_postgres` deliberately TRANSLATES `PRAGMA
table_info` into an information_schema query, so on Postgres the PRAGMA *succeeded*, the
except never fired, and execution fell through to SQLite-only DDL containing
AUTOINCREMENT. Every logged-in /enterprise request 500'd on live.

The 315 unit tests could not catch it: they all run on SQLite, where the buggy path is
the correct path. So this test asserts the invariant directly, for EVERY module at once
-- a new slice that adds an ensure_schema and forgets the guard fails here.

Input:  none (drives ensure_schema with DATABASE_URL set to a Postgres URL).
Output: none; asserts no statement is executed.
"""
from __future__ import annotations

import importlib
import os

import pytest

# Every module in the package that owns a SQLite mirror. Add new slices here.
_MODULES = [
    "app.enterprise_programme.tenancy",       # migration 025
    "app.enterprise_programme.workflows",     # migration 026
    "app.enterprise_programme.beneficiaries", # migration 027
    "app.enterprise_programme.documents",     # migration 028
    "app.enterprise_programme.rollout",       # migration 029
]


class _ExplodingConn:
    """A connection that fails the test if anything is executed against it.

    Postgres owns the schema. A correct ensure_schema() never touches this connection,
    so any call at all is the bug -- including the PRAGMA probe, which db_adapter would
    happily answer on a real Postgres connection and thereby wave the caller through
    into SQLite-only DDL.
    """

    def __init__(self):
        self.statements: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.statements.append(str(sql))
        raise AssertionError(
            f"ensure_schema executed SQL on Postgres, which the migrations own: {sql!r}"
        )

    # ensure_schema must not reach for these either.
    def cursor(self, *a, **k):
        raise AssertionError("ensure_schema opened a cursor on Postgres")

    def commit(self):
        raise AssertionError("ensure_schema committed on Postgres")


@pytest.fixture
def pg_env(monkeypatch):
    """Make is_postgres() / _is_postgres() report Postgres, the way live does."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@example.invalid:5432/solarpro")
    yield


@pytest.mark.parametrize("module_name", _MODULES)
def test_ensure_schema_executes_nothing_on_postgres(module_name, pg_env):
    mod = importlib.import_module(module_name)
    conn = _ExplodingConn()

    mod.ensure_schema(conn)          # _ExplodingConn raises if this touches the DB

    assert conn.statements == [], (
        f"{module_name}.ensure_schema must be a no-op on Postgres; "
        f"it ran {conn.statements!r}"
    )


def test_the_guard_is_not_vacuous(monkeypatch):
    """Sanity: on SQLite the mirrors DO run, so the test above is proving something.

    Without this, a bug that made every ensure_schema unconditionally return early would
    leave the parametrised test passing and the SQLite suite mysteriously schema-less.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.enterprise_programme import tenancy

    conn = _ExplodingConn()
    with pytest.raises(AssertionError, match="executed SQL on Postgres"):
        tenancy.ensure_schema(conn)   # on SQLite it must reach the connection
    assert conn.statements, "tenancy.ensure_schema built no SQLite schema at all"
