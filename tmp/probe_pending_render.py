"""Render /admin/marketplace/pending with seeded pending supplier + product."""
import os, sys, re

DB = "tmp/probe_pending.db"
try: os.remove(DB)
except FileNotFoundError: pass
os.environ["DB_PATH"] = DB
os.environ["SECRET_KEY"] = "x"
os.environ["SOLARPRO_ADMIN_PASSWORD"] = "x"
os.environ["SOLARPRO_OWNER_PASSWORD"] = "x"
for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OLLAMA_URL"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.abspath("."))
import web_app
print("imported web_app")

# Make sure marketplace tables exist.
try:
    web_app._ensure_marketplace_tables()
    web_app._ensure_supplier_schema()
except Exception as e:
    print(f"ensure tables: {e}")

# Seed admin (id=1) + a submitter (id=2).
with web_app.get_db() as c:
    try: c.execute("DELETE FROM users")
    except Exception: pass
    c.execute(
        "INSERT INTO users (id, username, email, password_hash, is_admin, plan, role, created_at) "
        "VALUES (1, 'admin', 'admin@solarpro.test', 'x', 1, 'enterprise', 'admin', CURRENT_TIMESTAMP)"
    )
    c.execute(
        "INSERT INTO users (id, username, email, password_hash, is_admin, plan, role, created_at) "
        "VALUES (2, 'submitter1', 'submitter1@solarpro.test', 'x', 0, 'free', 'supplier_admin', CURRENT_TIMESTAMP)"
    )

    # Seed a pending supplier owned by user 2.
    c.execute(
        "INSERT INTO suppliers (name, country, contact_name, phone, email, website, "
        "categories, user_id, is_verified, is_active) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("Tridem Test Co", "Ghana", "Ada Test", "+233", "ada@tridem.test",
         "tridem.test", "cables,sockets", 2, 0, 1),
    )

    # Seed a pending product submitted by user 2.
    c.execute(
        "INSERT INTO equipment_catalog (category, name, brand, model, spec, unit, "
        "price_usd, supplier_id, lead_time_days, notes, is_active, is_verified, "
        "is_public_visible, submitted_by_user_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        ("cables", "4mm Armoured PVC", "Tridem", "TR4-A", "LV 600/1000V",
         "m", 25.0, 0, 30, "", 1, 0, 0, 2),
    )

client = web_app.app.test_client()
with client.session_transaction() as sess:
    sess["user_id"] = 1

print("\n--- GET /admin/marketplace/pending")
r = client.get("/admin/marketplace/pending")
print(f"status: {r.status_code}")
body = r.get_data(as_text=True)
print(f"body length: {len(body)}")

errors = []
def check(label, ok, detail=""):
    s = "PASS" if ok else "FAIL"
    print(f"  [{s}] {label}{(' -- ' + detail) if detail else ''}")
    if not ok:
        errors.append(label)

check("HTTP 200", r.status_code == 200, f"got {r.status_code}")
check("supplier 'Tridem Test Co' in body", "Tridem Test Co" in body)
check("submitter email 'submitter1@solarpro.test' in body",
      "submitter1@solarpro.test" in body)
check("pending product '4mm Armoured PVC' in body", "4mm Armoured PVC" in body)
check("Submitted by column header", "Submitted by" in body)
check("Sent at column header", "Sent at" in body)
check("'Edit' button text appears", "> Edit" in body or "Edit</a>" in body or "Edit<" in body or " Edit\n" in body or "Edit&nbsp" in body or ">Edit" in body or "Edit</button>" in body)
check("'Open' button text appears", " Open" in body or "Open</a>" in body)
check("approve/reject buttons present", "Approve" in body and "Reject" in body)

print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)}")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
