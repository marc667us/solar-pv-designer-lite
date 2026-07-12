"""Enterprise Solar Programme Management module (rebuild).

Public API. Anything not re-exported here is internal and may change.

Built from the owner's three source specifications in
docs/enterprise-programme/source/, planned by Codex in
docs/enterprise-programme/rebuild/01..08, and adjudicated by the Supervisor in
docs/enterprise-programme/rebuild/09-supervisor-adjudication.md.
"""

from __future__ import annotations

from . import constants
from .gates import (
    CONTROL_GUARDS,
    EnterpriseGateError,
    GateBlockedError,
    control_summary,
    evaluate_gate,
    gate_authority,
)
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
from .workflows import (
    allowed_transitions,
    approve_gate,
    create_programme,
    get_programme_state,
    register_document,
    resume_from_hold,
    transition_programme_phase,
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
    # gates and the 15 controls
    "EnterpriseGateError",
    "GateBlockedError",
    "CONTROL_GUARDS",
    "control_summary",
    "evaluate_gate",
    "gate_authority",
    # lifecycle spine
    "create_programme",
    "register_document",
    "approve_gate",
    "transition_programme_phase",
    "resume_from_hold",
    "get_programme_state",
    "allowed_transitions",
]
