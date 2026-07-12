"""Enterprise Solar Programme -- shared transaction + audit primitives.

WHY THIS MODULE EXISTS
----------------------
These four functions were born inside workflows.py, where they were the only consumer.
Slice 4 adds a second service (templates.py) that needs exactly the same guarantees:
all-or-nothing writes that never hijack the caller's transaction, an audit row that
commits with the action it describes, and an inserted-row id that is never guessed.

Copying them would have been the fastest thing to do and the worst. Each one encodes a
bug that was found the hard way -- a silently-committed half-transaction, a rolled-back
audit that voided C12, a MAX(id) race that attached child rows to another tenant's
parent. A second copy is a second place for one of those to come back.

So they live here, and workflows.py imports them under its old private names. Nothing
about its behaviour changes; there is simply one definition instead of two.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

# Counter behind atomic()'s per-invocation savepoint names. Process-local and only ever
# incremented; it names a savepoint, it does not identify anything.
_savepoint_seq = 0


def is_postgres() -> bool:
    """True when running against Postgres rather than local SQLite."""
    return str(os.environ.get("DATABASE_URL", "")).startswith(
        ("postgres://", "postgresql://")
    )


def in_transaction(c) -> bool:
    """Is this connection already inside a transaction the CALLER owns?

    Input:  a DB connection (sqlite3, psycopg2, or the db_adapter wrapper).
    Output: True if a transaction is already open.

    Defensive on purpose: an unknown connection type answers False, which puts us on the
    "own the transaction" path -- the same behaviour this module had before, so an
    unrecognised driver degrades to the old semantics rather than to no transaction.
    """
    in_tx = getattr(c, "in_transaction", None)  # sqlite3.Connection
    if isinstance(in_tx, bool):
        return in_tx
    info = getattr(c, "info", None)  # psycopg2 connection
    status = getattr(info, "transaction_status", None)
    if isinstance(status, int):
        return status != 0  # 0 == TRANSACTION_STATUS_IDLE
    return False


def autocommit_is_on(c) -> bool:
    """Is this connection in autocommit mode, where a rollback would be a no-op?

    Input:  a DB connection.
    Output: True if each statement commits itself.

    psycopg2 exposes `.autocommit`; sqlite3 signals it with `isolation_level is None`.
    Neither is the case for connections this app hands out today (db_adapter leaves
    psycopg2 at its transactional default, and get_db() leaves sqlite3 at its), so this
    is a guard against a FUTURE change rather than a present bug.
    """
    if getattr(c, "autocommit", False) is True:  # psycopg2
        return True
    if hasattr(c, "isolation_level"):            # sqlite3
        return getattr(c, "isolation_level") is None
    return False


@contextmanager
def atomic(c):
    """Make a service's writes all-or-nothing WITHOUT hijacking the caller's transaction.

    Input:  a DB connection.
    Output: a context manager. On a clean exit the work is durable; on any exception the
            work is undone and the exception propagates.

    WHY THIS IS NOT JUST try/commit/except/rollback (Codex slice-2 review, HIGH):
    `get_db()` in this app hands out a FRESH connection per call, but a route is free to
    do its own writes on that connection and then call into this module. A bare
    `c.commit()` here would silently commit the route's unrelated half-finished work, and
    a bare `c.rollback()` would silently destroy it. Neither is ours to do.

    So: if a transaction is ALREADY open, we are a guest -- we take a SAVEPOINT, and on
    failure we roll back only to that savepoint, leaving the caller's work intact and the
    caller's commit still theirs to make. If no transaction is open, we are the owner and
    we commit or roll back as before.

    The savepoint name is UNIQUE PER INVOCATION. With a fixed name, a nested call would
    issue `SAVEPOINT enterprise_op` a second time and its RELEASE would collapse the
    outer savepoint of the same name -- after which an outer rollback would no longer
    undo the inner work. Nesting is not something the module does today, but "don't nest
    these" is a convention, and a convention is not a safeguard.

    AUTOCOMMIT IS REFUSED, LOUDLY. Under autocommit each statement commits itself, so a
    rollback undoes nothing and control C12 (audit-or-nothing) would quietly become a
    lie -- the gate approval would stand with no audit row behind it. No connection this
    app hands out is in autocommit today; this raises so that if one ever is, the module
    stops instead of silently shipping unauditable approvals.
    """
    if autocommit_is_on(c):
        raise RuntimeError(
            "enterprise_programme services require a transactional connection: under "
            "autocommit a failed audit write cannot be rolled back, which would silently "
            "void control C12 (every material action must be auditable)"
        )

    if in_transaction(c):
        global _savepoint_seq
        _savepoint_seq += 1
        sp = f"enterprise_op_{_savepoint_seq}"
        c.execute(f"SAVEPOINT {sp}")
        try:
            yield
        except Exception:
            c.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            c.execute(f"RELEASE SAVEPOINT {sp}")
            raise
        c.execute(f"RELEASE SAVEPOINT {sp}")
        return  # the caller owns the commit -- do NOT commit here

    try:
        yield
    except Exception:
        c.rollback()
        raise
    c.commit()


def audit_on(c):
    """The audit hook the services use by default: writes on OUR connection.

    Input:  the connection the service is already writing on.
    Output: a callable(action, **kw) -> bool.

    THIS IS WHAT MAKES CONTROL C12 STRUCTURAL rather than a compensating rollback. The
    audit row is inserted in the SAME transaction as the action it describes, so they
    commit together or neither does. There is no window in which one exists without the
    other, and no over-logging when a commit later fails.

    It also fixes a real deadlock, which SQLite surfaced immediately and Postgres never
    would have: write_audit_event used to resolve its OWN connection via get_db(), and
    get_db() hands out a FRESH connection per call. So the audit write raced the very
    transaction it was describing -- on SQLite the open write transaction locks the
    database file, the audit INSERT failed with "database is locked", C12 treated the
    failed audit as a failed action, and EVERY audited action rolled itself back. Every
    programme creation, silently undone.

    NOTE FOR CALLERS: on Postgres the audit writer takes a transaction-scoped advisory
    lock to serialise the hash chain, and that lock is held until YOU commit. Write the
    audit row LAST -- see app/security/audit.py::_compute_chain_for_insert.
    """
    def _audit(action: str, **kw) -> bool:
        return default_audit(action, conn=c, **kw)
    return _audit


def default_audit(action: str, **kw) -> bool:
    """Write one audit row through the app's unified audit trail.

    Input:  action name plus write_audit_event's keyword arguments (including `conn`).
    Output: True if the row persisted, False otherwise.

    Late-imported so this module can be imported (and unit-tested) without dragging in
    web_app. Injectable via the `audit=` parameter on every service, which is how the
    C12 rollback tests force a failed write.
    """
    try:
        from app.security.audit import write_audit_event
    except Exception:  # pragma: no cover - audit module unavailable
        return False
    return write_audit_event(action, **kw)


def inserted_id(c, cur) -> int:
    """The id of the row this cursor just inserted, on either backend.

    Input:  connection, the cursor returned by the INSERT.
    Output: integer primary key.
    Raises: RuntimeError if the id cannot be established -- fail loudly rather than
            guess, because a wrong id here attaches child rows to the wrong parent.

    psycopg2 does not populate `lastrowid` for a plain INSERT; db_adapter's cursor proxy
    fills it lazily via `SELECT lastval()`. sqlite3 populates it natively. Both are
    SESSION-scoped, so both are safe under concurrency.

    WHAT THIS DELIBERATELY DOES NOT DO (Codex slice-2 review, HIGH): fall back to
    `SELECT MAX(id) FROM <table>`. That reads a GLOBAL maximum, not this session's
    insert. Two concurrent programme creations would race -- request A inserts id 10,
    request B inserts id 11, A then reads MAX(id)=11 and seeds A's 16 phase rows and 14
    gate rows onto B's programme, in B's tenant. That is a cross-tenant data corruption
    bug, and it is exactly the kind that only shows up under load in production.
    """
    rowid = getattr(cur, "lastrowid", None)
    if rowid:
        return int(rowid)
    if is_postgres():
        # Session-scoped: returns the value THIS session last generated, never another's.
        row = c.execute("SELECT lastval()").fetchone()
        if row and row[0]:
            return int(row[0])
    raise RuntimeError(
        "could not determine the inserted row id; refusing to guess "
        "(guessing here attaches child rows to another tenant's parent)"
    )
