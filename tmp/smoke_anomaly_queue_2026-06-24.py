"""Smoke test for the anomaly queue (2026-06-24)."""
import os, sys

os.environ.setdefault("DB_PATH", "tmp/smoke_anomaly.db")
os.environ.setdefault("SECRET_KEY", "smoke-anomaly")
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "x")
for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OLLAMA_URL"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.abspath("."))
print("Importing web_app...")
import web_app  # noqa
print("OK")

errors = []
def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{(' -- ' + detail) if detail else ''}")
    if not ok:
        errors.append(label)


print("\n[schema] new columns exist")
from new_catalogue_pricing_routes import (_ensure_pricing_tables,
    _record_price_history, _resolve_user_email)
_ensure_pricing_tables(web_app.get_db, lambda: False)
with web_app.get_db() as c:
    cols = c.execute("PRAGMA table_info(equipment_catalog_price_history)").fetchall()
    names = {r["name"] for r in cols}
    check("submitted_by_email column", "submitted_by_email" in names)
    check("decided_at column", "decided_at" in names)
    check("decided_by_user_id column", "decided_by_user_id" in names)


print("\n[helper] _record_price_history with status=pending + email")
hid = _record_price_history(
    web_app.get_db, 99, 10.0, 15.0, "GHS", 180, "test-source",
    "anomaly test", 0, status="pending",
    submitted_by_email="test@example.com",
)
check("returns a row id", hid > 0, f"got {hid}")
with web_app.get_db() as c:
    row = c.execute(
        "SELECT approval_status, submitted_by_email FROM equipment_catalog_price_history "
        "WHERE id=?", (hid,),
    ).fetchone()
    check("row has pending status", row and row["approval_status"] == "pending")
    check("row has email", row and row["submitted_by_email"] == "test@example.com")


print("\n[routes] auth + registration")
web_app.app.config["TESTING"] = True
client = web_app.app.test_client()

url_map = web_app.app.url_map
endpoints = {r.endpoint for r in url_map.iter_rules()}
for ep in ("admin_marketplace_anomalies", "admin_marketplace_anomaly_decide"):
    check(f"endpoint registered: {ep}", ep in endpoints)

r = client.get("/admin/marketplace/anomalies", follow_redirects=False)
check("GET queue requires admin (302/403)",
      r.status_code in (302, 303, 401, 403), f"got {r.status_code}")

r = client.post("/admin/marketplace/anomalies/1/decide",
                data={"_csrf": "x", "decision": "approve"},
                follow_redirects=False)
check("POST decide requires admin",
      r.status_code in (302, 303, 401, 403), f"got {r.status_code}")


print("\n[context_processor] pending_anomaly_count injected")
with web_app.app.test_request_context("/"):
    # Render a tiny template that uses the variable
    from flask import render_template_string
    out = render_template_string("{{ pending_anomaly_count or 'missing' }}")
    check("pending_anomaly_count exposed",
          out.strip().isdigit() or out.strip() == "0",
          f"got {out!r}")


print("\n[fix] /admin/marketplace no longer has @require_role")
r = client.get("/admin/marketplace", follow_redirects=False)
# Without a session/admin we expect 302 (redirect to /login), NOT 401 missing-bearer.
check("/admin/marketplace returns 302 not 401",
      r.status_code in (302, 303, 403), f"got {r.status_code}")


print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
