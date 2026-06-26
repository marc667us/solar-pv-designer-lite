# ─── Routes — Zero-Cost AI Growth Layer (viralsolar 1.txt) ─────────────────
# Eight modules in one file: Social Card Generator, Proposal Beautifier,
# Share Link Generator, Referral QR, Lightweight Lead Tracker, CRM Connector,
# Sales Pipeline Connector, Growth Dashboard. All browser-first rendering;
# no paid APIs; reuses users.referral_code, the existing leads table, and the
# existing /r/<code> cookie.

import base64 as _gl_b64
import json as _gl_json
import secrets as _gl_secrets
import time as _gl_time

_GROWTH_SCHEMA_DONE = {"done": False}

_GROWTH_ALLOWED_ASSET_TYPES = (
    "solar_savings_card",
    "energy_score_card",
    "boq_summary_card",
    "proposal_preview",
    "installer_achievement_card",
    "supplier_product_card",
    "roof_before_after_card",
)

_GROWTH_LEAD_SOURCE_LABELS = {
    "solar_savings_card":          "ROI Social Card",
    "energy_score_card":           "Energy Score Card",
    "boq_summary_card":            "BOQ Share",
    "proposal_preview":            "Proposal Share",
    "installer_achievement_card":  "Installer Achievement Share",
    "supplier_product_card":       "Supplier Profile Share",
    "roof_before_after_card":      "Solar Estimate Share",
}

_GROWTH_PIPELINE_STAGES = (
    "viral_visitor", "lead_captured", "lead_qualified", "ai_followup",
    "demo", "trial", "proposal", "negotiation", "subscribed",
    "customer", "advocate",
)


