"""Slice 2 -- the lifecycle spine: 16 phases, 14 gates, 15 controls.

WHAT THESE TESTS ARE FOR
------------------------
Doc 3's whole value is that certain things become IMPOSSIBLE. A test suite that only
proves the happy path leaves the prohibitions untested, and an untested prohibition is
a prohibition that quietly stops working. So most of what follows asserts a refusal:

  * an illegal phase jump is refused                     (the state machine is real)
  * leaving Concept without sponsor sign-off is refused  (control C01)
  * an AI recommendation cannot approve anything         (control C11)
  * a failed audit write rolls the action back           (control C12)
  * another tenant's programme is invisible              (control C13)
  * Gates 10-14 are blocked, not silently passable       (the Release 1 boundary)

The audit hook is injected in every test. In production it is
app.security.audit.write_audit_event; here it is a spy, which is also how the C12
rollback test forces a write failure.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import constants, gates, rbac, tenancy, workflows
from app.enterprise_programme.gates import EnterpriseGateError, GateBlockedError


class AuditSpy:
    """Stands in for write_audit_event. `ok=False` simulates a failed audit write."""

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.events: list[tuple[str, dict]] = []

    def __call__(self, action: str, **kw) -> bool:
        self.events.append((action, kw))
        return self.ok

    def actions(self) -> list[str]:
        return [a for a, _ in self.events]


@pytest.fixture()
def audit():
    return AuditSpy()


class _Conn(sqlite3.Connection):
    """A connection we can hang the test org id on.

    Plain sqlite3.Connection has no __dict__, so `c.org = ...` raises. Subclassing is
    the least intrusive way to keep every test reading `db.org` instead of unpacking a
    tuple in forty places.
    """

    org: str


@pytest.fixture()
def db():
    """In-memory SQLite with slice-1 + slice-2 schema, one org, and three users.

    alice   = enterprise_owner (created the org) -> programme.create/edit/approve
    bob     = programme_sponsor                  -> the only one who may approve Gate 1
    carol   = steering_committee                 -> the only one who may approve Gate 2
    dave    = programme_manager                  -> programme.edit but NOT programme.approve
    mallory = member of no organisation          -> the IDOR probe
    """
    users = ((1, "alice"), (2, "bob"), (3, "carol"), (4, "mallory"), (5, "dave"))

    c = sqlite3.connect(":memory:", factory=_Conn)
    # SQLite does not enforce foreign keys unless asked, per connection. Turn them ON here
    # so the tenant-scoped composite FKs are genuinely exercised: a fallback schema that is
    # LAXER than production is worse than none, because a cross-tenant defect would sail
    # through the suite and only Postgres would reject it -- in production.
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in users:
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, user_id INTEGER)")
    c.execute("INSERT INTO projects (id, user_id) VALUES (100, 1)")

    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)

    for uid, name in users:
        tenancy.get_or_create_personal_tenant(c, uid, name)
    org = tenancy.create_organisation(c, 1, "Ministry of Energy", "ministry", "Ghana")
    tenancy.add_member(c, org, 2, "programme_sponsor", invited_by_user_id=1)
    tenancy.add_member(c, org, 3, "steering_committee", invited_by_user_id=1)
    tenancy.add_member(c, org, 5, "programme_manager", invited_by_user_id=1)

    # Commit the baseline. Without this the whole fixture sits in an open transaction,
    # and any test that exercises rollback semantics would roll the fixture's own tables
    # away underneath itself.
    c.commit()

    c.org = org  # type: ignore[attr-defined]
    yield c
    c.close()


def _programme(db, audit, *, sponsor=2, code="GH-SCHOOLS-01") -> int:
    """A programme at Phase 1 / Concept, sponsored by bob.

    `code` is a parameter because (tenant_id, code) is unique -- a test that needs two
    programmes must name them apart.
    """
    return workflows.create_programme(
        db, db.org, 1, code=code, name="Ghana Schools Solar",
        design_strategy="standard", sponsor_user_id=sponsor, audit=audit,
    )


def _pass_gate_1(db, audit, pid):
    """Everything Gate 1 demands: a concept note, then the sponsor's approval."""
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note v1", audit=audit)
    workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)


# --- the state machine is real ----------------------------------------------


def test_programme_is_born_at_concept_with_all_phases_and_gates_seeded(db, audit):
    pid = _programme(db, audit)
    state = workflows.get_programme_state(db, db.org, pid)

    assert state["current_phase_code"] == "P01_CONCEPT"
    assert state["status"] == "Concept"
    assert state["gate_to_leave"] == "G01"

    phases = db.execute(
        "SELECT COUNT(*) FROM enterprise_programme_phase_states WHERE programme_id=?", (pid,)
    ).fetchone()[0]
    gate_rows = db.execute(
        "SELECT COUNT(*) FROM enterprise_stage_gates WHERE programme_id=?", (pid,)
    ).fetchone()[0]
    assert phases == 16, "all 16 phases are seeded up front, not lazily"
    assert gate_rows == 14, "a missing gate row would mean a check that never runs"


