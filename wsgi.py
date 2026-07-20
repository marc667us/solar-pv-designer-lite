"""WSGI entry point for Render / gunicorn.

`init_db()` is deliberately NOT called at import. gunicorn imports this module
before it binds $PORT, so an exception raised here means the process never
listens and Render restarts it forever. That is precisely how the 2026-07-09
Postgres expiry became a total outage. See boot_state.py for the incident note.

boot_state.attach() attempts initialisation once, swallows any failure, and
retries lazily on later requests so the app recovers without a redeploy.
"""
from dotenv import load_dotenv
load_dotenv()

# The encrypted secrets store, loaded in the SAME position as load_dotenv and with the same
# rule: it fills gaps, it never overrides a value the environment already has.
#
# IT MUST RUN BEFORE `from web_app import app`. web_app reads SECRET_KEY straight from
# os.environ at import time and falls back to `secrets.token_hex(32)` when it is missing -- a
# RANDOM key on every restart, which silently invalidates every session and logs out every
# user. Loading the store after that import would be too late to matter.
#
# On Render this is a no-op: there is no .env.enc there and every secret is a dashboard
# variable. It exists so a machine can hold its secrets encrypted instead of in plaintext.
#
# WRAPPED, because this module must not raise at import under ANY circumstance -- see the
# docstring above and boot_state.py. `populate_environ` is already written not to raise, and
# this is the second belt: a secrets problem may degrade a feature, never refuse the port.
try:
    import secrets_file
    secrets_file.populate_environ()
except Exception as _secrets_exc:                       # pragma: no cover - boot resilience
    import logging
    logging.getLogger("wsgi").error(
        "secrets_file could not be loaded at boot (%s); continuing without the encrypted "
        "store", type(_secrets_exc).__name__)

from web_app import app, init_db
import boot_state

boot_state.attach(app, init_db)

# --- Enterprise Solar Programme Management module (Phase 1) -------------------
# Registered HERE, not in web_app.py: web_app.py is CRLF+mojibake and must never
# be edited. This mirrors how new_capital_investment_routes is attached
# (web_app.py:1034) -- dependencies injected to avoid a circular import.
#
# The try/except is not defensive noise. Per this module's docstring above, an
# exception raised at import time means gunicorn never binds $PORT and Render
# restarts the process forever -- that is exactly how the 2026-07-09 Postgres
# expiry became a total outage. A broken enterprise module must degrade to
# "feature missing", never to "site down". The module is dark by default anyway.
try:
    from enterprise_programme_routes import register_enterprise_programme
    import web_app as _wa

    register_enterprise_programme(
        app,
        get_db=_wa.get_db,
        login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect,
        current_user=_wa.current_user,
    )
except Exception as _e:  # pragma: no cover - boot resilience path
    import logging
    logging.getLogger(__name__).error(
        "Enterprise Programme module failed to register (app still serving): %s", _e
    )

# --- Ops Center technical support --------------------------------------------
# Explains every ops check in plain English and offers the fix that fits.
#
# Registered HERE for the same reason as the enterprise module: web_app.py is CRLF + mojibake
# and must never be edited. Wrapped in its own try/except so a fault in the SUPPORT surface can
# never stop the app serving -- a diagnostic tool that can take the site down is worse than no
# diagnostic tool.
try:
    from new_ops_support_routes import register_ops_support
    import web_app as _wa2

    register_ops_support(
        app,
        admin_required=_wa2.admin_required,
        csrf_protect=_wa2.csrf_protect,
    )
except Exception as _e:  # pragma: no cover - boot resilience path
    import logging
    logging.getLogger(__name__).error(
        "Ops support surface failed to register (app still serving): %s", _e
    )