def _ensure_growth_schema():
    """Idempotent schema init for SQLite (dev) AND Postgres (Render).
    Also lazy-extends the existing leads + referrals tables with growth columns."""
    if _GROWTH_SCHEMA_DONE["done"]:
        return
    is_pg = bool(os.environ.get("DATABASE_URL"))
    with get_db() as c:
        if is_pg:
            stmts = [
                """CREATE TABLE IF NOT EXISTS growth_share_assets (
                    id SERIAL PRIMARY KEY,
                    share_slug VARCHAR(20) UNIQUE NOT NULL,
                    tenant_id INTEGER,
                    owner_user_id INTEGER,
                    project_id INTEGER,
                    asset_type VARCHAR(60) NOT NULL,
                    title VARCHAR(240) NOT NULL,
                    summary VARCHAR(600) DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    referral_code VARCHAR(20) DEFAULT '',
                    campaign_id VARCHAR(60) DEFAULT '',
                    visibility VARCHAR(16) DEFAULT 'public',
                    expires_at VARCHAR(20),
                    revoked_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_owner   ON growth_share_assets(owner_user_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_project ON growth_share_assets(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_type    ON growth_share_assets(asset_type)",
                """CREATE TABLE IF NOT EXISTS growth_share_events (
                    id SERIAL PRIMARY KEY,
                    share_asset_id INTEGER NOT NULL,
                    event_type VARCHAR(30) NOT NULL,
                    channel VARCHAR(30) DEFAULT '',
                    referral_code VARCHAR(20) DEFAULT '',
                    campaign_id VARCHAR(60) DEFAULT '',
                    visitor_id VARCHAR(60) DEFAULT '',
                    device_type VARCHAR(20) DEFAULT '',
                    browser VARCHAR(40) DEFAULT '',
                    src VARCHAR(60) DEFAULT '',
                    cta_clicked VARCHAR(60) DEFAULT '',
                    converted_to_lead INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_event_asset ON growth_share_events(share_asset_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_event_type  ON growth_share_events(event_type)",
                """CREATE TABLE IF NOT EXISTS growth_referrals (
                    id SERIAL PRIMARY KEY,
                    referral_code VARCHAR(20) NOT NULL,
                    referrer_user_id INTEGER,
                    referrer_company_id INTEGER,
                    referred_lead_id INTEGER,
                    referred_user_id INTEGER,
                    share_asset_id INTEGER,
                    reward_status VARCHAR(20) DEFAULT 'pending',
                    reward_type VARCHAR(30) DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_ref_code ON growth_referrals(referral_code)",
                """CREATE TABLE IF NOT EXISTS growth_activities (
                    id SERIAL PRIMARY KEY,
                    lead_id INTEGER NOT NULL,
                    activity_type VARCHAR(40) NOT NULL,
                    payload_json TEXT DEFAULT '{}',
                    created_by_user_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_act_lead ON growth_activities(lead_id)",
                # Extend the existing leads table with the CRM-connector columns
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS lead_source_type VARCHAR(80) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS share_slug VARCHAR(20) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS asset_type VARCHAR(60) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS campaign_id VARCHAR(60) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS referrer_user_id INTEGER",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS preferred_contact VARCHAR(20) DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_stage VARCHAR(40) DEFAULT 'lead_captured'",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS sales_owner_user_id INTEGER",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_handoff_at TIMESTAMP",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS growth_source VARCHAR(80) DEFAULT ''",
            ]
            for s in stmts:
                try:
                    c.execute(s)
                except Exception:
                    pass
        else:
            # SQLite path — CREATE TABLEs first
            for s in [
                """CREATE TABLE IF NOT EXISTS growth_share_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_slug TEXT UNIQUE NOT NULL,
                    tenant_id INTEGER,
                    owner_user_id INTEGER,
                    project_id INTEGER,
                    asset_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    referral_code TEXT DEFAULT '',
                    campaign_id TEXT DEFAULT '',
                    visibility TEXT DEFAULT 'public',
                    expires_at TEXT,
                    revoked_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_owner   ON growth_share_assets(owner_user_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_project ON growth_share_assets(project_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_share_type    ON growth_share_assets(asset_type)",
                """CREATE TABLE IF NOT EXISTS growth_share_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_asset_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    channel TEXT DEFAULT '',
                    referral_code TEXT DEFAULT '',
                    campaign_id TEXT DEFAULT '',
                    visitor_id TEXT DEFAULT '',
                    device_type TEXT DEFAULT '',
                    browser TEXT DEFAULT '',
                    src TEXT DEFAULT '',
                    cta_clicked TEXT DEFAULT '',
                    converted_to_lead INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_event_asset ON growth_share_events(share_asset_id)",
                "CREATE INDEX IF NOT EXISTS idx_growth_event_type  ON growth_share_events(event_type)",
                """CREATE TABLE IF NOT EXISTS growth_referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_code TEXT NOT NULL,
                    referrer_user_id INTEGER,
                    referrer_company_id INTEGER,
                    referred_lead_id INTEGER,
                    referred_user_id INTEGER,
                    share_asset_id INTEGER,
                    reward_status TEXT DEFAULT 'pending',
                    reward_type TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_ref_code ON growth_referrals(referral_code)",
                """CREATE TABLE IF NOT EXISTS growth_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    payload_json TEXT DEFAULT '{}',
                    created_by_user_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_growth_act_lead ON growth_activities(lead_id)",
            ]:
                try:
                    c.execute(s)
                except Exception:
                    pass
            # SQLite has no ADD COLUMN IF NOT EXISTS — try each, swallow duplicate
            for col_ddl in [
                "ALTER TABLE leads ADD COLUMN lead_source_type TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN share_slug TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN asset_type TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN referral_code TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN campaign_id TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN referrer_user_id INTEGER",
                "ALTER TABLE leads ADD COLUMN preferred_contact TEXT DEFAULT ''",
                "ALTER TABLE leads ADD COLUMN pipeline_stage TEXT DEFAULT 'lead_captured'",
                "ALTER TABLE leads ADD COLUMN sales_owner_user_id INTEGER",
                "ALTER TABLE leads ADD COLUMN ai_handoff_at TEXT",
                "ALTER TABLE leads ADD COLUMN growth_source TEXT DEFAULT ''",
            ]:
                try:
                    c.execute(col_ddl)
                except Exception:
                    pass
    _GROWTH_SCHEMA_DONE["done"] = True


def _gen_share_slug():
    """10-char lowercase base32 slug, unique in growth_share_assets."""
    for _ in range(20):
        raw = _gl_secrets.token_bytes(8)
        slug = _gl_b64.b32encode(raw).decode("ascii").rstrip("=").lower()[:10]
        with get_db() as c:
            hit = c.execute(
                "SELECT 1 FROM growth_share_assets WHERE share_slug=?", (slug,)
            ).fetchone()
        if not hit:
            return slug
    raise RuntimeError("could not generate unique share slug after 20 attempts")


def _safe_card_payload(project_row, asset_type):
    """Extract SAFE-TO-PUBLISH fields from project.data_json.
    Uses SolarPro's real schema (web_app.py:3116):
        results.pv_kw, results.num_panels, results.bat_kwh, results.inv_kw,
        results.daily_kwh, results.economics.{annual_sav, payback,
        total_local, ...}, results.boq_rows, results.boq_grand.
    NEVER includes: rate_buildup, supplier_private_prices, internal_notes,
    admin info, or full BOQ pricing. Privacy guardrail per spec §20.
    # # growth-payload-fix-real-schema-applied
    """
    try:
        data = _gl_json.loads(project_row["data_json"] or "{}")
    except Exception:
        data = {}
    results = data.get("results") or {}
    eco = results.get("economics") or {}
    project_name = (project_row["name"] if "name" in project_row.keys()
                    else "Solar project")
    # Location lives at top of data, not inside results
    location = (data.get("location") or data.get("country")
                or data.get("location_label")
                or (data.get("location") or {}).get("label", "")
                or "")
    if isinstance(location, dict):
        location = location.get("label", "") or ""
    location = str(location)[:80]
    # Currency: prefer the symbol the user picked; else 3-letter code
    currency = (data.get("symbol") or data.get("currency") or "USD")
    currency = str(currency)[:6]

    # Real schema: results.pv_kw (legacy fallbacks for old projects)
    pv_kw = (results.get("pv_kw") or results.get("pv_size_kw")
             or results.get("system_kw") or 0)
    # Annual savings live INSIDE economics as `annual_sav`
    annual_savings = (eco.get("annual_sav")
                      or results.get("annual_savings_usd")
                      or results.get("annual_savings") or 0)
    # Payback INSIDE economics as `payback`
    payback = (eco.get("payback")
               or results.get("payback_years")
               or results.get("payback") or 0)
    try: payback = float(payback)
    except Exception: payback = 0
    if payback != payback or payback == float("inf"):  # NaN / inf guard
        payback = 0

    if asset_type == "solar_savings_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "payback_years": round(float(payback or 0), 1),
            "currency": currency,
        }
    if asset_type == "energy_score_card":
        # Energy-independence not directly stored; estimate from system type.
        system_type = (data.get("system_type", "") or "").lower()
        default_score = (95 if "off-grid" in system_type or "off grid" in system_type
                         else 70 if "hybrid" in system_type
                         else 35)
        score = (results.get("energy_independence_score")
                 or results.get("self_sufficiency_pct")
                 or results.get("solar_fraction_pct")
                 or default_score)
        return {
            "project_name": project_name, "location": location,
            "energy_score": round(float(score or 0), 0),
            "system_size_kw": round(float(pv_kw or 0), 2),
            "daily_kwh": round(float(results.get("daily_kwh") or 0), 1),
        }
    if asset_type == "boq_summary_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "module_count": int(results.get("num_panels") or 0),
            "battery_kwh": round(float(results.get("bat_kwh") or 0), 1),
            "inverter_kw": round(float(results.get("inv_kw") or 0), 1),
            # NO unit prices, NO supplier names, NO rate buildup.
        }
    if asset_type == "proposal_preview":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "payback_years": round(float(payback or 0), 1),
            "currency": currency,
        }
    if asset_type == "roof_before_after_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "currency": currency,
        }
    return {"project_name": project_name, "location": location}

