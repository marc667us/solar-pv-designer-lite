"""
Campaign portal — Flask blueprint backing the static GitHub Pages portal.

What it does
------------
- Exposes a small CORS-enabled REST API on the existing SolarPro Flask app.
- All campaign-portal data (pipeline status per entity, feedback items, rep notes)
  lives in SQLite tables in the existing `solar.db`. The portal HTML on GitHub
  Pages calls these endpoints — no localStorage for shared state.
- A simple shared API key in the X-Campaign-Key header gates write access.
  (Internal-only portal during beta; key rotation = re-deploy with new env var.)

Endpoints
---------
- GET   /api/campaign/health             liveness probe
- GET   /api/campaign/entities           returns master entity list seeded from
                                         data/ghana_beta_invitees.json
- GET   /api/campaign/state              full pipeline + feedback snapshot
- POST  /api/campaign/state/<name>       update one entity's status/notes/date
- POST  /api/campaign/feedback           add a feedback item
- PATCH /api/campaign/feedback/<id>      change feedback status

CORS
----
Allowed origins: https://campaign.aiappinvent.com and the github.io preview URL.
Methods: GET, POST, PATCH, OPTIONS. Header: X-Campaign-Key.

Persistence note
----------------
Railway free tier has an EPHEMERAL filesystem — solar.db is wiped on each
deploy. For beta this is acceptable because deploys are infrequent and the
human-readable notes can be rebuilt fast. To make this durable, attach a
Railway Volume mounted at /app and set DB_PATH=/app/solar.db (the existing
deploy workflow already pushes DB_PATH). Once a Volume is attached, this
module needs no changes.
"""
import json
import os
import sqlite3
import time
from pathlib import Path

from flask import Blueprint, jsonify, request, abort, make_response, g

# ---------------------------------------------------------------------------
# Config

# Shared key for write requests. Falls back to a known default so the API
# works the moment the code deploys; rotate by setting CAMPAIGN_API_KEY on
# Railway and redeploying. This is "obscurity auth" — adequate for an
# internal-only beta portal whose data is contact info already on the web.
CAMPAIGN_API_KEY = os.environ.get("CAMPAIGN_API_KEY", "campaign-ghana-2026-beta")

# Allowed CORS origins. Add another origin here if a new portal host appears.
ALLOWED_ORIGINS = {
    "https://campaign.aiappinvent.com",
    "https://marc667us.github.io",
    # During local development reps may open the file directly:
    "null",
}

# DB path uses the same SQLite file as the main SolarPro app. Defaults to
# /app/solar.db on Railway (or whatever DB_PATH is set to).
def _db_path():
    return os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "solar.db"))


# Seed file we read once on first startup to populate the entity table.
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ghana_beta_invitees.json")

campaign_bp = Blueprint("campaign", __name__, url_prefix="/api/campaign")


# ---------------------------------------------------------------------------
# Database init

def _conn():
    """Open a SQLite connection. Per-request (Flask `g`) so we close cleanly."""
    if not hasattr(g, "_campaign_db"):
        g._campaign_db = sqlite3.connect(_db_path())
        g._campaign_db.row_factory = sqlite3.Row
    return g._campaign_db


