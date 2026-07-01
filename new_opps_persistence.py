# === BEGIN: opps_persistence splice ===
# 2026-07-01: Persist solar opportunities fetched by admin_opportunities
# into `solar_opportunities_crawled` so history survives redeploys.
#
# Prior state:
#   - fetch_opportunities() stored results in _OPPS_CACHE (in-process, 1h
#     TTL). Every redeploy wiped the cache and every hour the whole feed
#     was re-scanned from scratch.
#
# This module:
#   - Creates the table if missing (idempotent, both SQLite + Postgres).
#   - Provides _persist_opportunities(items) that upserts on source_url:
#       INSERT if source_url is new;
#       UPDATE last_seen_at + refresh title/body/type/country/source if seen before.
#   - Exposes _opportunities_history_count() for the admin page.
#
# Kept in a splice module (not a background thread / celery job) so the
# existing 1-hour fetch cycle triggers persistence automatically the
# next time an admin visits /admin/opportunities. When a cron worker is
# eventually wired to hit the fetch endpoint on a schedule, no code
# change here is needed.


def _ensure_opps_crawled_table():
    """Create solar_opportunities_crawled table if missing. Idempotent
    across SQLite and Postgres backends."""
    try:
        with get_db() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS solar_opportunities_crawled (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    title          TEXT NOT NULL DEFAULT '',
                    source         TEXT DEFAULT '',
                    source_url     TEXT NOT NULL,
                    country        TEXT DEFAULT '',
                    type           TEXT DEFAULT '',
                    body           TEXT DEFAULT '',
                    published      TEXT DEFAULT '',
                    first_seen_at  TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at   TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(source_url)
                );
                CREATE INDEX IF NOT EXISTS idx_opps_crawled_type
                    ON solar_opportunities_crawled(type);
                CREATE INDEX IF NOT EXISTS idx_opps_crawled_country
                    ON solar_opportunities_crawled(country);
                CREATE INDEX IF NOT EXISTS idx_opps_crawled_last_seen
                    ON solar_opportunities_crawled(last_seen_at DESC);
                """
            )
    except Exception:
        # Postgres path: run each DDL separately since executescript is
        # SQLite-only; ADD COLUMN IF NOT EXISTS handles the schema safely.
        try:
            with get_db() as c:
                for _ddl in (
                    """CREATE TABLE IF NOT EXISTS solar_opportunities_crawled (
                        id             SERIAL PRIMARY KEY,
                        title          TEXT NOT NULL DEFAULT '',
                        source         TEXT DEFAULT '',
                        source_url     TEXT NOT NULL,
                        country        TEXT DEFAULT '',
                        type           TEXT DEFAULT '',
                        body           TEXT DEFAULT '',
                        published      TEXT DEFAULT '',
                        first_seen_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(source_url)
                    )""",
                    "CREATE INDEX IF NOT EXISTS idx_opps_crawled_type "
                    "ON solar_opportunities_crawled(type)",
                    "CREATE INDEX IF NOT EXISTS idx_opps_crawled_country "
                    "ON solar_opportunities_crawled(country)",
                    "CREATE INDEX IF NOT EXISTS idx_opps_crawled_last_seen "
                    "ON solar_opportunities_crawled(last_seen_at DESC)",
                ):
                    try:
                        c.execute(_ddl)
                    except Exception:
                        pass
        except Exception:
            pass


def _persist_opportunities(items):
    """Upsert a list of opportunity dicts (as produced by fetch_opportunities)
    into solar_opportunities_crawled. Returns (inserted, updated) counts.

    Idempotent on repeated calls thanks to UNIQUE(source_url).
    """
    if not items:
        return (0, 0)
    _ensure_opps_crawled_table()
    inserted = 0
    updated = 0
    try:
        with get_db() as c:
            for it in items:
                src_url = (it.get("source_url") or "").strip()
                if not src_url:
                    continue
                title    = (it.get("title") or "")[:500]
                source   = (it.get("source") or "")[:120]
                country  = (it.get("country") or "")[:100]
                type_    = (it.get("type") or "")[:20]
                body     = (it.get("body") or "")[:2000]
                pub      = (it.get("published") or "")[:80]
                try:
                    existing = c.execute(
                        "SELECT id FROM solar_opportunities_crawled "
                        "WHERE source_url=? LIMIT 1",
                        (src_url,),
                    ).fetchone()
                except Exception:
                    existing = None
                if existing:
                    try:
                        c.execute(
                            "UPDATE solar_opportunities_crawled "
                            "SET title=?, source=?, country=?, type=?, body=?, "
                            "    published=?, last_seen_at=CURRENT_TIMESTAMP "
                            "WHERE source_url=?",
                            (title, source, country, type_, body, pub, src_url),
                        )
                        updated += 1
                    except Exception:
                        pass
                else:
                    try:
                        c.execute(
                            "INSERT INTO solar_opportunities_crawled "
                            "(title, source, source_url, country, type, body, published) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (title, source, src_url, country, type_, body, pub),
                        )
                        inserted += 1
                    except Exception:
                        pass
    except Exception as _e:
        try: app.logger.warning("_persist_opportunities failed: %s", _e)
        except Exception: pass
    return (inserted, updated)


def _opportunities_history_stats():
    """Return summary counts for the admin dashboard.
    {total, by_type: {...}, by_country_top5: [...], newest_seen: str}"""
    out = {"total": 0, "by_type": {}, "by_country_top5": [], "newest_seen": ""}
    try:
        _ensure_opps_crawled_table()
        with get_db() as c:
            out["total"] = int(
                c.execute("SELECT COUNT(*) FROM solar_opportunities_crawled").fetchone()[0] or 0
            )
            rows = c.execute(
                "SELECT type, COUNT(*) as n FROM solar_opportunities_crawled "
                "GROUP BY type ORDER BY n DESC"
            ).fetchall()
            for r in rows:
                t = (r["type"] if hasattr(r, "keys") else r[0]) or "OTHER"
                n = int(r["n"] if hasattr(r, "keys") else r[1])
                out["by_type"][t] = n
            rows = c.execute(
                "SELECT country, COUNT(*) as n FROM solar_opportunities_crawled "
                "WHERE country != '' GROUP BY country ORDER BY n DESC LIMIT 5"
            ).fetchall()
            for r in rows:
                out["by_country_top5"].append({
                    "country": r["country"] if hasattr(r, "keys") else r[0],
                    "n":       int(r["n"] if hasattr(r, "keys") else r[1]),
                })
            r = c.execute(
                "SELECT last_seen_at FROM solar_opportunities_crawled "
                "ORDER BY last_seen_at DESC LIMIT 1"
            ).fetchone()
            if r:
                out["newest_seen"] = str(r["last_seen_at"] if hasattr(r, "keys") else r[0])
    except Exception:
        pass
    return out


# === END: opps_persistence splice ===