def _growth_resolve_user_referral_code(u):
    """Return the user's referral code, generating one if missing.
    Reuses the existing _gen_referral_code() from web_app.py."""
    code = (u.get("referral_code") if isinstance(u, dict)
            else getattr(u, "referral_code", None))
    if code:
        return code
    code = _gen_referral_code()
    with get_db() as c:
        c.execute("UPDATE users SET referral_code=? WHERE id=?", (code, u["id"]))
    return code


def _growth_share_url(slug):
    return request.host_url.rstrip("/") + "/s/" + slug


def _growth_ua_parse(ua):
    """Lightweight UA parser — no extra deps. Returns (device, browser)."""
    ua = (ua or "").lower()
    if "mobile" in ua and "iphone" not in ua and "android" not in ua:
        device = "mobile"
    elif "iphone" in ua or ("android" in ua and "mobile" in ua):
        device = "mobile"
    elif "ipad" in ua or "tablet" in ua:
        device = "tablet"
    else:
        device = "desktop"
    if   "edg/" in ua:       browser = "edge"
    elif "chrome/" in ua:    browser = "chrome"
    elif "firefox/" in ua:   browser = "firefox"
    elif "safari/" in ua:    browser = "safari"
    else:                    browser = "other"
    return device, browser


def _growth_ai_sales_handoff(context, lead_id):
    """AI Sales Agent handoff per spec §12. Zero-cost: writes a sales-activity
    row + flips pipeline_stage='ai_followup'. The existing
    /api/assistant/chat chain can be invoked out-of-band by ops."""
    plan = {
        "lead_score": 75 if context.get("phone") else 45,
        "intent_class": context.get("interestType", "unknown"),
        "follow_up_script": (
            "Hi " + str(context.get("name", "there"))
            + ", thanks for trying our solar estimate. "
            + "Mind if I call you at " + str(context.get("phone", "")) + "?"
        ),
        "follow_up_when_hours": 1,
        "recommended_channel": context.get("preferredContactMethod", "phone"),
    }
    with get_db() as c:
        c.execute(
            "INSERT INTO growth_activities (lead_id, activity_type, payload_json) "
            "VALUES (?,?,?)",
            (lead_id, "ai_handoff",
             _gl_json.dumps({"context": context, "plan": plan}, separators=(",", ":"))[:4000]),
        )
        c.execute(
            "UPDATE leads SET ai_handoff_at=CURRENT_TIMESTAMP, "
            "pipeline_stage='ai_followup' WHERE id=?",
            (lead_id,),
        )