def _init_db_once():
    """Idempotent schema migration. Safe to call on every import."""
    conn = sqlite3.connect(_db_path())
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS campaign_entities (
            name TEXT PRIMARY KEY,
            payload TEXT NOT NULL,           -- whole entity dict as JSON
            seeded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaign_pipeline (
            entity_name TEXT PRIMARY KEY,    -- FK to campaign_entities.name
            status TEXT NOT NULL DEFAULT 'INVITED',
            notes TEXT NOT NULL DEFAULT '',
            next_action_date TEXT NOT NULL DEFAULT '',
            literature_sent TEXT NOT NULL DEFAULT '[]',  -- JSON list
            last_updated TEXT NOT NULL,
            last_updated_by TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS campaign_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_name TEXT NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            captured_by TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_entity ON campaign_feedback(entity_name);
        CREATE INDEX IF NOT EXISTS idx_feedback_status ON campaign_feedback(status);
    """)
    # Seed entities if the table is empty
    cur.execute("SELECT COUNT(*) FROM campaign_entities")
    if cur.fetchone()[0] == 0 and os.path.exists(SEED_PATH):
        try:
            seed = json.loads(Path(SEED_PATH).read_text(encoding="utf-8"))
            now = time.strftime("%Y-%m-%d")
            for e in seed.get("entities", []):
                cur.execute(
                    "INSERT OR REPLACE INTO campaign_entities (name, payload, seeded_at) VALUES (?, ?, ?)",
                    (e["name"], json.dumps(e), now),
                )
            conn.commit()
        except Exception as exc:
            # Seeding is best-effort; if the JSON is missing we still serve []
            print(f"[campaign_api] seed skipped: {exc}")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CORS helpers

def _cors_headers(resp):
    """Attach CORS headers when the Origin is in our allowlist."""
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Campaign-Key, X-Campaign-Rep"
        resp.headers["Access-Control-Max-Age"] = "600"
    return resp


@campaign_bp.after_request
def _attach_cors(resp):
    return _cors_headers(resp)


@campaign_bp.before_request
def _preflight():
    """Reply 204 to CORS preflight without further processing."""
    if request.method == "OPTIONS":
        return _cors_headers(make_response("", 204))
    return None


def _check_key():
    """Enforce X-Campaign-Key on every write."""
    if request.headers.get("X-Campaign-Key") != CAMPAIGN_API_KEY:
        abort(401, description="bad campaign key")


def _rep():
    """The rep's display name for audit columns. Header X-Campaign-Rep."""
    return (request.headers.get("X-Campaign-Rep") or "anon").strip()[:80]


# ---------------------------------------------------------------------------
# Routes

@campaign_bp.route("/health", methods=["GET"])
def health():
    return jsonify(ok=True, ts=int(time.time()))


@campaign_bp.route("/entities", methods=["GET"])
def list_entities():
    """Return the entity master list."""
    cur = _conn().cursor()
    cur.execute("SELECT payload FROM campaign_entities ORDER BY name")
    items = [json.loads(r["payload"]) for r in cur.fetchall()]
    return jsonify({"generated": time.strftime("%Y-%m-%d"), "entities": items})


@campaign_bp.route("/state", methods=["GET"])
def get_state():
    """One snapshot containing pipeline + feedback so the portal can hydrate in 1 round-trip."""
    cur = _conn().cursor()
    cur.execute("SELECT * FROM campaign_pipeline")
    pipeline = {r["entity_name"]: {
        "status": r["status"], "notes": r["notes"],
        "next_action_date": r["next_action_date"],
        "literature_sent": json.loads(r["literature_sent"] or "[]"),
        "last_updated": r["last_updated"],
        "last_updated_by": r["last_updated_by"],
    } for r in cur.fetchall()}
    cur.execute("SELECT * FROM campaign_feedback ORDER BY id DESC")
    feedback = {}
    for r in cur.fetchall():
        feedback.setdefault(r["entity_name"], []).append({
            "id": r["id"], "date": r["date"], "type": r["type"],
            "severity": r["severity"], "text": r["text"],
            "status": r["status"], "captured_by": r["captured_by"],
        })
    return jsonify({"pipeline": pipeline, "feedback": feedback})


@campaign_bp.route("/state/<name>", methods=["POST"])
def update_state(name):
    _check_key()
    body = request.get_json(silent=True) or {}
    status = body.get("status", "INVITED")
    notes = body.get("notes", "")
    nad = body.get("next_action_date", "")
    lit = json.dumps(body.get("literature_sent", []))
    now = time.strftime("%Y-%m-%d")
    rep = _rep()
    conn = _conn()
    # UPSERT pattern compatible with old SQLite (no ON CONFLICT in v3 <3.24, but Railway has new)
    conn.execute(
        "INSERT INTO campaign_pipeline (entity_name, status, notes, next_action_date, literature_sent, last_updated, last_updated_by) "
        "VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(entity_name) DO UPDATE SET status=excluded.status, notes=excluded.notes, "
        "next_action_date=excluded.next_action_date, literature_sent=excluded.literature_sent, "
        "last_updated=excluded.last_updated, last_updated_by=excluded.last_updated_by",
        (name, status, notes, nad, lit, now, rep),
    )
    conn.commit()
    return jsonify(ok=True)


@campaign_bp.route("/feedback", methods=["POST"])
def add_feedback():
    _check_key()
    body = request.get_json(silent=True) or {}
    name = body.get("entity_name", "")
    if not name:
        abort(400, description="entity_name required")
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO campaign_feedback (entity_name, date, type, severity, text, status, captured_by) "
        "VALUES (?,?,?,?,?,?,?)",
        (name,
         body.get("date") or time.strftime("%Y-%m-%d"),
         body.get("type", "bug"),
         body.get("severity", "medium"),
         body.get("text", ""),
         body.get("status", "open"),
         _rep()),
    )
    conn.commit()
    return jsonify(ok=True, id=cur.lastrowid)


@campaign_bp.route("/feedback/<int:fid>", methods=["PATCH"])
def patch_feedback(fid):
    _check_key()
    body = request.get_json(silent=True) or {}
    if "status" not in body:
        abort(400, description="status required")
    conn = _conn()
    conn.execute("UPDATE campaign_feedback SET status=? WHERE id=?", (body["status"], fid))
    conn.commit()
    return jsonify(ok=True)


@campaign_bp.teardown_request
def _close_db(_exc):
    if hasattr(g, "_campaign_db"):
        g._campaign_db.close()


# ---------------------------------------------------------------------------
# Registration helper used by web_app.py

def register_campaign_api(app):
    """Attach the blueprint + run the one-shot schema migration.
    Inputs:  app = the Flask app from web_app.py
    Output:  None (side effects: blueprint registered, DB schema present)
    """
    app.register_blueprint(campaign_bp)
    try:
        _init_db_once()
    except Exception as exc:
        # Migration failure should not break the rest of the SolarPro app
        print(f"[campaign_api] init_db failed (non-fatal): {exc}")
