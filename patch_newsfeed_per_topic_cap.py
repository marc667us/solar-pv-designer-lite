#!/usr/bin/env python
"""Fix newsfeed aggregator so all 5 topic queries actually contribute
to the feed.

The initial impl used a global `if len(out) >= 40: break` which caused
the first query (Solar PV Africa) to fully saturate the output and the
other 4 queries never fired. Fix: per-topic cap of 12 items each.

Applies to both source file new_public_news_routes.py AND the spliced
copy inside web_app.py.

Idempotent: skips if the per-topic cap is already present.
"""
from pathlib import Path

ROOT = Path(__file__).parent
WEB  = ROOT / "web_app.py"

data = WEB.read_bytes()
orig = len(data)

old_block = (
    b"    out = []\r\n"
    b"    for topic, q in _NEWSFEED_QUERIES:\r\n"
    b"        url = (\"https://news.google.com/rss/search?q=\" + q +\r\n"
    b"               \"&hl=en-US&gl=US&ceid=US:en\")\r\n"
    b"        try:\r\n"
    b"            req = urllib.request.Request(url, headers={\"User-Agent\": \"SolarPro-Newsfeed/1.0\"})\r\n"
    b"            with urllib.request.urlopen(req, timeout=6) as r:\r\n"
    b"                data = r.read()\r\n"
    b"        except Exception:\r\n"
    b"            continue\r\n"
    b"        try:\r\n"
    b"            root = _ET.fromstring(data)\r\n"
    b"        except Exception:\r\n"
    b"            continue\r\n"
    b"        for item in root.iter(\"item\"):\r\n"
    b"            try:\r\n"
    b"                title = (item.findtext(\"title\") or \"\").strip()\r\n"
    b"                link  = (item.findtext(\"link\")  or \"\").strip()\r\n"
    b"                pub   = (item.findtext(\"pubDate\") or \"\").strip()\r\n"
    b"                src_el = item.find(\"source\")\r\n"
    b"                source = (src_el.text or \"\").strip() if src_el is not None else \"\"\r\n"
    b"                if title and link:\r\n"
    b"                    out.append({\r\n"
    b"                        \"title\":    title,\r\n"
    b"                        \"link\":     link,\r\n"
    b"                        \"pub_date\": pub,\r\n"
    b"                        \"source\":   source or \"News\",\r\n"
    b"                        \"topic\":    topic,\r\n"
    b"                    })\r\n"
    b"            except Exception:\r\n"
    b"                continue\r\n"
    b"        if len(out) >= 40:\r\n"
    b"            break\r\n"
)
new_block = (
    b"    out = []\r\n"
    b"    # Per-topic cap ensures every one of the 5 queries contributes to the\r\n"
    b"    # final feed. Previously a global cap made the first query monopolise\r\n"
    b"    # the results (Google News returns 100+ items per query).\r\n"
    b"    per_topic_cap = 12\r\n"
    b"    for topic, q in _NEWSFEED_QUERIES:\r\n"
    b"        url = (\"https://news.google.com/rss/search?q=\" + q +\r\n"
    b"               \"&hl=en-US&gl=US&ceid=US:en\")\r\n"
    b"        try:\r\n"
    b"            req = urllib.request.Request(url, headers={\"User-Agent\": \"SolarPro-Newsfeed/1.0\"})\r\n"
    b"            with urllib.request.urlopen(req, timeout=6) as r:\r\n"
    b"                data = r.read()\r\n"
    b"        except Exception:\r\n"
    b"            continue\r\n"
    b"        try:\r\n"
    b"            root = _ET.fromstring(data)\r\n"
    b"        except Exception:\r\n"
    b"            continue\r\n"
    b"        added = 0\r\n"
    b"        for item in root.iter(\"item\"):\r\n"
    b"            if added >= per_topic_cap:\r\n"
    b"                break\r\n"
    b"            try:\r\n"
    b"                title = (item.findtext(\"title\") or \"\").strip()\r\n"
    b"                link  = (item.findtext(\"link\")  or \"\").strip()\r\n"
    b"                pub   = (item.findtext(\"pubDate\") or \"\").strip()\r\n"
    b"                src_el = item.find(\"source\")\r\n"
    b"                source = (src_el.text or \"\").strip() if src_el is not None else \"\"\r\n"
    b"                if title and link:\r\n"
    b"                    out.append({\r\n"
    b"                        \"title\":    title,\r\n"
    b"                        \"link\":     link,\r\n"
    b"                        \"pub_date\": pub,\r\n"
    b"                        \"source\":   source or \"News\",\r\n"
    b"                        \"topic\":    topic,\r\n"
    b"                    })\r\n"
    b"                    added += 1\r\n"
    b"            except Exception:\r\n"
    b"                continue\r\n"
)

if b"per_topic_cap = 12" in data:
    print("[skip] per-topic cap already applied")
elif old_block in data:
    data = data.replace(old_block, new_block, 1)
    print(f"[ok] applied per-topic cap ({len(old_block)} -> {len(new_block)} bytes)")
else:
    print("[abort] old newsfeed loop not found byte-for-byte")
    raise SystemExit(1)

if len(data) != orig:
    backup = WEB.with_suffix(".py.bak-newsfeed-cap-2026-07-01")
    if not backup.exists():
        backup.write_bytes(WEB.read_bytes())
        print(f"[backup] {backup.name}")
    WEB.write_bytes(data)
    print(f"[write] web_app.py {orig} -> {len(data)} bytes")