def test_illegal_transition_is_refused(db, audit):
    """Concept may go to Initiation. It may not leap to Construction."""
    pid = _programme(db, audit)
    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P11_CONSTRUCTION",
                                             user_id=1, audit=audit)
    assert "illegal transition" in str(e.value)
    assert workflows.get_programme_state(db, db.org, pid)["current_phase_code"] \
        == "P01_CONCEPT"


def test_status_is_derived_from_phase_never_typed(db, audit):
    """20 statuses and 16 phases are two views of one truth; the phase drives."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    state = workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P02_INITIATION"
    assert state["status"] == constants.PHASE_STATUS["P02_INITIATION"] == "Under Initiation"


def test_every_phase_has_transitions_and_a_status(db):
    """Drift between constants.PHASES and the state machine would strand a programme."""
    for code, _seq, _label in constants.PHASES:
        assert code in constants.TRANSITIONS, f"{code} has no legal transitions"
        assert code in constants.PHASE_STATUS, f"{code} maps to no programme status"
        for target in constants.TRANSITIONS[code]:
            assert (target in constants.PHASE_STATUS
                    or target in constants.PSEUDO_STATES), \
                f"{code} -> {target} is neither a phase nor a pseudo-state"


# --- control C01: no programme proceeds without an approved sponsor ---------


def test_cannot_leave_concept_until_the_sponsor_approves_gate_1(db, audit):
    """C01. The concept note alone is not authority -- the sponsor must sign."""
    pid = _programme(db, audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note v1", audit=audit)

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=1, audit=audit)
    assert e.value.control == "C01"

    _pass_gate_1(db, audit, pid)
    state = workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P02_INITIATION"


def test_gate_1_cannot_be_approved_without_a_named_sponsor(db, audit):
    """The gate's own predicate. This is what stops C01 being circular."""
    pid = workflows.create_programme(db, db.org, 1, code="NO-SPONSOR",
                                     name="Unsponsored", sponsor_user_id=None, audit=audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=audit)
    with pytest.raises(EnterpriseGateError) as e:
        workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)
    assert "must name a sponsor" in str(e.value)


def test_gate_1_cannot_be_approved_without_its_required_document(db, audit):
    pid = _programme(db, audit)
    with pytest.raises(EnterpriseGateError) as e:
        workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)
    assert "concept note" in str(e.value)


# --- gate authority: the RIGHT person signs, or nobody does -----------------


def test_gate_approval_requires_the_named_role_not_merely_the_permission(db, audit):
    """Alice is enterprise_owner and holds programme.approve. Gate 1 is still not hers.

    Doc 3 names an approving authority per gate. If any holder of programme.approve
    could sign any gate, the 14 named authorities would be decoration.
    """
    pid = _programme(db, audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=audit)
    assert rbac.has_permission(db, db.org, 1, "programme.approve")

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, pid, "G01", user_id=1, audit=audit)

    # ...and the sponsor, who holds no generic approve permission bar this one, can.
    workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)
    row = db.execute(
        "SELECT status, decided_by_user_id FROM enterprise_stage_gates "
        " WHERE programme_id=? AND gate_code='G01'", (pid,)
    ).fetchone()
    assert row == ("Approved", 2)


def test_the_sponsor_cannot_also_approve_the_steering_committees_gate(db, audit):
    """Bob signs Gate 1. Gate 2 belongs to the Steering Committee, and only to them."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="programme_charter",
                                title="Charter", audit=audit)

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, pid, "G02", user_id=2, audit=audit)

    workflows.approve_gate(db, db.org, pid, "G02", user_id=3, audit=audit)  # carol
    assert db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE programme_id=? AND gate_code='G02'",
        (pid,)
    ).fetchone()[0] == "Approved"


def test_advancing_requires_the_gate_that_closes_the_current_phase(db, audit):
    """Gate 2 guards the exit from Initiation, not the entry to it."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P03_NEEDS",
                                             user_id=1, audit=audit)
    assert e.value.control == "G02"


def test_rework_backwards_needs_no_gate(db, audit):
    """Gates guard progress, not retreat -- but the retreat is still recorded."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)

    state = workflows.transition_programme_phase(db, db.org, pid, "P01_CONCEPT",
                                                 user_id=1, note="charter inadequate",
                                                 audit=audit)
    assert state["current_phase_code"] == "P01_CONCEPT"
    row = db.execute(
        "SELECT from_phase_code, to_phase_code, note FROM enterprise_workflow_transitions "
        " WHERE programme_id=? ORDER BY id DESC LIMIT 1", (pid,)
    ).fetchone()
    assert row == ("P02_INITIATION", "P01_CONCEPT", "charter inadequate")


def test_double_approving_a_gate_is_a_no_op_not_a_second_record(db, audit):
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)

    n = db.execute(
        "SELECT COUNT(*) FROM enterprise_approvals "
        " WHERE programme_id=? AND subject_id='G01'", (pid,)
    ).fetchone()[0]
    assert n == 1, "a double-click must not produce a second approval record"


# --- control C11: no AI recommendation becomes an approval ------------------


def test_ai_recommendation_cannot_be_the_approver(db, audit):
    """C11. An AI recommendation is evidence. It is never the decision."""
    pid = _programme(db, audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=audit)

    with pytest.raises(EnterpriseGateError) as e:
        workflows.approve_gate(db, db.org, pid, "G01", user_id=None,
                               ai_recommendation_id=42, audit=audit)
    assert e.value.control == "C11"
    assert db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE programme_id=? AND gate_code='G01'",
        (pid,)
    ).fetchone()[0] == "Pending"


def test_ai_recommendation_may_be_attached_as_evidence_to_a_human_approval(db, audit):
    """The permitted use: a human signs, and the AI's input is recorded alongside."""
    pid = _programme(db, audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=audit)
    workflows.approve_gate(db, db.org, pid, "G01", user_id=2, ai_recommendation_id=42,
                           audit=audit)

    row = db.execute(
        "SELECT decided_by_user_id, ai_recommendation_id FROM enterprise_approvals "
        " WHERE programme_id=? AND subject_id='G01'", (pid,)
    ).fetchone()
    assert row == (2, 42), "human decides; AI is attached as supporting evidence"


