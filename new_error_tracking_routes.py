# ─── Error tracking + reporting (SOC 2 M3.3 + M3.5) ──────────────────────
# Added 2026-06-25. Two layers:
#
#   1. Always-on local capture.  Every uncaught exception lands in the
#      error_logs table with: request_id, route, method, status, exc type,
#      exc message, stack trace, ip, user_agent, fingerprint (hash for grouping),
#      user_id, tenant_id, resolved flag.  No external dependency required.
#
#   2. Optional Sentry / GlitchTip push.  If SENTRY_DSN is set, the same
#      exception is also pushed to Sentry via the sentry-sdk Flask integration.
#      The sdk is imported lazily; missing package is non-fatal.
#
# Admin viewer at /admin/errors (list + filter) and /admin/errors/<id> (detail).
# Hooked into the SOC 2 audit (M3.5 Error tracker present check).
#
# The existing @app.errorhandler(Exception) at the err_uncaught function is
# extended (Pattern A patch) to also call _record_error(e) before rendering
# the friendly error page, so the user-facing behaviour is unchanged.

import hashlib as _hash_mod
import traceback as _tb_mod


# Module-level singleton flag so _maybe_init_sentry() runs once per process.
_SENTRY_INITIALIZED = False


def _maybe_init_sentry():
    """Best-effort Sentry initialisation. Gated on SENTRY_DSN; safe if the
    package isn't installed."""
    global _SENTRY_INITIALIZED
    if _SENTRY_INITIALIZED:
        return
    _SENTRY_INITIALIZED = True  # one shot, even on failure
    dsn = (os.environ.get("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.flask import FlaskIntegration  # type: ignore
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
            send_default_pii=False,
            environment=os.environ.get("APP_ENV", "production"),
            release=os.environ.get("APP_VERSION", "unknown"),
        )
    except Exception as _e:
        try:
            app.logger.warning("Sentry init skipped: %s", _e)
        except Exception:
            pass


def _ensure_error_logs_table(conn):
    """Idempotent create — works on Postgres and SQLite."""
    try:
        # Postgres-shaped
        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id           SERIAL PRIMARY KEY,
                created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                request_id   TEXT,
                route        TEXT,
                method       TEXT,
                status       INTEGER,
                error_type   TEXT,
                error_message TEXT,
                stack_trace  TEXT,
                ip_address   TEXT,
                user_agent   TEXT,
                user_id      INTEGER,
                tenant_id    TEXT,
                fingerprint  TEXT,
                resolved     BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
    except Exception:
        # SQLite fallback (no SERIAL, no BOOLEAN)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    request_id   TEXT,
                    route        TEXT,
                    method       TEXT,
                    status       INTEGER,
                    error_type   TEXT,
                    error_message TEXT,
                    stack_trace  TEXT,
                    ip_address   TEXT,
                    user_agent   TEXT,
                    user_id      INTEGER,
                    tenant_id    TEXT,
                    fingerprint  TEXT,
                    resolved     INTEGER NOT NULL DEFAULT 0
                )
            """)
        except Exception:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_logs_created ON error_logs(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_logs_fingerprint ON error_logs(fingerprint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_logs_resolved ON error_logs(resolved)")
    except Exception:
        pass


def _error_fingerprint(error_type, error_message, route):
    """Stable grouping key — same exception type + route = same fingerprint.
    Used so the viewer can collapse repeated errors."""
    raw = f"{error_type}|{route}|{(error_message or '')[:120]}"
    return _hash_mod.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _record_error(exc, status=500):
    """Write one row to error_logs and (optionally) push to Sentry.

    Wraps every step in try/except so a logging failure can never escalate
    a 500 into a worse user-facing failure.
    """
    _maybe_init_sentry()

    try:
        error_type = exc.__class__.__name__
        error_message = str(exc)[:1024]
        stack_trace = _tb_mod.format_exc()[:8192]
        try:
            route = request.path
            method = request.method
            ua = (request.headers.get("User-Agent") or "")[:300]
            try:
                ip = _get_real_ip()
            except Exception:
                ip = request.remote_addr or ""
        except Exception:
            route = method = ua = ip = ""
        try:
            user_id = session.get("user_id")
        except Exception:
            user_id = None
        try:
            ctx = getattr(g, "kc_ctx", None)
            tenant_id = ctx.tenant_id if ctx else None
        except Exception:
            tenant_id = None
        try:
            request_id = getattr(g, "request_id", None) or ""
        except Exception:
            request_id = ""
        fingerprint = _error_fingerprint(error_type, error_message, route)

        with get_db() as c:
            _ensure_error_logs_table(c)
            c.execute(
                "INSERT INTO error_logs (request_id, route, method, status, "
                "error_type, error_message, stack_trace, ip_address, user_agent, "
                "user_id, tenant_id, fingerprint) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (request_id, route, method, status, error_type, error_message,
                 stack_trace, ip, ua, user_id, tenant_id, fingerprint),
            )
    except Exception as _e:
        try:
            app.logger.error("error_logs write failed: %s", _e)
        except Exception:
            pass

    # Optional Sentry push (sentry_sdk auto-captures Flask exceptions when
    # init succeeded; the manual call is harmless and works without the
    # FlaskIntegration if the user installed only the bare sentry-sdk).
    try:
        import sentry_sdk  # type: ignore
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass


@app.route("/admin/errors")
@admin_required
def admin_errors_list():
    """Grouped + recent error log viewer."""
    status_filter = request.args.get("status")  # "open" | "resolved" | None
    fp_filter = request.args.get("fp") or ""
    limit = max(1, min(int(request.args.get("limit", "100") or 100), 500))

    rows = []
    grouped = []
    try:
        with get_db() as c:
            _ensure_error_logs_table(c)
            where = []
            params = []
            if status_filter == "open":
                where.append("(resolved=0 OR resolved=FALSE)")
            elif status_filter == "resolved":
                where.append("(resolved=1 OR resolved=TRUE)")
            if fp_filter:
                where.append("fingerprint = ?")
                params.append(fp_filter)
            where_sql = (" WHERE " + " AND ".join(where)) if where else ""

            rows = c.execute(
                "SELECT id, created_at, route, method, status, error_type, "
                "error_message, fingerprint, resolved, user_id, tenant_id "
                "FROM error_logs " + where_sql + " ORDER BY id DESC LIMIT ?",
                tuple(params) + (limit,),
            ).fetchall()

            grouped = c.execute(
                "SELECT fingerprint, error_type, route, COUNT(*) AS hits, "
                "MAX(created_at) AS last_seen "
                "FROM error_logs " + where_sql + " "
                "GROUP BY fingerprint, error_type, route "
                "ORDER BY hits DESC LIMIT 25",
                tuple(params),
            ).fetchall()
    except Exception as e:
        try:
            app.logger.warning("admin_errors_list failed: %s", e)
        except Exception:
            pass

    return render_template(
        "admin_errors.html",
        rows=[dict(r) for r in rows] if rows else [],
        grouped=[dict(r) for r in grouped] if grouped else [],
        status_filter=status_filter or "all",
        fp_filter=fp_filter,
        limit=limit,
        sentry_enabled=bool((os.environ.get("SENTRY_DSN") or "").strip()),
    )


@app.route("/admin/errors/<int:error_id>")
@admin_required
def admin_error_detail(error_id):
    row = None
    try:
        with get_db() as c:
            _ensure_error_logs_table(c)
            r = c.execute(
                "SELECT * FROM error_logs WHERE id=?", (error_id,)
            ).fetchone()
            row = dict(r) if r else None
    except Exception:
        row = None
    if not row:
        flash("Error record not found.", "warning")
        return redirect(url_for("admin_errors_list"))
    return render_template("admin_error_detail.html", row=row)


@app.route("/admin/errors/<int:error_id>/resolve", methods=["POST"])
@admin_required
def admin_error_resolve(error_id):
    csrf_protect()
    try:
        with get_db() as c:
            _ensure_error_logs_table(c)
            # Postgres uses TRUE/FALSE; SQLite uses 1/0. Both accept "1".
            c.execute("UPDATE error_logs SET resolved=1 WHERE id=?", (error_id,))
        try:
            log_audit(action="error_resolved",
                      user_id=session.get("user_id"),
                      status="pass",
                      details=f"error_id={error_id}")
        except Exception:
            pass
        flash(f"Error #{error_id} marked resolved.", "success")
    except Exception as e:
        flash(f"Could not mark resolved: {e}", "danger")
    return redirect(url_for("admin_errors_list"))


@app.route("/api/errors/recent")
@admin_required
def api_errors_recent():
    """JSON feed for dashboard widgets."""
    try:
        with get_db() as c:
            _ensure_error_logs_table(c)
            try:
                # Postgres path
                total24 = c.execute(
                    "SELECT COUNT(*) FROM error_logs "
                    "WHERE created_at > (NOW() - INTERVAL '24 hours')"
                ).fetchone()[0]
            except Exception:
                # SQLite fallback
                total24 = c.execute(
                    "SELECT COUNT(*) FROM error_logs "
                    "WHERE created_at > datetime('now', '-1 day')"
                ).fetchone()[0]
            try:
                open_count = c.execute(
                    "SELECT COUNT(*) FROM error_logs WHERE resolved=0 OR resolved=FALSE"
                ).fetchone()[0]
            except Exception:
                open_count = c.execute(
                    "SELECT COUNT(*) FROM error_logs WHERE resolved=0"
                ).fetchone()[0]
            recent = c.execute(
                "SELECT id, created_at, route, error_type, error_message "
                "FROM error_logs ORDER BY id DESC LIMIT 10"
            ).fetchall()
        return jsonify({
            "open": open_count,
            "last_24h": total24,
            "recent": [dict(r) for r in recent] if recent else [],
            "sentry_enabled": bool((os.environ.get("SENTRY_DSN") or "").strip()),
        })
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


# Initialise Sentry early so any uncaught exception during init still bubbles up.
_maybe_init_sentry()