# ─── 1) Composer page (in-app, owner-only) ─────────────────────────────────
@app.route("/share/<int:pid>", methods=["GET"])
@login_required
def growth_share_composer(pid):
    """In-app composer: pick a card type from a project, generate, share."""
    _ensure_growth_schema()
    u = current_user()
    with get_db() as c:
        p = c.execute(
            "SELECT * FROM projects WHERE id=? AND user_id=?",
            (pid, u["id"]),
        ).fetchone()
    if not p:
        abort(404)
    code = _growth_resolve_user_referral_code(u)
    return render_template(
        "growth/share_composer.html",
        user=u, project=p, referral_code=code,
    )


# ─── 2) Create a share asset (Social Card Generator + Share Link Generator) ─
@app.route("/api/growth/share-assets", methods=["POST"])
@login_required
def growth_create_share_asset():
    csrf_protect()
    _ensure_growth_schema()
    u = current_user()
    body = request.get_json(silent=True) or {}
    asset_type = (body.get("asset_type") or "").strip()
    if asset_type not in _GROWTH_ALLOWED_ASSET_TYPES:
        return jsonify({"error": "invalid asset_type"}), 400

    project_id = body.get("project_id")
    payload = {}
    title = (body.get("title") or "Solar share").strip()[:200]
    summary = (body.get("summary") or "")[:600]
    if project_id:
        with get_db() as c:
            p = c.execute(
                "SELECT * FROM projects WHERE id=? AND user_id=?",
                (project_id, u["id"]),
            ).fetchone()
        if not p:
            return jsonify({"error": "project not found"}), 404
        payload = _safe_card_payload(p, asset_type)
        title = (payload.get("project_name") or title)[:200]
    else:
        # Free-form (installer / supplier achievement cards). Trust the
        # owner-supplied payload but strip any obviously private keys.
        raw = body.get("payload") or {}
        for blocked in ("rate_buildup", "supplier_prices", "internal_notes",
                        "admin_notes", "private_prices"):
            raw.pop(blocked, None)
        payload = raw

    slug = _gen_share_slug()
    ref_code = _growth_resolve_user_referral_code(u)
    campaign = (body.get("campaign_id") or "").strip()[:60]
    visibility = body.get("visibility", "public")
    if visibility not in ("public", "private", "password"):
        visibility = "public"
    expires_at = (body.get("expires_at") or None)
    if expires_at and len(str(expires_at)) > 20:
        expires_at = str(expires_at)[:20]

    with get_db() as c:
        cur = c.execute(
            "INSERT INTO growth_share_assets "
            "(share_slug, owner_user_id, project_id, asset_type, title, summary, "
            " payload_json, referral_code, campaign_id, visibility, expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (slug, u["id"], project_id, asset_type, title, summary,
             _gl_json.dumps(payload, separators=(",", ":"))[:8000],
             ref_code, campaign, visibility, expires_at),
        )
        new_id = cur.lastrowid
        c.execute(
            "INSERT INTO growth_share_events "
            "(share_asset_id, event_type, referral_code, campaign_id) "
            "VALUES (?,?,?,?)",
            (new_id, "created", ref_code, campaign),
        )
    try:
        _write_audit_event(
            "growth_share_created",
            user_id=u["id"],
            details={"slug": slug, "type": asset_type, "project_id": project_id},
        )
    except Exception:
        pass
    return jsonify({
        "id": new_id, "share_slug": slug,
        "share_url": _growth_share_url(slug),
        "referral_code": ref_code,
        "asset_type": asset_type, "payload": payload,
        "visibility": visibility,
    })


