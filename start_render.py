"""Render.com entry point — Waitress on $PORT."""
import os
from dotenv import load_dotenv
load_dotenv()
from waitress import serve
from web_app import app, init_db

init_db()
port = int(os.environ.get("PORT", 5000))
print(f"Starting on port {port}", flush=True)
serve(app, host="0.0.0.0", port=port, threads=8)
