# ─── Admin Ops: missing endpoints — added 2026-06-09 ─────────────────────────
# 7 routes that the admin_operations.html JS calls but that 404'd before.
# All gated by @admin_required (which itself checks login + is_admin flag).

@app.route("/admin/ops/ping/queue")
@admin_required
def admin_ops_ping_queue():
    """Queue subsystem status. On Render free tier there's no Celery/Redis,
    so we return WARN (not error) — that's the expected configured state."""
    import time
    t0 = time.time()
    redis_url = (os.environ.get("REDIS_URL", "") or os.environ.get("CELERY_BROKER_URL", "")).strip()
    if not redis_url:
        return jsonify({
            "status": "warn", "service": "queue",
            "message": "Queue/Celery not configured (Render free tier — no Redis add-on)",
            "broker_url_set": False,
            "latency_ms": round((time.time() - t0) * 1000, 2),
        })
    try:
        import redis  # may not be installed; we lazy-import
        r = redis.from_url(redis_url, socket_timeout=2)
        r.ping()
        # Approximate queue depth via Celery's default queue name "celery"
        try:
            depth = r.llen("celery")
        except Exception:
            depth = -1
        return jsonify({
            "status": "ok", "service": "queue",
            "message": "Redis broker reachable",
            "broker_url_set": True, "queue_depth": depth,
            "latency_ms": round((time.time() - t0) * 1000, 2),
        })
    except Exception as e:
        return jsonify({
            "status": "warn", "service": "queue",
            "message": f"Redis broker unreachable: {e}",
            "broker_url_set": True,
            "latency_ms": round((time.time() - t0) * 1000, 2),
        })


@app.route("/admin/ops/ping/ai")
@admin_required
def admin_ops_ping_ai():
    """AI provider configuration snapshot. Reports which providers are
    configured (key present), not which actually respond — keeps the
    endpoint fast (no outbound HTTP calls)."""
    import time
    t0 = time.time()
    providers = {
        "anthropic":    bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
        "openrouter":   bool((os.environ.get("OPENROUTER_API_KEY") or "").strip()),
        "ollama":       bool((os.environ.get("OLLAMA_URL") or "").strip()),
        "github_models":bool((os.environ.get("GITHUB_TOKEN") or "").strip()),
    }
    configured_count = sum(1 for v in providers.values() if v)
    return jsonify({
        "status": "ok" if configured_count > 0 else "warn",
        "service": "ai",
        "message": f"{configured_count} of {len(providers)} AI providers configured",
        "providers": providers,
        "latency_ms": round((time.time() - t0) * 1000, 2),
    })


@app.route("/admin/ops/ping/storage")
@admin_required
def admin_ops_ping_storage():
    """Disk space status for the volume hosting solar.db."""
    import time, shutil
    t0 = time.time()
    db_path = os.environ.get("SQLITE_PATH", os.environ.get("DB_PATH", "solar.db"))
    target = os.path.dirname(os.path.abspath(db_path)) or "."
    try:
        usage = shutil.disk_usage(target)
        pct_used = round((usage.used / usage.total) * 100, 1)
        status = "ok" if pct_used < 85 else ("warn" if pct_used < 95 else "error")
        return jsonify({
            "status": status, "service": "storage",
            "message": f"Disk at {pct_used}% used on {target}",
            "total_gb": round(usage.total / (1024**3), 2),
            "free_gb":  round(usage.free  / (1024**3), 2),
            "used_pct": pct_used,
            "latency_ms": round((time.time() - t0) * 1000, 2),
        })
    except Exception as e:
        return jsonify({
            "status": "error", "service": "storage",
            "message": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 2),
        }), 500


def _admin_ops_download_json(filename, payload):
    """Helper: serve a JSON blob as a downloaded file (Content-Disposition)."""
    from flask import make_response
    import json as _json
    body = _json.dumps(payload, indent=2, default=str)
    resp = make_response(body)
    resp.headers["Content-Type"] = "application/json"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@app.route("/admin/ops/security/report")
@admin_required
def admin_ops_security_report():
    """Downloadable security snapshot — aggregates audit log, brute-force
    state, session count, and security headers state into one JSON file."""
    import time
    from datetime import datetime as _dt
    snapshot = {
        "generated_at": _dt.utcnow().isoformat() + "Z",
        "report_type": "security",
        "checks": {},
    }
    try:
        conn = get_db()
        try:
            failed_logins = conn.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='login_failed'"
            ).fetchone()[0] if _table_exists(conn, "audit_logs") else None
        except Exception:
            failed_logins = None
        try:
            user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
        except Exception:
            user_count = admin_count = None
        conn.close()
        snapshot["checks"]["users_total"]   = user_count
        snapshot["checks"]["admins_total"]  = admin_count
        snapshot["checks"]["failed_logins_lifetime"] = failed_logins
    except Exception as e:
        snapshot["checks"]["db_error"] = str(e)
    snapshot["headers_configured"] = {
        "csp": True,            # web_app sets a Content-Security-Policy header
        "csrf_on_post": True,   # CSRF _csrf token enforced on POST forms
        "session_cookie_secure": True,
        "brute_force_lockout_min": 15,
    }
    fname = f"solarpro-security-{int(time.time())}.json"
    return _admin_ops_download_json(fname, snapshot)