# ─── 3) Get a share asset (owner only) ─────────────────────────────────────
@app.route("/api/growth/share-assets/<int:aid>", methods=["GET"])
@login_required
def growth_get_share_asset(aid):
    _ensure_growth_schema()
    u = current_user()
    with get_db() as c:
        r = c.execute(
            "SELECT * FROM growth_share_assets WHERE id=? AND owner_user_id=?",
            (aid, u["id"]),
        ).fetchone()
    if not r:
        abort(404)
    d = dict(r)
    try:
        d["payload"] = _gl_json.loads(d.pop("payload_json", "{}") or "{}")
    except Exception:
        d["payload"] = {}
    d["share_url"] = _growth_share_url(d.get("share_slug", ""))
    return jsonify(d)


# ─── 4) Revoke a share asset ───────────────────────────────────────────────
@app.route("/api/growth/share-assets/<int:aid>/revoke", methods=["POST"])
@login_required
def growth_revoke_share_asset(aid):
    csrf_protect()
    _ensure_growth_schema()
    u = current_user()
    with get_db() as c:
        r = c.execute(
            "SELECT id FROM growth_share_assets WHERE id=? AND owner_user_id=?",
            (aid, u["id"]),
        ).fetchone()
        if not r:
            abort(404)
        c.execute(
            "UPDATE growth_share_assets SET revoked_at=CURRENT_TIMESTAMP "
            "WHERE id=?",
            (aid,),
        )
        c.execute(
            "INSERT INTO growth_share_events (share_asset_id, event_type) "
            "VALUES (?,?)",
            (aid, "revoked"),
        )
    try:
        _write_audit_event(
            "growth_share_revoked", user_id=u["id"], details={"id": aid},
        )
    except Exception:
        pass
    return jsonify({"ok": True})


# ─── 5) Public preview page + visit tracker ────────────────────────────────
@app.route("/s/<slug>", methods=["GET"])
@limiter.limit("60 per minute")
def growth_public_preview(slug):
    _ensure_growth_schema()
    slug = (slug or "").strip().lower()[:20]
    with get_db() as c:
        r = c.execute(
            "SELECT * FROM growth_share_assets WHERE share_slug=?", (slug,),
        ).fetchone()
    if not r:
        abort(404)
    d = dict(r)
    if d.get("revoked_at"):
        return render_template("growth/public_share_revoked.html"), 410
    today = _gl_time.strftime("%Y-%m-%d")
    if d.get("expires_at") and str(d["expires_at"])[:10] < today:
        return render_template("growth/public_share_expired.html"), 410
    if d.get("visibility") == "private":
        abort(403)
    try:
        payload = _gl_json.loads(d.get("payload_json") or "{}")
    except Exception:
        payload = {}
    # Ensure CSRF token exists so the lead-capture form on this page works.
    generate_csrf()
    # Set ref cookie like /r/<code> — keeps attribution on subsequent visits.
    resp = make_response(render_template(
        "growth/public_share.html",
        asset=d, payload=payload,
        share_url=request.host_url.rstrip("/") + "/s/" + slug,
        src=request.args.get("src", "direct")[:60],
    ))
    if d.get("referral_code"):
        resp.set_cookie(
            "ref_code", d["referral_code"], max_age=30 * 24 * 3600,
            httponly=False, samesite="Lax",
        )
    # Lightweight visit logging (best-effort; never fail the response).
    try:
        device, browser = _growth_ua_parse(request.headers.get("User-Agent", ""))
        with get_db() as c:
            c.execute(
                "INSERT INTO growth_share_events "
                "(share_asset_id, event_type, referral_code, campaign_id, "
                " src, device_type, browser) "
                "VALUES (?,?,?,?,?,?,?)",
                (d["id"], "visited", d.get("referral_code", ""),
                 d.get("campaign_id", ""),
                 request.args.get("src", "direct")[:60],
                 device, browser),
            )
    except Exception:
        pass
    return resp


