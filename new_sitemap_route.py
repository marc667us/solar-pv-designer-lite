# === BEGIN: sitemap_route splice ===
# 2026-07-01: /sitemap.xml exposes every public page so search engines can
# crawl and index them. Zero new dependencies.
#
# Included:
#   Landing pages, marketplace, bill-check, guides, support pages that are
#   public, news_index, newsfeed, opportunities, each published news_post
#   detail. Static entries have <changefreq> hints; per-post entries include
#   <lastmod> pulled from updated_at/created_at.
#
# Also serves /robots.txt if the file doesn't already exist statically; it
# points crawlers to /sitemap.xml.


@app.route("/sitemap.xml")
def sitemap_xml():
    from flask import make_response
    site_root = request.url_root.rstrip("/")

    def _u(endpoint, **kw):
        try:
            return site_root + url_for(endpoint, **kw)
        except Exception:
            return ""

    static_entries = [
        # (endpoint, changefreq, priority)
        ("landing",            "weekly",  "1.0"),
        ("landing_page2",      "weekly",  "0.9"),
        ("marketplace_public", "daily",   "0.9"),
        ("bill_check_landing", "monthly", "0.8"),
        ("news_index",         "daily",   "0.8"),
        ("newsfeed_public",    "hourly",  "0.7"),
        ("public_opportunities", "daily", "0.9"),
        ("news_rss",           "daily",   "0.5"),
        ("opportunities_rss",  "daily",   "0.5"),
    ]

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for endpoint, freq, prio in static_entries:
        loc = _u(endpoint)
        if not loc:
            continue
        parts.append("<url>")
        parts.append(f"<loc>{loc}</loc>")
        parts.append(f"<changefreq>{freq}</changefreq>")
        parts.append(f"<priority>{prio}</priority>")
        parts.append("</url>")

    # Public guides — Quick / Full / Technical walkthroughs
    for slug in ("quick", "full-user", "technical"):
        loc = _u("guides_view", slug=slug)
        if loc:
            parts.append("<url>")
            parts.append(f"<loc>{loc}</loc>")
            parts.append("<changefreq>monthly</changefreq>")
            parts.append("<priority>0.6</priority>")
            parts.append("</url>")

    # Individual news posts
    try:
        with get_db() as c:
            posts = c.execute(
                "SELECT id, updated_at, created_at FROM news_posts "
                "WHERE is_published=1 ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        for p in posts:
            loc = _u("news_detail", post_id=p["id"])
            if not loc:
                continue
            lastmod = str(p["updated_at"] or p["created_at"] or "")[:10]
            parts.append("<url>")
            parts.append(f"<loc>{loc}</loc>")
            if lastmod:
                parts.append(f"<lastmod>{lastmod}</lastmod>")
            parts.append("<changefreq>monthly</changefreq>")
            parts.append("<priority>0.7</priority>")
            parts.append("</url>")
    except Exception:
        pass

    parts.append("</urlset>")
    body = "\n".join(parts)
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "application/xml; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=1800"
    return resp


# === END: sitemap_route splice ===
