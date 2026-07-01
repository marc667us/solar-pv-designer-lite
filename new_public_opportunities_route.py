# === BEGIN: public_opportunities_route splice ===
# 2026-07-01: Public read-only view of solar_opportunities_crawled.
#
# Rationale: the underlying data is pulled from public Google News RSS
# feeds -- there's no reason to keep it admin-only. Making it public
# creates a lead-generation surface, cross-links to the marketplace,
# and fits the news/newsfeed/free-services theme.
#
# Route: GET /opportunities
#   Filters: ?type=RFQ|RFP|EOI|IPP|TENDER  ?country=<name>  ?page=<n>
#   Renders the persisted rows sorted by last_seen_at DESC.
#   If the table is empty (first-run bootstrap), triggers fetch_opportunities()
#   which writes through to the table via the persistence splice.


@app.route("/opportunities")
def public_opportunities():
    """Public read-only view of persisted solar opportunities."""
    _ensure_opps_crawled_table()

    # Bootstrap: if the table has never been populated, run a fetch now.
    with get_db() as c:
        n_total = int(c.execute(
            "SELECT COUNT(*) FROM solar_opportunities_crawled"
        ).fetchone()[0] or 0)

    if n_total == 0:
        try:
            fetch_opportunities()
            with get_db() as c:
                n_total = int(c.execute(
                    "SELECT COUNT(*) FROM solar_opportunities_crawled"
                ).fetchone()[0] or 0)
        except Exception:
            pass

    f_type    = (request.args.get("type") or "").strip().upper()
    f_country = (request.args.get("country") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1) or 1))
    except (TypeError, ValueError):
        page = 1
    per_page = 20
    offset = (page - 1) * per_page

    where = ["1=1"]
    params = []
    if f_type:
        where.append("type = ?")
        params.append(f_type)
    if f_country:
        where.append("LOWER(country) = LOWER(?)")
        params.append(f_country)
    where_sql = " AND ".join(where)

    with get_db() as c:
        n_filtered = int(c.execute(
            f"SELECT COUNT(*) FROM solar_opportunities_crawled WHERE {where_sql}",
            tuple(params),
        ).fetchone()[0] or 0)
        rows = c.execute(
            f"SELECT id, title, source, source_url, country, type, body, "
            f"       published, first_seen_at, last_seen_at "
            f"FROM solar_opportunities_crawled WHERE {where_sql} "
            f"ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
            tuple(params) + (per_page, offset),
        ).fetchall()

        # Facet counts for filter chips
        type_rows = c.execute(
            "SELECT type, COUNT(*) as n FROM solar_opportunities_crawled "
            "WHERE type != '' GROUP BY type ORDER BY n DESC"
        ).fetchall()
        country_rows = c.execute(
            "SELECT country, COUNT(*) as n FROM solar_opportunities_crawled "
            "WHERE country != '' GROUP BY country ORDER BY n DESC LIMIT 20"
        ).fetchall()

    def _row_to_dict(r):
        keys = ("id", "title", "source", "source_url", "country", "type",
                "body", "published", "first_seen_at", "last_seen_at")
        if hasattr(r, "keys"):
            return {k: r[k] for k in keys}
        return dict(zip(keys, r))

    def _facet(rows_):
        out = []
        for r in rows_:
            if hasattr(r, "keys"):
                out.append({"name": r[list(r.keys())[0]], "n": int(r["n"])})
            else:
                out.append({"name": r[0], "n": int(r[1])})
        return out

    total_pages = max(1, (n_filtered + per_page - 1) // per_page)
    return render_template(
        "opportunities_public.html",
        user=current_user(),
        items=[_row_to_dict(r) for r in rows],
        n_total=n_total,
        n_filtered=n_filtered,
        page=page,
        total_pages=total_pages,
        type_facets=_facet(type_rows),
        country_facets=_facet(country_rows),
        selected_type=f_type,
        selected_country=f_country,
    )


# === END: public_opportunities_route splice ===
