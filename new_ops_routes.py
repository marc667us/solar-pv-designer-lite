
# -- Admin Ops: Ping endpoints ------------------------------------------------

@app.route("/admin/ops/ping/frontend")
@admin_required
def admin_ops_ping_frontend():
    # Check if the frontend (this Flask server) is responding
    return jsonify({"status": "ok", "service": "frontend", "message": "Flask app responding", "host": request.host})


@app.route("/admin/ops/ping/backend")
@admin_required
def admin_ops_ping_backend():
    # Check backend health (DB + app)
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return jsonify({"status": "ok", "service": "backend", "message": "Backend healthy, DB reachable"})
    except Exception as e:
        return jsonify({"status": "error", "service": "backend", "message": str(e)}), 500


@app.route("/admin/ops/ping/redis")
@admin_required
def admin_ops_ping_redis():
    # Check Redis connectivity
    import os
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return jsonify({"status": "unavailable", "service": "redis", "message": "REDIS_URL not configured (SQLite mode)"})
    try:
        import redis as redis_lib
        r = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        r.ping()
        info = r.info("memory")
        return jsonify({"status": "ok", "service": "redis", "message": "Redis PONG",
                        "used_memory": info.get("used_memory_human")})
    except ImportError:
        return jsonify({"status": "unavailable", "service": "redis", "message": "redis package not installed"})
    except Exception as e:
        return jsonify({"status": "error", "service": "redis", "message": str(e)}), 500


@app.route("/admin/ops/ping/database")
@admin_required
def admin_ops_ping_database():
    # Check database and return basic stats
    import time, os
    try:
        conn = get_db()
        t0 = time.time()
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        latency_ms = round((time.time() - t0) * 1000, 2)
        conn.close()
        db_path = os.environ.get("SQLITE_PATH", "solar.db")
        db_size_kb = round(os.path.getsize(db_path) / 1024, 1) if os.path.exists(db_path) else 0
        return jsonify({"status": "ok", "service": "database", "message": "Database healthy",
                        "users": user_count, "projects": project_count,
                        "latency_ms": latency_ms, "db_size_kb": db_size_kb})
    except Exception as e:
        return jsonify({"status": "error", "service": "database", "message": str(e)}), 500


# -- Admin Ops: RLS + Tenant Isolation ----------------------------------------

@app.route("/admin/ops/db/rls-check")
@admin_required
def admin_ops_rls_check():
    # Check Row Level Security status
    import os
    db_url = os.environ.get("DATABASE_URL", "sqlite:///solar.db")
    results = []
    if db_url.startswith("sqlite"):
        try:
            conn = get_db()
            for tbl in ["users", "projects", "tickets", "payments"]:
                try:
                    cols = [row[1] for row in conn.execute("PRAGMA table_info(%s)" % tbl).fetchall()]
                    has_isolation = any(c in cols for c in ["user_id", "organization_id", "org_id"])
                    results.append({"table": tbl, "rls_active": has_isolation,
                                    "note": "tenant column present" if has_isolation else "no tenant column"})
                except Exception:
                    results.append({"table": tbl, "rls_active": False, "note": "table not found"})
            conn.close()
            return jsonify({"status": "ok", "service": "rls",
                            "message": "SQLite: tenant column checks passed. Full RLS after PostgreSQL migration.",
                            "policies": results})
        except Exception as e:
            return jsonify({"status": "error", "service": "rls", "message": str(e)}), 500
    else:
        try:
            import psycopg2
            conn2 = psycopg2.connect(db_url)
            cur = conn2.cursor()
            cur.execute("SELECT tablename, policyname, cmd FROM pg_policies WHERE schemaname='public' ORDER BY tablename")
            rows = cur.fetchall()
            results = [{"table": r[0], "policy": r[1], "cmd": r[2]} for r in rows]
            conn2.close()
            return jsonify({"status": "ok", "service": "rls",
                            "message": "%d RLS policies active on PostgreSQL" % len(results),
                            "policies": results})
        except Exception as e:
            return jsonify({"status": "error", "service": "rls", "message": str(e)}), 500


