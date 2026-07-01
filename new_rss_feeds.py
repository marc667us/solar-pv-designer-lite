# === BEGIN: rss_feeds splice ===
# 2026-07-01: RSS 2.0 feeds so external readers can subscribe.
#
# Routes:
#   GET /news.rss           -- latest 20 published news_posts
#   GET /opportunities.rss  -- latest 30 rows from solar_opportunities_crawled
#
# Zero new dependencies -- feed XML is assembled manually. Standards
# followed: RSS 2.0 spec, RFC 822 pubDate format.


def _rss_escape(s):
    """XML-escape a string for safe inclusion in RSS body."""
    if s is None:
        return ""
    s = str(s)
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


def _rfc822_date(ts):
    """Best-effort convert an ISO-8601 or db timestamp to RFC 822.
    Accepts either 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DDTHH:MM:SS' or None."""
    if not ts:
        return ""
    try:
        from datetime import datetime, timezone
        s = str(ts).strip().replace("T", " ")
        # Trim fractional seconds if present.
        if "." in s:
            s = s.split(".", 1)[0]
        # Drop timezone marker if it's already RFC 822-ish.
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
                return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except ValueError:
                continue
    except Exception:
        pass
    return str(ts)


@app.route("/news.rss")
def news_rss():
    """RSS 2.0 feed of published SolarPro news posts."""
    from flask import make_response
    with get_db() as c:
        posts = c.execute(
            "SELECT id, title, content, category, created_at, updated_at "
            "FROM news_posts WHERE is_published=1 "
            "ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
    site_root = request.url_root.rstrip("/")
    channel_link = site_root + url_for("news_index")
    build_date = _rfc822_date(request.url_root)  # falls back to string but harmless
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>SolarPro Global — News</title>',
        f'<link>{_rss_escape(channel_link)}</link>',
        f'<description>Industry, project, and platform updates from SolarPro Global.</description>',
        f'<language>en</language>',
        f'<atom:link href="{_rss_escape(site_root + url_for("news_rss"))}" rel="self" type="application/rss+xml" />',
    ]
    for p in posts:
        pid = p["id"]
        title = p["title"] or ""
        content = p["content"] or ""
        category = p["category"] or "industry"
        detail = site_root + url_for("news_detail", post_id=pid)
        pub = _rfc822_date(p["created_at"])
        parts.append("<item>")
        parts.append(f"<title>{_rss_escape(title)}</title>")
        parts.append(f"<link>{_rss_escape(detail)}</link>")
        parts.append(f'<guid isPermaLink="true">{_rss_escape(detail)}</guid>')
        parts.append(f"<category>{_rss_escape(category)}</category>")
        parts.append(f"<pubDate>{_rss_escape(pub)}</pubDate>")
        parts.append(f"<description>{_rss_escape(content[:800])}</description>")
        parts.append("</item>")
    parts.append("</channel>")
    parts.append("</rss>")
    body = "\n".join(parts)
    resp = make_response(body, 200)
    resp.headers["Content-Type"] = "application/rss+xml; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


@app.route("/opportunities.rss")
def opportunities_rss():
    """RSS 2.0 feed of latest solar_opportunities_crawled rows."""
    from flask import make_response
    _ensure_opps_crawled_table()
    with get_db() as c:
        rows = c.execute(
            "SELECT id, title, source, source_url, country, type, body, "
            "       published, last_seen_at "
            "FROM solar_opportunities_crawled "
            "ORDER BY last_seen_at DESC LIMIT 30"
        ).fetchall()
    site_root = request.url_root.rstrip("/")
    channel_link = site_root + url_for("public_opportunities")
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>SolarPro Global — Solar Opportunities (RFQ / RFP / EOI / Tender)</title>',
        f'<link>{_rss_escape(channel_link)}</link>',
        f'<description>Aggregated solar tender feed for RFQ, RFP, EOI and general procurement notices worldwide.</description>',
        f'<language>en</language>',
        f'<atom:link href="{_rss_escape(site_root + url_for("opportunities_rss"))}" rel="self" type="application/rss+xml" />',
    ]
    for r in rows:
        title = r["title"] or ""
        source = r["source"] or ""
        src_url = r["source_url"] or ""
        country = r["country"] or ""
        type_ = r["type"] or ""
        body = r["body"] or ""
        pub = _rfc822_date(r["published"] or r["last_seen_at"])
        display_title = title
        if country:
            display_title = f"[{country}] {title}"
        if type_ and type_ != "OTHER":
            display_title = f"({type_}) {display_title}"
        parts.append("<item>")
        parts.append(f"<title>{_rss_escape(display_title)}</title>")
        parts.append(f"<link>{_rss_escape(src_url)}</link>")
        if src_url:
            parts.append(f'<guid isPermaLink="true">{_rss_escape(src_url)}</guid>')
        if country:
            parts.append(f"<category>{_rss_escape(country)}</category>")
        if type_:
            parts.append(f"<category>{_rss_escape(type_)}</category>")
        if source:
            parts.append(f"<source>{_rss_escape(source)}</source>")
        parts.append(f"<pubDate>{_rss_escape(pub)}</pubDate>")
        parts.append(f"<description>{_rss_escape(body[:600])}</description>")
        parts.append("</item>")
    parts.append("</channel>")
    parts.append("</rss>")
    body_out = "\n".join(parts)
    resp = make_response(body_out, 200)
    resp.headers["Content-Type"] = "application/rss+xml; charset=utf-8"
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


# === END: rss_feeds splice ===
