"""_table_exists must work on BOTH backends, and /admin/marketplace must use it.

EVIDENCE THIS FIXES (live error_logs, 2026-07-19):
    7 x /admin/marketplace [UndefinedTable] last seen 2026-07-18

/admin/marketplace guarded against a missing `marketplace_audit_log` by querying
`sqlite_master` -- a SQLite system table that does not exist on Postgres. The EXISTENCE CHECK
was what raised, and the whole admin marketplace page 500'd on live.

`db_adapter` does not translate `sqlite_master` (it covers datetime/strftime/
last_insert_rowid), so this dialect split must be handled in the helper.

Run: python -m pytest test_table_exists_backends.py -q
"""
import re
import pathlib

import pytest

import web_app


@pytest.fixture
def conn():
    with web_app.get_db() as c:
        yield c


def test_finds_a_real_table(conn):
    assert web_app._table_exists(conn, "users") is True


def test_missing_table_is_false_not_an_exception(conn):
    assert web_app._table_exists(conn, "definitely_not_a_table_xyz") is False


def test_never_raises_on_a_hostile_name(conn):
    """A table name reaching this helper must not be able to blow up the caller."""
    for bad in ("", "  ", "'; DROP TABLE users;--", "a" * 300, None):
        assert web_app._table_exists(conn, bad) in (True, False)


def test_postgres_branch_uses_to_regclass_not_sqlite_master(monkeypatch):
    """THE REGRESSION. On Postgres it must not touch sqlite_master.

    Cannot be proven against the real DB here (dev is SQLite), so the branch is driven by
    forcing the backend flag and capturing the SQL the helper issues.
    """
    seen = []

    class FakeConn:
        def execute(self, sql, params=()):
            seen.append(sql)
            class R:
                def fetchone(self_inner):
                    return ("public.marketplace_audit_log",)
            return R()

    monkeypatch.setattr(web_app, "_inbox_is_pg", lambda: True)
    assert web_app._table_exists(FakeConn(), "marketplace_audit_log") is True
    joined = " ".join(seen)
    assert "to_regclass" in joined, "Postgres branch must use to_regclass"
    assert "sqlite_master" not in joined, (
        "sqlite_master does not exist on Postgres -- querying it is the bug being fixed")


def test_sqlite_branch_still_uses_sqlite_master(monkeypatch):
    seen = []

    class FakeConn:
        def execute(self, sql, params=()):
            seen.append(sql)
            class R:
                def fetchone(self_inner):
                    return None
            return R()

    monkeypatch.setattr(web_app, "_inbox_is_pg", lambda: False)
    assert web_app._table_exists(FakeConn(), "whatever") is False
    assert "sqlite_master" in " ".join(seen)


def test_postgres_branch_does_not_probe_then_fall_back(monkeypatch):
    """It must BRANCH, not try-SQLite-then-retry.

    A failed statement poisons the surrounding Postgres transaction --
    InFailedSqlTransaction appears in this app's own live error log -- so a probe that fails
    first would break the caller's transaction even when it recovers its own answer.
    """
    seen = []

    class FakeConn:
        def execute(self, sql, params=()):
            seen.append(sql)
            class R:
                def fetchone(self_inner):
                    return (None,)
            return R()

    monkeypatch.setattr(web_app, "_inbox_is_pg", lambda: True)
    web_app._table_exists(FakeConn(), "nope")
    assert len(seen) == 1, f"expected exactly one statement, got {len(seen)}"


def test_admin_marketplace_no_longer_inlines_a_sqlite_master_probe():
    """The call site must use the helper, not a second private copy of the check.

    Two copies of 'does this table exist' is how the two diverged in the first place.
    """
    src = pathlib.Path("web_app.py").read_bytes().decode("utf-8", "replace")
    i = src.index('@app.route("/admin/marketplace")')
    body = src[i:i + 4000]
    assert "sqlite_master" not in body, (
        "/admin/marketplace still inlines a sqlite_master query -- it 500s on Postgres")
    assert "_table_exists(c, \"marketplace_audit_log\")" in body


def test_admin_marketplace_renders():
    with web_app.app.test_client() as cl:
        with cl.session_transaction() as s:
            s["user_id"] = 1
        assert cl.get("/admin/marketplace").status_code == 200
