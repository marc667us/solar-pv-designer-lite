# ─── SOC 2 readiness audit ───────────────────────────────────────────────
# Added 2026-06-25 as part of SOC 2 M1.1 + M4.7 (audit dashboard seed).
# Walks the LIVE app + database and returns a concrete findings report:
#   * Keycloak flag retirement (M1.1)
#   * Phase B migration applied (M1.3)
#   * RLS coverage % (M1.6)
#   * Tenant-column coverage % (M3.1)
#   * Audit-log activity (proves logging works) (M3.1, M3.2)
#   * Security test count (M3.10)
#   * Policy doc count (M4.5)
#   * Backups / DR / pen-test / evidence collector — placeholders that
#     surface "not yet implemented" until the matching milestone closes.
# Two endpoints:
#   POST /admin/ops/soc2/audit  -> JSON for the opcenter AJAX panel
#   GET  /admin/soc2/report     -> full HTML report page (printable)


def _soc2_check_kc_flag_retired():
    """M1.1: the KEYCLOAK_ENABLED kill-switch must be hard-wired True."""
    try:
        from app.security.decorators import _keycloak_enabled as _dec
        from app.security.tenant_context import _keycloak_enabled as _tc
        from app.security.service_account_client import _keycloak_enabled as _sa
        from app.auth.oidc_routes import _keycloak_enabled as _oidc
        from app.auth.internal_calls import _keycloak_enabled as _ic
        helpers = (_dec, _tc, _sa, _oidc, _ic)
        all_true = all(h() for h in helpers)
        return {
            "status": "pass" if all_true else "fail",
            "detail": f"{sum(1 for h in helpers if h())}/{len(helpers)} _keycloak_enabled() helpers return True",
        }
    except Exception as e:
        return {"status": "fail", "detail": f"import error: {str(e)[:80]}"}


def _soc2_check_kc_issuer_configured():
    """OIDC requires a configured issuer for any flow to work."""
    iss = os.environ.get("KEYCLOAK_ISSUER", "").strip()
    if iss:
        return {"status": "pass", "detail": f"issuer set ({iss[:60]})"}
    return {"status": "fail", "detail": "KEYCLOAK_ISSUER env unset"}


def _soc2_check_phase_b_migration():
    """M1.3: bcrypt column dropped from users table."""
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users' AND column_name='password_hash'"
            ).fetchone()
            if row is None:
                return {"status": "pass", "detail": "users.password_hash dropped"}
            return {
                "status": "warn",
                "detail": "users.password_hash still present (Phase B migration not yet applied; ETA >= 2026-06-30)",
            }
    except Exception as e:
        # Probably SQLite (no information_schema) — try a PRAGMA
        try:
            with get_db() as c:
                cols = c.execute("PRAGMA table_info(users)").fetchall()
                has = any(r[1] == "password_hash" for r in cols)
                return {
                    "status": "warn" if has else "pass",
                    "detail": "users.password_hash " + ("present (SQLite dev DB)" if has else "absent"),
                }
        except Exception as e2:
            return {"status": "warn", "detail": f"introspection failed: {str(e2)[:80]}"}


def _soc2_check_rls_coverage():
    """M1.6: count tenant_isolation policies in pg_policies."""
    try:
        with get_db() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM pg_policies "
                "WHERE policyname LIKE '%_tenant_isolation' OR policyname LIKE '%tenant_policy%'"
            ).fetchone()
            n = (row[0] if row else 0) or 0
            if n >= 14:
                return {"status": "pass", "detail": f"{n} RLS policies present"}
            if n > 0:
                return {"status": "warn", "detail": f"only {n} RLS policies (expand to every tenant table — M1.6)"}
            return {"status": "fail", "detail": "no RLS policies found (SQLite dev DB or Phase 4 migration not applied)"}
    except Exception as e:
        return {"status": "warn", "detail": f"pg_policies introspection failed (likely SQLite): {str(e)[:60]}"}


def _soc2_check_tenant_column_coverage():
    """% of multi-tenant tables that carry tenant_id."""
    try:
        with get_db() as c:
            # Postgres path
            rows = c.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            ).fetchall()
            tables = [r[0] for r in rows]
            with_tid = c.execute(
                "SELECT DISTINCT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='tenant_id'"
            ).fetchall()
            with_tid = {r[0] for r in with_tid}
        total = len(tables) or 1
        present = len(with_tid)
        pct = round(100.0 * present / total, 1)
        status = "pass" if pct >= 90 else ("warn" if pct >= 50 else "fail")
        return {"status": status, "detail": f"{present}/{total} tables carry tenant_id ({pct}%)"}
    except Exception as e:
        return {"status": "warn", "detail": f"introspection failed (likely SQLite): {str(e)[:60]}"}


