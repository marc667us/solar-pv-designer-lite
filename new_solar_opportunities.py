# new_solar_opportunities.py
# Owner directive 2026-06-21: "think of alternating approach get solar
# projects asking for rfq or rfp, we get them and list them".
#
# 2026-06-26 REWRITE: the previous ReliefWeb RSS source returned trash —
# `?advanced-search=(F4)` no longer maps to "Tender" on ReliefWeb, the feed
# was actually Appeal Updates (humanitarian crises), and the v1 API has been
# decommissioned. v2 requires a registered appname (free but slow to obtain).
#
# Replacement: multi-query Google News RSS. No API key, real journalism,
# typically 30-60 fresh items per query that genuinely cite RFPs, tenders,
# EPC awards, and IPP biddings.
#
# Architecture:
#   - For each query, hit https://news.google.com/rss/search?q=…
#     with a real browser UA (Google blocks scraper UAs)
#   - In-process 1-hour cache (24 hits/day across the worker pool)
#   - Type-classify each title+excerpt into RFQ / RFP / TENDER / EOI / IPP
#   - Country-extract by matching against a known country whitelist (Google
#     News titles end with " - <Publisher>" not " - <Country>")
#   - De-dupe by link
#   - /admin/opportunities renders country / type chips + Add-to-leads

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


_OPPS_CACHE = {"fetched_at": 0, "items": []}
_OPPS_TTL_SECONDS = 60 * 60  # 1 hour

# Google News blocks programmatic UAs — must look like a real browser.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# Each query targets a different procurement phrasing. They overlap on
# purpose — de-dup happens after fetching.
_QUERIES = [
    '"solar tender" OR "solar RFP"',
    '"solar EPC" tender OR contract OR award',
    '"solar PV" "supply and install"',
    '"solar IPP" OR "solar power purchase agreement" bidding',
    '"mini grid" OR "mini-grid" solar tender OR RFP',
    '"rooftop solar" tender OR procurement OR "expression of interest"',
    '"photovoltaic" RFP OR tender OR "supply and install"',
    '"solar power project" bidding OR RFP OR "request for proposal"',
]


def _gnews_rss_url(query):
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )


# Country whitelist for extraction. Match in title (case-insensitive,
# word-boundary). Order matters — match the longest first to avoid
# "Korea" eating "South Korea".
_COUNTRY_HINTS = [
    "Saudi Arabia", "South Africa", "South Korea", "United Arab Emirates", "Sri Lanka",
    "United Kingdom", "United States", "Cape Verde", "Costa Rica", "Burkina Faso",
    "El Salvador", "Sierra Leone", "St. Kitts and Nevis", "Cayman Islands", "Hong Kong",
    "Czech Republic", "Dominican Republic", "Côte d'Ivoire", "Cote d'Ivoire",
    "Ivory Coast",
    "Afghanistan", "Algeria", "Angola", "Argentina", "Armenia", "Australia",
    "Austria", "Azerbaijan", "Bahrain", "Bangladesh", "Belgium", "Benin",
    "Bolivia", "Botswana", "Brazil", "Bulgaria", "Cambodia", "Cameroon",
    "Canada", "Chad", "Chile", "China", "Colombia", "Congo", "Croatia",
    "Cuba", "Cyprus", "Denmark", "Djibouti", "Ecuador", "Egypt", "Eritrea",
    "Estonia", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
    "Georgia", "Germany", "Ghana", "Greece", "Guatemala", "Guinea",
    "Guyana", "Haiti", "Honduras", "Hungary", "India", "Indonesia", "Iran",
    "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan",
    "Kazakhstan", "Kenya", "Kuwait", "Kyrgyzstan", "Laos", "Latvia",
    "Lebanon", "Lesotho", "Liberia", "Libya", "Lithuania", "Madagascar",
    "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania",
    "Mauritius", "Mexico", "Moldova", "Mongolia", "Morocco", "Mozambique",
    "Myanmar", "Namibia", "Nepal", "Netherlands", "Nicaragua", "Niger",
    "Nigeria", "Norway", "Oman", "Pakistan", "Panama", "Paraguay",
    "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
    "Rwanda", "Senegal", "Serbia", "Singapore", "Slovakia", "Slovenia",
    "Somalia", "Spain", "Sudan", "Sweden", "Switzerland", "Syria",
    "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Togo", "Tunisia",
    "Turkey", "Turkmenistan", "Uganda", "Ukraine", "Uruguay",
    "Uzbekistan", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]
# Precompile a single alternation regex (case-insensitive word boundaries).
_COUNTRY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _COUNTRY_HINTS) + r")\b",
    flags=re.IGNORECASE,
)


