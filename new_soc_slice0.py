# ─────────────────────────────────────────────────────────────────────────────
# AI-SOC — Slice 0: kill switch + read-only foundations  (automation OFF)
# ─────────────────────────────────────────────────────────────────────────────
# Embedded AI Support & Security Operations Centre. Per docs/AI_SOC_IMPLEMENTATION
# _PLAN_2026-07-10.md Slice 0 and ADR-0008 (deterministic-Python exemption from
# §0.1 Google-ADK-only). This slice ships the OFF-SWITCH and the schema BEFORE any
# agent can act — nothing here executes an automated action.
#
# Reuses (never duplicates): admin_settings kill-switch storage
# (_admin_setting / _admin_setting_set), the _inbox_is_pg() backend detector
# (SERIAL vs AUTOINCREMENT correctness), get_db(), admin_required, csrf_protect,
# _admin_notify, log_audit / log_security.
#
# Spliced into web_app.py by patch_soc_slice0.py (byte-level, CRLF-aware) — the
# file is CRLF + mojibake and must never be Edit-ed directly (ADR-0001).

# The seven agent roles (Pass A of the spec). Slice 0 only NAMES them so the
# pause flags and the automation gate are complete; their logic ships in later
# slices. Kept as a tuple so a typo'd pause target is rejected.
SOC_AGENTS = (
    "orchestrator",   # SupportOrchestrator — classify, dedupe, own the lifecycle
    "tier1",          # Tier1Agent          — enabled low-risk runbooks only
    "tier2",          # Tier2Agent          — read-only diagnostics
    "tier3",          # Tier3Agent          — repair package (never deploys)
    "security",       # SecurityAgent       — detect, preserve evidence, contain
    "knowledge",      # KnowledgeAgent      — write article on close
    "notification",   # NotificationAgent   — thin adapter over admin inbox
)

# admin_settings keys. Defaults are OFF — the app boots with the whole SOC dark.
_SOC_ENABLED_KEY      = "soc_enabled"            # "1"|"0" — master feature flag
_SOC_AUTOMATION_KEY   = "soc_automation_enabled" # "1"|"0" — the kill switch
_SOC_AGENT_PAUSE_PFX  = "soc_agent_paused:"      # + <agent> -> "1"|"0"


def _soc_flag(key, default="0"):
    """Read a SOC boolean flag from admin_settings as the string '1' or '0'.
    Inputs:  key (admin_settings key), default (string when unset).
    Output:  '1' or '0' (any truthy stored value normalises to '1')."""
    raw = _admin_setting(key, default)
    return "1" if str(raw).strip().lower() in ("1", "true", "yes", "on") else "0"


def soc_enabled():
    """True when the SOC subsystem is switched on at all. Default False."""
    return _soc_flag(_SOC_ENABLED_KEY) == "1"


def soc_automation_enabled():
    """True when automated remediation is permitted. Default False.
    This is the flag the kill switch flips."""
    return _soc_flag(_SOC_AUTOMATION_KEY) == "1"


def soc_agent_paused(agent):
    """True when a single named agent has been individually paused."""
    if agent not in SOC_AGENTS:
        return False
    return _soc_flag(_SOC_AGENT_PAUSE_PFX + agent) == "1"


def soc_kill_switch_engaged():
    """Convenience inverse of soc_automation_enabled(): True means 'braked' —
    no agent may take any automated action right now."""
    return not soc_automation_enabled()


def soc_automation_allowed(agent=None):
    """THE gate. Every automated agent action in every later slice MUST call this
    and refuse to act when it returns False.
    Inputs:  agent (optional name from SOC_AGENTS to also honour its pause flag).
    Output:  True only when the subsystem is enabled AND automation is enabled AND
             (if an agent is named) that agent is not individually paused.
    Fail-safe: defaults to False because both underlying flags default to '0'."""
    if not soc_enabled():
        return False
    if not soc_automation_enabled():
        return False
    if agent is not None and soc_agent_paused(agent):
        return False
    return True


