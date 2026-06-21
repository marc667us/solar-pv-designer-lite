# new_product_link_finder.py
# Web-crawl agent that finds Product Literature + Datasheet PDFs for
# products in equipment_catalog and saves the URLs onto the product row.
#
# Search strategy (zero-cost per the FOSS rule):
#   1. DuckDuckGo HTML endpoint (no API key needed)
#      https://html.duckduckgo.com/html/?q=...
#   2. Two queries per product:
#        <name> <brand> datasheet filetype:pdf
#        <name> <brand> brochure OR literature filetype:pdf
#   3. First non-aggregator PDF result wins.
#
# Politeness: 2-second sleep between requests, custom User-Agent that
# identifies the crawler, max 20 products per run (admin bulk mode).
#
# Schema additions (idempotent):
#   equipment_catalog.literature_url    VARCHAR(500) DEFAULT ''
#   equipment_catalog.datasheet_url     VARCHAR(500) DEFAULT ''
#   equipment_catalog.links_checked_at  TIMESTAMP                  -- when we last attempted lookup
#
# Routes:
#   POST /admin/agent/find-product-links              -- bulk, 20-product cap
#   POST /admin/agent/find-product-links/<int:pid>    -- single product
#   POST /supplier/products/<int:pid>/find-links      -- supplier self-service for their own product


# ---- Schema bootstrap (idempotent) ---------------------------------------

def _ensure_product_link_columns():
    """Add literature_url + datasheet_url + links_checked_at columns
    to equipment_catalog if not present. Works for both SQLite and
    Postgres."""
    is_pg = bool(os.environ.get("DATABASE_URL"))
    stmts_pg = [
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS literature_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS datasheet_url  VARCHAR(500) DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN IF NOT EXISTS links_checked_at TIMESTAMP",
    ]
    stmts_sqlite = [
        "ALTER TABLE equipment_catalog ADD COLUMN literature_url TEXT DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN datasheet_url  TEXT DEFAULT ''",
        "ALTER TABLE equipment_catalog ADD COLUMN links_checked_at TEXT",
    ]
    try:
        with get_db() as c:
            for s in (stmts_pg if is_pg else stmts_sqlite):
                try:
                    c.execute(s)
                except Exception:
                    pass
    except Exception:
        pass


# ---- Crawler ------------------------------------------------------------

_PRODUCT_LINK_UA = "SolarProBOQ/1.0 (+https://solarpro.aiappinvent.com; product-link-finder)"

# Domains we DON'T want as the "primary" datasheet/literature link --
# aggregators / search portals that don't host the actual PDF themselves.
_LINK_DENY = (
    "google.com", "duckduckgo.com", "bing.com",
    "wikipedia.org", "amazon.", "ebay.", "alibaba.",
    "youtube.com", "linkedin.com", "facebook.", "pinterest.",
    "reddit.", "quora.", "twitter.", "x.com",
)

# Brand -> preferred manufacturer doc-portal hostname(s). The crawler
# prefers a PDF on the manufacturer's own site over a reseller. Add new
# brands here as the catalogue grows.
_BRAND_DOMAINS = {
    "eaton":                 ["eaton.com"],
    "memshield":             ["eaton.com"],
    "schneider":             ["se.com", "schneider-electric.com", "schneider-electric.co.uk"],
    "abb":                   ["abb.com", "new.abb.com"],
    "siemens":               ["siemens.com", "siemens.de"],
    "philips":               ["philips.com", "lighting.philips.com", "philips.co.uk"],
    "mk":                    ["mkelectric.com", "honeywell.com"],
    "honeywell":             ["honeywell.com"],
    "hager":                 ["hager.com"],
    "hochiki":               ["hochikieurope.com", "hochiki.com"],
    "legrand":               ["legrand.com", "legrand.us"],
    "panasonic":             ["panasonic.com", "business.panasonic.com"],
    "cisco":                 ["cisco.com"],
    "juniper":               ["juniper.net"],
    "hid":                   ["hidglobal.com"],
    "hikvision":             ["hikvision.com"],
    "tropical":              ["tropical-cables.com", "tropicalcable.com"],
    "kable metal":           ["kablemetal.com"],
    "growatt":               ["growatt.com"],
    "goodwe":                ["goodwe.com"],
    "victron":               ["victronenergy.com"],
    "jinko":                 ["jinkosolar.com"],
    "ja solar":              ["jasolar.com"],
    "longi":                 ["longi.com", "en.longi.com"],
    "pylontech":             ["pylontech.com.cn"],
}


def _brand_domains(brand: str) -> list:
    """Return list of preferred manufacturer hostnames for a brand
    string. Matches partial / case-insensitive."""
    if not brand:
        return []
    bl = brand.lower()
    out = []
    for key, doms in _BRAND_DOMAINS.items():
        if key in bl or bl in key:
            for d in doms:
                if d not in out:
                    out.append(d)
    return out


