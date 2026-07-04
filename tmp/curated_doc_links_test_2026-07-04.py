# -*- coding: utf-8 -*-
"""Local test for the curated official datasheet/literature URL seed
(_seed_curated_doc_links, 2026-07-04). Verifies:
  1. Every curated (brand,model) present in the catalogue gets BOTH urls.
  2. The doc-redirect resolver 302s STRAIGHT to the curated url (no crawl).
  3. Additive: a pre-existing supplier url is NOT overwritten.
  4. All curated urls are https + official-looking (no google/aggregator).
Run after patch_curated_doc_links.py has been applied."""
import os, sys
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_curated_links.db")
try: os.remove(os.environ["DB_PATH"])
except OSError: pass

import web_app
app = web_app.app; app.config["WTF_CSRF_ENABLED"] = False
fails = []
def ck(n, c, e=''):
    print(("PASS" if c else "FAIL"), "-", n, e)
    if not c: fails.append(n)

# Cold-start seed builds the catalogue; the patched chain runs the curated seed.
web_app._ensure_marketplace_tables()

CUR = web_app._CURATED_DOC_LINKS
ck("curated list is non-empty", len(CUR) >= 30, "n=%d" % len(CUR))

# Every curated url must be https, manufacturer-ish (not a search/aggregator).
BAD = ("google.com/search", "bing.com", "duckduckgo", "alibaba", "amazon.",
       "made-in-china", "aliexpress", "enfsolar")
bad_urls = []
for brand, model, ds, lit in CUR:
    for u in (ds, lit):
        if not (u or "").startswith("https://") or any(b in (u or "").lower() for b in BAD):
            bad_urls.append((brand, model, u))
ck("all curated urls https + non-aggregator", not bad_urls, str(bad_urls[:4]))

# For every curated pair that matches a catalogue row, both cols are populated.
matched = 0; missing = []
with web_app.get_db() as c:
    for brand, model, ds, lit in CUR:
        r = c.execute("SELECT id, datasheet_url, literature_url FROM equipment_catalog "
                      "WHERE LOWER(COALESCE(brand,''))=LOWER(?) AND LOWER(COALESCE(model,''))=LOWER(?)",
                      (brand, model)).fetchone()
        if not r:
            continue  # product not in this build's sample set -> skip
        matched += 1
        d = dict(r)
        if not (d.get("datasheet_url") or "").strip() or not (d.get("literature_url") or "").strip():
            missing.append((brand, model))
ck("curated rows matched at least 30 catalogue products", matched >= 30, "matched=%d" % matched)
ck("every matched curated row has BOTH urls", not missing, str(missing[:5]))

# Resolver 302s straight to the curated datasheet (no crawl needed).
def _no_crawl(*a, **k):
    raise AssertionError("crawler must NOT run for a curated product")
web_app._find_links_for = _no_crawl
cl = app.test_client()
with web_app.get_db() as c:
    # pick a curated row that exists in this build
    pick = None
    for brand, model, ds, lit in CUR:
        r = c.execute("SELECT id FROM equipment_catalog WHERE LOWER(COALESCE(brand,''))=LOWER(?) "
                      "AND LOWER(COALESCE(model,''))=LOWER(?)", (brand, model)).fetchone()
        if r: pick = (dict(r)["id"], ds, lit); break
ck("found a curated product to probe", pick is not None)
if pick:
    pid, ds, lit = pick
    r = cl.get(f"/marketplace/product/{pid}/doc/datasheet")
    ck("curated datasheet -> 302", r.status_code == 302, r.status_code)
    ck("302 target is the curated datasheet url", r.headers.get("Location") == ds, r.headers.get("Location"))
    r = cl.get(f"/marketplace/product/{pid}/doc/literature")
    ck("302 target is the curated literature url", r.headers.get("Location") == lit, r.headers.get("Location"))

# Additive: a supplier url already present must not be overwritten by re-seed.
with web_app.get_db() as c:
    c.execute("UPDATE equipment_catalog SET datasheet_url='https://supplier.example/keep.pdf' "
              "WHERE id=?", (pick[0],))
web_app._seed_curated_doc_links()
with web_app.get_db() as c:
    keep = dict(c.execute("SELECT datasheet_url FROM equipment_catalog WHERE id=?", (pick[0],)).fetchone())
ck("re-seed does NOT overwrite an existing supplier url",
   keep["datasheet_url"] == "https://supplier.example/keep.pdf", keep["datasheet_url"])

print("=== CURATED DOC LINKS:", "ALL PASS" if not fails else "FAIL " + str(fails), "===")
sys.exit(1 if fails else 0)
