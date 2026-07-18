"""The owner may issue ANY approval -- but not without the evidence.

OWNER DIRECTIVE (2026-07-13): "owner must have the authority to issue all approvals."

THE TRAP THIS CLOSES
--------------------
approve_gate ran two separate checks: the caller must hold the gate's named ROLE, and -- if
the programme has NAMED a holder for that post -- the caller must BE that person
(_require_named_post_holder, control C01).

The second one bites the owner specifically. A programme records its sponsor, director and
manager BY USER ID. So the moment the owner appoints a colleague as sponsor, the owner --
who holds `programme_sponsor` and owns the entire organisation -- can never sign the
Initiation gate (nor any other gate the sponsor holds) on that programme. The ministry's
principal is locked out of their own lifecycle by an appointment they themselves made, and
there is no way back short of re-appointing themselves.

WHAT THE OVERRIDE IS, AND WHAT IT IS NOT
----------------------------------------
It grants AUTHORITY, not EXEMPTION FROM EVIDENCE. The owner can sign any gate. The owner
cannot sign a gate whose required document does not exist -- gates.evaluate_gate still runs.
An owner who could skip the evidence would make every gate in the module decorative, and
"authority to approve" does not mean "authority to pretend".

And it is RECORDED. An override that left no trace would destroy the accountability the
named-post-holder rule exists to create; one that leaves a trace moves that accountability
onto the owner, which is where it belongs.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, constants, documents, gates, members, rbac, rev4_phases, tenancy,
    workflows,
)
from app.enterprise_programme.gates import EnterpriseGateError
from app.security import audit as audit_mod

OWNER = 1        # created the organisation
SPONSOR = 2      # the colleague the owner appointed as sponsor
OUTSIDER = 3     # holds programme_sponsor, but is not this programme's sponsor


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
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((OWNER, "olga"), (SPONSOR, "sam"), (OUTSIDER, "otto")):
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)")

    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    beneficiaries.ensure_schema(c)   # documents.programme_facts reads the site register
    documents.ensure_schema(c)
    for uid, name in ((OWNER, "olga"), (SPONSOR, "sam"), (OUTSIDER, "otto")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry", "Ghana")
    tenancy.add_member(c, org, SPONSOR, "programme_sponsor", OWNER)
    tenancy.add_member(c, org, OUTSIDER, "programme_sponsor", OWNER)
    c.commit()
    c.org = org
    yield c
    c.close()
    audit_mod.reset_schema_probe()


@pytest.fixture()
def programme(db):
    """A programme whose SPONSOR IS SOMEBODY ELSE. That is the whole point."""
    pid = workflows.create_programme(
        db, db.org, OWNER, code="GH-1", name="Ghana Schools",
        design_strategy="standard", sponsor_user_id=SPONSOR,      # <-- not the owner
        country="Ghana", audit=_audit(db),
        description="Solar for 100 schools.",
    )
    db.commit()
    return pid


def _approval_request(db, programme):
    """The Initiation gate's evidence, written by the app.

    Revision 4's R4G1_INITIATION reads exactly one document -- the Programme Approval Request
    (R4P1_D12). It is no longer the LAST Initiation button: revision xx201 appended the
    Programme Business Case (D13) and the Official Programme Plan (D14) on 2026-07-18. The
    gate still reads D12 and only D12 -- which deliverable opens a gate is set by
    DELIVERABLE_GATE_DOC_TYPE, not by position in the list.
    """
    return documents.generate_document(
        db, db.org, OWNER, programme,
        deliverable_code="R4P1_D12", use_ai=False, audit=_audit(db),
    )


# ------------------------------------------------------- the trap, and the way out

def test_the_owner_is_NOT_the_named_sponsor_and_the_gate_names_the_sponsor(db, programme):
    """The premise. Without it the rest of this file proves nothing."""
    assert gates.gate_authority("R4G1_INITIATION") == "programme_sponsor"
    named = db.execute(
        "SELECT sponsor_user_id FROM enterprise_programme_registry WHERE id=?",
        (programme,)).fetchone()[0]
    assert named == SPONSOR, "the programme's sponsor must be someone other than the owner"
    # ...and the owner really does hold tenant.admin, which is what rescues them.
    assert rbac.has_permission(db, db.org, OWNER, "tenant.admin")


def test_the_owner_CAN_sign_a_gate_whose_named_holder_is_somebody_else(db, programme):
    """The directive: "owner must have the authority to issue all approvals"."""
    _approval_request(db, programme)                       # the evidence exists

    workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", OWNER, audit=_audit(db))

    status = db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE tenant_id=? AND programme_id=? "
        "AND gate_code='R4G1_INITIATION'", (db.org, programme)).fetchone()[0]
    assert status == "Approved"


def test_the_override_is_RECORDED_as_an_override(db, programme):
    """An override with no trace would destroy the accountability it is bypassing."""
    _approval_request(db, programme)
    workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", OWNER, audit=_audit(db))

    # The approvals table must not claim the owner signed AS the sponsor. They are not.
    role = db.execute(
        "SELECT decided_by_role FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND subject_id='R4G1_INITIATION'",
        (db.org, programme)).fetchone()[0]
    assert role == "enterprise_owner", (
        "the approvals table says the owner signed as the sponsor, which is false"
    )

    row = db.execute(
        "SELECT details FROM audit_logs WHERE action='ENTERPRISE_GATE_APPROVED' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    details = json.loads(row[0])
    assert details["owner_override"] is True
    assert details["authority_required"] == "programme_sponsor"


def test_the_owner_signing_a_gate_they_LEGITIMATELY_hold_is_not_an_override(db):
    """An override flag that fires on every owner approval tells an auditor nothing.

    Here the owner IS the sponsor, so nothing is bypassed and the record must say so.
    """
    pid = workflows.create_programme(
        db, db.org, OWNER, code="GH-2", name="Owner is sponsor",
        design_strategy="standard", sponsor_user_id=OWNER, country="Ghana",
        audit=_audit(db), description="x")
    documents.generate_document(
        db, db.org, OWNER, pid,
        deliverable_code="R4P1_D12", use_ai=False, audit=_audit(db))

    workflows.approve_gate(db, db.org, pid, "R4G1_INITIATION", OWNER, audit=_audit(db))

    role = db.execute(
        "SELECT decided_by_role FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND subject_id='R4G1_INITIATION'",
        (db.org, pid)).fetchone()[0]
    assert role == "programme_sponsor", "a normal approval was mislabelled an override"

    details = json.loads(db.execute(
        "SELECT details FROM audit_logs WHERE action='ENTERPRISE_GATE_APPROVED' "
        "ORDER BY id DESC LIMIT 1").fetchone()[0])
    assert details["owner_override"] is False


# --------------------------------------- what the override must NOT do

def test_the_owner_still_CANNOT_sign_without_the_evidence(db, programme):
    """AUTHORITY, NOT EXEMPTION. This is the line that keeps the gates from being decorative.

    No approval request is generated here. The Initiation gate demands one. The owner owns
    the organisation, holds every role, and is rescued from the post-holder check -- and is
    still refused, because the document the gate requires does not exist.
    """
    with pytest.raises(EnterpriseGateError) as e:
        workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", OWNER, audit=_audit(db))
    assert "programme approval request" in str(e.value).lower()

    status = db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE tenant_id=? AND programme_id=? "
        "AND gate_code='R4G1_INITIATION'", (db.org, programme)).fetchone()[0]
    assert status != "Approved"


def test_a_NON_owner_still_cannot_sign_another_persons_gate(db, programme):
    """The control survives for everyone else. OUTSIDER holds programme_sponsor tenant-wide
    but is not THIS programme's sponsor -- C01 says they may not sign, and they may not."""
    _approval_request(db, programme)

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", OUTSIDER, audit=_audit(db))


