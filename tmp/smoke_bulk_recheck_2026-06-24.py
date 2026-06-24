"""Smoke test for the bulk catalogue recheck (2026-06-24)."""
import os, sys

os.environ.setdefault("DB_PATH", "tmp/smoke_bulk.db")
os.environ.setdefault("SECRET_KEY", "smoke-bulk")
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


# Auth-gate test via Flask test client.
print("\n[routes] auth gates")
web_app.app.config["TESTING"] = True
client = web_app.app.test_client()

r = client.get("/admin/marketplace/recheck", follow_redirects=False)
check("GET picker requires admin", r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")

r = client.post("/admin/marketplace/recheck",
                data={"_csrf": "x", "category_id": "1", "currency": "GHS", "cap": "10"},
                follow_redirects=False)
check("POST recheck requires admin", r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")

r = client.get("/admin/marketplace/recheck/1/review", follow_redirects=False)
check("GET review requires admin", r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")

r = client.post("/admin/marketplace/recheck/1/apply",
                data={"_csrf": "x"}, follow_redirects=False)
check("POST apply requires admin", r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")


# Verify route registration -- names exist in url_map.
print("\n[routes] registration")
url_map = web_app.app.url_map
endpoints = {r.endpoint for r in url_map.iter_rules()}
for expected in (
    "admin_marketplace_recheck",
    "admin_marketplace_recheck_review",
    "admin_marketplace_recheck_apply",
):
    check(f"endpoint registered: {expected}", expected in endpoints)


# Verify the helper imports cleanly (no circular).
print("\n[imports] reuse from new_recheck_prices_routes")
from new_recheck_prices_routes import _recheck_build_prompt, _recheck_country_for
country, _ = _recheck_country_for("GHS")
check("country lookup works", country == "Ghana", f"got {country}")

# Build a prompt using the reused helper -- the same one bulk-recheck calls.
items = [{"id": 1, "name": "Test cable", "spec": "PVC",
          "brand": "Tridem", "unit": "m", "current_price": 25.0}]
p = _recheck_build_prompt(items, "Ghana", "GHS")
check("3-quote prompt builds", "THREE" in p or "three" in p.lower())


print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
