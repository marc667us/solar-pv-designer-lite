# -*- coding: utf-8 -*-
"""Local test for the on-demand doc-link resolver (owner 2026-07-04).
Cases:
  1. product WITH a saved datasheet_url -> 302 straight to it (no crawl).
  2. product WITHOUT urls -> runs finder (monkeypatched), caches BOTH, 302s to it.
  3. same product clicked again -> served from cache (no second crawl).
  4. product already crawled-but-empty (links_checked_at set) -> Google search fallback.
  5. unknown kind -> 404.
Uses the Flask test client + a monkeypatched _find_links_for (no network)."""
import os, sys
REPO = r"C:\Users\USER\Desktop\solar-pv-designer-lite"
os.chdir(REPO); sys.path.insert(0, REPO)
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "y")
os.environ["DB_PATH"] = os.path.join(REPO, "tmp", "_doc_redirect.db")
try: os.remove(os.environ["DB_PATH"])
except OSError: pass

import web_app
app = web_app.app; app.config["WTF_CSRF_ENABLED"] = False

fails = []
def ck(n, c, e=''):
    print(("PASS" if c else "FAIL"), "-", n, e);
    if not c: fails.append(n)

# Ensure catalog columns + a couple of products.
web_app._ensure_marketplace_tables()
try: web_app._ensure_product_link_columns()
except Exception: pass
with web_app.get_db() as c:
    c.execute("DELETE FROM equipment_catalog")   # deterministic clean slate
    c.execute("INSERT INTO equipment_catalog (name, category, brand, model, datasheet_url, literature_url) "
              "VALUES (?,?,?,?,?,?)", ("Saved Widget", "test", "Eaton", "MEM3", "https://example.com/saved.pdf", ""))
    pid_saved = c.execute("SELECT id FROM equipment_catalog WHERE name='Saved Widget'").fetchone()[0]
    c.execute("INSERT INTO equipment_catalog (name, category, brand, model) VALUES (?,?,?,?)",
              ("Fresh Widget", "test", "Schneider", "SW9"))
    pid_fresh = c.execute("SELECT id FROM equipment_catalog WHERE name='Fresh Widget'").fetchone()[0]
    c.execute("INSERT INTO equipment_catalog (name, category, brand, model, links_checked_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
              ("Empty Widget", "test", "NoName", "NN1"))
    pid_empty = c.execute("SELECT id FROM equipment_catalog WHERE name='Empty Widget'").fetchone()[0]
    c.execute("INSERT INTO equipment_catalog (name, category, brand, model, datasheet_url) "
              "VALUES (?,?,?,?,?)", ("Evil Widget", "test", "X", "X1", "javascript:alert(1)"))
    pid_evil = c.execute("SELECT id FROM equipment_catalog WHERE name='Evil Widget'").fetchone()[0]
    c.execute("INSERT INTO equipment_catalog (name, category, brand, model) VALUES (?,?,?,?)",
              ("Anon Widget", "test", "AnonBrand", "AW1"))
    pid_anon = c.execute("SELECT id FROM equipment_catalog WHERE name='Anon Widget'").fetchone()[0]
    uid = c.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

cl = app.test_client()
# On-demand crawl now requires a signed-in requester (anti-abuse). Log in.
with cl.session_transaction() as s:
    s["user_id"] = uid; s["_csrf"] = "tok"

# Case 1: saved URL -> 302 to it, no crawl.
calls = {"n": 0}
def fake_finder(name, brand="", model=""):
    calls["n"] += 1
    return ("https://cdn.example.com/%s-datasheet.pdf" % (model or "x"),
            "https://cdn.example.com/%s-brochure.pdf" % (model or "x"))
web_app._find_links_for = fake_finder

r = cl.get(f"/marketplace/product/{pid_saved}/doc/datasheet")
ck("1: saved datasheet -> 302", r.status_code == 302, r.status_code)
ck("1: 302 target is the saved url", r.headers.get("Location") == "https://example.com/saved.pdf", r.headers.get("Location"))
ck("1: no crawl for saved url", calls["n"] == 0, calls["n"])