def test_a_delegated_ORG_ADMIN_is_not_the_owner_and_cannot_override(db, programme):
    """CODEX HIGH, 2026-07-13. The override was first keyed to the `tenant.admin` PERMISSION.

    `org_admin` carries `tenant.admin` too. So every delegated administrator inherited the
    owner's C01 bypass -- and worse, the approvals table would have stamped their signature
    `enterprise_owner`, naming as owner a person who is not. The directive is "the OWNER
    must have the authority to issue all approvals", not "administrators may sign in other
    people's names".

    Dana is an org_admin. She is not the sponsor. She must be refused.
    """
    DANA = 4
    db.execute("INSERT INTO users (id, username) VALUES (?,?)", (DANA, "dana"))
    tenancy.get_or_create_personal_tenant(db, DANA, "dana")
    tenancy.add_member(db, db.org, DANA, "org_admin", OWNER)
    db.commit()

    # The premise: she really does hold the permission the override used to trust.
    assert rbac.has_permission(db, db.org, DANA, "tenant.admin")
    assert constants.OWNER_ROLE not in rbac.roles_for_user(db, db.org, DANA)

    _approval_request(db, programme)                       # the evidence is not the problem

    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", DANA, audit=_audit(db))

    status = db.execute(
        "SELECT status FROM enterprise_stage_gates WHERE tenant_id=? AND programme_id=? "
        "AND gate_code='R4G1_INITIATION'", (db.org, programme)).fetchone()[0]
    assert status != "Approved"