def _classify_type(title, body):
    """Classify RFQ / RFP / EOI / TENDER / IPP / OTHER from keywords."""
    blob = ((title or "") + " " + (body or "")).lower()
    if any(k in blob for k in ("request for quot", "rfq", "invitation for quot")):
        return "RFQ"
    if any(k in blob for k in ("request for propos", "rfp", "call for propos")):
        return "RFP"
    if "expression of interest" in blob or "eoi " in blob:
        return "EOI"
    if "ipp" in blob or "power purchase agreement" in blob or "ppa" in blob:
        return "IPP"
    if any(k in blob for k in ("tender", "itb ", "invitation to bid",
                               "bidding", "procurement")):
        return "TENDER"
    return "OTHER"


def _extract_country(title):
    """Match the title against the country whitelist. Returns the first hit
    or empty string. Sorted-by-length match prevents 'Korea' eating
    'South Korea'."""
    if not title:
        return ""
    m = _COUNTRY_RE.search(title)
    if not m:
        return ""
    hit = m.group(1).strip()
    # Normalise the canonical capitalisation
    for c in _COUNTRY_HINTS:
        if c.lower() == hit.lower():
            return c
    return hit.title()


def _extract_source(item):
    """Google News provides <source url=…>Publisher</source> per item.
    Fall back to parsing ` - Publisher` off the title."""
    src = item.find("source")
    if src is not None and (src.text or "").strip():
        return src.text.strip()
    t = (item.findtext("title") or "").strip()
    if " - " in t:
        return t.rsplit(" - ", 1)[1].strip()[:60]
    return "Google News"


def _strip_publisher_suffix(title):
    """Google News titles end with ` - Publisher`. Strip for cleaner display
    while keeping the publisher name in the `source` field."""
    if not title:
        return ""
    if " - " in title:
        return title.rsplit(" - ", 1)[0].strip()
    return title.strip()


def _fetch_one(query, timeout=8.0):
    url = _gnews_rss_url(query)
    req = urllib.request.Request(url, headers={
        "User-Agent": _BROWSER_UA,
        "Accept": "application/rss+xml,application/xml,text/xml",
    })
    out = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        root = ET.fromstring(body)
        channel = root.find("channel") or root
        for it in channel.findall("item"):
            raw_title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
            desc = re.sub(r"\s+", " ", desc).strip()
            pub = (it.findtext("pubDate") or "").strip()
            out.append({
                "title":      _strip_publisher_suffix(raw_title),
                "raw_title":  raw_title,
                "body":       desc[:600],
                "source_url": link,
                "source":     _extract_source(it),
                "country":    _extract_country(raw_title),
                "type":       _classify_type(raw_title, desc),
                "published":  pub,
            })
    except Exception as _e:
        try: app.logger.warning("Google News fetch failed for %r: %s", query, _e)
        except Exception: pass
    return out


def fetch_opportunities(force=False, timeout=8.0):
    """Fetch + de-dup solar opportunities from Google News across multiple
    queries. Returns a list of dicts:
       {title, body, source_url, source, country, type, published, raw_title}.
    Cached for 1 hour. Pass force=True to bypass cache."""
    now = time.time()
    if (not force and _OPPS_CACHE["items"]
            and (now - _OPPS_CACHE["fetched_at"]) < _OPPS_TTL_SECONDS):
        return _OPPS_CACHE["items"]

    seen = set()
    items = []
    for q in _QUERIES:
        for r in _fetch_one(q, timeout=timeout):
            key = (r.get("source_url") or "").strip().lower()
            # Fall back to title-key if URL missing
            if not key:
                key = "t:" + (r.get("title") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(r)

    # Order: RFQ first, then RFP, then EOI, then IPP, then TENDER, then OTHER.
    # Within each bucket, newest published first (best-effort string sort).
    _TYPE_PRIORITY = {"RFQ": 1, "RFP": 2, "EOI": 3, "IPP": 4,
                      "TENDER": 5, "OTHER": 6}
    def _key(x):
        return (_TYPE_PRIORITY.get(x["type"], 6),
                -len(x.get("published") or ""), x.get("title") or "")
    items.sort(key=_key)
    _OPPS_CACHE["items"] = items
    _OPPS_CACHE["fetched_at"] = now
    return items


@app.route("/admin/opportunities", methods=["GET"])
@login_required
def admin_opportunities():
    """List solar opportunities pulled from multi-query Google News RSS.
    Filterable by country, type, source. No API keys; cache 1 hour."""
    if not (current_user() and current_user().is_admin):
        from flask import abort as _abort
        return _abort(404)
    force = request.args.get("refresh") == "1"
    items = fetch_opportunities(force=force)
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
        items = [i for i in items
                 if (i.get("source") or "").lower() == f_source.lower()]

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
    """Copy a listed opportunity into the existing leads table so it can
    flow through the same pipeline as crawler-found leads."""
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
                 (title + " -- " + body)[:600], "gnews:" + src_url[:200],
                 "new", datetime.utcnow().isoformat() + "Z"),
            )
        flash("Added to leads.", "success")
    except Exception as e:
        try: app.logger.warning("add_to_leads failed: %s", e)
        except Exception: pass
        flash(f"Could not add to leads: {e}", "warning")
    return redirect(url_for("admin_opportunities"))