# --- control C12: a material action with no audit trail did not happen ------


def test_transition_rolls_back_when_the_audit_write_fails(db, audit):
    """C12. write_audit_event is non-raising by contract; here that must not be silent.

    A gate approval that happened but left no trace is exactly the record an auditor
    asks for and we cannot produce. Losing the transition is recoverable; losing the
    evidence is not.
    """
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)

    broken = AuditSpy(ok=False)
    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=1, audit=broken)
    assert e.value.control == "C12"

    state = workflows.get_programme_state(db, db.org, pid)
    assert state["current_phase_code"] == "P01_CONCEPT", "the phase move must be rolled back"
    assert db.execute(
        "SELECT COUNT(*) FROM enterprise_workflow_transitions "
        " WHERE programme_id=? AND to_phase_code='P02_INITIATION'", (pid,)
    ).fetchone()[0] == 0, "no transition row may survive a failed audit"


def test_material_actions_are_audited(db, audit):
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)
    assert audit.actions() == [
        "ENTERPRISE_PROGRAMME_CREATED",
        "ENTERPRISE_DOCUMENT_REGISTERED",
        "ENTERPRISE_GATE_APPROVED",
        "ENTERPRISE_PHASE_TRANSITION",
    ]


# --- control C13: tenant scope (IDOR) ---------------------------------------


def test_another_tenants_programme_is_invisible(db, audit):
    """C13. Mallory is a member of no organisation but her own personal tenant.

    Note the error is the same one a NON-EXISTENT programme produces. Saying "that
    programme exists but you may not see it" would leak the existence of other
    organisations' programmes.
    """
    pid = _programme(db, audit)
    mallory_tenant = tenancy.personal_tenant_id(4)

    with pytest.raises(EnterpriseGateError) as e:
        workflows.get_programme_state(db, mallory_tenant, pid)
    assert e.value.control == "C13"

    with pytest.raises(EnterpriseGateError):
        workflows.get_programme_state(db, mallory_tenant, 999999)  # same error, no leak


