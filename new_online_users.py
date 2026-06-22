# === BEGIN: online_users splice ===
# 2026-06-22 (session B): track who's currently online for the admin panel.
#
# Mechanism:
#   - users.last_seen TIMESTAMP column (idempotent ALTER).
#   - before_request hook updates last_seen for logged-in users, throttled
#     to once per 60s via a session timestamp marker so we don't write
#     on every static fetch.
#   - /admin/api/online-users JSON endpoint -> [{id,username,name,role,
#     ip,since_seconds}]
#   - Widget rendered on the admin marketplace dashboard (also good for
#     /admin home).

_ONLINE_WINDOW_SECS = 300   # 5 min counts as online
_LAST_SEEN_WRITE_GAP = 60   # only re-write last_seen once per minute per session


def _ensure_users_last_seen():
    """Idempotent ALTER on both engines."""
    for _ddl in (
        "ALTER TABLE users ADD COLUMN last_seen TEXT DEFAULT NULL",
    ):
        try:
            with get_db() as c:
                c.execute(_ddl)
        except Exception:
            pass


@app.before_request
def _bump_last_seen():
    """Update users.last_seen at most once per minute per active session."""
    try:
        uid = session.get("user_id")
        if not uid:
            return
        # Throttle via a session marker so we don't write on every request.
        try:
            from time import time as _t
        except Exception:
            return
        now_ts = int(_t())
        last_write = int(session.get("_ls_w", 0) or 0)
        if now_ts - last_write < _LAST_SEEN_WRITE_GAP:
            return
        session["_ls_w"] = now_ts
        # Best-effort write; never raises.
        try:
            with get_db() as c:
                c.execute(
                    "UPDATE users SET last_seen=CURRENT_TIMESTAMP WHERE id=?",
                    (uid,),
                )
        except Exception:
            try: _ensure_users_last_seen()
            except Exception: pass
    except Exception:
        pass


def _online_users(window_secs=None):
    """Return active-user rows (last_seen inside the window)."""
    if window_secs is None:
        window_secs = _ONLINE_WINDOW_SECS
    is_pg = bool(os.environ.get("DATABASE_URL"))
    try:
        with get_db() as c:
            if is_pg:
                rows = c.execute(
                    "SELECT id, username, COALESCE(name,'') AS name, "
                    "       COALESCE(role,'') AS role, COALESCE(plan,'') AS plan, "
                    "       last_seen, "
                    "       EXTRACT(EPOCH FROM (NOW() - last_seen))::INT AS since_seconds "
                    "FROM users "
                    "WHERE last_seen IS NOT NULL "
                    "  AND last_seen >= (NOW() - INTERVAL '%s seconds') "
                    "ORDER BY last_seen DESC LIMIT 100" % int(window_secs)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT id, username, COALESCE(name,'') AS name, "
                    "       COALESCE(role,'') AS role, COALESCE(plan,'') AS plan, "
                    "       last_seen, "
                    "       CAST(strftime('%s','now') - strftime('%s', last_seen) AS INT) AS since_seconds "
                    "FROM users "
                    "WHERE last_seen IS NOT NULL "
                    "  AND CAST(strftime('%s','now') - strftime('%s', last_seen) AS INT) <= ? "
                    "ORDER BY last_seen DESC LIMIT 100",
                    (window_secs,),
                ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({
                "id":            d.get("id"),
                "username":      d.get("username"),
                "name":          d.get("name") or "",
                "role":          d.get("role") or "",
                "plan":          d.get("plan") or "",
                "since_seconds": int(d.get("since_seconds") or 0),
            })
        return out
    except Exception:
        try: _ensure_users_last_seen()
        except Exception: pass
        return []


@app.route("/admin/api/online-users")
@admin_required
def admin_api_online_users():
    """JSON feed for the admin online-users widget. Polled every ~30s by
    the widget JS so the admin can see who's currently active."""
    users = _online_users()
    return jsonify({
        "count":  len(users),
        "users":  users,
        "window_seconds": _ONLINE_WINDOW_SECS,
    })


@app.route("/admin/online-users")
@admin_required
def admin_online_users_page():
    """Full-page view of online users for admins. Same data as the JSON
    endpoint but rendered as a table for first-load."""
    return render_template(
        "admin_online_users.html",
        user=current_user(),
        online=_online_users(),
        window_seconds=_ONLINE_WINDOW_SECS,
    )


# === END: online_users splice ===
