"""Enterprise Solar Programme -- membership administration (rebuild, slice 6.5).

WHY THIS SLICE EXISTS
---------------------
Slices 1-6 built role CHECKING and shipped it live. Nothing ever built role GRANTING.
Onboarding handed its creator `enterprise_owner`, and that role -- as written -- carried
no operational permissions at all: no template.manage, no beneficiary.import, no
qualification.*. So the person who created an organisation could register a programme and
then do nothing with it. Upload a beneficiary CSV: 403. Open the template form: no form.
Read the priority list: empty, forever.

And there was no way out, because granting a role requires `tenant.admin`, and the only
screen that could have used it did not exist. The owner held the permission and had
nowhere to spend it.

231 green unit tests never saw this. Every one of them hand-grants roles in its fixture
(`tenancy.add_member(..., "surveyor", ...)`), so the suite only ever exercised users who
had already been given what a real user is never given. It took one real login against
live to find it. That is the lesson worth keeping: a fixture that grants what reality
withholds does not test the system, it tests a wish.

THE TWO HALVES OF THE FIX
-------------------------
1. `enterprise_owner` gains the operational permissions (constants.py) -- so a solo
   operator can actually run their own programme.
2. THIS MODULE -- so an organisation with more than one person can delegate properly,
   which is the entire point of the 38-role model and cannot be faked by widening a role.

Both were needed. (1) alone leaves every multi-person org unable to onboard a surveyor;
(2) alone means the owner's first act after onboarding is a trip to an admin screen to
grant themselves eight roles, which is ceremony, not control.

SEPARATION OF DUTIES AND THE SOLO TENANT
----------------------------------------
See tenancy.is_solo_tenant. SoD needs two people to mean anything; with one person it is
not a control, it is a deadlock. The relaxation is computed from LIVE membership, never
stored -- so it evaporates the moment a second member joins, and cannot be left switched
on by accident.
"""

from __future__ import annotations

from . import rbac, tenancy, txn
from .constants import ROLE_CODES, ROLE_LABELS


class MemberError(Exception):
    """A membership action was refused for a reason the operator can act on.

    Carries a human-readable message intended to be flashed straight to the user -- these
    are all "you asked for something that does not make sense" errors (no such user, last
    administrator, personal workspace), not internal faults.
    """


def _require_audit(wrote, what: str) -> None:
    """C12 -- audit or nothing. The audit row commits in the same transaction as the act.

    A role grant that is not in the audit trail is worse than no role grant: it is an
    authority nobody can account for. If the audit write fails, the grant is undone.
    """
    if not wrote:
        raise MemberError(
            f"the {what} was not saved, because its audit record could not be written"
        )


def _guard_admin(c, tenant_id: str, actor_user_id: int) -> None:
    """The caller must administer THIS tenant, and it must be a real organisation.

    Input:  connection, tenant id, the acting user.
    Output: none.
    Raises: EnterprisePermissionError (-> 403) or MemberError.

    THE PERSONAL-WORKSPACE GUARD IS NOT COSMETIC. A personal tenant's id is the md5 hash
    the app already derives for that user (003_rls_tenant.sql), which is what makes the
    enterprise overlay line up with their existing project rows instead of fighting them.
    Admitting a second person into it would hand them a tenant id that is, elsewhere in
    this codebase, the identity of somebody's private data. Organisations are the thing
    you share; a personal workspace is not.
    """
    rbac.require_permission(c, tenant_id, actor_user_id, "tenant.admin")
    if tenancy.is_personal_tenant(c, tenant_id):
        raise MemberError(
            "This is your personal workspace, which is yours alone. Create an "
            "organisation first, then invite people into that."
        )


def overview(c, tenant_id: str, actor_user_id: int) -> dict:
    """Everything the members screen renders.

    Input:  connection, tenant id, the acting user.
    Output: {"members": [...], "assignable_roles": [(code, label)], "is_solo": bool}
    Raises: EnterprisePermissionError, MemberError.

    `is_solo` is surfaced to the template so the screen can SAY OUT LOUD that
    separation of duties is currently relaxed, and that inviting a second person turns it
    back on. A control that silently changes behaviour with headcount would be a nasty
    surprise to discover during an audit; one that announces itself is a feature.
    """
    _guard_admin(c, tenant_id, actor_user_id)
    return {
        "members": tenancy.list_members(c, tenant_id),
        "assignable_roles": [(code, ROLE_LABELS.get(code, code))
                             for code in sorted(ROLE_CODES)],
        "is_solo": tenancy.is_solo_tenant(c, tenant_id),
    }


