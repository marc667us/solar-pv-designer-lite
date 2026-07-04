@app.route("/marketplace/product/<int:pid>/doc/<kind>")
def marketplace_product_doc_redirect(pid, kind):
    """Open a product's literature/datasheet. Serves the cached URL if the
    catalogue already has one; otherwise (for a logged-in user) runs the smart
    web-crawl finder ONCE for this product, caches whatever it finds (both
    kinds), and opens it. So the links work for ANY product -- including ones
    added in the future -- and self-heal after a DB reseed, with no dependence
    on a one-time bulk crawl. Falls back to a filetype:pdf web search only when
    nothing can be found. Public (no login) so anonymous marketplace browsers
    still benefit from any cached URL.
    (owner 2026-07-04: "fix the links ... on the cards" + "new products will be
    added in future so ensure this dont happen again".)"""
    kind = (kind or "").strip().lower()
    if kind not in ("literature", "datasheet"):
        from flask import abort as _abort
        return _abort(404)
    col = "literature_url" if kind == "literature" else "datasheet_url"
    row = None
    try:
        with get_db() as c:
            # NB: only COALESCE the text URL columns. links_checked_at is a
            # TIMESTAMP on Postgres -- COALESCE(ts,'') throws "invalid input
            # syntax for type timestamp" there, so select it raw and null-check
            # in Python.
            r = c.execute(
                "SELECT id, name, brand, model, "
                "COALESCE(literature_url,'') AS literature_url, "
                "COALESCE(datasheet_url,'')  AS datasheet_url, "
                "links_checked_at "
                "FROM equipment_catalog WHERE id=?",
                (int(pid),)).fetchone()
            row = dict(r) if r else None
    except Exception as e:
        try: app.logger.warning("doc redirect lookup failed pid=%s kind=%s: %s", pid, kind, e)
        except Exception: pass
        row = None
    if not row:
        return render_template(
            "error.html", code=404, title="Product not found",
            message="That product isn't in the catalogue.",
            user=current_user() if 'current_user' in globals() else None,
        ), 404
    url = (row.get(col) or "").strip()
    # No cached URL -> resolve on demand (once, logged-in only) and cache it.
    if not url:
        url = _resolve_and_cache_doc_url(row, kind)
    # Only ever redirect to an http(s) URL (scheme allowlist -- never let a
    # stored javascript:/data:/other-scheme value drive the redirect). We do
    # NOT server-side HEAD-probe first: many supplier sites block bot probes and
    # would look "unreachable" though the browser loads them fine (the real
    # cause of the earlier "links don't work" reports). Browser is the source
    # of truth.
    if url and url.lower().startswith(("http://", "https://")):
        return redirect(url)
    # Nothing usable found -> a filetype:pdf search so the user still lands
    # somewhere useful rather than a dead end.
    import urllib.parse as _up
    kind_terms = "brochure literature" if kind == "literature" else "datasheet specification"
    terms = ("%s %s %s filetype:pdf" % (
        row.get("brand") or "", row.get("model") or row.get("name") or "", kind_terms)).strip()
    return redirect("https://www.google.com/search?q=" + _up.quote_plus(terms))


def _resolve_and_cache_doc_url(row, kind):
    """On-demand resolver for a product with no cached doc URL. For a LOGGED-IN
    requester only (anti-abuse: anonymous/bot traffic must not be able to drive
    synchronous outbound crawls), runs the smart web-crawl finder ONCE per
    product (guarded by links_checked_at so repeat clicks don't re-crawl),
    caches BOTH found URLs onto the product, and returns the requested one. This
    is what makes datasheet/literature links self-populate for every product --
    current or future -- so a wiped/reseeded DB or a newly added product heals
    itself the first time a signed-in user opens it; anonymous visitors then get
    the cached URL. Returns '' when the requester is anonymous, the product was
    already crawled (nothing found), or the finder is unavailable.
    Inputs: row = dict with id/name/brand/model/links_checked_at; kind in
    {'literature','datasheet'}. Output: the resolved URL string, or ''."""
    try:
        # Anti-abuse: only a signed-in user triggers a live crawl. Anonymous
        # clicks fall through to the search fallback; once any signed-in user
        # resolves a product it is cached, so anonymous users get it thereafter.
        try:
            _authed = bool(current_user()) if "current_user" in globals() else False
        except Exception:
            _authed = False
        if not _authed:
            return ""
        # Crawl at most once per product. Truthy check works for both a TEXT
        # value and a native Postgres TIMESTAMP (never call .strip() on it).
        if row.get("links_checked_at"):
            return ""
        if "_find_links_for" not in globals():
            return ""
        try:
            _ensure_product_link_columns()
        except Exception:
            pass
        crawl_ok = True
        try:
            ds, lit = _find_links_for(
                row.get("name") or "", row.get("brand") or "", row.get("model") or "")
        except Exception as e:
            try: app.logger.warning("on-demand link finder failed pid=%s: %s", row.get("id"), e)
            except Exception: pass
            ds, lit, crawl_ok = "", "", False
        # Persist (cache urls + stamp checked) ONLY when the crawl actually
        # completed -- a transient network/rate-limit failure must not poison
        # the product into "checked, never retry". Idempotent column-guarded
        # UPDATE, same shape as the bulk finder; db_adapter maps ?->%s.
        if crawl_ok:
            try:
                with get_db() as c:
                    c.execute(
                        "UPDATE equipment_catalog SET "
                        "literature_url = CASE WHEN COALESCE(literature_url,'')='' AND ? != '' THEN ? ELSE literature_url END, "
                        "datasheet_url  = CASE WHEN COALESCE(datasheet_url,'')='' AND ? != '' THEN ? ELSE datasheet_url END, "
                        "links_checked_at = CURRENT_TIMESTAMP WHERE id=?",
                        (lit, lit, ds, ds, row.get("id")))
            except Exception as e:
                try: app.logger.warning("on-demand link cache failed pid=%s: %s", row.get("id"), e)
                except Exception: pass
        return (lit if kind == "literature" else ds) or ""
    except Exception:
        return ""


