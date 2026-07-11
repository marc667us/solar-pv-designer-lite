# ─────────────────────────────────────────────────────────────────────────────
# Tutorial & Demo Framework — Manager (AC11) + Analytics (AC12)
# ─────────────────────────────────────────────────────────────────────────────
# The browser-first Tutorial & Demo Engine (static/tutorial/tutorial-engine.js +
# 60 scenario files + the base.html loader) already satisfies acceptance
# criteria 1-10 and 13-15 of pvsolar1/"video tutorial.txt". This slice closes
# the two remaining criteria — WITHOUT touching the working engine's core:
#
#   AC11  Admin can enable/disable tutorials.
#   AC12  Tutorial analytics are recorded (started/completed/skipped/step_failed
#         /average completion/most-viewed page/most-confusing step).
#
# It is deterministic Python bolted onto the existing Flask app (NOT an ADK
# agent — this is admin CRUD + event logging, so §0.1 ADK-only does not apply).
# Additive only: new routes + one new table + three admin_settings keys. The
# engine consults GET /api/tutorial/config to respect the admin's on/off choices
# and POSTs telemetry to /api/tutorial/event.
#
# Spliced by patch_tutorial_admin.py (byte-level, CRLF-aware, idempotent).

import os as _tut_os
import json as _tut_json
import re as _tut_re

# admin_settings keys (persisted via the existing _admin_setting helpers).
_TUT_MASTER_KEY = "tutorial_master_enabled"        # "1"/"0" — global on/off
_TUT_ANALYTICS_KEY = "tutorial_analytics_enabled"  # "1"/"0" — record events?
_TUT_DISABLED_PFX = "tutorial_disabled:"           # per-slug key: value "1"=disabled

# Telemetry event types we accept from the engine. Anything else is dropped so a
# forged/garbage POST cannot pollute the analytics table.
_TUT_EVENT_TYPES = ("started", "completed", "skipped", "step_shown", "step_failed")

# A scenario slug is a Flask endpoint name: lowercase, digits, underscore only.
_TUT_SLUG_RE = _tut_re.compile(r"^[a-z0-9_]{1,120}$")

# tutorial_events — one row per telemetry beacon. Low-sensitivity usage data;
# admin-read is gated at the app layer (@admin_required). tenant_id is captured
# when known (nullable, parallel-run escape); DB RLS is deferred to the gated
# migration 023_tutorial_rls.sql rather than auto-applied, so anonymous
# public-demo beacons are never silently rejected.
_TUT_EVENTS_TABLE = (
    "tutorial_events",
    "{id}, tenant_id INTEGER, user_id INTEGER, page VARCHAR(120), "
    "event_type VARCHAR(32), step_index INTEGER, step_title VARCHAR(200), "
    "mode VARCHAR(16), total_steps INTEGER, duration_ms INTEGER, "
    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    (
        "CREATE INDEX IF NOT EXISTS idx_tutorial_events_page ON tutorial_events(page)",
        "CREATE INDEX IF NOT EXISTS idx_tutorial_events_type ON tutorial_events(event_type)",
        "CREATE INDEX IF NOT EXISTS idx_tutorial_events_created ON tutorial_events(created_at)",
    ),
)


def _ensure_tutorial_schema(conn):
    """Create tutorial_events + its indexes on ``conn``. Backend-branched on the
    id type via _inbox_is_pg() (a sqlite:/// URL must NOT pick SERIAL). Never
    raises: a schema hiccup must not take down the telemetry path.

    DRIFT WARNING (feedback_solar_create_if_not_exists_schema_drift): CREATE
    TABLE IF NOT EXISTS does NOT add a column to a table that already exists.
    tutorial_events is new in this slice so first creation is complete on live.
    Any later slice that adds a column here MUST emit an idempotent
    ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` (Postgres) / guarded ALTER
    (SQLite) — editing this DDL string alone silently no-ops on existing DBs."""
    try:
        is_pg = _inbox_is_pg()
    except Exception:
        is_pg = False
    id_ddl = "id SERIAL PRIMARY KEY" if is_pg else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    name, cols, indexes = _TUT_EVENTS_TABLE
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS " + name + " (" + cols.format(id=id_ddl) + ")")
    except Exception:
        pass
    for idx in indexes:
        try:
            conn.execute(idx)
        except Exception:
            pass


# ── settings helpers ─────────────────────────────────────────────────────────

