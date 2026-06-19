"""Phase 4 task 20 + Phase 5 task 24-26 wiring on web_app.py.

Three byte-level edits, all CRLF-preserving, idempotent:

1) Widen the Phase 2/3 decorator import block to add the Phase 4 and
   Phase 5 imports (tenant_context + auth Blueprint).

2) Insert `register_error_handler(app)` + `register_oidc(app)` right
   after the app.config.update block. Both are no-ops in production
   until `KEYCLOAK_ENABLED=true`.

3) Inside `get_db()`, before returning the connection, call
   `apply_tenant_guc(conn)`. apply_tenant_guc short-circuits cleanly
   when:
     - KEYCLOAK_ENABLED unset (parallel-run),
     - connection is SQLite,
     - or there's no Flask request context (init_db, CLI scripts).

Per CLAUDE.md: never use the Edit tool on web_app.py -- byte patches only.
"""
from __future__ import annotations

import sys
from pathlib import Path


HERE = Path(__file__).parent
WEB_APP = HERE / "web_app.py"


# ── Edit 1: widen the decorator import block ───────────────────────────
OLD_IMPORTS = (
    b"from app.security.decorators import (\r\n"
    b"    require_role,\r\n"
    b"    require_service_account,\r\n"
    b"    get_request_context,\r\n"
    b")  # Phase 2 + 3: Keycloak parallel-run decorators\r\n"
)
NEW_IMPORTS = OLD_IMPORTS + (
    b"from app.security.tenant_context import (\r\n"
    b"    register_error_handler as _kc_register_tenant_error_handler,\r\n"
    b"    apply_tenant_guc as _kc_apply_tenant_guc,\r\n"
    b")  # Phase 4: tenant context bridge\r\n"
    b"from app.auth import register_oidc as _kc_register_oidc  # Phase 5: OIDC Blueprint\r\n"
)


# ── Edit 2: install the registrations after app.config.update ──────────
OLD_CONFIG_BLOCK = (
    b"app.config.update(\r\n"
    b"    TEMPLATES_AUTO_RELOAD  = True,\r\n"
    b"    SESSION_COOKIE_HTTPONLY= True,\r\n"
    b"    SESSION_COOKIE_SAMESITE= \"Lax\",\r\n"
    b"    SESSION_COOKIE_SECURE  = False,   # works over both http and https tunnels\r\n"
    b"    PERMANENT_SESSION_LIFETIME = timedelta(hours=8),\r\n"
    b")\r\n"
)
NEW_CONFIG_BLOCK = OLD_CONFIG_BLOCK + (
    b"\r\n"
    b"# Phase 4: turn MissingTenantContextError into a 403 JSON response.\r\n"
    b"# No-op in production until tenant-scoped routes call require_tenant_context().\r\n"
    b"_kc_register_tenant_error_handler(app)\r\n"
    b"\r\n"
    b"# Phase 5: mount /auth/login, /auth/callback, /auth/logout, /auth/refresh.\r\n"
    b"# All four routes fall back to /login?legacy=1 when KEYCLOAK_ENABLED is unset,\r\n"
    b"# so this is safe to deploy long before the cutover.\r\n"
    b"_kc_register_oidc(app)\r\n"
)


# ── Edit 3: apply_tenant_guc inside get_db() ───────────────────────────
OLD_GET_DB = (
    b"def get_db():\r\n"
    b"    # Phase B1: dual-backend dispatch on DATABASE_URL. When unset (today),\r\n"
    b"    # behavior is byte-identical to the original SQLite path.\r\n"
    b"    _db_url = os.environ.get(\"DATABASE_URL\", \"\")\r\n"
    b"    if _db_url.startswith((\"postgres://\", \"postgresql://\")):\r\n"
    b"        import db_adapter\r\n"
    b"        return db_adapter.open_postgres(_db_url)\r\n"
    b"    conn = sqlite3.connect(DB_PATH)\r\n"
    b"    conn.row_factory = sqlite3.Row\r\n"
    b"    return conn\r\n"
)
NEW_GET_DB = (
    b"def get_db():\r\n"
    b"    # Phase B1: dual-backend dispatch on DATABASE_URL. When unset (today),\r\n"
    b"    # behavior is byte-identical to the original SQLite path.\r\n"
    b"    _db_url = os.environ.get(\"DATABASE_URL\", \"\")\r\n"
    b"    if _db_url.startswith((\"postgres://\", \"postgresql://\")):\r\n"
    b"        import db_adapter\r\n"
    b"        conn = db_adapter.open_postgres(_db_url)\r\n"
    b"    else:\r\n"
    b"        conn = sqlite3.connect(DB_PATH)\r\n"
    b"        conn.row_factory = sqlite3.Row\r\n"
    b"    # Phase 4 task 20: install tenant + user GUCs on every fresh\r\n"
    b"    # Postgres connection so RLS policies can resolve them. The\r\n"
    b"    # helper is a no-op when KEYCLOAK_ENABLED is unset, the conn is\r\n"
    b"    # SQLite, or we're outside a Flask request context (init_db,\r\n"
    b"    # CLI tooling, background jobs).\r\n"
    b"    try:\r\n"
    b"        _kc_apply_tenant_guc(conn)\r\n"
    b"    except Exception as _e:\r\n"
    b"        # Hard-fail propagation would crash the request; instead we\r\n"
    b"        # log and let the RLS policy's parallel-run NULL escape keep\r\n"
    b"        # things running. The structured logger may not be ready at\r\n"
    b"        # very early startup, so guard the log call too.\r\n"
    b"        try:\r\n"
    b"            log_error(message=\"apply_tenant_guc failed\", error=str(_e))\r\n"
    b"        except Exception:\r\n"
    b"            pass\r\n"
    b"    return conn\r\n"
)


def patch(data: bytes, label: str, old: bytes, new: bytes) -> bytes:
    if new in data:
        print(f"[skip] {label}: already applied")
        return data
    if old not in data:
        raise SystemExit(f"[FAIL] {label}: anchor not found")
    data = data.replace(old, new, 1)
    print(f"[ok] {label}: +{len(new) - len(old)} bytes")
    return data


def main() -> int:
    data = WEB_APP.read_bytes()
    data = patch(data, "imports (Phase 4+5)", OLD_IMPORTS, NEW_IMPORTS)
    data = patch(data, "register calls (after app.config)",
                 OLD_CONFIG_BLOCK, NEW_CONFIG_BLOCK)
    data = patch(data, "get_db() tenant GUC install", OLD_GET_DB, NEW_GET_DB)
    WEB_APP.write_bytes(data)
    print(f"[done] wrote {WEB_APP} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
