"""
SolarPro Global — Production launcher
Starts Waitress WSGI server + Cloudflare Tunnel
Run: python start.py
"""
import subprocess, threading, time, sys, os, re

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# The encrypted secrets store -- same position as load_dotenv, same gap-filling rule, and it
# must run before web_app is imported (see the note in wsgi.py: web_app reads SECRET_KEY from
# os.environ at import time and falls back to a RANDOM key, logging every user out on restart).
try:
    import secrets_file
    secrets_file.populate_environ()
except Exception as _secrets_exc:      # a secrets problem must not stop the app starting
    print(f"warning: encrypted secrets store unavailable "
          f"({type(_secrets_exc).__name__}); continuing without it")

PORT = 5000

# ── Start Flask via Waitress ──────────────────────────────────
def run_waitress():
    from waitress import serve
    from web_app import app, init_db
    import boot_state
    # Bind the port even if the database is unreachable. See boot_state.py.
    boot_state.attach(app, init_db)
    print(f"[waitress] Listening on 0.0.0.0:{PORT}")
    serve(app, host="0.0.0.0", port=PORT, threads=8)

t = threading.Thread(target=run_waitress, daemon=True)
t.start()
time.sleep(3)  # let Waitress bind

# ── Start Cloudflare Tunnel ───────────────────────────────────
CF = r"C:\Users\USER\cloudflared.exe"

if not os.path.exists(CF):
    print("[tunnel] cloudflared.exe not found at", CF)
    print(f"[tunnel] App running locally at http://localhost:{PORT}")
    print("         Press Ctrl+C to stop.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)

print("[tunnel] Opening Cloudflare Tunnel…")
proc = subprocess.Popen(
    [CF, "tunnel", "--url", f"http://localhost:{PORT}"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

public_url = None
banner_shown = False

for line in proc.stdout:
    line = line.rstrip()
    # cloudflared prints the URL in stderr/stdout like: https://xxxx.trycloudflare.com
    match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
    if match and not banner_shown:
        public_url = match.group(0)
        banner_shown = True
        print()
        print("=" * 60)
        print("  SOLARPRO GLOBAL — LIVE")
        print("=" * 60)
        print(f"  Public URL : {public_url}")
        print(f"  Local URL  : http://localhost:{PORT}")
        print()
        print("  Admin login: admin / SolarAdmin2026!")
        print("  Share the Public URL with anyone worldwide.")
        print()
        print("  Press Ctrl+C to stop.")
        print("=" * 60)
        print()
    elif "ERR" in line or "error" in line.lower():
        print("[tunnel]", line)

try:
    proc.wait()
except KeyboardInterrupt:
    print("\n[shutdown] Stopping…")
    proc.terminate()
    sys.exit(0)