def tutorial_master_enabled():
    """Global tutorial on/off. Default ON (the engine ships enabled). Never
    raises."""
    try:
        return str(_admin_setting(_TUT_MASTER_KEY, "1")) != "0"
    except Exception:
        return True


def tutorial_analytics_enabled():
    """Whether telemetry is recorded. Default ON. Never raises."""
    try:
        return str(_admin_setting(_TUT_ANALYTICS_KEY, "1")) != "0"
    except Exception:
        return True


def tutorial_disabled_slugs():
    """The set of scenario slugs an admin has disabled. Stored one key per slug
    (``tutorial_disabled:<slug>`` = "1"), mirroring the SOC's per-agent
    ``soc_agent_paused:<agent>`` keys — so each toggle is a single-key upsert and
    concurrent toggles of different slugs cannot clobber one another (the shared
    JSON-blob read-modify-write would lose an update). Never raises; a query
    error degrades to 'nothing disabled'. The LIKE pattern is a bound param, so
    its literal '%' is data, never a psycopg2 format spec."""
    out = set()
    try:
        with get_db() as c:
            rows = c.execute(
                "SELECT key, value FROM admin_settings WHERE key LIKE ?",
                (_TUT_DISABLED_PFX + "%",)).fetchall()
        for r in (rows or []):
            k = r["key"] if hasattr(r, "keys") else r[0]
            v = r["value"] if hasattr(r, "keys") else r[1]
            if str(v) != "1":
                continue
            slug = k[len(_TUT_DISABLED_PFX):]
            if _TUT_SLUG_RE.match(slug):
                out.add(slug)
    except Exception:
        pass
    return out


def tutorial_is_enabled(slug):
    """A page's tutorial plays only when the master switch is on AND the slug is
    not in the disabled set."""
    if not tutorial_master_enabled():
        return False
    return slug not in tutorial_disabled_slugs()


def _tutorial_scenario_dir():
    """Absolute path to the scenario directory, from Flask's static folder (no
    hardcoded per-machine path — reusability §0.3)."""
    base = app.static_folder or _tut_os.path.join(_tut_os.path.dirname(__file__), "static")
    return _tut_os.path.join(base, "tutorial", "scenarios")


def tutorial_list_scenarios():
    """Enumerate every scenario file on disk with its title/step-count/draft flag
    and current enabled state. Read-only; never raises (returns [] on error)."""
    out = []
    d = _tutorial_scenario_dir()
    try:
        names = sorted(f for f in _tut_os.listdir(d) if f.endswith(".json"))
    except Exception:
        return out
    disabled = tutorial_disabled_slugs()
    for fn in names:
        slug = fn[:-5]
        if not _TUT_SLUG_RE.match(slug):
            continue
        title, steps, draft = slug, 0, False
        try:
            with open(_tut_os.path.join(d, fn), "r", encoding="utf-8") as fh:
                j = _tut_json.load(fh)
            title = j.get("title") or slug
            steps = len(j.get("steps") or [])
            draft = bool(j.get("draft"))
        except Exception:
            pass
        out.append({
            "slug": slug, "title": title, "steps": steps, "draft": draft,
            "enabled": (slug not in disabled),
        })
    return out


def tutorial_set_disabled(slug, disabled):
    """Enable/disable one tutorial via a single-key upsert (``tutorial_disabled:
    <slug>``). No shared-blob read-modify-write, so concurrent toggles of
    different slugs cannot clobber each other. Returns the new enabled state
    (True=enabled) or None on bad input."""
    if not (isinstance(slug, str) and _TUT_SLUG_RE.match(slug)):
        return None
    _admin_setting_set(_TUT_DISABLED_PFX + slug, "1" if disabled else "0")
    return (not disabled)


# ── analytics ────────────────────────────────────────────────────────────────

