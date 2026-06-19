"""SolarPro authentication surface.

Phase 5 of docs/SECURITY_MIGRATION_KEYCLOAK.md. Owns the Keycloak OIDC
routes (/auth/login, /auth/callback, /auth/logout, /auth/refresh).

See `oidc_routes.py` for the Blueprint; mount it from `web_app.py` via
`register_oidc(app)`.
"""

from .oidc_routes import register_oidc, oidc_bp

__all__ = ["register_oidc", "oidc_bp"]
