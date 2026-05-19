"""
Launch SolarPro Global web app with live public URL via ngrok tunnel.
Run: python3 deploy.py
"""
import threading, time, sys, os

# Ensure we run from project directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from web_app import app, init_db

def start_flask():
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

# Start Flask in background thread
t = threading.Thread(target=start_flask, daemon=True)
t.start()
time.sleep(2)

try:
    from pyngrok import ngrok, conf

    # Try to open tunnel
    tunnel = ngrok.connect(5000, "http")
    public_url = tunnel.public_url

    print("\n" + "="*60)
    print("  SOLARPO GLOBAL — LIVE DEPLOYMENT")
    print("="*60)
    print(f"\n  Public URL : {public_url}")
    print(f"  Local URL  : http://localhost:5000")
    print("\n  Default login: admin / admin123")
    print("  Or register a new account at the URL above")
    print("\n  Press Ctrl+C to stop the server")
    print("="*60 + "\n")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
        ngrok.disconnect(public_url)

except Exception as e:
    print(f"\n  ngrok tunnel failed: {e}")
    print("\n" + "="*60)
    print("  SOLARPO GLOBAL — LOCAL SERVER")
    print("="*60)
    print(f"\n  Local URL  : http://localhost:5000")
    print("\n  Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Shutting down...")
