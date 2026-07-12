"""The audit hash chain must survive the `conn=` parameter (Codex slice-3 HIGH).

app/security/audit.py gained an optional `conn=`, so an audited action can write its
evidence inside its OWN transaction -- which is what makes control C12 structural (the
action and its audit row commit together or not at all) and what fixed the SQLite
"database is locked" deadlock that was silently rolling back every enterprise action.

Two properties have to hold for that to be safe, and these tests pin both:

  1. A ROLLED-BACK action leaves NO audit row -- and therefore no hole in the chain.
     (An audit row for an action that did not happen is a lie; a chain with a gap does
     not verify. Neither is acceptable.)
  2. The chain still LINKS: each row's prev_hash is the previous row's row_hash. This is
     what verify_audit_chain() walks, and a fork makes the evidence stop being evidence.

The concurrency fix itself (a Postgres transaction-scoped advisory lock around
read-head-then-insert) cannot be exercised on SQLite, where the engine already serialises
writers with the database-file lock. What IS asserted here is that the chain the writer
produces is well-formed and gapless -- on the backend the test suite actually runs.
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from app.enterprise_programme import gates, tenancy, workflows
from app.enterprise_programme.gates import EnterpriseGateError
from app.security import audit as audit_mod


@pytest.fixture()
def db():
    """SQLite with the enterprise schema, an audit_logs table WITH the hash chain, one org."""
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username) VALUES (1,'alice')")
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)"
    )
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    tenancy.get_or_create_personal_tenant(c, 1, "alice")
    org = tenancy.create_organisation(c, 1, "Ministry of Energy", "ministry")
    c.commit()
    yield c, org
    c.close()
    audit_mod.reset_schema_probe()


def _audit(c):
    """The real writer, on our connection -- exactly what the services use."""
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


def _chain(c):
    return c.execute(
        "SELECT id, action, prev_hash, row_hash FROM audit_logs ORDER BY id"
    ).fetchall()


def test_the_audit_row_lands_in_the_same_transaction_as_the_action(db):
    """The whole point of `conn=`: the evidence commits with the action."""
    c, org = db
    pid = workflows.create_programme(c, org, 1, code="P1", name="One",
                                     sponsor_user_id=1, audit=_audit(c))
    rows = _chain(c)
    assert [r[1] for r in rows] == ["ENTERPRISE_PROGRAMME_CREATED"]
    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_programme_registry WHERE id=?", (pid,)
    ).fetchone()[0] == 1


def test_a_rolled_back_action_leaves_no_audit_row_and_no_gap(db):
    """Property 1. C12 cuts both ways.

    The old design wrote the audit on a SEPARATE connection, so a rolled-back action could
    leave a committed audit row behind -- an entry claiming something happened that did
    not. Now the row is inside the action's transaction, so it dies with it, and the chain
    has no gap to explain.
    """
    c, org = db
    workflows.create_programme(c, org, 1, code="P1", name="One",
                               sponsor_user_id=1, audit=_audit(c))
    before = _chain(c)

    # A transition that the gates refuse: no concept note, no approved Gate 1 (C01).
    pid = c.execute("SELECT id FROM enterprise_programme_registry").fetchone()[0]
    with pytest.raises(EnterpriseGateError):
        workflows.transition_programme_phase(c, org, pid, "P02_INITIATION", user_id=1,
                                             audit=_audit(c))

    assert _chain(c) == before, "a refused action must add nothing to the audit trail"


def test_the_chain_still_links_across_several_audited_actions(db):
    """Property 2. Each row's prev_hash is the previous row's row_hash.

    This is what verify_audit_chain() walks. If `conn=` had broken the chain -- by reading
    a stale head, or by writing out of order -- it would show up right here as a link that
    does not join.
    """
    c, org = db
    a = _audit(c)
    pid = workflows.create_programme(c, org, 1, code="P1", name="One",
                                     sponsor_user_id=1, audit=a)
    workflows.register_document(c, org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=a)
    workflows.approve_gate(c, org, pid, "G01", user_id=1, audit=a)
    workflows.transition_programme_phase(c, org, pid, "P02_INITIATION", user_id=1, audit=a)

    rows = _chain(c)
    assert [r[1] for r in rows] == [
        "ENTERPRISE_PROGRAMME_CREATED",
        "ENTERPRISE_DOCUMENT_REGISTERED",
        "ENTERPRISE_GATE_APPROVED",
        "ENTERPRISE_PHASE_TRANSITION",
    ]

    previous_hash = None
    for _id, _action, prev_hash, row_hash in rows:
        assert row_hash, "every row must be hashed"
        if previous_hash is not None:
            assert prev_hash == previous_hash, "the chain forked -- the evidence is broken"
        previous_hash = row_hash


def test_a_failed_audit_still_fails_the_action(db):
    """C12 has not been weakened by any of this: no audit row, no action."""
    c, org = db

    def broken(action, **kw):
        return False

    with pytest.raises(EnterpriseGateError) as e:
        workflows.create_programme(c, org, 1, code="P9", name="Nine",
                                   sponsor_user_id=1, audit=broken)
    assert e.value.control == "C12"
    assert c.execute(
        "SELECT COUNT(*) FROM enterprise_programme_registry WHERE code='P9'"
    ).fetchone()[0] == 0
