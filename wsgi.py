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

if __name__ == "__main__":
    app.run()
