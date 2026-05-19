# auth/news_fetcher.py
# Fetches solar PV news from RSS feeds every 48 hours.
# Caches results to data/news_cache.json.
# Falls back to static articles if offline.

import urllib.request
import xml.etree.ElementTree as ET
import json
import os
import re
import datetime

CACHE_HOURS = 48   # Refresh interval

# RSS feeds — all solar/energy focused
RSS_SOURCES = [
    ("PV Magazine",        "https://www.pv-magazine.com/feed/"),
    ("PV Tech",            "https://www.pv-tech.org/feed/"),
    ("Solar Power World",  "https://www.solarpowerworldonline.com/feed/"),
    ("CleanTechnica",      "https://cleantechnica.com/feed/"),
    ("Recharge News",      "https://www.rechargenews.com/rss"),
]

# Keyword → category mapping
CAT_KEYWORDS = {
    "Products": [
        "panel", "module", "perc", "topcon", "hjt", "bifacial",
        "inverter", "battery", "storage", "longi", "jinko", "ja solar",
        "canadian solar", "rec group", "victron", "sma", "growatt",
        "goodwe", "huawei", "pylontech", "byd", "catl", "lifepo",
    ],
    "Market": [
        "price", "market", "cost", "gigawatt", "megawatt", " gw",
        "capacity", "shipment", "record", "demand", "supply",
        "manufacturing", "milestone", "terawatt",
    ],
    "Policy": [
        "policy", "regulation", "government", "tariff", "incentive",
        "subsidy", "net metering", "feed-in", "legislation",
        "ecowas", "purc", "energy commission", "ministry",
    ],
    "Africa": [
        "africa", "ghana", "nigeria", "kenya", "ethiopia",
        "sub-saharan", "west africa", "east africa", "mini-grid",
        "off-grid", "ecg", "kplc", "nerc", "eskom",
    ],
}


# ── Paths ─────────────────────────────────────────────────────────────────────
def _root():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cache_path():
    return os.path.join(_root(), "data", "news_cache.json")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    for ent, ch in [("&amp;","&"),("&lt;","<"),("&gt;",">"),("&quot;",'"'),("&#39;","'")]:
        text = text.replace(ent, ch)
    text = re.sub(r'&#\d+;', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def _fmt_date(rss_date):
    """Convert RFC 2822 pubDate to readable string."""
    try:
        from email.utils import parsedate
        t = parsedate(rss_date or "")
        if t:
            d = datetime.datetime(*t[:6])
            return d.strftime("%B %d, %Y")
    except Exception:
        pass
    return (rss_date or "")[:16]


def _classify(text):
    t = text.lower()
    for cat, kws in CAT_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return cat
    return "Industry"


# ── Fetching ──────────────────────────────────────────────────────────────────
def _fetch_feed(url, source_name):
    articles = []
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SolarPVDesignerLite/1.0 (RSS reader)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
        try:
            xml_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            xml_text = raw.decode("latin-1", errors="replace")

        root = ET.fromstring(xml_text)

        # RSS 2.0
        channel = root.find("channel")
        items   = (channel or root).findall("item")

        # Atom fallback
        if not items:
            ns = "http://www.w3.org/2005/Atom"
            items = root.findall(f"{{{ns}}}entry")

        for item in items[:7]:
            title   = _clean_html(item.findtext("title") or
                                   item.findtext("{http://www.w3.org/2005/Atom}title", ""))[:160]
            link    = (item.findtext("link") or "").strip()
            if not link:
                lel = item.find("{http://www.w3.org/2005/Atom}link")
                link = (lel.get("href", "") if lel is not None else "")
            pubdate = item.findtext("pubDate") or item.findtext(
                "{http://www.w3.org/2005/Atom}published", "")
            desc    = (item.findtext("description") or
                       item.findtext("{http://www.w3.org/2005/Atom}summary") or
                       item.findtext("{http://www.w3.org/2005/Atom}content") or "")
            summary = _clean_html(desc)[:420]

            if title and link:
                articles.append({
                    "cat":     _classify(title + " " + summary),
                    "title":   title,
                    "source":  source_name,
                    "date":    _fmt_date(pubdate),
                    "summary": summary,
                    "link":    link,
                })
    except Exception:
        pass  # Skip unavailable feeds silently
    return articles


def fetch_all():
    """Fetch fresh articles from all RSS sources."""
    articles = []
    for name, url in RSS_SOURCES:
        articles.extend(_fetch_feed(url, name))
    return articles


# ── Cache ─────────────────────────────────────────────────────────────────────
def _load_cache():
    path = _cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_cache(articles):
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "articles":   articles,
        }, f, indent=2, ensure_ascii=False)


def cache_age_hours():
    """Return age of news cache in hours, or None if no cache exists."""
    cache = _load_cache()
    if not cache:
        return None
    try:
        fetched = datetime.datetime.fromisoformat(cache["fetched_at"])
        return (datetime.datetime.now() - fetched).total_seconds() / 3600
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────
def load_news(force_refresh=False):
    """Return (articles, fetched_at_str).
    Uses cache if < 48 hrs old; fetches otherwise.
    Falls back to cache if offline; returns ([], '') if nothing available.
    """
    cache = _load_cache()

    # Use cache if fresh enough
    if not force_refresh and cache:
        try:
            fetched   = datetime.datetime.fromisoformat(cache["fetched_at"])
            age_hours = (datetime.datetime.now() - fetched).total_seconds() / 3600
            if age_hours < CACHE_HOURS:
                return cache["articles"], cache["fetched_at"]
        except Exception:
            pass

    # Try fetching fresh
    fresh = fetch_all()
    if fresh:
        _save_cache(fresh)
        return fresh, datetime.datetime.now().isoformat(timespec="seconds")

    # Offline — return stale cache if available
    if cache:
        return cache.get("articles", []), cache.get("fetched_at", "")

    return [], ""
