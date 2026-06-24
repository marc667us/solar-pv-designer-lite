"""Smoke test for B (3-quote Recheck) + C (Catalogue pricing) 2026-06-24."""
import os, sys

os.environ.setdefault("DB_PATH", "tmp/smoke_bc.db")
os.environ.setdefault("SECRET_KEY", "smoke-bc")
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


print("\n[B] 3-quote prompt build")
from new_recheck_prices_routes import _recheck_build_prompt, _recheck_parse

items = [{"id": 1, "name": "4mm cable", "spec": "PVC", "brand": "Tridem",
          "unit": "m", "current_price": 25.0}]
p = _recheck_build_prompt(items, "Ghana", "GHS")
check("prompt asks for THREE suppliers", "THREE" in p or "three" in p.lower())
check("prompt has quotes schema", '"quotes"' in p)
check("prompt mentions Tridem/Beta Stores", "Tridem" in p)


print("\n[B] parse 3-quote response")
raw = '''{"prices":[{"id":1,"price":27.5,"source":"avg of 3","confidence":"high",
"quotes":[{"supplier":"Tridem","price":25,"note":""},
{"supplier":"Beta Stores","price":28,"note":"online"},
{"supplier":"A-Life","price":29.5,"note":""}]}]}'''
parsed = _recheck_parse(raw)
check("3-quote parses", 1 in parsed and len(parsed[1].get("quotes", [])) == 3)
check("avg price preserved", abs(parsed[1]["price"] - 27.5) < 0.01)
check("quote 0 supplier = Tridem", parsed[1]["quotes"][0]["supplier"] == "Tridem")

# Parser falls back: if model only returns quotes (no avg), compute it.
raw2 = '''{"prices":[{"id":2,"price":0,"source":"3 quotes","confidence":"med",
"quotes":[{"supplier":"A","price":10,"note":""},{"supplier":"B","price":20,"note":""},
{"supplier":"C","price":30,"note":""}]}]}'''
parsed2 = _recheck_parse(raw2)
check("avg computed from quotes when missing",
      2 in parsed2 and abs(parsed2[2]["price"] - 20.0) < 0.01)


print("\n[B+C] pricing-schema bootstrap")
from new_catalogue_pricing_routes import (_ensure_pricing_tables,
    _record_catalog_quote, _record_price_history)
_ensure_pricing_tables(web_app.get_db, lambda: False)
# Verify tables exist
with web_app.get_db() as c:
    try:
        c.execute("INSERT INTO equipment_catalog_quotes (catalog_item_id, supplier_name, price_local, currency) VALUES (1, 'Test', 10.0, 'GHS')")
        c.execute("INSERT INTO equipment_catalog_price_history (catalog_item_id, old_price_usd, new_price_usd) VALUES (1, 5, 7)")
        check("both tables accept INSERT", True)
    except Exception as e:
        check("both tables accept INSERT", False, str(e))


print("\n[C] record_price_history + record_catalog_quote helpers")
_record_price_history(web_app.get_db, 42, 5.0, 7.5, "GHS", 90, "Tridem",
                      "monthly market review", 1, "approved")
_record_catalog_quote(web_app.get_db, 42, "Beta Stores", 0, 95.0, "GHS",
                      "online ref", True, 1, "proposed")
with web_app.get_db() as c:
    h = c.execute(
        "SELECT old_price_usd, new_price_usd, source FROM equipment_catalog_price_history "
        "WHERE catalog_item_id=42 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    check("history row written", h is not None and h["new_price_usd"] == 7.5)
    q = c.execute(
        "SELECT supplier_name, price_local, anomaly_flag FROM equipment_catalog_quotes "
        "WHERE catalog_item_id=42 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    check("quote row written", q is not None and q["supplier_name"] == "Beta Stores")
    check("anomaly flag set", q is not None and q["anomaly_flag"] == 1)


print("\n[routes] auth gates")
web_app.app.config["TESTING"] = True
client = web_app.app.test_client()
r = client.post("/admin/catalogue/1/update-price",
                data={"_csrf": "x", "new_price": "10"}, follow_redirects=False)
check("update-price requires admin (302/403)",
      r.status_code in (302, 303, 401, 403), f"got {r.status_code}")
r = client.get("/admin/catalogue/1/price-history", follow_redirects=False)
check("price-history requires admin",
      r.status_code in (302, 303, 401, 403), f"got {r.status_code}")


print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors: print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