def tutorial_record_event(page, event_type, *, step_index=None, step_title=None,
                          mode=None, total_steps=None, duration_ms=None,
                          user_id=None, tenant_id=None):
    """Insert one telemetry row. Silently no-ops when analytics is off or the
    event_type/page is not in the accepted allowlist/shape. NEVER raises — a
    telemetry failure must never surface to the user or break a page."""
    try:
        if not tutorial_analytics_enabled():
            return False
        if event_type not in _TUT_EVENT_TYPES:
            return False
        page = str(page or "")[:120]
        if not _TUT_SLUG_RE.match(page):
            return False

        def _int(v, lo=None, hi=None):
            try:
                n = int(v)
            except Exception:
                return None
            if lo is not None and n < lo:
                return None
            if hi is not None and n > hi:
                return None
            return n

        si = _int(step_index, 0, 100000)
        ts = _int(total_steps, 0, 100000)
        dm = _int(duration_ms, 0, 86400000)  # cap at 24h of ms — reject garbage
        st = (str(step_title)[:200] if step_title else None)
        md = (str(mode)[:16] if mode else None)

        with get_db() as c:
            _ensure_tutorial_schema(c)
            c.execute(
                "INSERT INTO tutorial_events "
                "(tenant_id, user_id, page, event_type, step_index, step_title, "
                "mode, total_steps, duration_ms) VALUES (?,?,?,?,?,?,?,?,?)",
                (tenant_id, user_id, page, event_type, si, st, md, ts, dm))
        return True
    except Exception:
        return False


def tutorial_analytics_summary(limit_pages=25):
    """Aggregate the telemetry into the spec's report shape (spec ANALYTICS
    section): started/completed/skipped totals, average completion %, most-viewed
    pages, and the most-confusing step (highest step_failed count). Read-only;
    never raises (returns a well-formed empty summary on error)."""
    empty = {"totals": {}, "avg_completion_pct": 0, "by_page": [],
             "most_confusing": [], "events": 0}
    try:
        with get_db() as c:
            _ensure_tutorial_schema(c)

            def _grp(sql, params=()):
                out = {}
                try:
                    for r in c.execute(sql, params).fetchall():
                        k = r[0] if not hasattr(r, "keys") else r[0]
                        out[k] = int(r[1])
                except Exception:
                    pass
                return out

            totals = _grp("SELECT event_type, COUNT(*) FROM tutorial_events GROUP BY event_type")

            # average completion %: mean of step/total over 'completed'+'skipped'
            # end events that carry a total_steps.
            avg_pct = 0
            try:
                rows = c.execute(
                    "SELECT step_index, total_steps FROM tutorial_events "
                    "WHERE event_type IN ('completed','skipped') "
                    "AND total_steps IS NOT NULL AND total_steps > 0").fetchall()
                pcts = []
                for r in rows:
                    si = r[0] if not hasattr(r, "keys") else r[0]
                    tot = r[1] if not hasattr(r, "keys") else r[1]
                    if tot:
                        reached = (int(si) + 1) if si is not None else int(tot)
                        pcts.append(max(0, min(100, round(100.0 * reached / int(tot)))))
                if pcts:
                    avg_pct = round(sum(pcts) / len(pcts))
            except Exception:
                pass

            # per-page: started vs completed (drives most-viewed + completion).
            by_page = []
            try:
                rows = c.execute(
                    "SELECT page, "
                    "SUM(CASE WHEN event_type='started' THEN 1 ELSE 0 END), "
                    "SUM(CASE WHEN event_type='completed' THEN 1 ELSE 0 END), "
                    "SUM(CASE WHEN event_type='skipped' THEN 1 ELSE 0 END) "
                    "FROM tutorial_events GROUP BY page "
                    "ORDER BY 2 DESC").fetchall()
                for r in rows[:limit_pages]:
                    v = list(r) if not hasattr(r, "keys") else [r[i] for i in range(4)]
                    by_page.append({
                        "page": v[0], "started": int(v[1] or 0),
                        "completed": int(v[2] or 0), "skipped": int(v[3] or 0),
                    })
            except Exception:
                pass

            # most-confusing step: highest step_failed count per (page, step).
            most_confusing = []
            try:
                rows = c.execute(
                    "SELECT page, step_index, step_title, COUNT(*) FROM tutorial_events "
                    "WHERE event_type='step_failed' GROUP BY page, step_index, step_title "
                    "ORDER BY 4 DESC").fetchall()
                for r in rows[:15]:
                    v = list(r) if not hasattr(r, "keys") else [r[i] for i in range(4)]
                    most_confusing.append({
                        "page": v[0], "step_index": v[1],
                        "step_title": v[2], "fails": int(v[3] or 0),
                    })
            except Exception:
                pass

            return {
                "totals": totals,
                "avg_completion_pct": avg_pct,
                "by_page": by_page,
                "most_confusing": most_confusing,
                "events": int(sum(totals.values())) if totals else 0,
            }
    except Exception:
        return empty


# ── public engine endpoints ──────────────────────────────────────────────────