def invite(c, tenant_id: str, actor_user_id: int, identifier: str,
           role_code: str, audit=None) -> dict:
    """Add an existing app user to this organisation with one starting role.

    Input:  connection, tenant id, the acting admin, a username or email, a role code.
    Output: the invited user's {"id", "username", "email"}.
    Raises: EnterprisePermissionError, MemberError.

    THE INVITEE MUST ALREADY HAVE AN ACCOUNT. This does not create users, and deliberately
    so: user creation is Keycloak's job in this app, and a membership row pointing at a
    users.id that does not exist would be a foreign key into nothing -- every later JOIN
    would simply drop the member, silently, and an admin would swear they had added them.

    It also does not leak. "No such user" is the same answer whether the account does not
    exist or the admin fat-fingered it, which is correct: a membership form that
    distinguishes the two is a free account-enumeration oracle for anyone who can create
    an organisation, and anyone can create an organisation.
    """
    _guard_admin(c, tenant_id, actor_user_id)

    if role_code not in ROLE_CODES:
        raise MemberError(f"Unknown role: {role_code}")

    user = tenancy.find_user(c, identifier)
    if not user:
        raise MemberError(
            f"No user account matches {identifier!r}. They need a SolarPro account "
            f"before they can be added to an organisation."
        )

    existing = c.execute(
        "SELECT status FROM enterprise_tenant_memberships "
        " WHERE tenant_id = ? AND user_id = ?",
        (tenant_id, user["id"]),
    ).fetchone()
    if existing and existing[0] == "active":
        raise MemberError(f"{user['username']} is already a member of this organisation.")

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        cleared = 0
        if existing:
            # Re-admitting somebody who was offboarded. Their old membership row is still
            # there (revoked, kept for the audit trail), so add_member's ON CONFLICT DO
            # NOTHING would quietly do nothing at all and the invite would appear to
            # succeed while changing precisely nothing. Reinstate it explicitly.
            #
            # AND CLEAR THEIR OLD ROLES FIRST (Supervisor slice-6.6, MED).
            # remove_member deliberately KEEPS the role rows and only revokes the membership
            # -- roles_for_user JOINs status='active', so they go inert, and the trail can
            # still answer "what could this person do in March". But reinstating the
            # membership makes every one of those rows live again. So an owner who offboards
            # a Technical Director and later re-invites them as a Surveyor would silently
            # hand back template approval and gate-signing authority -- while THIS audit row
            # says `role: surveyor`. The audit trail would not merely miss the escalation; it
            # would contradict it.
            #
            # A re-invitation is a NEW grant of authority. It starts from nothing and gives
            # exactly the role that was named, and the audit row records how many stale grants
            # were cleared to make that true.
            cur = c.execute(
                "DELETE FROM enterprise_role_assignments "
                " WHERE tenant_id = ? AND user_id = ? AND scope_type = 'tenant'",
                (tenant_id, user["id"]),
            )
            cleared = max(0, int(getattr(cur, "rowcount", 0) or 0))

            c.execute(
                "UPDATE enterprise_tenant_memberships "
                "   SET status = 'active', updated_at = CURRENT_TIMESTAMP, "
                "       invited_by_user_id = ? "
                " WHERE tenant_id = ? AND user_id = ?",
                (actor_user_id, tenant_id, user["id"]),
            )
            tenancy.grant_role(c, tenant_id, user["id"], role_code, actor_user_id)
        else:
            tenancy.add_member(c, tenant_id, user["id"], role_code, actor_user_id,
                               email=user["email"] or "")

        _require_audit(
            audit("ENTERPRISE_MEMBER_ADDED", user_id=actor_user_id, tenant_id=tenant_id,
                  details={"member_user_id": user["id"],
                           "member_username": user["username"],
                           "role": role_code,
                           "reinstated": bool(existing),
                           "stale_roles_cleared": cleared}),
            "membership",
        )
    return user


def grant(c, tenant_id: str, actor_user_id: int, target_user_id: int,
          role_code: str, audit=None) -> None:
    """Give an existing member another tenant-wide role.

    Input:  connection, tenant id, acting admin, the member, the role code.
    Output: none.
    Raises: EnterprisePermissionError, MemberError.

    Self-granting is ALLOWED and is not an oversight. The holder of `tenant.admin` can
    already grant any role to anyone, so refusing to let them name themselves would stop
    nothing -- they would grant it to a second account and log in as that. It would only
    make the solo operator's life absurd. What matters is that the act is in the audit
    trail with a name against it, which it is.
    """
    _guard_admin(c, tenant_id, actor_user_id)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        try:
            tenancy.grant_role(c, tenant_id, target_user_id, role_code, actor_user_id)
        except ValueError as e:
            raise MemberError(str(e)) from e

        _require_audit(
            audit("ENTERPRISE_ROLE_GRANTED", user_id=actor_user_id, tenant_id=tenant_id,
                  details={"member_user_id": target_user_id, "role": role_code,
                           "self": target_user_id == actor_user_id}),
            "role grant",
        )


def revoke(c, tenant_id: str, actor_user_id: int, target_user_id: int,
           role_code: str, audit=None) -> None:
    """Take a tenant-wide role away from a member.

    Input:  connection, tenant id, acting admin, the member, the role code.
    Output: none.
    Raises: EnterprisePermissionError, MemberError (including the last-administrator guard).
    """
    _guard_admin(c, tenant_id, actor_user_id)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        try:
            tenancy.revoke_role(c, tenant_id, target_user_id, role_code)
        except ValueError as e:
            raise MemberError(str(e)) from e

        _require_audit(
            audit("ENTERPRISE_ROLE_REVOKED", user_id=actor_user_id, tenant_id=tenant_id,
                  details={"member_user_id": target_user_id, "role": role_code,
                           "self": target_user_id == actor_user_id}),
            "role revocation",
        )


def remove(c, tenant_id: str, actor_user_id: int, target_user_id: int,
           audit=None) -> None:
    """Offboard a member from the organisation.

    Input:  connection, tenant id, acting admin, the member being removed.
    Output: none.
    Raises: EnterprisePermissionError, MemberError (including the last-administrator guard).

    The membership goes to 'revoked', not away: `roles_for_user` JOINs membership and
    requires status='active', so every role they held stops granting anything the instant
    this commits -- while the row itself survives to answer "who was in this organisation
    in March", which a DELETE would erase.
    """
    _guard_admin(c, tenant_id, actor_user_id)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        try:
            tenancy.remove_member(c, tenant_id, target_user_id)
        except ValueError as e:
            raise MemberError(str(e)) from e

        _require_audit(
            audit("ENTERPRISE_MEMBER_REMOVED", user_id=actor_user_id, tenant_id=tenant_id,
                  details={"member_user_id": target_user_id,
                           "self": target_user_id == actor_user_id}),
            "member removal",
        )
