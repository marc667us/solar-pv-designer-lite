# === BEGIN: admin_actions_log splice ===
# 2026-06-22 (session B): /admin/actions-log page reading marketplace_audit_log
# with filters (action substring, user, time window) + pagination.
#
# Uses the existing _log_marketplace_action() writer + the
# marketplace_audit_log table that's already created lazily on first use.

@app.route("/admin/actions-log")
@admin_required
def admin_actions_log():
    """Admin-only audit feed. Filterable by action substring, user name,
    and time window (hours). Paginated via _products_per_page() default."""
    # Make sure the table exists so even a fresh DB renders an empty page.
    try:
        with get_db() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS marketplace_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    target_kind TEXT NOT NULL,
                    target_id INTEGER NOT NULL,
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
    except Exception:
        pass

    action_q = (request.args.get("action") or "").strip().lower()[:80]
    user_q   = (request.args.get("user") or "").strip().lower()[:80]
    try:
        hours_q = int(request.args.get("hours") or 0)
    except (TypeError, ValueError):
        hours_q = 0
    try:
        page = max(1, int(request.args.get("page") or 1))
    except (TypeError, ValueError):
        page = 1

    try:
        per_page = _products_per_page()
    except Exception:
        per_page = 24
    per_page = max(10, min(200, per_page))  # logs render denser; sensible window.

    is_pg = bool(os.environ.get("DATABASE_URL"))

    where = ["1=1"]
    args  = []
    if action_q:
        where.append("LOWER(mal.action) LIKE ?")
        args.append(f"%{action_q}%")
    if user_q:
        where.append("LOWER(COALESCE(u.username,'')) LIKE ?")
        args.append(f"%{user_q}%")
    if hours_q and hours_q > 0:
        if is_pg:
            where.append("mal.created_at >= (NOW() - INTERVAL '%d hours')" % int(hours_q))
        else:
            where.append("CAST(strftime('%s','now') - strftime('%s', mal.created_at) AS INT) <= ?")
            args.append(int(hours_q) * 3600)

    where_clause = " AND ".join(where)
    rows, total = [], 0
    try:
        with get_db() as c:
            count_sql = (
                "SELECT COUNT(*) "
                "FROM marketplace_audit_log mal "
                "LEFT JOIN users u ON u.id=mal.user_id "
                f"WHERE {where_clause}"
            )
            total = int(c.execute(count_sql, args).fetchone()[0] or 0)
            total_pages = max(1, (total + per_page - 1) // per_page)
            if page > total_pages:
                page = total_pages
            offset = (page - 1) * per_page
            sql = (
                "SELECT mal.id, mal.user_id, mal.action, mal.target_kind, mal.target_id, "
                "       mal.notes, mal.created_at, COALESCE(u.username,'(system)') AS actor "
                "FROM marketplace_audit_log mal "
                "LEFT JOIN users u ON u.id=mal.user_id "
                f"WHERE {where_clause} "
                "ORDER BY mal.created_at DESC, mal.id DESC LIMIT ? OFFSET ?"
            )
            rows = c.execute(sql, args + [per_page, offset]).fetchall()
    except Exception:
        total_pages = 1

    # Action-type tally for the filter chips.
    action_tally = []
    try:
        with get_db() as c:
            trows = c.execute(
                "SELECT action, COUNT(*) AS n FROM marketplace_audit_log "
                "GROUP BY action ORDER BY n DESC LIMIT 20"
            ).fetchall()
            action_tally = [{"action": r["action"], "n": int(r["n"])} for r in trows]
    except Exception:
        pass

    return render_template(
        "admin_actions_log.html",
        user=current_user(),
        rows=rows,
        page=page, total_pages=total_pages, products_per_page=per_page,
        filter_count=total,
        action_q=action_q, user_q=user_q, hours_q=hours_q,
        action_tally=action_tally,
    )


# === END: admin_actions_log splice ===
