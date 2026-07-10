"""Render.com entry point — Waitress on $PORT."""
import os
from dotenv import load_dotenv
load_dotenv()
from waitress import serve
from web_app import app, init_db
import boot_state

# Never call init_db() at import here either. This file is an alternate Render
# entrypoint; if it ever becomes the startCommand, an unreachable database must
# not stop waitress from binding $PORT. See boot_state.py for the incident note.
boot_state.attach(app, init_db)
port = int(os.environ.get("PORT", 5000))
print(f"Starting on port {port}", flush=True)
serve(app, host="0.0.0.0", port=port, threads=8)