# ─── 6) Public event ping (CTA clicked, shared, etc.) ──────────────────────
@app.route("/api/growth/share-assets/<int:aid>/event", methods=["POST"])
@limiter.limit("60 per minute")
def growth_log_event(aid):
    _ensure_growth_schema()
    body = request.get_json(silent=True) or {}
    event_type = (body.get("event_type") or "visited")
    if event_type not in ("visited", "cta_clicked", "shared"):
        return jsonify({"error": "invalid event_type"}), 400
    channel = (body.get("channel") or "")[:30]
    src = (body.get("src") or "")[:60]
    cta = (body.get("cta") or "")[:60]
    with get_db() as c:
        r = c.execute(
            "SELECT id, referral_code, campaign_id, revoked_at "
            "FROM growth_share_assets WHERE id=?", (aid,),
        ).fetchone()
        if not r:
            return ("", 204)
        if dict(r).get("revoked_at"):
            return ("", 204)
        c.execute(
            "INSERT INTO growth_share_events "
            "(share_asset_id, event_type, channel, src, cta_clicked, "
            " referral_code, campaign_id) VALUES (?,?,?,?,?,?,?)",
            (aid, event_type, channel, src, cta,
             dict(r).get("referral_code", ""),
             dict(r).get("campaign_id", "")),
        )
    return ("", 204)


# ─── 7) Lead capture (CRM + Sales Pipeline + AI handoff) ───────────────────
@app.route("/api/growth/lead-capture", methods=["POST"])
@limiter.limit("20 per minute")
def growth_lead_capture():
    csrf_protect()
    _ensure_growth_schema()
    body = request.get_json(silent=True) or request.form.to_dict()
    name = (body.get("name") or "").strip()[:120]
    phone = (body.get("phone") or "").strip()[:40]
    email = (body.get("email") or "").strip()[:120]
    location = (body.get("location") or "").strip()[:120]
    interest = (body.get("interest") or "Residential Solar").strip()[:60]
    pref = (body.get("preferred_contact") or "phone").strip()[:20]
    if pref not in ("phone", "email", "whatsapp"):
        pref = "phone"
    slug = (body.get("share_slug") or "").strip()[:20]
    consent = bool(body.get("consent"))
    if not name or not phone or not consent:
        return jsonify({"error": "name, phone and consent required"}), 400

    asset = None
    asset_type = ""
    ref_code = (body.get("referral_code")
                or request.cookies.get("ref_code") or "")[:16]
    campaign = ""
    project_id = None
    if slug:
        with get_db() as c:
            r = c.execute(
                "SELECT * FROM growth_share_assets WHERE share_slug=?", (slug,),
            ).fetchone()
        if r:
            asset = dict(r)
            asset_type = asset.get("asset_type", "")
            ref_code = ref_code or (asset.get("referral_code") or "")
            campaign = asset.get("campaign_id") or ""
            project_id = asset.get("project_id")

    # Resolve referrer (the owner of the referral_code)
    referrer_id = None
    if ref_code:
        with get_db() as c:
            row = c.execute(
                "SELECT id FROM users WHERE referral_code=?", (ref_code,),
            ).fetchone()
        referrer_id = (row["id"] if row else None)

    source_label = _GROWTH_LEAD_SOURCE_LABELS.get(asset_type, "Growth Layer")

    safe_email = email or ("noemail+" + _gl_secrets.token_hex(4)
                           + "@growth.local")
    with get_db() as c:
        cur = c.execute(
            "INSERT INTO leads "
            "(name, email, phone, company, country, interest, message, source, "
            " status, notes, lead_source_type, share_slug, asset_type, "
            " referral_code, campaign_id, referrer_user_id, preferred_contact, "
            " pipeline_stage, growth_source) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, safe_email, phone, "", location, interest, "",
             source_label, "new", "", source_label, slug, asset_type,
             ref_code, campaign, referrer_id, pref,
             "lead_captured", source_label),
        )
        lead_id = cur.lastrowid
        c.execute(
            "INSERT INTO growth_activities (lead_id, activity_type, payload_json) "
            "VALUES (?,?,?)",
            (lead_id, "pipeline_stage_change",
             _gl_json.dumps({"to": "lead_captured"})),
        )
        if asset:
            c.execute(
                "INSERT INTO growth_share_events "
                "(share_asset_id, event_type, channel, referral_code, "
                " campaign_id, converted_to_lead) "
                "VALUES (?,?,?,?,?,?)",
                (asset["id"], "lead_captured", "form",
                 ref_code, campaign, 1),
            )
        # Referral record — separate growth_referrals table since the existing
        # `referrals` table requires both sides to be users.
        if referrer_id:
            try:
                c.execute(
                    "INSERT INTO growth_referrals "
                    "(referral_code, referrer_user_id, referred_lead_id, "
                    " share_asset_id, reward_status, reward_type) "
                    "VALUES (?,?,?,?,?,?)",
                    (ref_code, referrer_id, lead_id,
                     (asset["id"] if asset else None),
                     "pending", "credits"),
                )
            except Exception:
                pass

    try:
        _write_audit_event(
            "growth_lead_captured",
            details={"lead_id": lead_id, "slug": slug, "source": source_label},
        )
    except Exception:
        pass

    # AI Sales Agent handoff (zero-cost stub; real LLM scoring is opt-in)
    try:
        _growth_ai_sales_handoff({
            "leadSourceType": source_label, "assetType": asset_type,
            "shareSlug": slug, "referralCode": ref_code,
            "referrerUserId": referrer_id, "projectId": project_id,
            "interestType": interest, "location": location,
            "name": name, "phone": phone, "email": email,
            "preferredContactMethod": pref,
        }, lead_id)
    except Exception:
        pass

    return jsonify({
        "ok": True, "lead_id": lead_id,
        "pipeline_stage": "ai_followup",
        "source": source_label,
    })