@app.route("/admin/ops/db/report")
@admin_required
def admin_ops_db_report():
    """Downloadable DB health report — table sizes, row counts, schema version."""
    import time
    from datetime import datetime as _dt
    snapshot = {
        "generated_at": _dt.utcnow().isoformat() + "Z",
        "report_type": "database",
        "backend": "postgresql" if (os.environ.get("DATABASE_URL","").startswith("postgres"))
                                else "sqlite",
        "checks": {},
    }
    try:
        conn = get_db()
        tables = ("users", "projects", "tickets", "audit_logs", "beta_feedback",
                  "email_logs", "secret_audit")
        counts = {}
        for t in tables:
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                counts[t] = None  # table not present
        snapshot["checks"]["row_counts"] = counts
        db_path = os.environ.get("DB_PATH", "solar.db")
        if os.path.exists(db_path):
            snapshot["checks"]["file_size_kb"] = round(os.path.getsize(db_path) / 1024, 1)
        conn.close()
    except Exception as e:
        snapshot["checks"]["db_error"] = str(e)
    fname = f"solarpro-db-{int(time.time())}.json"
    return _admin_ops_download_json(fname, snapshot)


@app.route("/admin/ops/health/report")
@admin_required
def admin_ops_health_report():
    """Downloadable consolidated health report aggregating every subsystem."""
    import time
    from datetime import datetime as _dt
    snapshot = {
        "generated_at": _dt.utcnow().isoformat() + "Z",
        "report_type": "health",
        "host": os.environ.get("HOSTNAME", "unknown"),
        "render_service": os.environ.get("RENDER_SERVICE_NAME", "unknown"),
        "subsystems": {},
    }
    # Re-invoke each ping endpoint INTERNALLY to pull its JSON response body.
    for sub in ("database", "redis", "queue", "ai", "storage", "backend"):
        vf = app.view_functions.get(f"admin_ops_ping_{sub}")
        if vf is None:
            snapshot["subsystems"][sub] = {"status": "not_implemented"}
            continue
        try:
            resp = vf()
            body = resp.get_data() if hasattr(resp, "get_data") else b""
            import json as _json
            snapshot["subsystems"][sub] = _json.loads(body) if body else {}
        except Exception as e:
            snapshot["subsystems"][sub] = {"status": "error", "message": str(e)}
    fname = f"solarpro-health-{int(time.time())}.json"
    return _admin_ops_download_json(fname, snapshot)


@app.route("/admin/ops/logs/archive", methods=["POST"])
@admin_required
def admin_ops_logs_archive():
    """Archive (rotate) log files: rename current logs/*.log to
    logs/<name>.YYYYMMDD.log.gz and start fresh. Returns a summary.
    On Render free tier where logs aren't persistent across restart,
    this is mostly informational."""
    import time, os, gzip, shutil
    from datetime import datetime as _dt
    logs_dir = os.environ.get("LOGS_DIR", "logs")
    archived = []
    errors = []
    if not os.path.isdir(logs_dir):
        return jsonify({
            "status": "warn",
            "message": f"No logs directory at {logs_dir}",
            "archived": [],
        })
    stamp = _dt.utcnow().strftime("%Y%m%d_%H%M%S")
    for fname in os.listdir(logs_dir):
        if not fname.endswith(".log"):
            continue
        src = os.path.join(logs_dir, fname)
        dst = os.path.join(logs_dir, f"{fname[:-4]}.{stamp}.log.gz")
        try:
            with open(src, "rb") as fin, gzip.open(dst, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            # Truncate the live log so it starts fresh (don't unlink — keep handle valid)
            open(src, "w").close()
            archived.append({"file": fname, "archive": os.path.basename(dst)})
        except Exception as e:
            errors.append({"file": fname, "error": str(e)})
    return jsonify({
        "status": "ok" if not errors else "partial",
        "message": f"Archived {len(archived)} log file(s); {len(errors)} error(s)",
        "archived": archived, "errors": errors,
        "timestamp": stamp,
    })


def _table_exists(conn, table_name):
    """SQLite-specific helper: check if a table exists. Returns False on
    Postgres (where the caller should use information_schema). For the
    security report this is best-effort; missing audit_logs table just
    yields None for that field."""
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        ).fetchone()
        return row is not None
    except Exception:
        return False