def _soc2_check_audit_log_activity():
    """M3.1: audit_logs table receives writes in the last 24h."""
    try:
        with get_db() as c:
            row = c.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
            total = (row[0] if row else 0) or 0
            row = c.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE created_at > (NOW() - INTERVAL '24 hours')"
            ).fetchone() if total else None
            recent = (row[0] if row else 0) or 0
        if total == 0:
            return {"status": "fail", "detail": "audit_logs table empty"}
        if recent == 0:
            return {"status": "warn", "detail": f"{total} total rows but 0 in last 24h"}
        return {"status": "pass", "detail": f"{recent} rows in last 24h (lifetime {total})"}
    except Exception as e:
        # SQLite fallback (no NOW())
        try:
            with get_db() as c:
                row = c.execute("SELECT COUNT(*) FROM audit_logs").fetchone()
                total = (row[0] if row else 0) or 0
            return {"status": "warn", "detail": f"{total} total rows (SQLite -- no time filter)"}
        except Exception:
            return {"status": "fail", "detail": f"audit_logs missing: {str(e)[:60]}"}


def _soc2_check_route_decorator_coverage():
    """% of /admin and /api/* routes that have a role/jwt decorator.

    Heuristic: walk web_app.py source (the only module that defines these
    routes) and count `@app.route("/admin"... | "/api/"...)` declarations
    where the immediately preceding block contains at least one known auth
    decorator. Runtime __wrapped__ chains are unreliable because the
    project's decorators don't all use functools.wraps.
    """
    try:
        path = os.path.join(os.path.dirname(__file__), "web_app.py")
        with open(path, "rb") as f:
            src = f.read().decode("utf-8", errors="ignore")
        import re
        route_re = re.compile(
            r"@app\.route\(\s*[\"']/(admin|api)([\"'/])",
        )
        auth_markers = (
            "@require_role", "@require_jwt", "@require_any_role",
            "@require_scope", "@require_service_account",
            "@admin_required", "@login_required", "@require_tenant_match",
        )
        total = 0
        decorated = 0
        for m in route_re.finditer(src):
            total += 1
            # Look back up to 6 lines for a known auth marker
            line_start = src.rfind("\n", 0, m.start())
            window = src[max(0, line_start - 600):m.start()]
            if any(mk in window for mk in auth_markers):
                decorated += 1
        if total == 0:
            return {"status": "warn", "detail": "no /admin or /api routes found in source"}
        pct = round(100.0 * decorated / total, 1)
        status = "pass" if pct >= 95 else ("warn" if pct >= 70 else "fail")
        return {
            "status": status,
            "detail": f"{decorated}/{total} /admin + /api route declarations have an auth decorator ({pct}%)",
        }
    except Exception as e:
        return {"status": "warn", "detail": f"route walk failed: {str(e)[:80]}"}


def _soc2_check_security_tests_present():
    """M3.10: tests/security/ folder populated."""
    import glob
    files = glob.glob(os.path.join(os.path.dirname(__file__), "tests", "security", "test_*.py"))
    n = len(files)
    if n >= 8:
        return {"status": "pass", "detail": f"{n} security test files"}
    if n >= 3:
        return {"status": "warn", "detail": f"only {n} security test files (target >= 8)"}
    return {"status": "fail", "detail": "no security tests found"}


def _soc2_check_policy_docs_present():
    """M4.5: docs/policies/*.md formal policies."""
    import glob
    files = glob.glob(os.path.join(os.path.dirname(__file__), "docs", "policies", "*.md"))
    n = len(files)
    if n >= 12:
        return {"status": "pass", "detail": f"{n} policy documents"}
    if n > 0:
        return {"status": "warn", "detail": f"{n}/12 policy documents (M4.5 not yet complete)"}
    return {"status": "fail", "detail": "no policy docs yet (M4.5 pending)"}


def _soc2_check_backup_workflow():
    """M4.1: backup workflow present."""
    p = os.path.join(os.path.dirname(__file__), ".github", "workflows", "backup-postgres.yml")
    if os.path.exists(p):
        return {"status": "pass", "detail": "backup-postgres.yml present"}
    return {"status": "fail", "detail": "no backup workflow (M4.1 pending)"}