def test_an_org_admin_cannot_GRANT_THEMSELVES_ownership_to_get_the_override(db, programme):
    """CODEX HIGH (second order), 2026-07-13. Closing the front door left the back door open.

    Once the override keys off the OWNER ROLE rather than the `tenant.admin` permission, the
    next question is who can hand that role out. `members.grant()` is guarded by
    `tenant.admin` -- which `org_admin` holds -- and its assignable list was every role in
    ROLE_CODES. So a delegated administrator could simply grant THEMSELVES `enterprise_owner`
    and collect the override anyway. The escalation is a closed loop: the grant power is
    derived from ownership, so ownership must not be grantable.

    Ownership is conferred by CREATING the organisation, and by nothing else.
    """
    DANA = 5
    db.execute("INSERT INTO users (id, username) VALUES (?,?)", (DANA, "dana2"))
    tenancy.get_or_create_personal_tenant(db, DANA, "dana2")
    tenancy.add_member(db, db.org, DANA, "org_admin", OWNER)
    db.commit()

    # She really is an administrator -- this is not a permission failure.
    assert rbac.has_permission(db, db.org, DANA, "tenant.admin")

    # The screen does not even offer it...
    screen = members.overview(db, db.org, DANA)
    offered = {code for code, _label in screen["assignable_roles"]}
    assert constants.OWNER_ROLE not in offered

    # ...and the hand-rolled POST that ignores the screen is refused too.
    with pytest.raises(members.MemberError):
        members.grant(db, db.org, DANA, DANA, constants.OWNER_ROLE, audit=_audit(db))

    assert constants.OWNER_ROLE not in rbac.roles_for_user(db, db.org, DANA)

    # And so she still cannot sign the sponsor's gate.
    _approval_request(db, programme)
    with pytest.raises(rbac.EnterprisePermissionError):
        workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", DANA, audit=_audit(db))


def test_an_org_admin_cannot_STRIP_the_owner_of_ownership(db, programme):
    """SUPERVISOR, 2026-07-13. Making the role ungrantable made revoking it IRREVERSIBLE.

    Nothing in the app can put `enterprise_owner` back. So a revoke would let a delegated
    administrator permanently destroy the very authority the owner directive exists to
    grant -- repairable only by editing the database. Grant and revoke have to be symmetric.
    """
    DANA = 6
    db.execute("INSERT INTO users (id, username) VALUES (?,?)", (DANA, "dana3"))
    tenancy.get_or_create_personal_tenant(db, DANA, "dana3")
    tenancy.add_member(db, db.org, DANA, "org_admin", OWNER)
    db.commit()

    with pytest.raises(members.MemberError):
        members.revoke(db, db.org, DANA, OWNER, constants.OWNER_ROLE, audit=_audit(db))

    assert constants.OWNER_ROLE in rbac.roles_for_user(db, db.org, OWNER)
    # ...and the owner can still sign, which is the thing the strip would have destroyed.
    _approval_request(db, programme)
    workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", OWNER, audit=_audit(db))


def test_the_owner_role_is_still_conferred_by_CREATING_the_organisation(db):
    """The ban must not have broken the one path that legitimately confers ownership."""
    assert constants.OWNER_ROLE in rbac.roles_for_user(db, db.org, OWNER)
    assert constants.OWNER_ROLE in constants.ONBOARDING_OWNER_ROLES


def test_the_named_sponsor_can_still_sign_their_own_gate(db, programme):
    """The override must not have broken the ordinary path it was bolted onto."""
    _approval_request(db, programme)
    workflows.approve_gate(db, db.org, programme, "R4G1_INITIATION", SPONSOR, audit=_audit(db))

    role = db.execute(
        "SELECT decided_by_role FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND subject_id='R4G1_INITIATION'",
        (db.org, programme)).fetchone()[0]
    assert role == "programme_sponsor"


def test_the_owner_holds_every_gate_authority(db):
    """The bundle the owner is granted at onboarding must cover every gate they can reach.

    Under Revision 4 that is ALL FIVE of them: every gate asks only for its own phase's
    approval document, which the app itself writes, so nothing is deferred
    (rev4_phases.GATES_DEFERRED_BEYOND_RELEASE_1 is empty) and every gate is reachable.
    """
    assert not rev4_phases.GATES_DEFERRED_BEYOND_RELEASE_1, (
        "a deferred gate would mean this test no longer covers every gate the owner can reach"
    )
    owner_roles = set(constants.ONBOARDING_OWNER_ROLES)
    for code in rev4_phases.GATE_CODES:
        authority = gates.gate_authority(code)
        assert authority in owner_roles, (
            f"the onboarding owner does not hold {authority}, the authority for {code}"
        )
