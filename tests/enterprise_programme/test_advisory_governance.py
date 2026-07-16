"""ADVISORY GOVERNANCE — the shipped default. Nothing blocks. Everything is still recorded.

OWNER, 2026-07-14, over several messages:
  "the owner must be able to walk through without blocks"
  "the controls are not needed like that, user must be able to work at any phase"
  "the enterprise interface was made too large and governance is too tight"
  "reduce and loosen governance"
  "we don't need to do proving to any entity"

THE LINE THIS FILE DEFENDS
--------------------------
Loosening governance means the app stops standing in the operator's way. It does NOT mean the
app starts saying something untrue.

So: a gate can be approved with no evidence — and the approval row then SAYS "APPROVED WITHOUT
EVIDENCE". A programme can jump to any phase — and the transition SAYS it moved past an
unapproved gate. Nothing refuses; nothing lies.

That distinction is the entire value of what is left. An approval record in which an
unevidenced approval is indistinguishable from an evidenced one is not a loosened record — it
is a worthless one, and deleting it would at least have been honest.

STRICT MODE STILL EXISTS: one flag (`enterprise_governance_advisory` = '0'). The ~230 other
tests in this package describe it, and conftest.py runs them in it.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, documents, flags, tenancy, workflows,
)
from app.enterprise_programme.gates import EnterpriseGateError
from app.security import audit as audit_mod

pytestmark = pytest.mark.advisory        # opt out of conftest's strict default

OWNER = 1


class _Conn(sqlite3.Connection):
    org: str


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


@pytest.fixture()
def db():
    audit_mod.reset_schema_probe()
    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username) VALUES (1,'olga')")
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)")
    # The flag lives here. Absent -> advisory, which is the shipped default.
    c.execute("CREATE TABLE admin_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    for mod in (tenancy, workflows, beneficiaries, documents):
        mod.ensure_schema(c)
    tenancy.get_or_create_personal_tenant(c, OWNER, "olga")
    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry", "Ghana")
    c.commit()
    c.org = org
    yield c
    c.close()
    audit_mod.reset_schema_probe()


@pytest.fixture()
def prog(db):
    pid = workflows.create_programme(
        db, db.org, OWNER, code="GH-1", name="Ghana Schools",
        design_strategy="standard", sponsor_user_id=OWNER, country="Ghana",
        description="Rooftop solar for 100 rural schools.", audit=_audit(db))
    db.commit()
    return pid


def _strict(db):
    db.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
               (flags.FLAG_ADVISORY, "0"))
    db.commit()


# --- the flag itself ----------------------------------------------------------

def test_advisory_is_the_DEFAULT(db):
    """The owner asked for the blocks off. A switch nobody finds is not a fix."""
    assert flags.advisory_governance(db) is True


def test_a_missing_admin_settings_table_does_not_silently_re_impose_the_blocks(db):
    """Failing CLOSED here would put every block back with no way to see why."""
    db.execute("DROP TABLE admin_settings")
    assert flags.advisory_governance(db) is True


def test_strict_mode_still_exists_and_is_one_row(db):
    _strict(db)
    assert flags.advisory_governance(db) is False


# --- nothing blocks -----------------------------------------------------------

def test_a_gate_can_be_approved_with_NO_evidence(db, prog):
    """The Initiation gate demands a Programme Approval Request. There is none. It is
    approved anyway."""
    workflows.approve_gate(db, db.org, prog, "R4G1_INITIATION", OWNER, audit=_audit(db))

    status = db.execute(
        "SELECT status FROM enterprise_stage_gates "
        " WHERE tenant_id=? AND programme_id=? AND gate_code='R4G1_INITIATION'",
        (db.org, prog)).fetchone()[0]
    assert status == "Approved"


def test_the_programme_can_JUMP_to_any_phase(db, prog):
    """"user must be able to work at any phase". Initiation -> Closure, in one move.

    In strict mode this is illegal twice over: it is not in rev4_phases.TRANSITIONS (which
    only lets Initiation reach Planning), and Closure demands the Value gate on entry.
    """
    workflows.transition_programme_phase(
        db, db.org, prog, "R4_CLOSURE", user_id=OWNER, audit=_audit(db))

    phase = db.execute(
        "SELECT current_phase_code FROM enterprise_programme_registry "
        " WHERE tenant_id=? AND id=?", (db.org, prog)).fetchone()[0]
    assert phase == "R4_CLOSURE"


def test_a_phase_can_be_left_without_an_approved_sponsor(db, prog):
    """C01 used to hold the birth phase shut until a sponsor was approved. The sponsor is
    usually the LAST thing settled, not the first."""
    workflows.transition_programme_phase(
        db, db.org, prog, "R4_PLANNING", user_id=OWNER, audit=_audit(db))
    assert db.execute(
        "SELECT current_phase_code FROM enterprise_programme_registry WHERE id=?",
        (prog,)).fetchone()[0] == "R4_PLANNING"


# --- ...but nothing lies ------------------------------------------------------

def test_an_unevidenced_approval_SAYS_SO_on_the_approval_row(db, prog):
    """THE LINE. A funder reading this table must be able to tell the two kinds apart."""
    workflows.approve_gate(db, db.org, prog, "R4G1_INITIATION", OWNER, comment="Signed by me",
                           audit=_audit(db))

    comment = db.execute(
        "SELECT comment FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND subject_id='R4G1_INITIATION'",
        (db.org, prog)).fetchone()[0]
    assert "APPROVED WITHOUT EVIDENCE" in comment
    assert "Signed by me" in comment, "the operator's own comment was thrown away"


def test_an_unevidenced_approval_SAYS_SO_in_the_audit_trail(db, prog):
    workflows.approve_gate(db, db.org, prog, "R4G1_INITIATION", OWNER, audit=_audit(db))

    details = json.loads(db.execute(
        "SELECT details FROM audit_logs WHERE action='ENTERPRISE_GATE_APPROVED' "
        "ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert details["evidence_missing"], (
        "an approval made with no evidence left no trace of that — which makes every other "
        "row in this table unreadable too"
    )


def test_an_EVIDENCED_approval_is_NOT_smeared_with_the_warning(db, prog):
    """If the warning fired on every approval it would tell a reader nothing at all."""
    documents.generate_document(db, db.org, OWNER, prog, deliverable_code="R4P1_D12",
                                use_ai=False, audit=_audit(db))

    workflows.approve_gate(db, db.org, prog, "R4G1_INITIATION", OWNER, comment="All in order",
                           audit=_audit(db))

    comment = db.execute(
        "SELECT comment FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND subject_id='R4G1_INITIATION'",
        (db.org, prog)).fetchone()[0]
    assert "WITHOUT EVIDENCE" not in (comment or "")
    assert comment == "All in order"

    details = json.loads(db.execute(
        "SELECT details FROM audit_logs WHERE action='ENTERPRISE_GATE_APPROVED' "
        "ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert not details["evidence_missing"]


def test_jumping_past_an_unapproved_gate_is_RECORDED_on_the_transition(db, prog):
    workflows.transition_programme_phase(
        db, db.org, prog, "R4_CLOSURE", user_id=OWNER, audit=_audit(db))

    note = db.execute(
        "SELECT note FROM enterprise_workflow_transitions "
        " WHERE tenant_id=? AND programme_id=? ORDER BY id DESC LIMIT 1",
        (db.org, prog)).fetchone()[0]
    assert "unapproved gate" in (note or "").lower()
    # R4G4_VALUE is what Closure demands ON ENTRY, and it is the gate this jump routed
    # around -- naming it is the whole point of the record.
    assert "R4G4_VALUE" in (note or "")


# --- the limits of "any phase" ------------------------------------------------

def test_any_phase_is_not_any_STRING(db, prog):
    """A typo'd target would write a phase code no screen renders and no gate is seeded
    against — the programme would vanish from its own lifecycle."""
    with pytest.raises(EnterpriseGateError):
        workflows.transition_programme_phase(
            db, db.org, prog, "P99_NONSENSE", user_id=OWNER, audit=_audit(db))


def test_strict_mode_puts_the_blocks_back(db, prog):
    """The escape hatch has to actually work, or it is decoration."""
    _strict(db)

    with pytest.raises(EnterpriseGateError):
        workflows.approve_gate(db, db.org, prog, "R4G1_INITIATION", OWNER, audit=_audit(db))

    with pytest.raises(EnterpriseGateError):
        workflows.transition_programme_phase(
            db, db.org, prog, "R4_CLOSURE", user_id=OWNER, audit=_audit(db))
