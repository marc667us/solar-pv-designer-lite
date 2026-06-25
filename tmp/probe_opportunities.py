"""End-to-end render: log in as admin, hit /admin/opportunities, surface any
runtime errors (template + fetch path)."""
import os, sys, traceback

DB = "tmp/probe_opps.db"
try: os.remove(DB)
except FileNotFoundError: pass
os.environ["DB_PATH"] = DB
os.environ["SECRET_KEY"] = "x"
os.environ["SOLARPRO_ADMIN_PASSWORD"] = "x"
os.environ["SOLARPRO_OWNER_PASSWORD"] = "x"

sys.path.insert(0, os.path.abspath("."))
import web_app
print("imported web_app")

# Seed admin id=1
with web_app.get_db() as c:
    try: c.execute("DELETE FROM users")
    except Exception: pass
    c.execute("INSERT INTO users (id, username, email, password_hash, is_admin, plan, role, created_at) VALUES (1, 'admin', 'admin@test', 'x', 1, 'enterprise', 'admin', CURRENT_TIMESTAMP)")

client = web_app.app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = 1

# Force empty cache so fetch runs.
try:
    web_app._OPPS_CACHE["items"] = []
    web_app._OPPS_CACHE["fetched_at"] = 0
except AttributeError:
    pass

print("\n--- GET /admin/opportunities (cold, will fetch RSS) ---")
try:
    r = client.get("/admin/opportunities")
    print(f"status: {r.status_code}")
    body = r.get_data(as_text=True)
    print(f"body length: {len(body)}")
    # Search for error markers
    for marker in ("Traceback", "Internal Server Error", "{{ ", "}}}", "UndefinedError", "TypeError", "AttributeError", "no items", "No opportunities", "empty"):
        if marker.lower() in body.lower():
            print(f"  marker found: {marker!r}")
except Exception as e:
    print(f"REQUEST FAILED: {e!r}")
    traceback.print_exc()

# Also check the cached state.
try:
    items = web_app._OPPS_CACHE.get("items") or []
    print(f"cache size after fetch: {len(items)}")
    if items:
        print(f"first item: {items[0]}")
except Exception as e:
    print(f"cache check failed: {e!r}")

print("\n--- GET /admin/opportunities?refresh=1 (force re-fetch) ---")
try:
    r = client.get("/admin/opportunities?refresh=1")
    print(f"status: {r.status_code}, body={len(r.get_data())} bytes")
except Exception as e:
    print(f"refresh failed: {e!r}")
    traceback.print_exc()