# --- CDC outbox drainer (change-data-capture, slice 3) ------------------------
# The first consumer of the change feed that migrations 036/037 set up. Drained by a
# scheduled GitHub Action, exactly like the enterprise job queue and for the same reason:
# Render's free tier gives this account one instance, so there is no worker process.
#
# Registered HERE for the same reason as the modules above: web_app.py is CRLF + mojibake and
# must never be edited. Wrapped in its own try/except because a fault in an OBSERVABILITY
# surface must never stop the app serving -- the feed exists to report on the app, so it
# taking the app down would invert its whole purpose.
try:
    from new_cdc_drain_routes import register_cdc_drain
    import web_app as _wa3

    register_cdc_drain(
        app,
        get_db=_wa3.get_db,
        admin_notify=_wa3._admin_notify,
    )
except Exception as _e:  # pragma: no cover - boot resilience path
    import logging
    logging.getLogger(__name__).error(
        "CDC drain surface failed to register (app still serving): %s", _e
    )

# --- CDC pg_notify listener (change-data-capture, slice 4) --------------------
# The BROADCAST half: slice 3's drainer runs in ONE worker and so cannot invalidate the
# per-worker marketplace cache. This listens on the `cdc` channel that cdc_capture() has been
# publishing to since migration 036 and clears this process's cache.
#
# SHIPS DARK. The thread starts, but the loop holds no connection and does nothing until the
# `cdc_listener_enabled` flag in admin_settings says "1". The flag read fails closed.
#
# Started HERE, at import, deliberately: Render runs gunicorn with NO --preload (threads do
# not survive fork()), so each worker imports this module itself and the thread really does
# exist in the worker. start() is documented never to raise -- the try/except is the second
# belt, for the same reason as every block above.
try:
    import cdc_listener
    import web_app as _wa4
    from app.enterprise_programme.flags import read_flag as _read_flag

    cdc_listener.start(
        get_db=_wa4.get_db,
        invalidate=_wa4._mp_cache_invalidate,
        notify_admin=_wa4._admin_notify,
        read_flag=_read_flag,
    )

    # THIS HOOK IS WHAT ACTUALLY MAKES THE LISTENER RUN, not the start() above.
    #
    # The first dark deploy showed the serving process holding a thread that had entered the
    # loop, never unwound, and was gone from threading.enumerate() -- i.e. the process was
    # forked after import, so it inherited the module's MEMORY but none of its THREADS.
    # start() therefore cannot guarantee anything about the process that answers requests.
    #
    # ensure_running() is the guarantee: the serving process notices it has no live listener
    # of its own (pid comparison -- the one check a forked child cannot pass by accident) and
    # spawns one. Its fast path is two comparisons and a flag read, no I/O and no lock, so it
    # is cheap enough for every request; respawns are rate-limited so a persistently failing
    # spawn cannot busy-loop on the request path. It never raises.
    app.before_request(lambda: cdc_listener.ensure_running())
except Exception as _e:  # pragma: no cover - boot resilience path
    import logging
    logging.getLogger(__name__).error(
        "CDC listener failed to start (app still serving): %s", _e
    )

# --- API versioning: /api/v1 aliases (slice 1) -------------------------------
# ADDITIVE ONLY. Every /api/v1 rule points at the SAME view function as its
# unversioned twin, which keeps working unchanged and is NOT deprecated. This
# repo previously had no API versioning at all.
#
# Registered HERE rather than spliced into web_app.py deliberately: a bad byte
# splice into that file is an import-time crash, i.e. a total outage, and that
# was named the single most dangerous step in this change. This path costs
# nothing and risks nothing by comparison.
#
# SHIPS DARK: register() returns immediately unless API_V1_ENABLED is set, so
# the first deploy proves only that the import is harmless. A second deploy
# turns it on. register() is documented never to raise; the try/except is the
# second belt, matching every block above.
try:
    import new_api_v1_routes

    _v1_summary = new_api_v1_routes.register(app)
    if _v1_summary["enabled"]:
        import logging
        logging.getLogger(__name__).info(
            "api_v1: enabled=%s registered=%d missing=%s",
            _v1_summary["enabled"],
            len(_v1_summary["registered"]),
            _v1_summary["missing"],
        )
except Exception as _e:  # pragma: no cover - boot resilience path
    import logging
    logging.getLogger(__name__).error(
        "api_v1 failed to register (app still serving): %s", _e
    )

if __name__ == "__main__":
    app.run()
