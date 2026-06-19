"""
SolarPro security package.

Phase 2 of docs/SECURITY_MIGRATION_KEYCLOAK.md. Exports the Keycloak
JWT verification + Flask decorators used by route handlers.
"""

from .keycloak_middleware import (
    KeycloakConfig,
    RequestContext,
    extract_request_context,
    get_config,
    reset_jwks_cache,
    set_config,
    verify_jwt,
    JWTError,
)
from .decorators import (
    get_request_context,
    require_all_roles,
    require_any_role,
    require_jwt,
    require_role,
    require_scope,
    require_service_account,
    require_tenant_match,
)

__all__ = [
    # middleware
    "KeycloakConfig",
    "RequestContext",
    "extract_request_context",
    "get_config",
    "reset_jwks_cache",
    "set_config",
    "verify_jwt",
    "JWTError",
    # decorators
    "get_request_context",
    "require_all_roles",
    "require_any_role",
    "require_jwt",
    "require_role",
    "require_scope",
    "require_service_account",
    "require_tenant_match",
]
