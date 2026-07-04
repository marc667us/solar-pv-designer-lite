# -*- coding: utf-8 -*-
"""Local test for slice 1 -- solar-farm BOQ gap marketplace seed.
Verifies:
  1. New categories (circuit_breakers, plant_control) exist + appear in registries.
  2. IPS + Battery Chargers added to power_system subcategories.
  3. All 31 gap products seeded with correct category_id + subcategory + price.
  4. Prices are sane (Ghana GHS = price_usd * 11.2 within realistic bands).
  5. Idempotent: re-seeding does not duplicate.
Run after patch_solar_farm_gap_seed.py is applied."""
import os, sys
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_sf_gap.db")
try: os.remove(os.environ["DB_PATH"])
except OSError: pass

import web_app
fails = []
def ck(n, c, e=''):
    print(("PASS" if c else "FAIL"), "-", n, e)
    if not c: fails.append(n)

web_app._ensure_marketplace_tables()

# 1. registries extended
codes = {row[0] for row in web_app._MARKETPLACE_CATEGORIES}
ck("circuit_breakers category registered", "circuit_breakers" in codes)
ck("plant_control category registered", "plant_control" in codes)
ck("circuit_breakers has subcats", len(web_app._MARKETPLACE_SUBCATEGORIES.get("circuit_breakers", [])) >= 8)
ck("plant_control has subcats", len(web_app._MARKETPLACE_SUBCATEGORIES.get("plant_control", [])) >= 6)
ck("IPS added to power_system subcats", "IPS" in web_app._MARKETPLACE_SUBCATEGORIES.get("power_system", []))
ck("circuit_breakers has default unit", web_app._MARKETPLACE_DEFAULT_UNIT.get("circuit_breakers") == "No.")
ck("circuit_breakers has spec fields", len(web_app._MARKETPLACE_SPEC_FIELDS.get("circuit_breakers", [])) >= 5)

# 2. categories persisted to product_categories
with web_app.get_db() as c:
    pc = {r["code"]: r["id"] for r in c.execute("SELECT id, code FROM product_categories").fetchall()}
ck("circuit_breakers in product_categories", "circuit_breakers" in pc)
ck("plant_control in product_categories", "plant_control" in pc)

# 3. all 31 products seeded with right category + price
GHS = web_app._CURRENCY_RATES_FROM_USD.get("GHS", 11.2)
with web_app.get_db() as c:
    seeded = 0; miscat = []; bad_price = []
    for (code, sub, name, brand, model, spec, unit, price_usd, lt) in web_app._SOLAR_FARM_GAP_PRODUCTS:
        r = c.execute("SELECT category_id, subcategory, price_usd, is_public_visible "
                      "FROM equipment_catalog WHERE brand=? AND model=?", (brand, model)).fetchone()
        if not r:
            miscat.append(("MISSING", brand, model)); continue
        d = dict(r); seeded += 1
        if d["category_id"] != pc.get(code): miscat.append(("CAT", brand, model, d["category_id"], pc.get(code)))
        if d["subcategory"] != sub: miscat.append(("SUB", brand, model, d["subcategory"]))
        ghs = (d["price_usd"] or 0) * GHS
        if ghs <= 0: bad_price.append((brand, model, ghs))
        if not d["is_public_visible"]: miscat.append(("HIDDEN", brand, model))
ck("all 31 gap products seeded", seeded == len(web_app._SOLAR_FARM_GAP_PRODUCTS), "seeded=%d" % seeded)
ck("every product has correct category_id/subcategory/visibility", not miscat, str(miscat[:4]))
ck("every product has a positive GHS price", not bad_price, str(bad_price[:4]))

# spot-check a couple of GHS prices are in a realistic band
with web_app.get_db() as c:
    mcb = dict(c.execute("SELECT price_usd FROM equipment_catalog WHERE model='A9F74116'").fetchone())  # 1P 16A MCB
    acb = dict(c.execute("SELECT price_usd FROM equipment_catalog WHERE model='MTZ225N1'").fetchone())  # 2500A ACB
    scada = dict(c.execute("SELECT price_usd FROM equipment_catalog WHERE model='ECOSTRUXURE-SCADA'").fetchone())
ck("MCB 1P 16A GHS in 40-150 band", 40 <= mcb["price_usd"] * GHS <= 150, "%.0f" % (mcb["price_usd"] * GHS))
ck("ACB 2500A GHS in 50k-150k band", 50000 <= acb["price_usd"] * GHS <= 150000, "%.0f" % (acb["price_usd"] * GHS))
ck("SCADA GHS in 400k-1.5M band", 400000 <= scada["price_usd"] * GHS <= 1500000, "%.0f" % (scada["price_usd"] * GHS))

# 4. idempotent -- re-seed, count unchanged
with web_app.get_db() as c:
    before = c.execute("SELECT COUNT(*) FROM equipment_catalog").fetchone()[0]
web_app._seed_solar_farm_gap_products()
with web_app.get_db() as c:
    after = c.execute("SELECT COUNT(*) FROM equipment_catalog").fetchone()[0]
ck("re-seed does not duplicate", before == after, "before=%d after=%d" % (before, after))

print("=== SOLAR-FARM GAP SEED:", "ALL PASS" if not fails else "FAIL " + str(fails), "===")
sys.exit(1 if fails else 0)