def test_a_member_without_edit_permission_cannot_transition(db, audit):
    """Bob is the sponsor; sponsoring is not editing."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    assert not rbac.has_permission(db, db.org, 2, "programme.edit")

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=2, audit=audit)


# --- holds are not amnesia --------------------------------------------------


def test_hold_remembers_its_phase_and_resume_returns_exactly_there(db, audit):
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)

    workflows.transition_programme_phase(db, db.org, pid, "ON_HOLD", user_id=1,
                                         note="funding review", audit=audit)
    held = workflows.get_programme_state(db, db.org, pid)
    assert held["status"] == "On Hold"
    assert held["held_from_phase_code"] == "P02_INITIATION"
    assert held["allowed_transitions"] == ["RESUME", "CANCELLED"]

    resumed = workflows.resume_from_hold(db, db.org, pid, user_id=1, audit=audit)
    assert resumed["current_phase_code"] == "P02_INITIATION"
    assert resumed["status"] == "Under Initiation"
    assert resumed["held_from_phase_code"] is None


def test_a_held_programme_cannot_simply_move_on(db, audit):
    """Resuming needs an approval. A plain transition must not be the way around that."""
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "ON_HOLD", user_id=1, audit=audit)

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=1, audit=audit)
    assert "must be resumed" in str(e.value)


def test_resume_requires_approve_permission_not_merely_edit(db, audit):
    """Doc 3: coming back from a hold takes an approval record.

    Lifting a hold is a strictly higher bar than moving through phases. dave is a
    Programme Manager: he holds programme.edit, so he can drive the lifecycle -- and he
    can even put the programme ON_HOLD. He does NOT hold programme.approve, so he cannot
    lift the hold he just applied. That asymmetry is the entire value of a hold: it
    escalates, rather than being a speed bump the same person steps over.
    """
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)

    assert rbac.has_permission(db, db.org, 5, "programme.edit")            # dave can move it
    assert not rbac.has_permission(db, db.org, 5, "programme.approve")     # but not un-hold it
    workflows.transition_programme_phase(db, db.org, pid, "ON_HOLD", user_id=5, audit=audit)

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.resume_from_hold(db, db.org, pid, user_id=5, audit=audit)

    workflows.resume_from_hold(db, db.org, pid, user_id=3, audit=audit)  # carol: steering cttee
    assert workflows.get_programme_state(db, db.org, pid)["status"] == "Concept"
    assert db.execute(
        "SELECT COUNT(*) FROM enterprise_approvals "
        " WHERE programme_id=? AND approval_type='resume_from_hold'", (pid,)
    ).fetchone()[0] == 1


def test_a_cancelled_programme_can_only_be_archived(db, audit):
    """A terminal programme has exactly one move left: out of the active register.

    Archived is one of doc 3's 20 programme statuses, and this is the only way to reach
    it -- before, it was declared vocabulary that no programme could ever attain.
    """
    pid = _programme(db, audit)
    workflows.transition_programme_phase(db, db.org, pid, "CANCELLED", user_id=1,
                                         note="policy change", audit=audit)
    state = workflows.get_programme_state(db, db.org, pid)
    assert state["status"] == "Cancelled"
    assert state["allowed_transitions"] == ["ARCHIVED"]

    with pytest.raises(EnterpriseGateError, match="only remaining move is ARCHIVED"):
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=1, audit=audit)

    state = workflows.transition_programme_phase(db, db.org, pid, "ARCHIVED", user_id=1,
                                                 audit=audit)
    assert state["status"] == "Archived"
    assert state["allowed_transitions"] == [], "an archived programme is truly finished"

    with pytest.raises(EnterpriseGateError, match="no further transitions"):
        workflows.transition_programme_phase(db, db.org, pid, "ARCHIVED", user_id=1,
                                             audit=audit)


# --- the Release 1 boundary is honest ---------------------------------------


def test_gates_10_to_14_are_blocked_not_silently_passable(db, audit):
    """Release 1 delivers the lifecycle through Gate 9.

    The later gates are seeded and visible, and they FAIL CLOSED. A gate that quietly
    passed because its evidence table does not exist yet would be worse than no gate.
    """
    pid = _programme(db, audit)
    for gate_code in sorted(constants.GATES_DEFERRED_BEYOND_RELEASE_1):
        with pytest.raises(GateBlockedError):
            gates.evaluate_gate(db, db.org, pid, gate_code)


def test_every_control_in_the_spec_has_a_live_guard(db):
    """A control cannot be dropped by deleting its guard -- this is what notices."""
    for code, _requirement, guard_name in constants.CONTROLS:
        assert code in gates.CONTROL_GUARDS, f"{code} has no guard"
        assert hasattr(gates, guard_name), f"{code}'s guard {guard_name}() does not exist"
        assert gates.CONTROL_GUARDS[code] is getattr(gates, guard_name)


def test_not_yet_shipped_controls_fail_closed(db, audit):
    """The guards for later slices refuse. They do not pass-through."""
    pid = _programme(db, audit)
    with pytest.raises(GateBlockedError):
        gates.require_qualified_beneficiary(db, db.org, 1)      # C02, slice 6
    with pytest.raises(GateBlockedError):
        gates.require_approved_template_version(db, db.org, 1)  # C03, slice 4
    with pytest.raises(GateBlockedError):
        gates.require_approved_boq_snapshot(db, db.org, [1])    # C05, slice 8
    assert gates.control_summary()[0]["enforced_now"] is True   # C01 is live now


def test_control_summary_does_not_overstate_what_is_enforced(db):
    summary = {row["code"]: row["enforced_now"] for row in gates.control_summary()}
    assert summary["C01"] is True and summary["C11"] is True
    assert summary["C12"] is True and summary["C13"] is True
    assert summary["C03"] is False, "the template control is not enforceable until slice 4"
    assert len(summary) == 15


# --- Codex round-4 regressions: routing around a gate ------------------------


def _approve_gates(db, pid, *codes):
    """Force gates approved directly, to set up a phase deep in the lifecycle."""
    for code in codes:
        db.execute("UPDATE enterprise_stage_gates SET status='Approved' "
                   " WHERE programme_id=? AND gate_code=?", (pid, code))


def test_mobilisation_cannot_be_reached_by_routing_around_funding_and_contract(db, audit):
    """Codex round-4 HIGH -- the deepest bug in this slice.

    Doc 3 permits P06 -> P09 (engineering runs in parallel with funding and tendering) and
    P09 -> P10. Chain them, and with an exit-only gate rule a programme reached MOBILISATION
    having approved only G06 and G09: no financial close (G07), no contract award (G08). It
    would be mobilising contractors it never hired, with money it never raised.

    The fix is not per-edge patching -- the hole belongs to the DESTINATION, not the route.
    P10 now declares its entry requirements, and they hold no matter how you arrive.
    """
    pid = _programme(db, audit)
    _approve_gates(db, pid, "G01", "G06")  # sponsor signed; templates standardised
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P06_TEMPLATES', "
               "       status='Approved' WHERE id=?", (pid,))

    # The legitimate parallel-engineering skip still works.
    workflows.transition_programme_phase(db, db.org, pid, "P09_ENGINEERING",
                                         user_id=1, audit=audit)
    _approve_gates(db, pid, "G09")  # design approved

    # ...but mobilisation is refused: no funding, no contract.
    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P10_MOBILISATION",
                                             user_id=1, audit=audit)
    assert e.value.control == "G08", "cannot mobilise without a contract award"

    _approve_gates(db, pid, "G07", "G08")
    state = workflows.transition_programme_phase(db, db.org, pid, "P10_MOBILISATION",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P10_MOBILISATION"


def test_rework_backwards_into_procurement_still_needs_funding(db, audit):
    """The same hole in reverse: P09 -> P08 is a backward edge, so an exit-only rule
    checked nothing and let a programme enter Procurement without G07 (financial close).
    Entry requirements apply to backward moves too.
    """
    pid = _programme(db, audit)
    _approve_gates(db, pid, "G01", "G06")
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P09_ENGINEERING', "
               "       status='Under Design' WHERE id=?", (pid,))

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P08_PROCUREMENT",
                                             user_id=1, audit=audit)
    assert e.value.control == "G07", "no major procurement before financial close"


def test_a_contract_cannot_be_awarded_before_financial_close(db, audit):
    """The dependency belongs on the GATE, not on every edge that might reach it.

    G08 (Contract Award) requires G07 (Financial Close). This is what makes the entry rule
    above transitively enforce funding: mobilisation needs G08, and G08 needs G07 -- so no
    path to mobilisation can exist without funding, whatever route is taken.
    """
    pid = _programme(db, audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="signed_contract",
                                title="EPC Contract", audit=audit)

    with pytest.raises(EnterpriseGateError) as e:
        gates.evaluate_gate(db, db.org, pid, "G08")
    assert "G07 must be approved before G08" in str(e.value)

    _approve_gates(db, pid, "G07")
    gates.evaluate_gate(db, db.org, pid, "G08")  # now permitted


def test_the_rebuild_does_not_collide_with_the_live_024_tables(db):
    """Codex round-4 HIGH. Migration 024 is APPLIED TO LIVE and owns `enterprise_programmes`
    and `enterprise_programme_phases`. CREATE TABLE IF NOT EXISTS would have silently
    skipped them, left 024's old shape in place, and the first composite FK would have
    killed the migration mid-apply -- a repeat of how 024's own first apply died.

    The rebuild therefore uses new names and never touches a 024 table.
    """
    tables = {
        row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "enterprise_programme_registry" in tables
    assert "enterprise_programme_phase_states" in tables
    assert "enterprise_programmes" not in tables, \
        "the rebuild must not create a table that migration 024 already owns on live"
    assert "enterprise_programme_phases" not in tables

    sql = open("migrations/026_enterprise_programme_lifecycle.sql", encoding="utf-8").read()
    body = "\n".join(ln for ln in sql.splitlines() if not ln.strip().startswith("--"))
    for owned_by_024 in ("enterprise_programmes", "enterprise_programme_phases",
                         "enterprise_organisations", "enterprise_memberships",
                         "enterprise_beneficiaries", "enterprise_programme_jobs"):
        assert f"CREATE TABLE IF NOT EXISTS {owned_by_024}\n" not in body + "\n", \
            f"026 must not create {owned_by_024} -- migration 024 owns it on live"


def test_the_database_itself_rejects_a_cross_tenant_child_row(db, audit):
    """Codex round-5 MEDIUM. The service layer never builds such a row -- but "the app is
    careful" is not a database constraint.

    Every child carries tenant_id AND programme_id. With a bare FK on programme_id alone,
    the database would accept tenant A's tenant_id beside tenant B's programme_id, and RLS
    (which filters on the child's OWN tenant_id) would then hand tenant B's child row to
    tenant A. The composite FK makes that impossible in the database, not merely unlikely
    in the service.
    """
    pid = _programme(db, audit)  # belongs to the org
    stranger_tenant = tenancy.personal_tenant_id(4)  # mallory's personal tenant

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO enterprise_documents "
            "(tenant_id, programme_id, doc_type, title) VALUES (?,?,?,?)",
            (stranger_tenant, pid, "concept_note", "smuggled in"),
        )
    db.rollback()


def test_a_cross_tenant_write_is_404_shaped_even_without_permission(db, audit):
    """Codex slice-3 MEDIUM. C13 must be decided BEFORE the permission check.

    If we authorised first, a stranger POSTing at another tenant's programme would get
    EnterprisePermissionError -> 403 -- and a 403 CONFIRMS the programme exists, which is
    exactly the leak C13 forbids. "Does it exist for you" is a strictly earlier question
    than "may you do this", so the answer must always be the C13 one.
    """
    pid = _programme(db, audit)
    stranger_tenant = tenancy.personal_tenant_id(4)  # mallory: no membership, no permissions

    for call in (
        lambda: workflows.transition_programme_phase(db, stranger_tenant, pid,
                                                     "P02_INITIATION", user_id=4, audit=audit),
        lambda: workflows.register_document(db, stranger_tenant, 4, pid,
                                            doc_type="concept_note", title="x", audit=audit),
        lambda: workflows.resume_from_hold(db, stranger_tenant, pid, user_id=4, audit=audit),
        lambda: workflows.approve_gate(db, stranger_tenant, pid, "G01", user_id=4, audit=audit),
        lambda: workflows.approve_expansion(db, stranger_tenant, pid, user_id=4, audit=audit),
    ):
        with pytest.raises(EnterpriseGateError) as e:
            call()
        assert e.value.control == "C13", (
            "a cross-tenant write must answer 'no such programme' (404), never "
            "'you may not' (403) -- the latter confirms it exists"
        )


# --- Supervisor review regressions ------------------------------------------


def test_only_the_NAMED_sponsor_may_approve_gate_1(db, audit):
    """Supervisor HIGH -- and the one the reviewer chain nearly shipped.

    Holding the programme_sponsor role is NECESSARY but NOT SUFFICIENT. The programme
    names Bob as its sponsor; Erin also holds programme_sponsor tenant-wide (she sponsors
    other programmes). Erin must not be able to sign Bob's Gate 1 -- otherwise
    sponsor_user_id is decoration and control C01 ("no programme proceeds without an
    approved sponsor") is satisfied by an approval the actual sponsor never gave.
    """
    tenancy.get_or_create_personal_tenant(db, 6, "erin")
    tenancy.add_member(db, db.org, 6, "programme_sponsor", invited_by_user_id=1)

    pid = _programme(db, audit, sponsor=2)  # bob is THE sponsor
    workflows.register_document(db, db.org, 1, pid, doc_type="concept_note",
                                title="Concept Note", audit=audit)

    assert "programme_sponsor" in rbac.roles_for_user(db, db.org, 6), "Erin holds the role"
    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, pid, "G01", user_id=6, audit=audit)
    assert db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE programme_id=? AND gate_code='G01'",
        (pid,)
    ).fetchone()[0] == "Pending"

    workflows.approve_gate(db, db.org, pid, "G01", user_id=2, audit=audit)  # the real sponsor
    assert db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE programme_id=? AND gate_code='G01'",
        (pid,)
    ).fetchone()[0] == "Approved"


def test_an_unfilled_post_falls_back_to_the_role_check(db, audit):
    """Gate 2's authority (steering_committee) is a body, not a named post, so any holder
    signs. Only the three named posts (sponsor/director/manager) are identity-checked.
    """
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)
    workflows.register_document(db, db.org, 1, pid, doc_type="programme_charter",
                                title="Charter", audit=audit)

    workflows.approve_gate(db, db.org, pid, "G02", user_id=3, audit=audit)  # carol
    assert db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE programme_id=? AND gate_code='G02'",
        (pid,)
    ).fetchone()[0] == "Approved"


def test_a_sponsor_from_outside_the_organisation_is_rejected(db, audit):
    """Supervisor finding. A stranger cannot be named sponsor.

    Gate 1's predicate only checks the column is non-NULL, so without this a programme
    could name a user from another tenant (or one who does not exist) and still look
    correctly sponsored.
    """
    with pytest.raises(ValueError, match="not an active member"):
        workflows.create_programme(db, db.org, 1, code="OUTSIDER", name="Bad Sponsor",
                                   sponsor_user_id=4, audit=audit)  # mallory: not a member
    with pytest.raises(ValueError, match="not an active member"):
        workflows.create_programme(db, db.org, 1, code="GHOST", name="Ghost Sponsor",
                                   sponsor_user_id=99999, audit=audit)  # no such user


def test_control_summary_tracks_the_guards_not_a_hand_kept_list(db):
    """Supervisor finding. enforced_now is derived from the guard's own @_deferred marker,
    so the compliance dashboard cannot claim a control is enforced when it is not.
    """
    summary = {row["code"]: row["enforced_now"] for row in gates.control_summary()}
    for code, guard in gates.CONTROL_GUARDS.items():
        assert summary[code] is not getattr(guard, "is_deferred", False), \
            f"{code}: the dashboard disagrees with the guard itself"


# --- Codex slice-2 review regressions ---------------------------------------


def test_expansion_exits_require_an_expansion_approval(db, audit):
    """Codex MEDIUM. P16's legal exits both point BACKWARD (clone to Concept, or re-plan
    from Structuring), so the sequence comparison classes them as rework and would have
    let a Programme Manager spend the next tranche on `programme.edit` alone.

    Doc 3 gates P16's exit on an expansion approval record. This is that record.
    """
    pid = _programme(db, audit)
    db.execute(
        "UPDATE enterprise_programme_registry SET current_phase_code='P16_EXPANSION', "
        "       status='Approved' WHERE id=?", (pid,)
    )

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P01_CONCEPT",
                                             user_id=1, audit=audit)
    assert e.value.control == "P16"

    # dave (programme_manager) may edit, but expansion needs programme.approve.
    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_expansion(db, db.org, pid, user_id=5, audit=audit)

    workflows.approve_expansion(db, db.org, pid, user_id=3, audit=audit)  # steering cttee
    state = workflows.transition_programme_phase(db, db.org, pid, "P01_CONCEPT",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P01_CONCEPT"


def test_expansion_cannot_be_approved_by_an_ai_recommendation(db, audit):
    """C11 again, on the most expensive decision in the lifecycle."""
    pid = _programme(db, audit)
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P16_EXPANSION' "
               " WHERE id=?", (pid,))
    with pytest.raises(EnterpriseGateError) as e:
        workflows.approve_expansion(db, db.org, pid, user_id=None,
                                    ai_recommendation_id=7, audit=audit)
    assert e.value.control == "C11"


def test_service_does_not_commit_or_destroy_the_callers_open_transaction(db, audit):
    """Codex HIGH. A route may already have written on this connection before calling us.

    Committing it would publish the route's half-finished work; rolling it back would
    destroy it. We must do neither -- so when a transaction is already open we take a
    SAVEPOINT and leave the commit to whoever owns it.
    """
    db.execute("INSERT INTO projects (id, user_id) VALUES (777, 1)")  # caller's own work
    assert db.in_transaction, "precondition: the caller has an open transaction"

    pid = _programme(db, audit)  # our service runs as a guest inside it
    assert db.in_transaction, "the service must not have committed the caller's transaction"

    db.rollback()  # the CALLER decides -- and takes our programme with it
    assert db.execute("SELECT COUNT(*) FROM projects WHERE id=777").fetchone()[0] == 0
    assert db.execute(
        "SELECT COUNT(*) FROM enterprise_programme_registry WHERE id=?", (pid,)
    ).fetchone()[0] == 0


def test_failed_audit_inside_a_caller_transaction_rolls_back_only_our_work(db, audit):
    """The other half of the same finding: our rollback must not take the caller's work.

    C12 still has to hold (our writes vanish), but the route's unrelated row survives.
    """
    db.execute("INSERT INTO projects (id, user_id) VALUES (888, 1)")
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)

    broken = AuditSpy(ok=False)
    with pytest.raises(EnterpriseGateError):
        workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                             user_id=1, audit=broken)

    assert workflows.get_programme_state(db, db.org, pid)["current_phase_code"] \
        == "P01_CONCEPT", "C12: our transition must be undone"
    assert db.execute("SELECT COUNT(*) FROM projects WHERE id=888").fetchone()[0] == 1, \
        "the caller's unrelated work must survive our rollback"


def test_inserted_id_never_guesses(db, audit):
    """Codex HIGH. The old MAX(id) fallback read a GLOBAL maximum, not this session's
    insert: two concurrent creates would race and seed one programme's 16 phase rows onto
    the other programme -- in the other tenant. There is now no guessing path at all.
    """
    class _NoLastRowId:
        """A cursor that, like raw psycopg2, exposes no usable lastrowid."""
        lastrowid = None

    with pytest.raises(RuntimeError, match="refusing to guess"):
        workflows._inserted_id(db, _NoLastRowId())


def test_two_programmes_get_their_own_phase_and_gate_rows(db, audit):
    """The consequence the MAX(id) race would have produced, asserted directly."""
    p1 = workflows.create_programme(db, db.org, 1, code="P-1", name="One",
                                    sponsor_user_id=2, audit=audit)
    p2 = workflows.create_programme(db, db.org, 1, code="P-2", name="Two",
                                    sponsor_user_id=2, audit=audit)
    assert p1 != p2
    for pid in (p1, p2):
        assert db.execute(
            "SELECT COUNT(*) FROM enterprise_programme_phase_states WHERE programme_id=?", (pid,)
        ).fetchone()[0] == 16
        assert db.execute(
            "SELECT COUNT(*) FROM enterprise_stage_gates WHERE programme_id=?", (pid,)
        ).fetchone()[0] == 14


def test_sqlite_fallback_mirrors_the_postgres_migration(db):
    """Codex LOW. A fallback that is not a mirror lets the suite pass against a schema
    production does not have. Every table migration 026 creates must exist here.
    """
    created = {
        row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table in (
        "enterprise_programme_registry", "enterprise_programme_phase_states", "enterprise_stage_gates",
        "enterprise_workflow_transitions", "enterprise_approvals", "enterprise_documents",
        "enterprise_geographic_areas", "enterprise_sites",
        "enterprise_programme_templates", "enterprise_template_versions",
    ):
        assert table in created, f"migration 026 creates {table}; the fallback does not"

    cols = {r[1] for r in db.execute("PRAGMA table_info(enterprise_programme_registry)").fetchall()}
    assert {"target_capacity_kwp", "target_beneficiaries"} <= cols

    indexes = {
        row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    for ix in ("ix_ent_programme_tenant_created", "ix_ent_gate_status"):
        assert ix in indexes, f"migration 026 creates index {ix}; the fallback does not"


def test_autocommit_connection_is_refused_rather_than_silently_voiding_c12(db, audit):
    """Codex round-2 HIGH. Under autocommit a rollback undoes nothing.

    C12 would quietly become a lie: the gate approval would stand with no audit row
    behind it. No connection this app hands out is in autocommit today, so this guard is
    about the change that would introduce one -- it must stop, not ship unauditable
    approvals.
    """
    db.isolation_level = None  # sqlite3's autocommit
    try:
        with pytest.raises(RuntimeError, match="transactional connection"):
            workflows.create_programme(db, db.org, 1, code="AC-1", name="Autocommit",
                                       sponsor_user_id=2, audit=audit)
    finally:
        db.isolation_level = ""


def test_a_forward_skip_cannot_route_around_a_gate(db, audit):
    """Codex round-3 HIGH -- the worst bug found in this slice.

    P08 -> P10 is a legal forward SKIP over Detailed Engineering (P09). Checking only
    "the gate that closes the phase we are leaving" meant a programme could award a
    contract (G08), jump straight to Mobilisation, and go on to build with NO design ever
    approved -- control C04 defeated not by a missing check but by a routing choice. The
    skip edge must satisfy G09 too.
    """
    pid = _programme(db, audit)
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P08_PROCUREMENT', "
               "       status='Procurement Planning' WHERE id=?", (pid,))
    # Sponsor signed G01 (C01), and the contract gate G08 is approved.
    for gate in ("G01", "G08"):
        db.execute("UPDATE enterprise_stage_gates SET status='Approved' "
                   " WHERE programme_id=? AND gate_code=?", (pid, gate))

    with pytest.raises(EnterpriseGateError) as e:
        workflows.transition_programme_phase(db, db.org, pid, "P10_MOBILISATION",
                                             user_id=1, audit=audit)
    assert e.value.control == "G09", "mobilisation must not skip Design Approval"

    # With the design approved, the same skip is legitimate.
    db.execute("UPDATE enterprise_stage_gates SET status='Approved' "
               " WHERE programme_id=? AND gate_code='G09'", (pid,))
    state = workflows.transition_programme_phase(db, db.org, pid, "P10_MOBILISATION",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P10_MOBILISATION"


def test_the_intentional_skip_past_funding_still_works(db, audit):
    """The other skip edge, P06 -> P09, is deliberate: detailed engineering routinely runs
    in parallel with funding close and tendering. It needs G06 and nothing more.
    """
    pid = _programme(db, audit)
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P06_TEMPLATES', "
               "       status='Approved' WHERE id=?", (pid,))
    for gate in ("G01", "G06"):
        db.execute("UPDATE enterprise_stage_gates SET status='Approved' "
                   " WHERE programme_id=? AND gate_code=?", (pid, gate))

    state = workflows.transition_programme_phase(db, db.org, pid, "P09_ENGINEERING",
                                                 user_id=1, audit=audit)
    assert state["current_phase_code"] == "P09_ENGINEERING", \
        "engineering may start before funding closes (G07/G08 gate their own exits)"


def test_a_held_programme_can_still_be_cancelled(db, audit):
    """Codex round-3 MEDIUM. allowed_transitions() advertised CANCELLED for a held
    programme, but the service refused every move -- so a programme held from Needs
    Assessment (whose phase has no CANCELLED edge of its own) could never be cancelled at
    all. The dropdown and the server now agree.
    """
    pid = _programme(db, audit)
    _pass_gate_1(db, audit, pid)
    workflows.transition_programme_phase(db, db.org, pid, "P02_INITIATION",
                                         user_id=1, audit=audit)
    workflows.transition_programme_phase(db, db.org, pid, "ON_HOLD", user_id=1,
                                         note="budget freeze", audit=audit)

    state = workflows.get_programme_state(db, db.org, pid)
    assert "CANCELLED" in state["allowed_transitions"]

    state = workflows.transition_programme_phase(db, db.org, pid, "CANCELLED", user_id=1,
                                                 note="cancelled during freeze", audit=audit)
    assert state["status"] == "Cancelled"

    # ...but a held programme still cannot simply carry on without an approved resume.
    pid2 = _programme(db, audit, code="GH-SCHOOLS-02")
    _pass_gate_1(db, audit, pid2)
    workflows.transition_programme_phase(db, db.org, pid2, "ON_HOLD", user_id=1, audit=audit)
    with pytest.raises(EnterpriseGateError, match="must be resumed"):
        workflows.transition_programme_phase(db, db.org, pid2, "P02_INITIATION",
                                             user_id=1, audit=audit)


def test_closing_from_expansion_does_not_need_an_expansion_approval(db, audit):
    """A reviewer flagged P16 -> CLOSED as an approval bypass. It is not, and this test
    is here to stop that "fix" being applied later.

    The expansion approval authorises spending the NEXT tranche -- cloning the programme
    to a fresh Concept, or re-planning from Structuring. Closing is the opposite decision:
    the choice NOT to expand. Requiring an approval-to-expand before you may stop
    expanding would make winding a programme down harder than continuing it.

    Contrast with test_expansion_exits_require_an_expansion_approval, which proves the two
    exits that DO spend money are gated.
    """
    pid = _programme(db, audit)
    db.execute("UPDATE enterprise_programme_registry SET current_phase_code='P16_EXPANSION', "
               "       status='Approved' WHERE id=?", (pid,))

    assert db.execute(
        "SELECT COUNT(*) FROM enterprise_approvals "
        " WHERE programme_id=? AND approval_type='expansion'", (pid,)
    ).fetchone()[0] == 0, "precondition: no expansion has been approved"

    state = workflows.transition_programme_phase(db, db.org, pid, "CLOSED", user_id=1,
                                                 note="benefits realised; not replicating",
                                                 audit=audit)
    assert state["status"] == "Closed"
    assert state["allowed_transitions"] == ["ARCHIVED"]
