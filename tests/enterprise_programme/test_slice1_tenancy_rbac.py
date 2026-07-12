"""Slice 1 -- enterprise tenancy + RBAC.

These tests exist to prove the two things that would be catastrophic to get wrong:

  1. The tenancy overlay does NOT disturb existing single-user project ownership.
     (test_personal_tenant_id_matches_sql_hash, test_no_writes_to_projects_tables)
  2. A crafted tenant id cannot read another organisation's data.
     (test_resolve_active_tenant_rejects_non_member -- the IDOR case)

Everything else here guards the vocabularies the whole state machine is built on.
"""

from __future__ import annotations

import hashlib
import sqlite3
import uuid

import pytest

from app.enterprise_programme import constants, rbac, tenancy


@pytest.fixture()
def db():
    """In-memory SQLite with the slice-1 schema and two users."""
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username, email) VALUES (1,'alice','a@x.com')")
    c.execute("INSERT INTO users (id, username, email) VALUES (2,'bob','b@x.com')")
    # The real app's project tables, so we can prove we never write to them.
    c.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY, user_id INTEGER)")
    c.execute("INSERT INTO projects (id, user_id) VALUES (100, 1)")
    tenancy.ensure_schema(c)
    yield c
    c.close()


# --- safety property 1: existing ownership is untouched ----------------------

def test_personal_tenant_id_matches_sql_hash():
    """Python and the SQL backfill must derive the SAME personal tenant id.

    If these ever diverge, migration 025 and the running app would each create their
    own personal tenant for the same user, and the user would silently lose access to
    whichever one they were not currently resolving to.
    """
    expected = str(uuid.UUID(hashlib.md5(b"solarpro-tenant-v1:7").hexdigest()))
    assert tenancy.personal_tenant_id(7) == expected


def test_no_writes_to_projects_tables(db):
    """The tenancy overlay must never touch project ownership."""
    before = db.execute("SELECT id, user_id FROM projects").fetchall()

    tenancy.get_or_create_personal_tenant(db, 1, "alice", "a@x.com")
    tenancy.create_organisation(db, 1, "Ministry of Energy", "ministry", "Ghana")

    after = db.execute("SELECT id, user_id FROM projects").fetchall()
    assert before == after, "enterprise tenancy must not modify project ownership"


# --- safety property 2: cross-tenant access is denied (IDOR) -----------------

def test_resolve_active_tenant_rejects_non_member(db):
    """A tenant id from the client is hostile input until membership is proven.

    Bob asks to act inside Alice's organisation by passing its id. He is not a
    member, so the request must fall back to his own personal tenant -- never Alice's.
    """
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    alice_org = tenancy.create_organisation(db, 1, "Ghana Education Service", "government")
    bob_personal = tenancy.get_or_create_personal_tenant(db, 2, "bob")

    resolved = tenancy.resolve_active_tenant(db, user_id=2, requested_tenant_id=alice_org)

    assert resolved != alice_org, "cross-tenant IDOR: Bob must not act in Alice's org"
    assert resolved == bob_personal


def test_resolve_active_tenant_honours_real_membership(db):
    """The same path must still work for a genuine member."""
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Volta River Authority", "utility")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    tenancy.add_member(db, org, user_id=2, role_code="programme_manager", invited_by_user_id=1)

    assert tenancy.resolve_active_tenant(db, 2, org) == org


# --- tenancy basics ---------------------------------------------------------

def test_personal_tenant_creation_is_idempotent(db):
    """Double-calling must not produce two personal tenants for one user."""
    a = tenancy.get_or_create_personal_tenant(db, 1, "alice")
    b = tenancy.get_or_create_personal_tenant(db, 1, "alice")
    assert a == b
    n = db.execute(
        "SELECT COUNT(*) FROM enterprise_tenants WHERE legacy_user_id=1"
    ).fetchone()[0]
    assert n == 1


def test_user_with_no_org_still_has_exactly_one_tenant(db):
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    tenants = tenancy.list_tenants_for_user(db, 1)
    assert len(tenants) == 1
    assert tenants[0]["is_personal"] is True


def test_create_organisation_rejects_unknown_type(db):
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    with pytest.raises(ValueError):
        tenancy.create_organisation(db, 1, "Bogus Corp", "not_a_real_type")


# --- RBAC -------------------------------------------------------------------

def test_org_creator_is_enterprise_owner(db):
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Ministry of Health", "ministry")
    assert "enterprise_owner" in rbac.roles_for_user(db, org, 1)
    assert rbac.has_permission(db, org, 1, "programme.create")


def test_member_without_role_has_no_permissions(db):
    """Roles are not globally powerful by default -- the master prompt requires this."""
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Donor Agency", "donor")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    # donor_viewer is deliberately granted no permissions
    tenancy.add_member(db, org, 2, "donor_viewer", invited_by_user_id=1)

    assert rbac.permissions_for_user(db, org, 2) == frozenset()
    with pytest.raises(rbac.EnterprisePermissionError):
        rbac.require_permission(db, org, 2, "programme.create")