def _soc2_check_evidence_collector():
    """M4.6: nightly evidence collector workflow."""
    p = os.path.join(os.path.dirname(__file__), ".github", "workflows", "soc2-evidence.yml")
    if os.path.exists(p):
        return {"status": "pass", "detail": "soc2-evidence.yml present"}
    return {"status": "fail", "detail": "no evidence collector workflow (M4.6 pending)"}


def _soc2_check_security_ci():
    """M3.7: dedicated security CI workflow with semgrep/trivy/etc."""
    p = os.path.join(os.path.dirname(__file__), ".github", "workflows", "security.yml")
    if os.path.exists(p):
        return {"status": "pass", "detail": "security.yml present"}
    return {"status": "fail", "detail": "no security scanner workflow (M3.7 pending)"}


def _soc2_check_error_tracking():
    """M3.5: error_logs table exists; bonus pass if SENTRY_DSN set."""
    try:
        with get_db() as c:
            row = c.execute("SELECT COUNT(*) FROM error_logs").fetchone()
            n = (row[0] if row else 0) or 0
        sentry = bool((os.environ.get("SENTRY_DSN") or "").strip())
        if sentry:
            return {"status": "pass", "detail": f"local capture ({n} rows) + Sentry/GlitchTip connected"}
        if n >= 0:  # table reachable
            return {"status": "warn", "detail": f"local capture only ({n} rows) -- set SENTRY_DSN to push to Sentry/GlitchTip"}
    except Exception as e:
        return {"status": "fail", "detail": f"error_logs unreachable: {str(e)[:80]}"}


_SOC2_CHECKS = [
    ("M1.1  KEYCLOAK_ENABLED flag retired",            _soc2_check_kc_flag_retired),
    ("M1.1  KEYCLOAK_ISSUER configured",               _soc2_check_kc_issuer_configured),
    ("M1.3  Phase B migration applied",                _soc2_check_phase_b_migration),
    ("M1.6  RLS policies cover tenant tables",         _soc2_check_rls_coverage),
    ("M3.1  Tables carry tenant_id column",            _soc2_check_tenant_column_coverage),
    ("M3.1  audit_logs receives writes (24h)",         _soc2_check_audit_log_activity),
    ("M2.6  /admin + /api routes carry auth decorator", _soc2_check_route_decorator_coverage),
    ("M3.10 Security test suite present",              _soc2_check_security_tests_present),
    ("M3.7  Security CI workflow",                     _soc2_check_security_ci),
    ("M3.5  Error tracking present",                   _soc2_check_error_tracking),
    ("M4.1  Backup workflow present",                  _soc2_check_backup_workflow),
    ("M4.5  Policy docs present",                      _soc2_check_policy_docs_present),
    ("M4.6  Evidence collector workflow",              _soc2_check_evidence_collector),
]


def _run_soc2_audit():
    """Run every SOC 2 check, return a structured result.

    Each check is wrapped so one failure can never abort the whole audit.
    Scoring: pass=1.0, warn=0.5, fail=0. The overall score is the mean.
    """
    findings = []
    score_sum = 0.0
    weight = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    for label, fn in _SOC2_CHECKS:
        try:
            result = fn() or {"status": "fail", "detail": "no result"}
        except Exception as e:
            result = {"status": "fail", "detail": f"check raised: {str(e)[:80]}"}
        findings.append({"label": label, **result})
        score_sum += weight.get(result.get("status"), 0.0)
    score = round(100.0 * score_sum / len(_SOC2_CHECKS), 1)
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for f in findings:
        counts[f.get("status", "fail")] = counts.get(f.get("status", "fail"), 0) + 1
    return {
        "score": score,
        "counts": counts,
        "findings": findings,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "version": "1.0 (M1.1 baseline)",
    }


@app.route("/admin/ops/soc2/audit", methods=["POST"])
@admin_required
def admin_ops_soc2_audit():
    """POST endpoint for the opcenter's "Run SOC 2 Audit" button.

    Returns JSON with the readiness score + per-check findings. Designed
    to be cheap (under 1s) so it can be re-run from the UI as code lands.
    """
    csrf_protect()
    report = _run_soc2_audit()
    try:
        log_audit(action="soc2_audit_run",
                  user_id=session.get("user_id"),
                  status="pass",
                  details=f"score={report['score']} counts={report['counts']}")
    except Exception:
        pass
    return jsonify(report)


@app.route("/admin/soc2/report")
@admin_required
def admin_soc2_report():
    """Full HTML readiness report. Printable / shareable with auditors."""
    report = _run_soc2_audit()
    try:
        log_audit(action="soc2_report_view",
                  user_id=session.get("user_id"),
                  status="pass")
    except Exception:
        pass
    return render_template("soc2_report.html", report=report)


