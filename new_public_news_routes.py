# === BEGIN: public_news_routes splice ===
# 2026-07-01: Complete the news + newsfeed surface.
#
# Prior state:
#   - Admin CRUD at /admin/news exists (news_posts table).
#   - Landing pages show LATEST 3 posts as preview, but there is no way
#     to read the full article and no way to browse older posts.
#   - No newsfeed endpoint — the RSS scraping helper exists for admin
#     Solar Opportunities but is not surfaced to the public.
#
# This module adds three PUBLIC routes:
#
#   GET /news                    — index of all published news_posts,
#                                  10 per page, newest first.
#   GET /news/<int:post_id>      — single-post detail view.
#   GET /newsfeed                — live industry newsfeed pulled from
#                                  Google News RSS (5 solar queries).
#                                  15-min in-process cache; free tier.
#
# All three surfaces link to each other and to the free-service pages
# (marketplace, bill-check, support). Splices into web_app.py alongside
# the other public route modules.

import time
import re
import urllib.request
import urllib.parse
from xml.etree import ElementTree as _ET


_NEWSFEED_CACHE = {"items": [], "fetched_at": 0.0}
_NEWSFEED_TTL_SECONDS = 15 * 60

_NEWSFEED_QUERIES = [
    ("Solar PV Africa",         "solar+pv+africa"),
    ("Solar Tenders",           "solar+tender+RFP"),
    ("Solar Financing",         "solar+financing+africa"),
    ("Solar Manufacturing",     "solar+panel+manufacturing"),
    ("Solar Grid Integration",  "solar+grid+integration"),
]


def _newsfeed_fetch_items(force_refresh=False):
    """Return a list of dict{title,link,pub_date,source,topic} pulled from
    Google News RSS for 5 solar-industry queries. In-process 15-min cache.
    Never raises — returns whatever it managed to fetch, or the cached
    result on failure.
    """
    now = time.time()
    if not force_refresh and _NEWSFEED_CACHE["items"] and \
            now - _NEWSFEED_CACHE["fetched_at"] < _NEWSFEED_TTL_SECONDS:
        return _NEWSFEED_CACHE["items"]

    out = []
    for topic, q in _NEWSFEED_QUERIES:
        url = ("https://news.google.com/rss/search?q=" + q +
               "&hl=en-US&gl=US&ceid=US:en")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SolarPro-Newsfeed/1.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = r.read()
        except Exception:
            continue
        try:
            root = _ET.fromstring(data)
        except Exception:
            continue
        for item in root.iter("item"):
            try:
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link")  or "").strip()
                pub   = (item.findtext("pubDate") or "").strip()
                src_el = item.find("source")
                source = (src_el.text or "").strip() if src_el is not None else ""
                if title and link:
                    out.append({
                        "title":    title,
                        "link":     link,
                        "pub_date": pub,
                        "source":   source or "News",
                        "topic":    topic,
                    })
            except Exception:
                continue
        if len(out) >= 40:
            break

    # De-dup by title (Google News sometimes returns the same story from
    # multiple sources for the same query).
    seen = set()
    deduped = []
    for it in out:
        key = (it["title"] or "").lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    if deduped:
        _NEWSFEED_CACHE["items"] = deduped
        _NEWSFEED_CACHE["fetched_at"] = now
    return deduped or _NEWSFEED_CACHE["items"]


@app.route("/news")
def news_index():
    """Public news index. Paginated 10/page, newest first."""
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
    except (TypeError, ValueError):
        page = 1
    per_page = 10
    offset = (page - 1) * per_page
    with get_db() as c:
        total = c.execute(
            "SELECT COUNT(*) FROM news_posts WHERE is_published=1"
        ).fetchone()[0]
        posts = c.execute(
            "SELECT id, title, content, category, created_at, updated_at "
            "FROM news_posts WHERE is_published=1 "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset),
        ).fetchall()
    total_pages = max(1, (int(total or 0) + per_page - 1) // per_page)
    return render_template(
        "news_index.html",
        user=current_user(),
        posts=posts,
        page=page,
        total_pages=total_pages,
        total=int(total or 0),
    )


@app.route("/news/<int:post_id>")
def news_detail(post_id):
    """Public news detail page."""
    with get_db() as c:
        post = c.execute(
            "SELECT id, title, content, category, created_at, updated_at "
            "FROM news_posts WHERE id=? AND is_published=1",
            (post_id,),
        ).fetchone()
        if not post:
            abort(404)
        related = c.execute(
            "SELECT id, title, created_at FROM news_posts "
            "WHERE is_published=1 AND id != ? AND category=? "
            "ORDER BY created_at DESC LIMIT 4",
            (post_id, post["category"] or "industry"),
        ).fetchall()
    return render_template(
        "news_detail.html",
        user=current_user(),
        post=post,
        related=related,
    )


@app.route("/newsfeed")
def newsfeed_public():
    """Public solar-industry newsfeed via Google News RSS. Cached 15 min.
    Optional ?refresh=1 (rate-limit friendly since cache is in-process
    only and cleared on redeploy)."""
    force = request.args.get("refresh") == "1"
    items = _newsfeed_fetch_items(force_refresh=force)
    topics = sorted({it["topic"] for it in items})
    selected_topic = (request.args.get("topic") or "").strip()
    if selected_topic:
        items = [it for it in items if it["topic"] == selected_topic]
    fetched_at = _NEWSFEED_CACHE.get("fetched_at") or 0
    from datetime import datetime as _dt, timezone as _tz
    fetched_iso = (_dt.fromtimestamp(fetched_at, _tz.utc).isoformat()
                   if fetched_at else "")
    return render_template(
        "newsfeed.html",
        user=current_user(),
        items=items,
        topics=topics,
        selected_topic=selected_topic,
        fetched_iso=fetched_iso,
    )


# === END: public_news_routes splice ===
