"""The backfill unlocks an organisation onboarded BEFORE slice 6.5 -- and nothing else.

Slice 6.5 made create_organisation grant ONBOARDING_OWNER_ROLES. Organisations created
before it shipped hold `enterprise_owner` and nothing else, so their owner still cannot
author a template, import a beneficiary, or score a site. The live suite fails exactly
4 checks for exactly that reason.

These tests reconstruct that pre-6.5 state directly (an org whose owner holds only
`enterprise_owner`) and assert the backfill fixes it, is idempotent, and -- the one that
matters most -- does NOT touch personal tenants, which every user on the platform has and
which ALSO grant `enterprise_owner`. A backfill that ignored that distinction would hand
all 11 enterprise roles to every user on the platform.
"""
from __future__ import annotations

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.enterprise_programme import members, rbac, tenancy, workflows  # noqa: E402
from app.enterprise_programme.constants import ONBOARDING_OWNER_ROLES  # noqa: E402
from app.security import audit as audit_mod                            # noqa: E402
from scripts.backfill_onboarding_owner_roles import backfill           # noqa: E402


class _Conn(sqlite3.Connection):
    """sqlite3.Connection has no __dict__, so a plain attribute cannot be attached."""


OWNER = 1        # onboards the organisation
BYSTANDER = 2    # never onboards anything; has only a personal tenant


@pytest.fixture()
def db():
    os.environ.pop("DATABASE_URL", None)
    audit_mod.reset_schema_probe()

    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((OWNER, "owen"), (BYSTANDER, "bea")):
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)"
    )
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    for uid, name in ((OWNER, "owen"), (BYSTANDER, "bea")):
        tenancy.get_or_create_personal_tenant(c, uid, name)
    return c


def _pre_6_5_organisation(c) -> str:
    """An organisation exactly as it existed on live before slice 6.5: owner holds ONLY
    `enterprise_owner`. create_organisation now grants the whole bundle, so the extra role
    rows are stripped back off to reconstruct the old state faithfully."""
    tid = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry")
    c.execute(
        "DELETE FROM enterprise_role_assignments "
        " WHERE tenant_id=? AND user_id=? AND role_code<>'enterprise_owner'",
        (tid, OWNER),
    )
    held = {r[0] for r in c.execute(
        "SELECT role_code FROM enterprise_role_assignments WHERE tenant_id=? AND user_id=?",
        (tid, OWNER)).fetchall()}
    assert held == {"enterprise_owner"}, f"fixture did not reproduce the pre-6.5 state: {held}"
    return tid


def _held(c, tid, uid) -> set[str]:
    return {r[0] for r in c.execute(
        "SELECT role_code FROM enterprise_role_assignments "
        " WHERE tenant_id=? AND user_id=? AND scope_type='tenant'", (tid, uid)).fetchall()}


def test_the_pre_6_5_owner_is_genuinely_locked_out(db):
    """Establishes the bug is real before asserting the fix -- otherwise the test below
    could pass against a system that was never broken."""
    tid = _pre_6_5_organisation(db)

    for perm in ("template.manage", "beneficiary.import",
                 "qualification.score", "qualification.approve"):
        assert not rbac.has_permission(db, tid, OWNER, perm), (
            f"the pre-6.5 owner should NOT hold {perm} -- fixture is wrong"
        )


def test_dry_run_writes_nothing(db):
    tid = _pre_6_5_organisation(db)

    stats = backfill(db, apply=False, out=lambda *a: None)

    assert stats["owners"] == 1
    assert stats["missing"] == len(ONBOARDING_OWNER_ROLES) - 1   # they already hold owner
    assert stats["granted"] == 0
    assert _held(db, tid, OWNER) == {"enterprise_owner"}, "dry run granted a role"


def test_backfill_unlocks_the_owner(db):
    tid = _pre_6_5_organisation(db)

    stats = backfill(db, apply=True, out=lambda *a: None)

    assert stats["granted"] == len(ONBOARDING_OWNER_ROLES) - 1
    assert _held(db, tid, OWNER) == set(ONBOARDING_OWNER_ROLES)

    # The four permissions the live suite fails on.
    for perm in ("template.manage", "beneficiary.import",
                 "qualification.score", "qualification.approve"):
        assert rbac.has_permission(db, tid, OWNER, perm), f"still cannot {perm}"


def test_backfill_is_idempotent(db):
    _pre_6_5_organisation(db)

    backfill(db, apply=True, out=lambda *a: None)
    second = backfill(db, apply=True, out=lambda *a: None)

    assert second["missing"] == 0, "a second run found work to do; it is not idempotent"
    assert second["granted"] == 0


def test_a_post_6_5_organisation_is_left_alone(db):
    """An org onboarded AFTER 6.5 already holds the bundle. The backfill must be a no-op."""
    tenancy.create_organisation(db, OWNER, "New Ministry", "ministry")

    stats = backfill(db, apply=True, out=lambda *a: None)

    assert stats["missing"] == 0
    assert stats["granted"] == 0


def test_personal_tenants_are_never_touched(db):
    """THE ONE THAT MATTERS.

    Every user on the platform has a personal tenant, and get_or_create_personal_tenant
    grants `enterprise_owner` in it. If the backfill selected owners without filtering on
    legacy_user_id IS NULL, it would grant all 11 enterprise roles to EVERY USER. BYSTANDER
    never onboarded anything and must come out of this holding exactly what they went in with.
    """
    _pre_6_5_organisation(db)
    personal = tenancy.get_or_create_personal_tenant(db, BYSTANDER, "bea")
    before = _held(db, personal, BYSTANDER)
    assert before == {"enterprise_owner"}, "fixture: a personal tenant grants enterprise_owner"

    backfill(db, apply=True, out=lambda *a: None)

    assert _held(db, personal, BYSTANDER) == before, (
        "the backfill granted enterprise roles inside a PERSONAL tenant"
    )
    assert not rbac.has_permission(db, personal, BYSTANDER, "template.manage")


def test_every_grant_is_audited(db):
    """Control C12: a role grant that leaves no audit row is indistinguishable from one
    that never happened. This is why the backfill drives members.grant() rather than SQL."""
    _pre_6_5_organisation(db)
    before = db.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='ENTERPRISE_ROLE_GRANTED'").fetchone()[0]

    stats = backfill(db, apply=True, out=lambda *a: None)

    after = db.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='ENTERPRISE_ROLE_GRANTED'").fetchone()[0]
    assert after - before == stats["granted"], "a role was granted without an audit row"
