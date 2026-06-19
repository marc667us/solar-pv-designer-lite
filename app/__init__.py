"""SolarPro Global -- new modular code lives here.

The legacy single-file `web_app.py` is grandfathered (ADR-0001). New
work goes into well-organized packages under `app/`:

    app/security/   -- Keycloak JWT verification + Flask decorators
                       (Phase 2 of SECURITY_MIGRATION_KEYCLOAK.md)
"""
