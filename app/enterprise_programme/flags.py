"""Enterprise Solar Programme -- feature flags (rebuild, slice 3).

The rebuild is DARK until `enterprise_rebuild_enabled` is '1' in admin_settings
(seeded '0' by migrations 025 and 026). Nothing here turns it on -- that is the owner's
call, made through the gated workflow.

WHY THIS IS NOT A PLAIN SELECT
------------------------------
`admin_settings` is RLS-protected, FORCE-enabled and admin-only, and migration 017 dropped
its parallel-run escape. A plain SELECT on a NORMAL user's request therefore matches no
policy, returns zero rows, and the flag reads as its default FOREVER -- the module would be
permanently dark with nothing in the logs to explain why. So the read sets
`app.current_role='admin'` transaction-locally, exactly as the Phase-1 module learned to
(enterprise_programme_repository.py:78, and memory `feedback-solar-rls-seed-admin-role`).

The GUC is `is_local=true`, so it dies with the transaction even if the reset is skipped.

FAILS CLOSED. Any error reading the flag leaves the module dark. A feature flag that opens
on error is not a feature flag.
"""

from __future__ import annotations

import os
import time

FLAG_ENABLED = "enterprise_rebuild_enabled"

_TTL_SECONDS = 60.0
_cache: dict[str, tuple[float, str]] = {}


def _is_postgres() -> bool:
    """True when running against Postgres rather than local SQLite."""
    return str(os.environ.get("DATABASE_URL", "")).startswith(
        ("postgres://", "postgresql://")
    )


def read_flag(get_db, key: str, default: str = "0") -> str:
    """Read one flag from admin_settings.

    Input:  the injected get_db factory, the flag key, a default.
    Output: the flag's string value, or `default` on any failure.
    """
    conn = None
    try:
        conn = get_db()
        # get_db() hands back a FRESH connection, and the `with` block below commits but
        # does NOT close it -- so the close belongs in a finally, or every cache miss leaks
        # a connection (a scarce thing on a free-tier Postgres).
        with conn as c:
            if _is_postgres():
                c.execute("SELECT set_config('app.current_role', 'admin', true)")
            row = c.execute(
                "SELECT value FROM admin_settings WHERE key=?", (key,)
            ).fetchone()
            if _is_postgres():
                # Reset explicitly: the connection may be reused later in this request,
                # and it must not carry admin authority into an ordinary query.
                c.execute("SELECT set_config('app.current_role', '', true)")
            return str(row[0]).strip() if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def module_enabled(get_db) -> bool:
    """True when the rebuilt enterprise module is switched on. Dark by default.

    Input:  the injected get_db factory.
    Output: bool.

    Cached per process for a minute so that every request does not pay for an
    admin-GUC round trip just to discover the module is off.
    """
    now = time.monotonic()
    hit = _cache.get(FLAG_ENABLED)
    if hit and (now - hit[0]) < _TTL_SECONDS:
        return hit[1] == "1"

    value = read_flag(get_db, FLAG_ENABLED, "0")
    _cache[FLAG_ENABLED] = (now, value)
    return value == "1"


def clear_cache() -> None:
    """Drop the flag cache. For tests, and for the admin toggle route."""
    _cache.clear()
