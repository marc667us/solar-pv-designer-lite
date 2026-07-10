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

if __name__ == "__main__":
    app.run()