# Case 2: fresh product -> crawl once, cache both, 302 to found datasheet.
r = cl.get(f"/marketplace/product/{pid_fresh}/doc/datasheet")
ck("2: fresh datasheet -> 302", r.status_code == 302, r.status_code)
ck("2: 302 to crawled datasheet", (r.headers.get("Location") or "").endswith("SW9-datasheet.pdf"), r.headers.get("Location"))
ck("2: crawl happened once", calls["n"] == 1, calls["n"])
with web_app.get_db() as c:
    rr = dict(c.execute("SELECT datasheet_url, literature_url, links_checked_at FROM equipment_catalog WHERE id=?", (pid_fresh,)).fetchone())
ck("2: datasheet cached", rr["datasheet_url"].endswith("SW9-datasheet.pdf"), rr["datasheet_url"])
ck("2: literature ALSO cached (both kinds)", rr["literature_url"].endswith("SW9-brochure.pdf"), rr["literature_url"])
ck("2: links_checked_at stamped", bool((rr["links_checked_at"] or "").strip()), rr["links_checked_at"])

# Case 3: same fresh product literature -> served from cache, NO second crawl.
r = cl.get(f"/marketplace/product/{pid_fresh}/doc/literature")
ck("3: cached literature -> 302", r.status_code == 302, r.status_code)
ck("3: 302 to cached brochure", (r.headers.get("Location") or "").endswith("SW9-brochure.pdf"), r.headers.get("Location"))
ck("3: no second crawl (served from cache)", calls["n"] == 1, calls["n"])

# Case 4: already-checked empty product -> Google search fallback, no crawl.
r = cl.get(f"/marketplace/product/{pid_empty}/doc/datasheet")
ck("4: checked-empty -> 302 fallback", r.status_code == 302, r.status_code)
ck("4: fallback is a filetype:pdf search", "google.com/search" in (r.headers.get("Location") or "") and "filetype" in (r.headers.get("Location") or ""), r.headers.get("Location"))
ck("4: no crawl for already-checked", calls["n"] == 1, calls["n"])

# Case 5: unknown kind -> 404.
r = cl.get(f"/marketplace/product/{pid_saved}/doc/bogus")
ck("5: bad kind -> 404", r.status_code == 404, r.status_code)

# Case 6: stored non-http(s) URL (javascript:) -> NOT redirected; search fallback.
r = cl.get(f"/marketplace/product/{pid_evil}/doc/datasheet")
loc = r.headers.get("Location") or ""
ck("6: evil scheme -> 302 fallback", r.status_code == 302, r.status_code)
ck("6: NOT redirected to javascript: url", not loc.lower().startswith("javascript:"), loc)
ck("6: fallback is a search", "google.com/search" in loc, loc)

# Case 7: ANONYMOUS requester (no session) -> no crawl; search fallback.
anon = app.test_client()
calls_before = calls["n"]
r = anon.get(f"/marketplace/product/{pid_anon}/doc/datasheet")
ck("7: anon fresh -> 302 (no crawl)", r.status_code == 302, r.status_code)
ck("7: anon did NOT trigger a crawl", calls["n"] == calls_before, calls["n"])
ck("7: anon gets search fallback", "google.com/search" in (r.headers.get("Location") or ""), r.headers.get("Location"))
with web_app.get_db() as c:
    anon_checked = c.execute("SELECT links_checked_at FROM equipment_catalog WHERE id=?", (pid_anon,)).fetchone()[0]
ck("7: anon click did NOT stamp/poison the product", not (anon_checked or ""), anon_checked)

print("=== DOC REDIRECT ON-DEMAND:", "ALL PASS" if not fails else "FAIL " + str(fails), "===")
sys.exit(1 if fails else 0)