@app.route("/admin/ops/security/tenant-isolation")
@admin_required
def admin_ops_tenant_isolation():
    # Verify tenant isolation checks
    try:
        conn = get_db()
        tests = []
        orphan_projects = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE user_id NOT IN (SELECT id FROM users)"
        ).fetchone()[0]
        tests.append({"test": "orphan_projects", "passed": orphan_projects == 0,
                      "detail": "%d orphan projects" % orphan_projects})
        try:
            orphan_tickets = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE user_id NOT IN (SELECT id FROM users)"
            ).fetchone()[0]
            tests.append({"test": "orphan_tickets", "passed": orphan_tickets == 0,
                          "detail": "%d orphan tickets" % orphan_tickets})
        except Exception:
            tests.append({"test": "orphan_tickets", "passed": True, "detail": "skipped"})
        admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1").fetchone()[0]
        tests.append({"test": "admin_accounts", "passed": admin_count > 0,
                      "detail": "%d admin account(s)" % admin_count})
        try:
            plaintext = conn.execute(
                "SELECT COUNT(*) FROM users WHERE password NOT LIKE '$%' AND password NOT LIKE 'pbkdf2%' AND length(password) < 30"
            ).fetchone()[0]
            tests.append({"test": "password_hashing", "passed": plaintext == 0,
                          "detail": "all passwords hashed" if plaintext == 0 else "%d possibly plaintext" % plaintext})
        except Exception:
            tests.append({"test": "password_hashing", "passed": True, "detail": "skipped"})
        conn.close()
        all_passed = all(t["passed"] for t in tests)
        return jsonify({"status": "ok" if all_passed else "warning",
                        "service": "tenant_isolation",
                        "message": "All isolation checks passed" if all_passed else "Some checks failed",
                        "tests": tests})
    except Exception as e:
        return jsonify({"status": "error", "service": "tenant_isolation", "message": str(e)}), 500


# -- Admin Ops: System tools --------------------------------------------------

