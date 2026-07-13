"""Registering a programme whose CODE is taken must SAY SO -- never hiccup.

THE BUG THIS PINS
-----------------
The owner reported: "register a new programme takes user to hiccup page", and then
"look for the duplicate key error and fix".

Migration 026 declares `CREATE UNIQUE INDEX ux_ent_programme_code ON
enterprise_programme_registry (tenant_id, code)`. Nothing in create_programme checked it,
and the route (enterprise_programme_routes.enterprise_programme_new) catches only
ValueError, EnterpriseGateError and EnterprisePermissionError. So a re-used code raised a
raw IntegrityError -- "duplicate key value violates unique constraint" -- which escaped to
the catch-all handler and rendered the friendly error page.

The result was a dead end with no information in it: the owner pressed Register, got a
"hiccup", changed nothing (because nothing told them what was wrong), pressed Register
again, and got the same hiccup. Forever. The one fact they needed -- THAT CODE IS TAKEN --
was in the exception, and the exception was swallowed by a page that says "we hit a small
hiccup".

A refusal the user cannot act on is indistinguishable from a broken app. So the test is
not "does it reject the duplicate" (the database always did) -- it is "does it reject it
in a way that TELLS THE USER WHAT TO DO".
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import tenancy, workflows


class AuditSpy:
    def __call__(self, action: str, **kw) -> bool:
        return True


class _Conn(sqlite3.Connection):
    org: str


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username) VALUES (1, 'alice')")
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    tenancy.get_or_create_personal_tenant(c, 1, "alice")
    org = tenancy.create_organisation(c, 1, "Ministry of Energy", "ministry", "Ghana")
    c.commit()
    c.org = org  # type: ignore[attr-defined]
    yield c
    c.close()


def _create(db, code: str) -> int:
    return workflows.create_programme(
        db, db.org, 1, code=code, name="Ghana Schools Solar",
        design_strategy="standard", audit=AuditSpy(),
    )


def test_a_duplicate_code_is_refused_with_a_message_the_user_can_act_on(db):
    _create(db, "GH-SCHOOLS-01")

    with pytest.raises(ValueError) as excinfo:
        _create(db, "GH-SCHOOLS-01")

    msg = str(excinfo.value)
    # It must name the offending code, and say what to do about it. "IntegrityError:
    # duplicate key value violates unique constraint ux_ent_programme_code" satisfies
    # neither, which is why it became a hiccup page instead of a fix.
    assert "GH-SCHOOLS-01" in msg, "the message must name the code that is taken"
    assert "already exists" in msg.lower()
    assert "different" in msg.lower() or "unique" in msg.lower(), (
        "the message must tell the user what to DO -- choose another code"
    )


def test_the_failure_is_a_ValueError_so_the_route_flashes_instead_of_hiccupping(db):
    """The route's `except (ValueError, EnterpriseGateError)` arm flashes and redirects.

    Anything NOT in that tuple -- an IntegrityError, say -- escapes to the catch-all
    handler and becomes the error page. So the exception TYPE is the whole difference
    between a helpful red banner and the owner's dead end, and it is worth asserting
    directly rather than trusting that it stays in the family.
    """
    _create(db, "DUP-1")
    with pytest.raises(ValueError):
        _create(db, "DUP-1")


def test_the_duplicate_check_is_scoped_to_the_organisation(db):
    """(tenant_id, code) is the unique key -- NOT code alone.

    Two different ministries must both be able to run a programme called PHASE-1. If the
    pre-check were written `WHERE code = ?` it would leak one organisation's programme
    codes into another's namespace, and would refuse a code the database would happily
    accept -- a refusal invented by the app, enforcing a rule nobody asked for.
    """
    other = tenancy.create_organisation(db, 1, "Ministry of Health", "ministry", "Ghana")
    _create(db, "PHASE-1")

    pid = workflows.create_programme(
        db, other, 1, code="PHASE-1", name="Clinics", design_strategy="standard",
        audit=AuditSpy(),
    )
    assert pid, "the same code in a DIFFERENT organisation must be allowed"


def test_the_first_programme_still_exists_after_the_duplicate_is_refused(db):
    """The refusal must not take the original with it.

    create_programme seeds 16 phases and 14 gates inside one atomic block. On Postgres a
    constraint violation ABORTS THE TRANSACTION, so a fix that caught the error and carried
    on would have left the programme half-seeded. The rejected attempt must roll back
    completely and touch nothing that already existed.
    """
    first = _create(db, "KEEP-ME")

    with pytest.raises(ValueError):
        _create(db, "KEEP-ME")

    rows = db.execute(
        "SELECT COUNT(*) FROM enterprise_programme_registry WHERE tenant_id=? AND code=?",
        (db.org, "KEEP-ME"),
    ).fetchone()
    assert rows[0] == 1, "the duplicate attempt must not have created a second row"

    phases = db.execute(
        "SELECT COUNT(*) FROM enterprise_programme_phase_states WHERE programme_id=?",
        (first,),
    ).fetchone()
    assert phases[0] == 16, "the original programme's 16 phases must survive intact"

    gates_n = db.execute(
        "SELECT COUNT(*) FROM enterprise_stage_gates WHERE programme_id=?",
        (first,),
    ).fetchone()
    assert gates_n[0] == 14, "the original programme's 14 gates must survive intact"