def _score_url(url: str, query: str, brand_domains: list, kind: str) -> int:
    """Higher = more likely the right link. Heuristics:
      +60  hosted on the manufacturer's own domain
      +40  ends in .pdf
      +20  URL path contains 'datasheet' / 'brochure' / 'spec'
      +15  URL contains the brand name
      +10  any query word appears in URL
      -50  generic e-commerce / aggregator (already filtered by deny list)
    """
    u = (url or "").lower()
    if not u.startswith("http"):
        return 0
    if any(d in u for d in _LINK_DENY):
        return 0
    score = 0
    if any(d in u for d in (brand_domains or [])):
        score += 60
    path = u.split("?", 1)[0]
    if path.endswith(".pdf"):
        score += 40
    keywords = {
        "datasheet": ("datasheet", "data-sheet", "spec-sheet", "specsheet"),
        "literature":("brochure", "literature", "catalog", "catalogue", "product-info"),
    }
    for kw in keywords.get(kind, ()):
        if kw in u:
            score += 20
            break
    if brand_domains:
        for d in brand_domains:
            if d.split(".", 1)[0] in u:
                score += 15
                break
    for word in (query or "").lower().split():
        if len(word) >= 3 and word.isalnum() and word in u:
            score += 4
    return score


def _decode_ddg_url(href: str) -> str:
    """DuckDuckGo wraps the actual URL in /l/?uddg=encoded -- unwrap it."""
    import urllib.parse, re as _re
    if href.startswith("/l/?uddg=") or href.startswith("//duckduckgo.com/l/?") or href.startswith("https://duckduckgo.com/l/?"):
        m = _re.search(r"uddg=([^&]+)", href)
        if m:
            return urllib.parse.unquote(m.group(1))
    return href


