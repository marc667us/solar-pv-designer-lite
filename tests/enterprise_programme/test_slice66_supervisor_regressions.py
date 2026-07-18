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
    beneficiaries, documents, imports, members, rbac, tenancy, txn, workflows,
)
from app.enterprise_programme.rev4_phases import DELIVERABLE_INDEX
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


def test_a_report_cannot_fan_out_into_an_unbounded_number_of_llm_calls(db, monkeypatch):
    """HIGH -- an ordinary click could take the site down.

    Every drafted section is one SEQUENTIAL LLM round trip inside a single HTTP request,
    holding a database connection, against gunicorn's 120s timeout on a two-worker instance.
    The old model let one click tick 183 activities and cost a round trip each; Rev 4's reports
    are structurally narrower (a report is ONE deliverable and its sections are its topics), but
    the budget is what actually bounds the cost -- MAX_AI_SECTIONS -- and it must be ENFORCED
    rather than merely declared.

    So the budget is squeezed below the widest report the app can write and the calls are
    counted. Past the budget the report must keep generating on the deterministic path -- the
    same path it takes when no LLM is reachable at all -- so a long report degrades in quality,
    never in availability.
    """
    c, org, pid = db

    # The widest report Rev 4 can ask for: the most sections any deliverable resolves to.
    widest = max(DELIVERABLE_INDEX, key=lambda d: len(documents._sections_for_deliverable(d)))
    n_sections = len(documents._sections_for_deliverable(widest))
    assert n_sections > 2, "no report is wide enough for this test to bound anything"

    calls = []

    def _counting_ai_write(subject, facts, passage_body="", *, brief="", document_title=""):
        calls.append(subject)
        return f"{subject} is drafted by the writing service."

    # BOTH WRITING PATHS ARE COUNTED. Sections are now prefetched in BATCHES to survive
    # OpenRouter's 50-requests-a-day free tier, so most sections are written by
    # `_ai_write_many` and never reach `_ai_write`. Counting only the single-section path
    # would have let an unbounded batch fan-out pass this test while reporting zero calls --
    # the budget must bound the TOTAL number of provider round trips, whichever path makes
    # them, because that total is what the timeout and the daily quota actually see.
    def _counting_ai_write_many(sections, facts, *, document_title="", deadline=None):
        calls.append(f"batch:{len(list(sections))}")
        return {}

    monkeypatch.setattr(documents, "_ai_write", _counting_ai_write)
    monkeypatch.setattr(documents, "_ai_write_many", _counting_ai_write_many)
    monkeypatch.setattr(documents, "MAX_AI_SECTIONS", 2)

    md = documents.build_markdown(c, org, pid, widest,
                                  title=DELIVERABLE_INDEX[widest][1], use_ai=True)

    assert len(calls) == 2, (
        f"the AI budget did not stop the fan-out: {len(calls)} provider calls on a budget "
        f"of 2 -- {calls}")
    # ...and the report is still a report: every section is present. Past the model budget it
    # uses the deterministic path; a failed first model call is covered by the loud-failure
    # document tests instead of being passed off as a report.
    assert md.count("## ") == n_sections


def test_the_duplicate_RETRY_is_charged_to_the_ai_budget_too(db, monkeypatch):
    """HIGH -- the retry must not double the request's model calls behind the budget's back.

    The duplicate-statement guard (2026-07-16) gives a repeating model ONE chance to rewrite the
    section. That retry is another SEQUENTIAL round trip to a free-tier model inside the same
    HTTP request, against gunicorn's 120s timeout on a two-worker instance. If it is not charged
    to MAX_AI_SECTIONS, the budget stops meaning what it says: a report that happens to repeat
    itself can make twice the calls the budget allows, and it is precisely the slow, repetitive
    report that times the request out.

    The sibling fan-out test cannot catch this: its stub returns UNIQUE prose per subject, so the
    retry never fires there. This one forces the retry by parroting one sentence at every
    section -- the owner's real "same statement" failure -- and holds the total call count to the
    budget.
    """
    c, org, pid = db

    widest = max(DELIVERABLE_INDEX, key=lambda d: len(documents._sections_for_deliverable(d)))
    assert len(documents._sections_for_deliverable(widest)) > 3, "report too narrow to bound"

    calls = []
    PARROT = "The programme is progressing in line with its objectives."

    def _parroting_ai_write(subject, facts, passage_body="", *, brief="", document_title=""):
        # Every call repeats -> every section after the first triggers a retry.
        calls.append(subject)
        return PARROT

    monkeypatch.setattr(documents, "_ai_write", _parroting_ai_write)
    monkeypatch.setattr(documents, "MAX_AI_SECTIONS", 3)

    documents.build_markdown(c, org, pid, widest,
                             title=DELIVERABLE_INDEX[widest][1], use_ai=True)

    assert len(calls) <= 3, (
        "the retry escaped the AI budget: %d calls against a budget of 3. Every retry is a "
        "sequential round trip inside one request." % len(calls)
    )


def test_the_ai_budget_is_never_reached_by_a_report_the_app_can_actually_write():
    """The budget is a backstop, not a ceiling an operator meets in normal use.

    A report whose sections outran the budget would silently lose its drafting on the sections
    past it -- so if a future edit widens the topic table past MAX_AI_SECTIONS, that is a
    decision someone must take deliberately, not discover in production.
    """
    widest = max(len(documents._sections_for_deliverable(d)) for d in DELIVERABLE_INDEX)
    assert widest <= documents.MAX_AI_SECTIONS


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
