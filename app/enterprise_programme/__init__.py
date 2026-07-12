"""Enterprise Solar Programme Management module (rebuild).

Public API. Anything not re-exported here is internal and may change.

Built from the owner's three source specifications in
docs/enterprise-programme/source/, planned by Codex in
docs/enterprise-programme/rebuild/01..08, and adjudicated by the Supervisor in
docs/enterprise-programme/rebuild/09-supervisor-adjudication.md.
"""

from __future__ import annotations

from . import constants
from .rbac import (
    EnterprisePermissionError,
    has_permission,
    permissions_for_user,
    require_permission,
    require_role,
    roles_for_user,
)
from .tenancy import (
    add_member,
    apply_enterprise_guc,
    create_organisation,
    ensure_schema,
    get_or_create_personal_tenant,
    list_tenants_for_user,
    personal_tenant_id,
    resolve_active_tenant,
)

__all__ = [
    "constants",
    # tenancy
    "personal_tenant_id",
    "apply_enterprise_guc",
    "ensure_schema",
    "get_or_create_personal_tenant",
    "list_tenants_for_user",
    "resolve_active_tenant",
    "create_organisation",
    "add_member",
    # rbac
    "EnterprisePermissionError",
    "roles_for_user",
    "permissions_for_user",
    "has_permission",
    "require_permission",
    "require_role",
]