@app.route("/api/tutorial/config", methods=["GET"])
def api_tutorial_config():
    """The engine fetches this on boot to respect the admin's choices. Readable
    by anyone (including anonymous visitors on public pages) — it exposes only
    which tutorials exist and whether they are on, never any tenant data."""
    return jsonify({
        "enabled": tutorial_master_enabled(),
        "analytics": tutorial_analytics_enabled(),
        "disabled": sorted(tutorial_disabled_slugs()),
    })


@app.route("/api/tutorial/event", methods=["POST"])
def api_tutorial_event():
    """Telemetry sink for the engine (AC12). Accepts a small JSON beacon. No CSRF
    token is required (it is a non-mutating usage beacon, not a state change on
    business data) but every field is strictly validated and clamped, and the
    event_type is allowlisted, so a forged POST can at worst add a bounded junk
    row that the allowlist already filters. Captures user_id/tenant_id when the
    caller is authenticated; anonymous public-demo beacons are accepted too."""
    if not tutorial_analytics_enabled():
        return jsonify({"ok": False, "reason": "disabled"}), 202
    try:
        body = request.get_json(silent=True)
    except Exception:
        body = None
    # A JSON array/string/number parses fine but has no .get() — normalise to a
    # dict so a non-object body can never raise AttributeError on the beacon path.
    if not isinstance(body, dict):
        body = {}
    uid = None
    tid = None
    try:
        uid = session.get("user_id")
    except Exception:
        pass
    try:
        tid = globals().get("current_tenant_id") and current_tenant_id()
    except Exception:
        tid = None
    ok = tutorial_record_event(
        body.get("page"), body.get("event_type"),
        step_index=body.get("step_index"), step_title=body.get("step_title"),
        mode=body.get("mode"), total_steps=body.get("total_steps"),
        duration_ms=body.get("duration_ms"), user_id=uid, tenant_id=tid)
    # Always 202 so the beacon never shows an error in the user's console.
    return jsonify({"ok": bool(ok)}), 202


# ── admin manager (AC11) ─────────────────────────────────────────────────────

@app.route("/admin/tutorials", methods=["GET"])
@admin_required
def admin_tutorials():
    """Tutorial Manager: list every scenario with an enable/disable toggle, plus
    the master + analytics switches. Server-rendered inside the admin area (no
    new portal). RBAC: @admin_required — normal users can only play tutorials."""
    from flask import render_template_string
    scenarios = tutorial_list_scenarios()
    tpl = """{% extends "base.html" %}{% block content %}
    <div class="container-fluid py-3">
      <h3 class="mb-3"><i class="bi bi-mortarboard me-2"></i>Tutorial Manager</h3>
      <p class="text-muted small">Enable or disable the guided tour / auto demo on any page.
        Disabled tutorials stop offering the launcher to users.
        <a href="{{ url_for('admin_tutorials_analytics') }}">View analytics &rarr;</a></p>

      <form method="post" action="{{ url_for('admin_tutorials_master') }}" class="mb-3 d-flex gap-3 align-items-center flex-wrap">
        <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
        <div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" name="master" id="mSw" {{ 'checked' if master }}>
          <label class="form-check-label" for="mSw">Tutorials globally enabled</label>
        </div>
        <div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" name="analytics" id="aSw" {{ 'checked' if analytics }}>
          <label class="form-check-label" for="aSw">Record analytics</label>
        </div>
        <button class="btn btn-sm btn-primary" type="submit">Save switches</button>
      </form>

      <table class="table table-sm table-striped align-middle">
        <thead><tr><th>Page (endpoint)</th><th>Title</th><th>Steps</th><th>State</th><th></th></tr></thead>
        <tbody>
        {% for s in scenarios %}
          <tr>
            <td><code>{{ s.slug }}</code>{% if s.draft %} <span class="badge bg-warning text-dark">draft</span>{% endif %}</td>
            <td>{{ s.title }}</td>
            <td>{{ s.steps }}</td>
            <td>{% if s.enabled %}<span class="badge bg-success">Enabled</span>{% else %}<span class="badge bg-secondary">Disabled</span>{% endif %}</td>
            <td>
              <form method="post" action="{{ url_for('admin_tutorials_toggle', slug=s.slug) }}" class="d-inline">
                <input type="hidden" name="_csrf" value="{{ csrf_token() }}">
                <input type="hidden" name="disable" value="{{ '0' if s.enabled else '1' }}">
                <button class="btn btn-sm {{ 'btn-outline-secondary' if s.enabled else 'btn-outline-success' }}" type="submit">
                  {{ 'Disable' if s.enabled else 'Enable' }}
                </button>
              </form>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% if not scenarios %}<div class="alert alert-info">No scenario files found.</div>{% endif %}
    </div>{% endblock %}"""
    return render_template_string(
        tpl, scenarios=scenarios,
        master=tutorial_master_enabled(), analytics=tutorial_analytics_enabled())