def _search_engine(query: str, timeout: float = 9.0) -> list:
    """Return a list of candidate URLs from DuckDuckGo HTML.
    Falls back to Bing HTML if DDG returns nothing. Never raises."""
    import urllib.request, urllib.parse, re
    out = []
    headers = {"User-Agent": _PRODUCT_LINK_UA, "Accept-Language": "en-GB,en;q=0.9"}
    for engine_url in (
        "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query}),
        "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query}),
    ):
        try:
            req = urllib.request.Request(engine_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception:
            continue
        # DuckDuckGo result anchors
        for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"', html):
            out.append(_decode_ddg_url(m.group(1)))
        # Bing result anchors
        for m in re.finditer(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"', html):
            out.append(m.group(1))
        if out:
            break  # got something from the first engine
    # Dedup preserving order
    seen, deduped = set(), []
    for u in out:
        u = u.strip()
        if not u or u in seen: continue
        seen.add(u); deduped.append(u)
    return deduped


def _best_match(query: str, brand_domains: list, kind: str) -> str:
    """Run the search, score every candidate, return the URL with the
    highest score (or '' if all are filtered out)."""
    candidates = _search_engine(query)
    scored = [(c, _score_url(c, query, brand_domains, kind)) for c in candidates]
    scored = [(u, s) for (u, s) in scored if s > 0]
    if not scored:
        return ""
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]


def _find_links_for(name: str, brand: str = "", model: str = "") -> tuple:
    """Return (datasheet_url, literature_url). Smart search:
      1. Try manufacturer-domain-scoped query first
      2. Fall back to a generic query
      3. Score all candidates and pick the best
    """
    import time
    base_terms = [t for t in (name, brand, model) if t]
    if not base_terms:
        return ("", "")
    brand_domains = _brand_domains(brand)
    base = " ".join(base_terms).strip()
    # Strip extremely common BOQ prose so the query is just the product name.
    for stop in ("Supply and install ", "Supply and fix ", "Supply, lay and connect ",
                 "Supply, lay and terminate ", "Wire the following points ",
                 "Wire the following point ", " as Memshield or approved equal",
                 " as Eaton or approved equal", " as Tropical or approved equal",
                 " as MK or approved equal", " as Philips or approved equal",
                 " as Hochiki or approved equal", " or approved equal"):
        base = base.replace(stop, "")
        base = base.replace(stop.strip(), "")
    base = " ".join(base.split())[:160]

    def _try(kind_word: str, kind_key: str) -> str:
        # 1. Manufacturer-domain-scoped
        for dom in brand_domains:
            q = f'{base} {kind_word} site:{dom} filetype:pdf'
            url = _best_match(q, brand_domains, kind_key)
            if url:
                return url
        # 2. Brand + kind + filetype:pdf
        q = f"{base} {kind_word} filetype:pdf"
        url = _best_match(q, brand_domains, kind_key)
        if url:
            return url
        # 3. Looser: brand + kind (any file)
        q = f"{base} {kind_word}"
        return _best_match(q, brand_domains, kind_key)

    ds = _try("datasheet", "datasheet")
    time.sleep(2.0)  # politeness between queries
    lit = _try("brochure OR literature", "literature")
    return (ds, lit)


# ---- Routes -------------------------------------------------------------

@app.route("/admin/agent/find-product-links", methods=["POST"])
@login_required
def admin_find_product_links_bulk():
    """Process up to 20 products with missing literature/datasheet URLs."""
    u = current_user()
    if not (u and u["is_admin"]):
        abort(403)
    csrf_protect()
    _ensure_product_link_columns()
    LIMIT = 20
    with get_db() as c:
        rows = c.execute(
            "SELECT id, name, brand, model FROM equipment_catalog "
            "WHERE COALESCE(literature_url,'')='' OR COALESCE(datasheet_url,'')='' "
            "ORDER BY id LIMIT ?",
            (LIMIT,),
        ).fetchall()
    found_ds = 0
    found_lit = 0
    for r in rows:
        ds, lit = _find_links_for(r["name"] or "", r["brand"] or "", r["model"] or "")
        if ds or lit:
            with get_db() as c:
                c.execute(
                    "UPDATE equipment_catalog SET "
                    "literature_url = CASE WHEN COALESCE(literature_url,'')='' AND ? != '' THEN ? ELSE literature_url END, "
                    "datasheet_url  = CASE WHEN COALESCE(datasheet_url,'')='' AND ? != '' THEN ? ELSE datasheet_url END, "
                    "links_checked_at = CURRENT_TIMESTAMP "
                    "WHERE id=?",
                    (lit, lit, ds, ds, r["id"]),
                )
            if ds: found_ds += 1
            if lit: found_lit += 1
        else:
            # Even when nothing found, record the attempt so we don't loop forever on it.
            with get_db() as c:
                c.execute(
                    "UPDATE equipment_catalog SET links_checked_at = CURRENT_TIMESTAMP WHERE id=?",
                    (r["id"],),
                )
    try:
        from new_boq_hierarchy_schema import boq_audit
        boq_audit(get_db, u["id"], "product_link_finder_run", "equipment_catalog", 0,
                  f"processed={len(rows)} datasheets={found_ds} literature={found_lit}")
    except Exception:
        pass
    flash(f"Product link finder ran for {len(rows)} product(s): "
          f"{found_ds} datasheet(s), {found_lit} literature link(s) found.",
          "success")
    return redirect(request.referrer or url_for("admin_marketplace_products"))


@app.route("/admin/agent/find-product-links/<int:pid>", methods=["POST"])
@login_required
def admin_find_product_links_one(pid):
    u = current_user()
    if not (u and u["is_admin"]):
        abort(403)
    csrf_protect()
    _ensure_product_link_columns()
    with get_db() as c:
        r = c.execute(
            "SELECT id, name, brand, model FROM equipment_catalog WHERE id=?", (pid,)
        ).fetchone()
    if not r:
        flash("Product not found.", "warning")
        return redirect(url_for("admin_marketplace_products"))
    ds, lit = _find_links_for(r["name"] or "", r["brand"] or "", r["model"] or "")
    with get_db() as c:
        c.execute(
            "UPDATE equipment_catalog SET "
            "literature_url = CASE WHEN ? != '' THEN ? ELSE literature_url END, "
            "datasheet_url  = CASE WHEN ? != '' THEN ? ELSE datasheet_url END, "
            "links_checked_at = CURRENT_TIMESTAMP "
            "WHERE id=?",
            (lit, lit, ds, ds, pid),
        )
    flash(f"Looked up links for product #{pid}: "
          f"datasheet={'found' if ds else 'not found'}, "
          f"literature={'found' if lit else 'not found'}.",
          "success" if (ds or lit) else "warning")
    return redirect(request.referrer or url_for("admin_marketplace_products"))


@app.route("/supplier/products/<int:pid>/find-links", methods=["POST"])
@login_required
def supplier_find_product_links(pid):
    """Supplier self-service: only the owning supplier user can run this
    on their own products."""
    uid = session["user_id"]
    csrf_protect()
    _ensure_product_link_columns()
    with get_db() as c:
        r = c.execute(
            "SELECT ec.id, ec.name, ec.brand, ec.model, s.user_id AS supplier_uid "
            "FROM equipment_catalog ec "
            "LEFT JOIN suppliers s ON s.id=ec.supplier_id "
            "WHERE ec.id=?",
            (pid,),
        ).fetchone()
    if not r:
        flash("Product not found.", "warning")
        return redirect(url_for("supplier_products"))
    if int(r["supplier_uid"] or 0) != int(uid):
        u = current_user()
        if not (u and u["is_admin"]):
            abort(403)
    ds, lit = _find_links_for(r["name"] or "", r["brand"] or "", r["model"] or "")
    with get_db() as c:
        c.execute(
            "UPDATE equipment_catalog SET "
            "literature_url = CASE WHEN ? != '' THEN ? ELSE literature_url END, "
            "datasheet_url  = CASE WHEN ? != '' THEN ? ELSE datasheet_url END, "
            "links_checked_at = CURRENT_TIMESTAMP "
            "WHERE id=?",
            (lit, lit, ds, ds, pid),
        )
    flash(f"Links lookup for '{r['name']}' -- "
          f"datasheet: {'found' if ds else 'not found'}, "
          f"literature: {'found' if lit else 'not found'}.",
          "success" if (ds or lit) else "warning")
    return redirect(request.referrer or url_for("supplier_products"))
