# new_solar_opportunities.py
# Owner directive 2026-06-21: "think of alternating approach get solar
# projects asking for rfq orfp, we get them and list them".
#
# Replaces the deep-crawl prospecting agent (which timed out on Render's
# free tier) with a simple, reliable RSS-feed listing:
#
#   - Pulls ReliefWeb global tender RSS (filtered for solar / PV /
#     photovoltaic / off-grid / mini-grid keywords)
#   - In-process cache for 60 minutes -- hits the source at most 24
#     times per day across the whole worker pool
#   - Renders /admin/opportunities with country / type / source chips
#   - Each row links directly to the source page; "Add to leads" copies
#     it into the existing leads table
#
# Reliefweb RSS schema:
#   <item>
#     <title>[Title] [Source] [Country]</title>
#     <link>...</link>
#     <description>HTML excerpt</description>
#     <pubDate>RFC 822</pubDate>
#     <category>tender</category>
#   </item>


import time
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


_OPPS_CACHE = {"fetched_at": 0, "items": []}
_OPPS_TTL_SECONDS = 60 * 60  # 1 hour


_RELIEFWEB_TENDERS_RSS = (
    "https://reliefweb.int/updates/rss.xml?"
    "advanced-search=%28F4%29"  # F4 = Format: Tender
)


_SOLAR_KEYWORDS = (
    "solar", "photovoltaic", " pv ", "pv,", "pv.", "pv-", "pv/",
    "off-grid", "off grid", "on-grid", "on grid",
    "hybrid system", "mini-grid", "mini grid",
    "rooftop", "ground-mount", "ground mount",
    "renewable energy",
)


def _is_solar(text):
    t = (text or "").lower()
    return any(k in t for k in _SOLAR_KEYWORDS)


def _classify_type(title, body):
    """Classify whether the opportunity is an RFQ / RFP / Tender / EOI
    based on keywords in the title and body."""
    blob = ((title or "") + " " + (body or "")).lower()
    if any(k in blob for k in ("request for quot", "rfq", "invitation for quot")):
        return "RFQ"
    if any(k in blob for k in ("request for propos", "rfp", "call for propos")):
        return "RFP"
    if "expression of interest" in blob or "eoi " in blob:
        return "EOI"
    if "tender" in blob or "itb " in blob or "invitation to bid" in blob:
        return "TENDER"
    return "OTHER"


def _strip_html(html_text):
    """Cheap HTML strip for the description body. We don't need a real
    parser -- ReliefWeb gives us a one-paragraph excerpt."""
    text = re.sub(r"<[^>]+>", " ", html_text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_country(title):
    """ReliefWeb titles follow `... - <Country>` pattern. Extract."""
    if not title:
        return ""
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2 and len(parts[1]) < 50:
        return parts[1].strip()
    return ""


def fetch_opportunities(force=False, timeout=10.0):
    """Fetch and filter solar opportunities. Returns a list of dicts:
       {title, body, source_url, source, country, type, published, raw_title}.
       Cached for 1 hour by default. Pass force=True to bypass cache."""
    now = time.time()
    if (not force and _OPPS_CACHE["items"]
            and (now - _OPPS_CACHE["fetched_at"]) < _OPPS_TTL_SECONDS):
        return _OPPS_CACHE["items"]

    items = []

    # ---- ReliefWeb tenders RSS ----
    try:
        req = urllib.request.Request(_RELIEFWEB_TENDERS_RSS, headers={
            "User-Agent": "Mozilla/5.0 (SolarPro opportunities fetcher)",
            "Accept": "application/rss+xml,application/xml,text/xml",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        root = ET.fromstring(body)
        # RSS 2.0: rss > channel > item*
        channel = root.find("channel") or root
        for it in channel.findall("item"):
            t = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = _strip_html(it.findtext("description") or "")
            pub = (it.findtext("pubDate") or "").strip()
            if not _is_solar(t + " " + desc):
                continue
            items.append({
                "title": t,
                "raw_title": t,
                "body": desc[:600],
                "source_url": link,
                "source": "ReliefWeb",
                "country": _extract_country(t),
                "type": _classify_type(t, desc),
                "published": pub,
            })
    except Exception as _e:
        try: app.logger.warning("ReliefWeb fetch failed: %s", _e)
        except Exception: pass

    # Order by classified type so RFQ/RFP come first.
    _TYPE_PRIORITY = {"RFQ": 1, "RFP": 2, "TENDER": 3, "EOI": 4, "OTHER": 5}
    items.sort(key=lambda x: (_TYPE_PRIORITY.get(x["type"], 5), x["title"]))
    _OPPS_CACHE["items"] = items
    _OPPS_CACHE["fetched_at"] = now
    return items


@app.route("/admin/opportunities", methods=["GET"])
@login_required
def admin_opportunities():
    """List solar opportunities pulled from public tender RSS feeds.
    Filterable by country, type, source. Far simpler + more reliable than
    the deep-crawl prospecting agent."""
    if not (current_user() and current_user().is_admin):
        from flask import abort as _abort
        return _abort(404)
    force = request.args.get("refresh") == "1"
    items = fetch_opportunities(force=force)
    # Filter chips
    f_country = (request.args.get("country") or "").strip()
    f_type    = (request.args.get("type") or "").strip().upper()
    f_source  = (request.args.get("source") or "").strip()
    if f_country:
        items = [i for i in items
                 if f_country.lower() in (i.get("country") or "").lower()
                 or f_country.lower() in (i.get("title") or "").lower()]
    if f_type:
        items = [i for i in items if i.get("type") == f_type]
    if f_source:
        items = [i for i in items if (i.get("source") or "").lower() == f_source.lower()]

    # Build chip counts off the unfiltered cache
    all_items = _OPPS_CACHE.get("items") or []
    countries = sorted({i.get("country") or "" for i in all_items if i.get("country")})
    types     = sorted({i.get("type") or "" for i in all_items if i.get("type")})
    sources   = sorted({i.get("source") or "" for i in all_items if i.get("source")})

    return render_template(
        "admin_opportunities.html",
        user=current_user(),
        items=items,
        countries=countries,
        types=types,
        sources=sources,
        active_country=f_country,
        active_type=f_type,
        active_source=f_source,
        cache_age_sec=int(time.time() - _OPPS_CACHE.get("fetched_at", time.time())),
        total_unfiltered=len(all_items),
    )


@app.route("/admin/opportunities/add-to-leads/<path:src_url>", methods=["POST"])
@login_required
def admin_opportunity_add_to_leads(src_url):
    """One-click: copy a RSS-listed opportunity into the existing leads
    table so the owner can work it through the same pipeline as
    crawler-found leads."""
    if not (current_user() and current_user().is_admin):
        from flask import abort as _abort
        return _abort(404)
    csrf_protect()
    title = (request.form.get("title") or "")[:300]
    country = (request.form.get("country") or "")[:80]
    type_ = (request.form.get("type") or "")[:20]
    body = (request.form.get("body") or "")[:1000]
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO leads (name, email, country, project_type, message, "
                "source, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (title[:120], "", country, "solar-" + type_.lower(),
                 (title + " -- " + body)[:600], "rss:" + src_url[:200],
                 "new", datetime.utcnow().isoformat() + "Z"),
            )
        flash("Added to leads.", "success")
    except Exception as e:
        try: app.logger.warning("add_to_leads failed: %s", e)
        except Exception: pass
        flash(f"Could not add to leads: {e}", "warning")
    return redirect(url_for("admin_opportunities"))