@app.route("/admin/tutorials/<slug>/toggle", methods=["POST"])
@admin_required
def admin_tutorials_toggle(slug):
    """Enable/disable a single tutorial. CSRF-protected + audit-logged."""
    csrf_protect()
    disable = (request.form.get("disable") or "0") == "1"
    state = tutorial_set_disabled(slug, disable)
    if state is None:
        return jsonify({"error": "invalid slug"}), 400
    try:
        log_audit(action="tutorial_toggle", user_id=session.get("user_id"),
                  status="success",
                  detail="%s -> %s" % (slug, "enabled" if state else "disabled"))
    except Exception:
        pass
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True, "slug": slug, "enabled": state})
    return redirect(url_for("admin_tutorials"))


@app.route("/admin/tutorials/master", methods=["POST"])
@admin_required
def admin_tutorials_master():
    """Flip the global master + analytics switches. CSRF-protected + audited."""
    csrf_protect()
    master = "1" if request.form.get("master") else "0"
    analytics = "1" if request.form.get("analytics") else "0"
    _admin_setting_set(_TUT_MASTER_KEY, master)
    _admin_setting_set(_TUT_ANALYTICS_KEY, analytics)
    try:
        log_audit(action="tutorial_master", user_id=session.get("user_id"),
                  status="success",
                  detail="master=%s analytics=%s" % (master, analytics))
    except Exception:
        pass
    return redirect(url_for("admin_tutorials"))


@app.route("/admin/tutorials/analytics", methods=["GET"])
@admin_required
def admin_tutorials_analytics():
    """Tutorial analytics dashboard (AC12). ?format=json returns the raw summary;
    otherwise a server-rendered table inside the admin area."""
    summary = tutorial_analytics_summary()
    if (request.args.get("format") or "").lower() == "json":
        return jsonify(summary)
    from flask import render_template_string
    tpl = """{% extends "base.html" %}{% block content %}
    <div class="container-fluid py-3">
      <h3 class="mb-3"><i class="bi bi-graph-up me-2"></i>Tutorial Analytics</h3>
      <p class="text-muted small"><a href="{{ url_for('admin_tutorials') }}">&larr; Tutorial Manager</a>
         &nbsp;·&nbsp; {{ s.events }} events recorded &nbsp;·&nbsp; avg completion {{ s.avg_completion_pct }}%</p>

      <div class="row g-2 mb-3">
        {% for k, v in s.totals.items() %}
        <div class="col-auto"><div class="card"><div class="card-body py-2 px-3">
          <div class="small text-muted text-uppercase">{{ k }}</div>
          <div class="fs-5 fw-bold">{{ v }}</div>
        </div></div></div>
        {% endfor %}
      </div>

      <h6 class="mt-3">Most-viewed pages</h6>
      <table class="table table-sm table-striped align-middle">
        <thead><tr><th>Page</th><th>Started</th><th>Completed</th><th>Skipped</th><th>Completion</th></tr></thead>
        <tbody>
        {% for p in s.by_page %}
          <tr><td><code>{{ p.page }}</code></td><td>{{ p.started }}</td>
              <td>{{ p.completed }}</td><td>{{ p.skipped }}</td>
              <td>{% if p.started %}{{ (100 * p.completed / p.started) | round | int }}%{% else %}-{% endif %}</td></tr>
        {% endfor %}
        </tbody>
      </table>
      {% if not s.by_page %}<div class="alert alert-info">No tutorial usage recorded yet.</div>{% endif %}

      {% if s.most_confusing %}
      <h6 class="mt-3">Most-confusing steps (target not found)</h6>
      <table class="table table-sm align-middle">
        <thead><tr><th>Page</th><th>Step</th><th>Title</th><th>Fails</th></tr></thead>
        <tbody>
        {% for m in s.most_confusing %}
          <tr><td><code>{{ m.page }}</code></td><td>{{ m.step_index }}</td>
              <td>{{ m.step_title or '-' }}</td><td>{{ m.fails }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
      {% endif %}
    </div>{% endblock %}"""
    return render_template_string(tpl, s=summary)