# ── Schema — the ten tables the plan §5 identifies as genuinely missing ────────
# All idempotent (CREATE TABLE IF NOT EXISTS), backend-branched on id type only.
# tenant_id carried on every table so the RLS migration (migrations/022) can be
# layered on live with the same current_tenant_id() IS NULL parallel-run escape
# the rest of the app uses. Indexes follow CLAUDE.md §11.

_SOC_TABLES = (
    ("support_incidents", """
        {id},
        tenant_id       TEXT,
        status          TEXT NOT NULL DEFAULT 'Detected',
        severity        TEXT NOT NULL DEFAULT 'P4',
        module          TEXT,
        source          TEXT,
        tier            TEXT,
        title           TEXT NOT NULL DEFAULT 'Incident',
        summary         TEXT,
        probable_cause  TEXT,
        fingerprint     TEXT,
        assigned_agent  TEXT,
        created_by      INTEGER,
        human_reviewer  INTEGER,
        audit_reference TEXT,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at     TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_incidents_tenant ON support_incidents(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_support_incidents_tenant_status ON support_incidents(tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_support_incidents_tenant_created ON support_incidents(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_incidents_fp ON support_incidents(fingerprint)",
    )),
    ("support_events", """
        {id},
        tenant_id    TEXT,
        incident_id  INTEGER,
        source       TEXT,
        event_type   TEXT,
        severity     TEXT,
        module       TEXT,
        error_code   TEXT,
        payload      TEXT,
        fingerprint  TEXT,
        created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_events_tenant_created ON support_events(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_events_incident ON support_events(incident_id)",
        "CREATE INDEX IF NOT EXISTS idx_support_events_fp ON support_events(fingerprint)",
    )),
    ("support_actions", """
        {id},
        tenant_id       TEXT,
        incident_id     INTEGER,
        agent           TEXT,
        action_type     TEXT,
        runbook_id      INTEGER,
        mode            TEXT NOT NULL DEFAULT 'proposed',
        status          TEXT NOT NULL DEFAULT 'proposed',
        detail          TEXT,
        audit_reference TEXT,
        created_by      INTEGER,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_actions_tenant_created ON support_actions(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_actions_incident ON support_actions(incident_id)",
    )),
    ("support_approvals", """
        {id},
        tenant_id     TEXT,
        incident_id   INTEGER,
        action_id     INTEGER,
        requested_by  TEXT,
        status        TEXT NOT NULL DEFAULT 'pending',
        decided_by    INTEGER,
        decided_at    TIMESTAMP,
        reason        TEXT,
        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_approvals_tenant_status ON support_approvals(tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_support_approvals_incident ON support_approvals(incident_id)",
    )),
    ("support_agent_runs", """
        {id},
        tenant_id    TEXT,
        agent        TEXT NOT NULL,
        incident_id  INTEGER,
        input_hash   TEXT,
        output_hash  TEXT,
        status       TEXT NOT NULL DEFAULT 'started',
        started_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at  TIMESTAMP,
        error        TEXT
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_agent_runs_tenant_created ON support_agent_runs(tenant_id, started_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_support_agent_runs_agent ON support_agent_runs(agent)",
    )),
    ("support_runbooks", """
        {id},
        tenant_id          TEXT,
        rkey               TEXT,
        name               TEXT NOT NULL DEFAULT 'Runbook',
        category           TEXT,
        description        TEXT,
        allowed_tiers      TEXT,
        risk_level         TEXT NOT NULL DEFAULT 'low',
        requires_approval  INTEGER NOT NULL DEFAULT 1,
        steps              TEXT,
        verification_steps TEXT,
        rollback_steps     TEXT,
        enabled            INTEGER NOT NULL DEFAULT 0,
        created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_support_runbooks_tenant ON support_runbooks(tenant_id)",
        "CREATE INDEX IF NOT EXISTS idx_support_runbooks_enabled ON support_runbooks(enabled)",
    )),
    ("security_incidents", """
        {id},
        tenant_id           TEXT,
        incident_id         INTEGER,
        category            TEXT,
        severity            TEXT NOT NULL DEFAULT 'P3',
        source_ip           TEXT,
        subject_user        INTEGER,
        containment_applied TEXT,
        status              TEXT NOT NULL DEFAULT 'Detected',
        created_by          INTEGER,
        human_reviewer      INTEGER,
        audit_reference     TEXT,
        created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_security_incidents_tenant_status ON security_incidents(tenant_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_security_incidents_tenant_created ON security_incidents(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_security_incidents_ip ON security_incidents(source_ip)",
    )),
    ("security_evidence", """
        {id},
        tenant_id            TEXT,
        security_incident_id INTEGER,
        kind                 TEXT,
        content              TEXT,
        sha256               TEXT,
        created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_security_evidence_incident ON security_evidence(security_incident_id)",
        "CREATE INDEX IF NOT EXISTS idx_security_evidence_tenant ON security_evidence(tenant_id)",
    )),
    ("knowledge_articles", """
        {id},
        tenant_id    TEXT,
        incident_id  INTEGER,
        title        TEXT NOT NULL DEFAULT 'Article',
        symptom      TEXT,
        root_cause   TEXT,
        resolution   TEXT,
        tags         TEXT,
        redacted     INTEGER NOT NULL DEFAULT 1,
        created_by   INTEGER,
        human_reviewer INTEGER,
        created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_knowledge_articles_tenant_created ON knowledge_articles(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_knowledge_articles_incident ON knowledge_articles(incident_id)",
    )),
    ("deployment_changes", """
        {id},
        tenant_id       TEXT,
        incident_id     INTEGER,
        commit_sha      TEXT,
        workflow_run_id TEXT,
        status          TEXT NOT NULL DEFAULT 'proposed',
        notes           TEXT,
        created_by      INTEGER,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    """, (
        "CREATE INDEX IF NOT EXISTS idx_deployment_changes_tenant_created ON deployment_changes(tenant_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_deployment_changes_incident ON deployment_changes(incident_id)",
    )),
)

# Names only, for the read-only status route's row-count summary and the tests.
SOC_TABLE_NAMES = tuple(name for (name, _ddl, _idx) in _SOC_TABLES)


def _ensure_soc_schema(conn):
    """Idempotently create the ten AI-SOC tables + their indexes on the given
    connection. Backend-branched on id type via _inbox_is_pg() (a sqlite:/// URL
    must NOT pick SERIAL, or id lands NULL — see _ensure_admin_notifications_table).
    Never raises: a schema hiccup must not take down a request path.

    DRIFT WARNING (feedback_solar_create_if_not_exists_schema_drift): CREATE TABLE
    IF NOT EXISTS does NOT add a column to a table that already exists. These ten
    tables are new in Slice 0 so first creation is complete on live. But any LATER
    slice that adds a column here MUST also emit an idempotent
    `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (Postgres) / guarded ALTER (SQLite)
    or ship a migration — editing the DDL string alone silently no-ops on existing
    databases."""
    is_pg = _inbox_is_pg()
    id_ddl = "id SERIAL PRIMARY KEY" if is_pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    for name, cols, indexes in _SOC_TABLES:
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS " + name + " ("
                + cols.format(id=id_ddl) + ")")
        except Exception:
            pass
        for idx in indexes:
            try:
                conn.execute(idx)
            except Exception:
                pass


def soc_init():
    """Best-effort one-shot schema create outside a request (cron/hook use)."""
    try:
        with get_db() as c:
            _ensure_soc_schema(c)
        return True
    except Exception:
        return False


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/admin/soc/status", methods=["GET"])
@admin_required
def admin_soc_status():
    """Read-only SOC state: the kill-switch flags + per-table row counts. No
    action, no automation — safe to hit any time. Returns JSON."""
    counts = {}
    try:
        with get_db() as c:
            _ensure_soc_schema(c)
            for name in SOC_TABLE_NAMES:
                try:
                    r = c.execute("SELECT COUNT(*) AS n FROM " + name).fetchone()
                    counts[name] = int((r["n"] if hasattr(r, "keys") else r[0]) or 0)
                except Exception:
                    counts[name] = None
    except Exception:
        app.logger.exception("admin_soc_status failed")
    paused = {a: soc_agent_paused(a) for a in SOC_AGENTS}
    return jsonify({
        "soc_enabled": soc_enabled(),
        "soc_automation_enabled": soc_automation_enabled(),
        "kill_switch_engaged": soc_kill_switch_engaged(),
        "automation_allowed": soc_automation_allowed(),
        "agents": list(SOC_AGENTS),
        "agents_paused": paused,
        "table_row_counts": counts,
    })


@app.route("/admin/soc/kill-switch", methods=["POST"])
@admin_required
def admin_soc_kill_switch():
    """Flip a SOC kill-switch flag. Admin + CSRF + audit gated.
    Form fields (one of):
      flag=soc_enabled|soc_automation_enabled  value=0|1
      pause_agent=<agent>                       value=0|1
    Every change is audited and mirrored to the admin inbox so a pause/resume is
    never silent. Returns JSON (for the ops panel fetch) or redirects for a form."""
    csrf_protect()
    uid = session.get("user_id")
    flag = (request.form.get("flag") or "").strip()
    pause_agent = (request.form.get("pause_agent") or "").strip()
    raw_val = (request.form.get("value") or "").strip().lower()
    value = "1" if raw_val in ("1", "true", "yes", "on") else "0"

    changed = None
    if pause_agent:
        if pause_agent not in SOC_AGENTS:
            return _soc_reply({"error": "unknown_agent", "agent": pause_agent}, 400,
                              "Unknown SOC agent: %s" % pause_agent, "warning")
        _admin_setting_set(_SOC_AGENT_PAUSE_PFX + pause_agent, value)
        changed = "paused" if value == "1" else "resumed"
        detail = "agent %s %s" % (pause_agent, changed)
    elif flag in (_SOC_ENABLED_KEY, _SOC_AUTOMATION_KEY):
        _admin_setting_set(flag, value)
        changed = "on" if value == "1" else "off"
        detail = "%s -> %s" % (flag, changed)
    else:
        return _soc_reply({"error": "bad_flag"}, 400,
                          "Specify flag=soc_enabled|soc_automation_enabled or pause_agent=<agent>.",
                          "warning")

    # Audit trail (structured log) — non-raising.
    try:
        log_security(event_type="soc_kill_switch", user_id=uid,
                     flag=flag or ("pause:" + pause_agent), value=value)
    except Exception:
        pass
    try:
        log_audit(action="soc_kill_switch", user_id=uid, status="success",
                  detail=detail)
    except Exception:
        pass
    # Inbox mirror so operators see a flip even if they weren't the one who did it.
    try:
        # Any change to the automation (kill-switch) flag is noteworthy in BOTH
        # directions -> warning. The fingerprint includes the value so an
        # on->off toggle is NOT deduped against the preceding on-alert: the
        # kill-switch-OFF notice must never be swallowed as a duplicate.
        sev = "warning" if flag == _SOC_AUTOMATION_KEY else "info"
        fp = "soc:" + (flag or ("pause:" + pause_agent)) + ":" + value
        _admin_notify("soc", sev, "AI-SOC setting changed", detail,
                      ref_type="soc_setting", fingerprint=fp)
    except Exception:
        pass

    return _soc_reply({
        "ok": True,
        "detail": detail,
        "soc_enabled": soc_enabled(),
        "soc_automation_enabled": soc_automation_enabled(),
        "automation_allowed": soc_automation_allowed(),
    }, 200, "AI-SOC updated: %s" % detail, "success")


def _soc_reply(payload, code, flash_msg, category):
    """Return JSON for an XHR/ops-panel call, or flash+redirect for a plain form
    POST. Detected via the Accept header / X-Requested-With, matching how the
    ops center panels talk to their endpoints."""
    wants_json = (
        "application/json" in (request.headers.get("Accept") or "")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or (request.form.get("as") or "") == "json"
    )
    if wants_json:
        return jsonify(payload), code
    try:
        flash(flash_msg, category if category in ("success", "info", "warning", "error") else "info")
    except Exception:
        pass
    try:
        return redirect(url_for("admin_operations"))
    except Exception:
        return redirect("/admin/operations")
