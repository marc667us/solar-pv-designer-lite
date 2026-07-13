"""Regressions pinning the Supervisor audit of slices 6.5 / 6.6.

Every one of these was invisible to a SQLite-only suite. That is the point of the file:
three of the four defects below could ONLY bite on Postgres, and 268 green tests never came
close to any of them.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, constants, documents, imports, members, rbac, tenancy, txn, workflows,
)
from app.enterprise_programme.documents import DocumentError
from app.security import audit as audit_mod


class _Conn(sqlite3.Connection):
    pass


OWNER = 1
BOB = 2


@pytest.fixture()
def db():
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((OWNER, "owen"), (BOB, "bob")):
        c.execute("INSERT INTO users (id, username, email) VALUES (?,?,?)",
                  (uid, name, name + "@example.com"))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)"
    )
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    beneficiaries.ensure_schema(c)
    documents.ensure_schema(c)
    for uid, name in ((OWNER, "owen"), (BOB, "bob")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry")
    pid = workflows.create_programme(c, org, OWNER, code="GH-1", name="Homes",
                                     sponsor_user_id=OWNER, audit=_audit(c))
    c.commit()
    yield c, org, pid
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


# --- HIGH-1: one bad row must not kill the batch ----------------------------


def test_a_duplicate_row_is_flagged_and_the_rest_of_the_batch_still_imports(db):
    """HIGH -- on Postgres a failed INSERT poisons the whole transaction.

    write_beneficiary_row's INSERT is bare. Without a per-row SAVEPOINT, a duplicate site
    code aborts the psycopg2 transaction (InFailedSqlTransaction) and the very next
    statement -- the UPDATE that marks the row as an Error -- raises. That is not an
    EnterpriseGateError, so it escapes the loop and 500s the request with the ENTIRE batch
    rolled back: the exact opposite of "one bad row must not cost the other 1999".

    Deterministic, not a race: ticking "import duplicates too" makes the first duplicate row
    a guaranteed collision. SQLite cannot reproduce the poisoning, so this test pins the
    BEHAVIOUR the savepoint buys on both backends -- the good rows land, the bad row is
    flagged.
    """
    c, org, pid = db

    # KP-01 is already in the register, so the sheet's KP-01 row is a guaranteed collision.
    beneficiaries.create_beneficiary(
        c, org, OWNER, pid, code="KP-01", name="Kpando Senior High",
        beneficiary_type="school", audit=_audit(c),
    )

    csv = (b"Site Code,School Name\n"
           b"KP-01,Kpando Senior High\n"      # collides with the row already registered
           b"HO-02,Hohoe Technical\n"
           b"AC-03,Accra Girls\n")
    headers, rows = imports.parse_file("sites.csv", csv)
    batch_id = imports.stage_import(
        c, org, OWNER, pid, filename="sites.csv", headers=headers, rows=rows,
        mapping=imports.auto_map(headers), default_type="school", audit=_audit(c),
    )
    result = imports.commit_batch(c, org, OWNER, batch_id,
                                  include_duplicates=True, audit=_audit(c))

    # The two good rows landed; the collision was flagged, not fatal.
    assert result["imported"] == 2
    assert result["failed"] == 1

    codes = {r[0] for r in c.execute(
        "SELECT code FROM enterprise_beneficiary_register "
        " WHERE tenant_id=? AND programme_id=?",
        (org, pid),
    )}
    assert codes == {"KP-01", "HO-02", "AC-03"}


# --- HIGH-2: the adapter must report its transaction state ------------------


def test_the_postgres_adapter_reports_whether_a_transaction_is_open():
    """HIGH -- txn.atomic's SAVEPOINT branch was DEAD CODE on the only backend that matters.

    `_PgConnAdapter` exposed neither sqlite3's `in_transaction` nor psycopg2's `info`, and
    has no connection-level __getattr__ passthrough -- so txn.in_transaction() fell through
    to its "unknown driver" default of False, ALWAYS. Consequences: a nested service silently
    committed its caller's half-finished work, and there was no savepoint anywhere to recover
    a poisoned transaction -- which is what made HIGH-1 fatal rather than merely untidy.
    """
    import db_adapter

    class _FakeInfo:
        def __init__(self, status):
            self.transaction_status = status

    class _FakeRaw:
        def __init__(self, status):
            self.info = _FakeInfo(status)

    idle = db_adapter._PgConnAdapter(_FakeRaw(0))       # TRANSACTION_STATUS_IDLE
    open_ = db_adapter._PgConnAdapter(_FakeRaw(2))      # TRANSACTION_STATUS_INTRANS

    assert hasattr(idle, "info")
    assert txn.in_transaction(idle) is False
    assert txn.in_transaction(open_) is True            # was False before the fix


# --- HIGH-3: a click must not fan out into hundreds of LLM calls ------------


def test_a_document_cannot_cover_an_unbounded_number_of_activities(db):
    """HIGH -- "Select the whole Planning stage" ticks 183 activities in one click.

    With AI drafting on (the default) that was up to 366 SEQUENTIAL LLM round trips inside a
    single HTTP request, holding a database connection, against gunicorn's 120s timeout on a
    two-worker instance. An ordinary click could take the site down.
    """
    c, org, pid = db
    many = [a for p in ("P03_NEEDS", "P04_FEASIBILITY", "P05_STRUCTURING")
            for a, _t in constants.PHASE_ACTIVITIES[p]]
    assert len(many) > documents.MAX_ACTIVITIES_PER_DOCUMENT

    with pytest.raises(DocumentError, match="the limit is"):
        documents.generate_document(c, org, OWNER, pid, activity_codes=many,
                                    use_ai=False, audit=_audit(c))


def test_the_whole_planning_stage_really_does_exceed_the_cap():
    """The cap is not theoretical -- the stage select-all button genuinely exceeds it."""
    planning = [p for s, _n, ps in constants.LIFECYCLE_STAGES if s == "S2_PLANNING"
                for p in ps]
    n = sum(len(constants.PHASE_ACTIVITIES[p]) for p in planning)
    assert n > documents.MAX_ACTIVITIES_PER_DOCUMENT


def test_the_ai_budget_is_smaller_than_the_document_cap():
    """A document may be long; the number of LLM calls it costs may not scale with it."""
    assert documents.MAX_AI_ACTIVITIES < documents.MAX_ACTIVITIES_PER_DOCUMENT


# --- MED-1: re-inviting must not silently restore old authority -------------


def test_reinviting_an_offboarded_member_does_not_restore_their_old_roles(db):
    """MED -- and the audit trail would have actively CONTRADICTED it.

    remove_member keeps the role rows (correct: they go inert via the membership JOIN, and
    the trail can still answer "what could Bob do in March"). But reinstating the membership
    made every one of them live again. Offboard a Technical Director, re-invite them as a
    Surveyor, and they silently get template approval and gate-signing back -- while the
    ENTERPRISE_MEMBER_ADDED row says `role: surveyor`.
    """
    c, org, _pid = db

    members.invite(c, org, OWNER, "bob", "technical_director", audit=_audit(c))
    members.grant(c, org, OWNER, BOB, "programme_manager", audit=_audit(c))
    assert set(rbac.roles_for_user(c, org, BOB)) == {"technical_director",
                                                     "programme_manager"}

    members.remove(c, org, OWNER, BOB, audit=_audit(c))

    # Re-invited as a plain surveyor: that, and nothing more.
    members.invite(c, org, OWNER, "bob", "surveyor", audit=_audit(c))
    assert set(rbac.roles_for_user(c, org, BOB)) == {"surveyor"}

    assert not rbac.has_permission(c, org, BOB, "template.approve")
    assert not rbac.has_permission(c, org, BOB, "qualification.approve")
    assert rbac.has_permission(c, org, BOB, "qualification.score")
