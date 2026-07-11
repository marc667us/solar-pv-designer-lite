# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 8: Knowledge base (redacted) + Support Supervisor
# ─────────────────────────────────────────────────────────────────────────────
# Per plan Slice 8 + spec §9/§12. On incident close the KnowledgeAgent writes a
# knowledge_articles row THROUGH A REDACTION PASS (no secrets/tokens/PII — spec
# lines 1887-1895). Articles are searchable from the admin area and reusable by
# the helpline. The Support Supervisor produces SLA / dedupe / digest reports.
#
# Spliced by patch_soc_slice8.py (byte-level, CRLF-aware).

import re as _soc8_re

# Redaction patterns — mask anything that looks like a credential or PII BEFORE
# it is persisted to a knowledge article. Order matters (specific before broad).
_SOC_REDACTIONS = (
    (_soc8_re.compile(r'-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z]*PRIVATE KEY-----'), '[REDACTED_PEM]'),
    (_soc8_re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._\-]+'), '[REDACTED_TOKEN]'),
    (_soc8_re.compile(r'\beyJ[A-Za-z0-9._\-]{10,}'), '[REDACTED_JWT]'),
    (_soc8_re.compile(r'\b(?:xkeysib|xsmtpsib)-[A-Za-z0-9]{8,}'), '[REDACTED_KEY]'),
    (_soc8_re.compile(r'\bAKIA[0-9A-Z]{12,}\b'), '[REDACTED_KEY]'),
    (_soc8_re.compile(r'\bgh[pousr]_[A-Za-z0-9]{16,}'), '[REDACTED_KEY]'),
    (_soc8_re.compile(r'\bAIza[0-9A-Za-z_\-]{20,}'), '[REDACTED_KEY]'),        # Google
    (_soc8_re.compile(r'\bxox[abprs]-[0-9A-Za-z\-]{8,}'), '[REDACTED_KEY]'),   # Slack
    (_soc8_re.compile(r'\b(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{8,}'), '[REDACTED_KEY]'),  # Stripe
    (_soc8_re.compile(r'\b(?:sk|rk|pk|re)[-_][A-Za-z0-9]{10,}'), '[REDACTED_KEY]'),
    (_soc8_re.compile(r'(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b\s*[=:]\s*\S+'),
     r'\1=[REDACTED]'),
    (_soc8_re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[REDACTED_EMAIL]'),
    (_soc8_re.compile(r'\b[A-Fa-f0-9]{32,}\b'), '[REDACTED_HASH]'),
)


def _soc_redact(text):
    """Mask credentials + PII in free text before it is stored/shown. Never
    raises; returns the redacted string (or '' for falsy input)."""
    if not text:
        return ""
    try:
        s = str(text)
        for pat, repl in _SOC_REDACTIONS:
            s = pat.sub(repl, s)
        return s
    except Exception:
        return ""


def soc_knowledge_write(incident_id):
    """Write (or update) a redacted knowledge article for an incident. Intended
    to run on close. Gated on soc_enabled. Returns the article id or None.
    NEVER raises. Every stored field passes through _soc_redact()."""
    try:
        if not soc_enabled():
            return None
        diag = soc_tier2_diagnose(incident_id) or {}          # Slice 6 (read-only)
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            row = c.execute(
                "SELECT id, module, severity, title, summary, probable_cause, tenant_id "
                "FROM support_incidents WHERE id=?", (incident_id,)).fetchone()
            if row is None:
                return None
            keys = ("id", "module", "severity", "title", "summary", "probable_cause", "tenant_id")
            inc = {k: (row[k] if hasattr(row, "keys") else row[i]) for i, k in enumerate(keys)}

            title = _soc_redact("%s — %s" % (inc.get("severity"), inc.get("title") or inc.get("module") or "incident"))
            symptom = _soc_redact(inc.get("summary"))
            root_cause = _soc_redact(inc.get("probable_cause") or diag.get("root_cause"))
            resolution = _soc_redact("%s | rollback: %s" % (
                diag.get("proposed_fix") or "see incident", diag.get("rollback_plan") or "-"))
            tags = _soc_redact("%s,%s,%s" % (inc.get("severity"), inc.get("module") or "", diag.get("risk_level") or ""))

            # Upsert-ish: one article per incident.
            existing = c.execute(
                "SELECT id FROM knowledge_articles WHERE incident_id=? LIMIT 1",
                (incident_id,)).fetchone()
            if existing:
                aid = existing[0] if not hasattr(existing, "keys") else existing["id"]
                c.execute(
                    "UPDATE knowledge_articles SET title=?, symptom=?, root_cause=?, "
                    "resolution=?, tags=?, redacted=1, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (title[:200], symptom, root_cause, resolution, tags[:200], aid))
                return aid
            cur = c.execute(
                "INSERT INTO knowledge_articles "
                "(tenant_id, incident_id, title, symptom, root_cause, resolution, tags, redacted) "
                "VALUES (?,?,?,?,?,?,?,1)",
                (inc.get("tenant_id"), incident_id, title[:200], symptom,
                 root_cause, resolution, tags[:200]))
            try:
                return int(getattr(cur, "lastrowid", 0) or 0)
            except Exception:
                return None
    except Exception:
        return None


def soc_knowledge_search(query, limit=50):
    """Search knowledge articles (reusable by the helpline). Read-only. Returns a
    list of dicts. NEVER raises."""
    keys = ("id", "incident_id", "title", "symptom", "root_cause", "resolution",
            "tags", "created_at")
    try:
        q = "%" + (str(query or "").strip().lower()) + "%"
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)
            rows = c.execute(
                "SELECT id, incident_id, title, symptom, root_cause, resolution, tags, created_at "
                "FROM knowledge_articles WHERE LOWER(title) LIKE ? OR LOWER(root_cause) LIKE ? "
                "OR LOWER(resolution) LIKE ? OR LOWER(tags) LIKE ? "
                "ORDER BY id DESC LIMIT ?", (q, q, q, q, int(limit))).fetchall()
            return [{k: (r[k] if hasattr(r, "keys") else r[i]) for i, k in enumerate(keys)} for r in rows]
    except Exception:
        return []


def soc_supervisor_report():
    """Support Supervisor: SLA / dedupe / digest over the incident set. Read-only
    summary. NEVER raises."""
    try:
        with get_db() as c:
            if _inbox_is_pg():
                try:
                    c.execute("SELECT set_config('app.current_role', 'admin', true)")
                except Exception:
                    pass
            _ensure_soc_schema(c)

            def _grp(col):
                out = {}
                try:
                    for r in c.execute("SELECT %s, COUNT(*) FROM support_incidents GROUP BY %s" % (col, col)).fetchall():
                        out[(r[0] if not hasattr(r, "keys") else r[0])] = int(r[1])
                except Exception:
                    pass
                return out

            open_statuses = _SOC_OPEN_STATUSES   # Slice 2
            ph = ",".join("?" for _ in open_statuses)
            open_n = c.execute(
                "SELECT COUNT(*) FROM support_incidents WHERE status IN (" + ph + ")",
                open_statuses).fetchone()
            open_count = int((open_n[0] if open_n else 0) or 0)

            # dedupe signal: fingerprints with more than one incident
            dup = c.execute(
                "SELECT COUNT(*) FROM (SELECT fingerprint FROM support_incidents "
                "WHERE fingerprint IS NOT NULL GROUP BY fingerprint HAVING COUNT(*) > 1) t"
            ).fetchone()
            dup_fps = int((dup[0] if dup else 0) or 0)

            return {
                "by_severity": _grp("severity"),
                "by_status": _grp("status"),
                "by_tier": _grp("tier"),
                "open_incidents": open_count,
                "duplicate_fingerprints": dup_fps,
                "articles": int((c.execute("SELECT COUNT(*) FROM knowledge_articles").fetchone() or [0])[0] or 0),
                "agent_runs": int((c.execute("SELECT COUNT(*) FROM support_agent_runs").fetchone() or [0])[0] or 0),
            }
    except Exception:
        return {}


# ── Admin routes ──────────────────────────────────────────────────────────────

@app.route("/admin/soc/incidents/<int:iid>/knowledge", methods=["POST"])
@admin_required
def admin_soc_generate_article(iid):
    """Generate/refresh the redacted knowledge article for an incident."""
    csrf_protect()
    aid = soc_knowledge_write(iid)
    if not aid:
        return jsonify({"error": "not_written (incident missing or SOC disabled)"}), 400
    try:
        log_audit(action="soc_knowledge_write", user_id=session.get("user_id"),
                  status="success", detail="incident %s -> article %s" % (iid, aid))
    except Exception:
        pass
    return jsonify({"ok": True, "article_id": aid})


@app.route("/admin/soc/knowledge", methods=["GET"])
@admin_required
def admin_soc_knowledge_search():
    """Search the knowledge base (JSON)."""
    q = request.args.get("q") or ""
    return jsonify({"query": q, "results": soc_knowledge_search(q)})


@app.route("/admin/soc/supervisor", methods=["GET"])
@admin_required
def admin_soc_supervisor():
    """Support Supervisor digest (JSON)."""
    return jsonify(soc_supervisor_report())