def test_revoked_member_loses_all_roles(db):
    """Codex HIGH #1 regression.

    A role row is not authority on its own. Deactivating the membership must strip
    every permission immediately -- otherwise removing someone from an organisation
    is a no-op while their role rows quietly survive, and offboarding does not work.
    """
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Ministry of Energy", "ministry")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    tenancy.add_member(db, org, 2, "programme_manager", invited_by_user_id=1)
    assert rbac.has_permission(db, org, 2, "beneficiary.approve")

    # Bob leaves the organisation. His role row is deliberately left behind.
    db.execute(
        "UPDATE enterprise_tenant_memberships SET status='revoked' "
        " WHERE tenant_id=? AND user_id=?",
        (org, 2),
    )

    assert rbac.roles_for_user(db, org, 2) == frozenset()
    assert not rbac.has_permission(db, org, 2, "beneficiary.approve")
    with pytest.raises(rbac.EnterprisePermissionError):
        rbac.require_permission(db, org, 2, "beneficiary.approve")


def test_expired_role_assignment_grants_nothing(db):
    """Codex HIGH #2 regression.

    Time-boxed grants (a contractor, a seconded engineer) must actually expire.
    """
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "GES", "government")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    tenancy.add_member(db, org, 2, "donor_viewer", invited_by_user_id=1)

    # A procurement role that ended yesterday.
    db.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, starts_at, ends_at) "
        "VALUES (?,?,?,?, datetime('now','-30 days'), datetime('now','-1 day'))",
        (org, 2, "procurement_manager", "tenant"),
    )
    assert not rbac.has_permission(db, org, 2, "procurement.manage")

    # ...and one that has not started yet.
    db.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, starts_at, ends_at) "
        "VALUES (?,?,?,?, datetime('now','+7 days'), NULL)",
        (org, 2, "contract_manager", "tenant"),
    )
    assert not rbac.has_permission(db, org, 2, "contract.manage")

    # A currently-valid window still grants.
    db.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, starts_at, ends_at) "
        "VALUES (?,?,?,?, datetime('now','-1 day'), datetime('now','+30 days'))",
        (org, 2, "funding_manager", "tenant"),
    )
    assert rbac.has_permission(db, org, 2, "funding.manage")


def test_require_permission_fails_closed_on_unknown_code(db):
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Utility Co", "utility")
    with pytest.raises(rbac.EnterprisePermissionError):
        rbac.require_permission(db, org, 1, "permission.that.does.not.exist")


def test_programme_scoped_role_does_not_leak_to_other_programmes(db):
    """A programme-scoped grant must not become tenant-wide authority."""
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "GES", "government")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    tenancy.add_member(db, org, 2, "donor_viewer", invited_by_user_id=1)
    # Bob is Regional Manager on programme 55 ONLY.
    db.execute(
        "INSERT INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, scope_id) VALUES (?,?,?,?,?)",
        (org, 2, "regional_manager", "programme", 55),
    )

    assert rbac.has_permission(db, org, 2, "beneficiary.approve", programme_id=55)
    assert not rbac.has_permission(db, org, 2, "beneficiary.approve", programme_id=56)
    assert not rbac.has_permission(db, org, 2, "beneficiary.approve")


def test_gate_approval_requires_the_named_role_not_just_a_permission(db):
    """Doc 3 names an approving authority per gate. Holding the permission is not enough."""
    tenancy.get_or_create_personal_tenant(db, 1, "alice")
    org = tenancy.create_organisation(db, 1, "Ministry", "ministry")
    tenancy.get_or_create_personal_tenant(db, 2, "bob")
    # Procurement Manager holds programme.approve...
    tenancy.add_member(db, org, 2, "procurement_manager", invited_by_user_id=1)
    assert rbac.has_permission(db, org, 2, "programme.approve")

    # ...but Gate 1's authority is the Programme Sponsor, and Bob is not one.
    gate1_authority = next(g[3] for g in constants.GATES if g[0] == "G01")
    assert gate1_authority == "programme_sponsor"
    with pytest.raises(rbac.EnterprisePermissionError):
        rbac.require_role(db, org, 2, gate1_authority)


# --- the vocabularies the state machine is built on -------------------------

def test_doc3_vocabularies_are_complete():
    """The owner's spec is explicit about these counts. Drift here breaks the spec."""
    assert len(constants.PHASES) == 16
    assert len(constants.GATES) == 14
    assert len(constants.PROGRAMME_STATUSES) == 20
    assert len(constants.CONTROLS) == 15
    assert constants.PROGRAMME_STATUSES[0] == "Concept"
    assert constants.DEFAULT_PHASE_CODE == "P01_CONCEPT"


def test_every_gate_closes_a_real_phase_and_names_a_real_role():
    phase_codes = {p[0] for p in constants.PHASES}
    for code, phase_code, _name, authority in constants.GATES:
        assert phase_code in phase_codes, f"{code} closes unknown phase {phase_code}"
        assert authority in constants.ROLE_CODES, f"{code} names unknown role {authority}"


def test_every_role_permission_maps_to_a_real_permission():
    for role, perms in constants.ROLE_PERMISSIONS.items():
        assert role in constants.ROLE_CODES, f"unknown role in permission map: {role}"
        for p in perms:
            assert p in constants.PERMISSION_CODES, f"{role} grants unknown permission {p}"


def test_only_approved_and_published_templates_may_generate():
    """Control C03. A Draft template must never be able to create a project."""
    assert constants.TEMPLATE_STATUSES_GENERATIVE == frozenset({"Approved", "Published"})
    assert "Draft" not in constants.TEMPLATE_STATUSES_GENERATIVE