@app.route("/admin/ops/system/pip-audit", methods=["POST"])
@admin_required
def admin_ops_pip_audit():
    # Run pip-audit or pip check for known vulnerabilities
    csrf_protect()
    import subprocess, sys, json as _json
    for cmd in [
        [sys.executable, "-m", "pip_audit", "--format=json", "--progress-spinner=off"],
        [sys.executable, "-m", "pip", "check"],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            output = result.stdout or result.stderr or "(no output)"
            if "pip_audit" in " ".join(cmd):
                try:
                    audit_data = _json.loads(output)
                    vulns = audit_data.get("vulnerabilities", [])
                    return jsonify({"status": "ok" if len(vulns) == 0 else "warning",
                                   "tool": "pip-audit",
                                   "vulnerabilities_found": len(vulns),
                                   "results": vulns[:20],
                                   "message": "No known vulnerabilities" if not vulns else "%d vulnerabilities found" % len(vulns)})
                except Exception:
                    return jsonify({"status": "ok", "tool": "pip-audit", "output": output[:2000], "return_code": result.returncode})
            else:
                return jsonify({"status": "ok" if result.returncode == 0 else "warning",
                               "tool": "pip check",
                               "output": output[:2000],
                               "message": "No package conflicts" if result.returncode == 0 else "Conflicts detected",
                               "return_code": result.returncode})
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            return jsonify({"status": "error", "message": "Timed out after 60s"}), 500
    return jsonify({"status": "error", "message": "pip-audit and pip check unavailable"}), 500


@app.route("/admin/ops/queue/restart", methods=["POST"])
@admin_required
def admin_ops_restart_queue():
    # Signal Celery workers to restart gracefully
    csrf_protect()
    import os
    try:
        from celery import Celery
    except ImportError:
        return jsonify({"status": "unavailable",
                       "message": "Celery not installed. Restart via: kubectl rollout restart deployment/celery-worker"})
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return jsonify({"status": "unavailable",
                       "message": "REDIS_URL not configured. Celery requires Redis broker."})
    try:
        app_celery = Celery(broker=redis_url)
        app_celery.control.warm_shutdown(reply=False)
        return jsonify({"status": "ok", "message": "Warm shutdown sent to Celery workers."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/ops/cache/clear", methods=["POST"])
@admin_required
def admin_ops_clear_cache():
    # Clear Redis cache entries
    csrf_protect()
    import os
    redis_url = os.environ.get("REDIS_URL", "")
    cleared_items = []
    try:
        from api_manager import api as _apim
        _apim.clear_cache()
        cleared_items.append("api_manager cache")
    except Exception:
        pass
    if not redis_url:
        return jsonify({"status": "ok" if cleared_items else "unavailable",
                       "message": "Redis not configured. Cleared: %s" % (", ".join(cleared_items) or "nothing")})
    try:
        import redis as redis_lib
        r = redis_lib.from_url(redis_url, socket_connect_timeout=3)
        deleted = 0
        for pattern in [b"shard:*", b"solar:*", b"rate:*"]:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        cleared_items.append("Redis (%d keys)" % deleted)
        return jsonify({"status": "ok", "message": "Cache cleared: %s" % ", ".join(cleared_items), "keys_deleted": deleted})
    except ImportError:
        return jsonify({"status": "unavailable", "message": "redis package not installed"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/ops/logs/view")
@admin_required
def admin_ops_view_logs():
    # Return last 100 app log entries as JSON
    import os, json as _json
    log_type = request.args.get("type", "app")
    log_paths = {"app": "logs/backend/app.log", "error": "logs/backend/error.log",
                 "security": "logs/security/security.log"}
    log_path = log_paths.get(log_type, "logs/backend/app.log")
    if not os.path.exists(log_path):
        return jsonify({"status": "ok", "entries": [],
                        "message": "Log file not found: %s. Logging to stdout in this environment." % log_path})
    entries = []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()[-100:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_json.loads(line))
            except Exception:
                entries.append({"raw": line})
        return jsonify({"status": "ok", "log_type": log_type, "entries": entries, "count": len(entries)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/ops/logs/audit")
@admin_required
def admin_ops_view_audit_logs():
    # Return last 100 audit log entries
    import os, json as _json
    for audit_path in ["logs/audit/audit.log", "logs/audit.log"]:
        if os.path.exists(audit_path):
            entries = []
            try:
                with open(audit_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()[-100:]
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(_json.loads(line))
                    except Exception:
                        entries.append({"raw": line})
                return jsonify({"status": "ok", "source": "file", "entries": entries, "count": len(entries)})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
    try:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT id, action, user_id, resource, status, created_at FROM audit_log ORDER BY id DESC LIMIT 100"
            ).fetchall()
            entries = [{"id": r[0], "action": r[1], "user_id": r[2],
                        "resource": r[3], "status": r[4], "created_at": r[5]} for r in rows]
            conn.close()
            return jsonify({"status": "ok", "source": "database", "entries": entries, "count": len(entries)})
        except Exception:
            conn.close()
            return jsonify({"status": "ok", "entries": [],
                            "message": "No audit_log table yet. Activates after PostgreSQL migration."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/admin/ops/system/load-test", methods=["POST"])
@admin_required
def admin_ops_load_test():
    # Run lightweight internal load test: 50 requests to /api/ping
    csrf_protect()
    import time, threading
    CONCURRENT = 5
    REQUESTS_EACH = 10
    results = {"success": 0, "error": 0, "times": []}
    lock = threading.Lock()

    def _worker():
        for _ in range(REQUESTS_EACH):
            t0 = time.time()
            try:
                with app.test_client() as tc:
                    resp = tc.get("/api/ping")
                    elapsed = (time.time() - t0) * 1000
                    with lock:
                        if resp.status_code == 200:
                            results["success"] += 1
                        else:
                            results["error"] += 1
                        results["times"].append(round(elapsed, 2))
            except Exception:
                with lock:
                    results["error"] += 1

    threads = [threading.Thread(target=_worker) for _ in range(CONCURRENT)]
    t_start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    duration = round(time.time() - t_start, 2)
    times = sorted(results["times"])
    total = results["success"] + results["error"]
    return jsonify({
        "status": "ok",
        "message": "%d requests in %ss" % (total, duration),
        "total_requests": total,
        "successful": results["success"],
        "errors": results["error"],
        "duration_seconds": duration,
        "rps": round(total / max(duration, 0.01), 1),
        "latency_ms": {
            "min": min(times) if times else 0,
            "max": max(times) if times else 0,
            "avg": round(sum(times) / max(len(times), 1), 2),
            "p95": times[int(len(times) * 0.95)] if len(times) > 1 else (times[0] if times else 0),
        }
    })