# ─── 8) Explicit referral record endpoint (per spec §10) ───────────────────
@app.route("/api/growth/referral/record", methods=["POST"])
@limiter.limit("20 per minute")
def growth_referral_record():
    csrf_protect()
    _ensure_growth_schema()
    body = request.get_json(silent=True) or {}
    ref_code = (body.get("referral_code") or "")[:16]
    lead_id = body.get("lead_id")
    share_asset_id = body.get("share_asset_id")
    if not ref_code:
        return jsonify({"error": "referral_code required"}), 400
    with get_db() as c:
        r = c.execute(
            "SELECT id FROM users WHERE referral_code=?", (ref_code,),
        ).fetchone()
        if not r:
            return jsonify({"error": "unknown referral_code"}), 404
        try:
            c.execute(
                "INSERT INTO growth_referrals "
                "(referral_code, referrer_user_id, referred_lead_id, "
                " share_asset_id, reward_status) "
                "VALUES (?,?,?,?,?)",
                (ref_code, r["id"], lead_id, share_asset_id, "pending"),
            )
        except Exception:
            pass
    return jsonify({"ok": True})


# ─── 9) Growth dashboard (JSON + HTML) ─────────────────────────────────────
@app.route("/api/growth/dashboard", methods=["GET"])
@login_required
def growth_dashboard_json():
    _ensure_growth_schema()
    u = current_user()
    is_admin = bool((u.get("is_admin") if isinstance(u, dict)
                     else getattr(u, "is_admin", 0)))
    with get_db() as c:
        def scalar(sql, *args):
            row = c.execute(sql, args).fetchone()
            return ((row[0] if row else 0) or 0)

        if is_admin:
            total_assets = scalar("SELECT COUNT(*) FROM growth_share_assets")
            total_visits = scalar(
                "SELECT COUNT(*) FROM growth_share_events "
                "WHERE event_type='visited'")
            total_leads = scalar(
                "SELECT COUNT(*) FROM leads "
                "WHERE COALESCE(lead_source_type,'')<>''")
            by_source = c.execute(
                "SELECT COALESCE(lead_source_type,'(none)') AS s, COUNT(*) AS n "
                "FROM leads WHERE COALESCE(lead_source_type,'')<>'' "
                "GROUP BY COALESCE(lead_source_type,'(none)') "
                "ORDER BY COUNT(*) DESC LIMIT 10").fetchall()
            top_referrers = c.execute(
                "SELECT COALESCE(referral_code,'(none)') AS c, COUNT(*) AS n "
                "FROM leads WHERE COALESCE(referral_code,'')<>'' "
                "GROUP BY COALESCE(referral_code,'(none)') "
                "ORDER BY COUNT(*) DESC LIMIT 10").fetchall()
            top_asset = c.execute(
                "SELECT asset_type AS t, COUNT(*) AS n "
                "FROM growth_share_assets GROUP BY asset_type "
                "ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
            pipeline_counts = c.execute(
                "SELECT COALESCE(pipeline_stage,'(none)') AS s, COUNT(*) AS n "
                "FROM leads WHERE COALESCE(lead_source_type,'')<>'' "
                "GROUP BY COALESCE(pipeline_stage,'(none)')").fetchall()
        else:
            uid = u["id"]
            total_assets = scalar(
                "SELECT COUNT(*) FROM growth_share_assets "
                "WHERE owner_user_id=?", uid)
            total_visits = scalar(
                "SELECT COUNT(*) FROM growth_share_events e "
                "JOIN growth_share_assets a ON a.id=e.share_asset_id "
                "WHERE e.event_type='visited' AND a.owner_user_id=?", uid)
            total_leads = scalar(
                "SELECT COUNT(*) FROM leads WHERE referrer_user_id=?", uid)
            by_source = c.execute(
                "SELECT COALESCE(lead_source_type,'(none)') AS s, COUNT(*) AS n "
                "FROM leads WHERE referrer_user_id=? "
                "GROUP BY COALESCE(lead_source_type,'(none)') "
                "ORDER BY COUNT(*) DESC LIMIT 10", (uid,)).fetchall()
            top_referrers = []
            top_asset = c.execute(
                "SELECT asset_type AS t, COUNT(*) AS n "
                "FROM growth_share_assets WHERE owner_user_id=? "
                "GROUP BY asset_type ORDER BY COUNT(*) DESC LIMIT 1",
                (uid,)).fetchone()
            pipeline_counts = c.execute(
                "SELECT COALESCE(pipeline_stage,'(none)') AS s, COUNT(*) AS n "
                "FROM leads WHERE referrer_user_id=? "
                "GROUP BY COALESCE(pipeline_stage,'(none)')", (uid,)).fetchall()
    conv = 0.0
    if total_visits > 0:
        conv = round(100.0 * float(total_leads) / float(total_visits), 1)

    def rows_to_list(rs):
        if not rs:
            return []
        out = []
        for row in rs:
            try:
                out.append(dict(row))
            except Exception:
                out.append({"s": row[0], "n": row[1]})
        return out

    return jsonify({
        "scope": ("admin" if is_admin else "user"),
        "total_share_assets": total_assets,
        "total_visits": total_visits,
        "total_leads": total_leads,
        "conversion_pct": conv,
        "top_asset_type": (dict(top_asset).get("t") if top_asset else ""),
        "leads_by_source": rows_to_list(by_source),
        "top_referrers": rows_to_list(top_referrers),
        "pipeline_counts": rows_to_list(pipeline_counts),
    })


@app.route("/growth", methods=["GET"])
@login_required
def growth_dashboard_page():
    _ensure_growth_schema()
    u = current_user()
    with get_db() as c:
        my_assets = c.execute(
            "SELECT id, share_slug, asset_type, title, created_at, revoked_at "
            "FROM growth_share_assets WHERE owner_user_id=? "
            "ORDER BY id DESC LIMIT 50",
            (u["id"],),
        ).fetchall()
    return render_template(
        "growth/dashboard.html",
        user=u, my_assets=[dict(r) for r in my_assets],
    )


# ─── 10) Proposal Beautifier (uses existing proposal data) ─────────────────
@app.route("/project/<int:pid>/proposal/beautified", methods=["GET"])
@login_required
def growth_proposal_beautifier(pid):
    _ensure_growth_schema()
    u = current_user()
    with get_db() as c:
        p = c.execute(
            "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, u["id"]),
        ).fetchone()
    if not p:
        abort(404)
    try:
        data = _gl_json.loads(p["data_json"] or "{}")
    except Exception:
        data = {}
    results = data.get("results") or {}
    return render_template(
        "growth/proposal_beautified.html",
        user=u, project=p, data=data, results=results,
    )
