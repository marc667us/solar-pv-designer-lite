"""Authenticated BFS crawler for solarpro.

Goal: surface every 500 and unexpected 404 across the app so we can
fix them. Uses the Flask test client against a temp SQLite DB so the
crawl is fast and deterministic. Seeds enough data (project, BOM,
BOQ project, supplier) that most routes have something to render.
"""

from __future__ import annotations

import os, sys, re, tempfile
from html.parser import HTMLParser

TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False); TMP.close()
os.environ["SOLARPRO_ADMIN_PASSWORD"] = "smoke-admin"
os.environ["SOLARPRO_OWNER_PASSWORD"] = "smoke-owner"
os.environ["SECRET_KEY"] = "smoke-secret"
for k in ("BREVO_API_KEY","RESEND_API_KEY","ANTHROPIC_API_KEY","OPENROUTER_API_KEY","DATABASE_URL"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import web_app
web_app.DB_PATH = TMP.name
web_app.init_db()
web_app._ensure_marketplace_tables()
web_app._ensure_bom_tables()
web_app._ensure_bom_rates_table()
with web_app.get_db() as _c:
    for s in [
        "ALTER TABLE equipment_catalog ADD COLUMN is_verified INTEGER DEFAULT 1",
        "ALTER TABLE suppliers          ADD COLUMN user_id INTEGER DEFAULT 0",
        "ALTER TABLE suppliers          ADD COLUMN is_verified INTEGER DEFAULT 1",
        "ALTER TABLE users              ADD COLUMN role TEXT DEFAULT ''",
    ]:
        try: _c.execute(s)
        except Exception: pass
from new_boq_hierarchy_schema import ensure_boq_hierarchy_schema
ensure_boq_hierarchy_schema(web_app.get_db)
app = web_app.app
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False


class _Anchors(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = set()
        self.actions = set()
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.hrefs.add(d["href"])
        if tag == "form" and d.get("action"):
            self.actions.add((d.get("method","GET").upper(), d["action"]))


def _csrf(client, path):
    r = client.get(path)
    m = re.search(rb'name="_csrf"\s+value="([^"]+)"', r.data)
    return m.group(1).decode() if m else ""


SKIP_PREFIXES = (
    "javascript:", "mailto:", "tel:", "#",
    "http://", "https://", "//",
)
SKIP_SUBSTR = (
    "/logout", "/delete", "/revoke", "/destroy",
    "/paystack/", "/stripe/", "/webhook",
    "/api/health", "/api/ping", "/metrics",
    "/static/", "/uploads/",  # static + uploads not interesting
    "?download=", "/export",  # exports may stream binaries -- still ok but slow
    "/ops/", "/admin/ops/",  # admin ops side-effects
)
# Don't try to follow forms POSTed by the user; the crawler only walks GETs.

results = {}     # url -> (status, where_found)
visited = set()
queue = []

def enqueue(url, src="seed"):
    if url in visited: return
    if not url.startswith("/"): return
    if any(url.startswith(p) for p in SKIP_PREFIXES): return
    if any(s in url for s in SKIP_SUBSTR): return
    if url in queue: return
    queue.append((url, src))


with app.test_client() as c:
    # Log in as the seeded marc667us paid-plan user.
    tok = _csrf(c, "/login")
    r = c.post("/login", data={"username":"marc667us","password":"smoke-owner","_csrf":tok}, follow_redirects=False)
    assert r.status_code in (302, 303), f"login failed {r.status_code}"

    # Seed minimal data so parameterised routes have something to render.
    # 1) Create a solar project
    tok = _csrf(c, "/projects/new")
    c.post("/projects/new", data={"_csrf":tok,"name":"CrawlProj","region":"Greater Accra","country":"GH","currency":"GHS"})
    with web_app.get_db() as cc:
        prow = cc.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()
        pid = prow["id"] if prow else None
    print(f"seeded solar project id={pid}")

    # 2) Create a BOM
    tok = _csrf(c, "/boms/new")
    c.post("/boms/new", data={"_csrf":tok,"title":"CrawlBOM","project_name":"CrawlProj","client_name":"Crawl"})
    with web_app.get_db() as cc:
        bomrow = cc.execute("SELECT id FROM marketplace_boms ORDER BY id DESC LIMIT 1").fetchone()
        bom_id = bomrow["id"] if bomrow else None
    print(f"seeded BOM id={bom_id}")

    # 3) Create a BOQ project + building + floor
    tok = _csrf(c, "/boq-projects/new")
    c.post("/boq-projects/new", data={"_csrf":tok,"project_name":"CrawlBOQ","project_type":"single_building"})
    with web_app.get_db() as cc:
        bqrow = cc.execute("SELECT id FROM boq_projects ORDER BY id DESC LIMIT 1").fetchone()
        boqpid = bqrow["id"] if bqrow else None
    print(f"seeded BOQ project id={boqpid}")
    if boqpid:
        tok = _csrf(c, f"/boq-projects/{boqpid}/buildings/new")
        c.post(f"/boq-projects/{boqpid}/buildings/new", data={
            "_csrf":tok,"building_name":"BLK","primary_purpose":"commercial",
            "purpose_subtype":"Office","number_of_floors":"1",
        })
        with web_app.get_db() as cc:
            bidrow = cc.execute("SELECT id FROM boq_buildings ORDER BY id DESC LIMIT 1").fetchone()
            fidrow = cc.execute("SELECT id FROM boq_floors ORDER BY id DESC LIMIT 1").fetchone()
        bid_ = bidrow["id"] if bidrow else None
        fid_ = fidrow["id"] if fidrow else None
        print(f"seeded BOQ building={bid_} floor={fid_}")

    # Seed root URLs to crawl from
    for u in [
        "/dashboard", "/account",
        "/boms", "/boq-projects", "/rfqs",
        "/marketplace", "/procurement-center", "/procurement",
        "/admin", "/admin/operations", "/admin/logs",
        "/admin/marketplace", "/admin/marketplace/pending",
        "/admin/library/pending",
        "/support", "/upgrade", "/referrals",
    ]:
        enqueue(u, "seed")
    if pid:
        for u in [f"/project/{pid}/report/boq", f"/project/{pid}/report/pv", f"/project/{pid}/report/cable", f"/project/{pid}/report/economic", f"/project/{pid}/report/installation", f"/myproject"]:
            enqueue(u, "seed")
    if bom_id:
        for u in [f"/boms/{bom_id}", f"/boms/{bom_id}/boq", f"/boms/{bom_id}/rate-buildup"]:
            enqueue(u, "seed")
    if boqpid:
        enqueue(f"/boq-projects/{boqpid}", "seed")
        enqueue(f"/boq-projects/{boqpid}/summary", "seed")
        enqueue(f"/boq-projects/{boqpid}/boq", "seed")
        enqueue(f"/boq-projects/{boqpid}/boq?view=internal", "seed")
        enqueue(f"/boq-projects/{boqpid}/boq.pdf", "seed")
        enqueue(f"/boq-projects/{boqpid}/boq.xlsx", "seed")
        if bid_ and fid_:
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}", "seed")
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}/floors/{fid_}", "seed")
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}/floors/{fid_}/summary", "seed")
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}/floors/{fid_}/from-template", "seed")
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}/floors/{fid_}/from-template/auditorium-1ugls", "seed")
            enqueue(f"/boq-projects/{boqpid}/buildings/{bid_}/floors/{fid_}/section/new", "seed")

    # BFS crawl
    LIMIT = 200
    while queue and len(visited) < LIMIT:
        url, src = queue.pop(0)
        if url in visited: continue
        visited.add(url)
        try:
            r = c.get(url, follow_redirects=False)
            status = r.status_code
        except Exception as e:
            status = f"EXC: {e}"
            results[url] = (status, src)
            continue
        results[url] = (status, src)
        # Parse hrefs for further GET crawling (only on 200 responses).
        if status == 200 and r.mimetype and "html" in r.mimetype:
            try:
                p = _Anchors()
                p.feed(r.data.decode("utf-8", "replace"))
                for h in p.hrefs:
                    # Strip fragments
                    if "#" in h: h = h.split("#",1)[0]
                    if not h: continue
                    enqueue(h, url)
            except Exception:
                pass

    print(f"\n=== Crawl summary ===")
    print(f"visited: {len(visited)}")
    by_status = {}
    for u, (s, src) in results.items():
        by_status.setdefault(s, []).append((u, src))
    for s in sorted(by_status.keys(), key=lambda x: (str(type(x)), str(x))):
        print(f"  {s}: {len(by_status[s])}")

    print(f"\n=== 5xx ===")
    for s, urls in by_status.items():
        if isinstance(s, int) and s >= 500:
            for u, src in urls:
                print(f"  {s}  {u}  (from {src})")
    print(f"\n=== 404 ===")
    for u, src in by_status.get(404, []):
        print(f"  {u}  (from {src})")
    # Any exceptions
    for s, urls in by_status.items():
        if isinstance(s, str) and s.startswith("EXC"):
            for u, src in urls:
                print(f"  EXC {u}  (from {src})  {s}")

try: os.unlink(TMP.name)
except: pass
