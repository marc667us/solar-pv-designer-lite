"""Enterprise Solar Programme -- RBAC service (rebuild, slice 1).

WHAT THIS IS
------------
Domain authorisation for the enterprise module: which of the 38 programme roles the
caller holds in the active tenant, and therefore which actions they may take.

WHAT THIS IS NOT
----------------
A second authentication system. The master prompt forbids one, and the app already
has authn: Flask session on the legacy path, Keycloak JWT via
app/security/decorators.py on the API path. By the time anything here runs, WHO the
caller is has already been established. This file only answers WHAT THEY MAY DO.

WHY PERMISSION CHECKS LIVE IN SERVICES, NOT JUST DECORATORS
-----------------------------------------------------------
A route decorator only guards the route. Background jobs, the queue drainer and
internal service calls do not pass through routes -- so a decorator-only design has
a hole exactly where bulk operations (project generation, imports) live. Every
mutating service therefore calls require_permission() itself. The route decorator is
a fast fail, not the boundary.
"""

from __future__ import annotations

from .constants import ROLE_CODES, PERMISSION_CODES, permissions_for_roles


class EnterprisePermissionError(PermissionError):
    """Raised when the caller lacks a permission in the active tenant.

    Callers should turn this into a 403. It deliberately does NOT say whether the
    subject row exists -- telling an attacker "that programme exists but you can't
    see it" is an information leak.
    """

    def __init__(self, permission: str, tenant_id: str | None = None):
        self.permission = permission
        self.tenant_id = tenant_id
        super().__init__(f"Permission denied: {permission}")


def roles_for_user(c, tenant_id: str, user_id: int,
                   programme_id: int | None = None) -> frozenset[str]:
    """The role codes the user holds in this tenant, honouring membership and scope.

    Input:  connection, active tenant id, users.id, optional programme id.
    Output: frozenset of role code strings (empty if they hold none).

    THREE things must ALL hold for a role to count. Each was a real bug at review:

    1. ACTIVE MEMBERSHIP. A role row alone is not authority. If the membership is
       revoked (status != 'active') the role grants nothing -- otherwise removing
       someone from an organisation would be a no-op while their role rows survived,
       and offboarding would silently not work. Hence the JOIN, not a bare SELECT.

    2. NOT EXPIRED. `starts_at`/`ends_at` bound a time-boxed grant (a contractor, a
       seconded engineer). NULL means "no bound". A grant that has ended must stop
       granting.

    3. IN SCOPE. A tenant-wide assignment always applies. A programme-scoped one
       applies only to that programme -- so a Regional Manager on one programme does
       not gain authority over every other programme in the organisation.
    """
    # CURRENT_TIMESTAMP is valid in both SQLite and Postgres, so one query serves both.
    time_ok = ("(ra.starts_at IS NULL OR ra.starts_at <= CURRENT_TIMESTAMP) "
               "AND (ra.ends_at IS NULL OR ra.ends_at > CURRENT_TIMESTAMP)")

    base = (
        "SELECT ra.role_code "
        "  FROM enterprise_role_assignments ra "
        "  JOIN enterprise_tenant_memberships m "
        "    ON m.tenant_id = ra.tenant_id AND m.user_id = ra.user_id "
        " WHERE ra.tenant_id = ? AND ra.user_id = ? "
        "   AND m.status = 'active' "
        f"   AND {time_ok} "
    )

    if programme_id is None:
        rows = c.execute(base + "AND ra.scope_type = 'tenant'",
                         (tenant_id, user_id)).fetchall()
    else:
        rows = c.execute(
            base + "AND (ra.scope_type = 'tenant' "
                   "     OR (ra.scope_type = 'programme' AND ra.scope_id = ?))",
            (tenant_id, user_id, programme_id),
        ).fetchall()

    return frozenset(r[0] for r in rows if r[0] in ROLE_CODES)


def permissions_for_user(c, tenant_id: str, user_id: int,
                         programme_id: int | None = None) -> frozenset[str]:
    """The permission codes the user effectively holds in this tenant.

    Input:  connection, tenant id, users.id, optional programme id.
    Output: frozenset of permission code strings.

    Derived from roles via the role->permission map in constants.py. There is no
    "admin bypass" here on purpose: an Enterprise Owner is powerful because their
    role grants many permissions, not because the code special-cases them.
    """
    return permissions_for_roles(roles_for_user(c, tenant_id, user_id, programme_id))


def has_permission(c, tenant_id: str, user_id: int, permission: str,
                   programme_id: int | None = None) -> bool:
    """Non-raising permission test, for deciding what to render.

    Input:  connection, tenant id, users.id, permission code, optional programme id.
    Output: True/False.

    Use this to hide a button. Use require_permission() to actually stop the action --
    hiding a button is not a security control (a user can still POST the URL).
    """
    if permission not in PERMISSION_CODES:
        # An unknown permission code is a programming error, not a grant. Fail closed.
        return False
    return permission in permissions_for_user(c, tenant_id, user_id, programme_id)


def require_permission(c, tenant_id: str, user_id: int, permission: str,
                       programme_id: int | None = None) -> None:
    """Enforce a permission. Raises EnterprisePermissionError if the caller lacks it.

    Input:  connection, tenant id, users.id, permission code, optional programme id.
    Output: none (returns quietly when allowed).
    Raises: EnterprisePermissionError -> 403.

    Call this at the top of EVERY mutating service function, including ones only ever
    reached from a background job. Fails closed on an unknown permission code.
    """
    if not tenant_id or not user_id:
        raise EnterprisePermissionError(permission, tenant_id)
    if not has_permission(c, tenant_id, user_id, permission, programme_id):
        raise EnterprisePermissionError(permission, tenant_id)


def require_role(c, tenant_id: str, user_id: int, role_code: str,
                 programme_id: int | None = None) -> None:
    """Enforce holding a specific ROLE, not merely a permission.

    Input:  connection, tenant id, users.id, role code, optional programme id.
    Output: none.
    Raises: EnterprisePermissionError.

    Needed because the 14 stage gates name an APPROVING AUTHORITY by role (doc 3):
    Gate 1 is the Programme Sponsor's to approve, Gate 6 the Technical Director's.
    Holding `programme.approve` is not sufficient -- the right person must sign.
    """
    if role_code not in ROLE_CODES:
        raise EnterprisePermissionError(f"role:{role_code}", tenant_id)
    if role_code not in roles_for_user(c, tenant_id, user_id, programme_id):
        raise EnterprisePermissionError(f"role:{role_code}", tenant_id)
