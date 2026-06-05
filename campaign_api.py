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
import hashlib
import hmac
import json
import os
import secrets
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

# Bootstrap admin — created on first DB init if no users exist. Marc gets
# admin rights and a default password he should change immediately.
BOOTSTRAP_ADMIN_EMAIL    = os.environ.get("CAMPAIGN_ADMIN_EMAIL", "marc667us@yahoo.com")
BOOTSTRAP_ADMIN_NAME     = os.environ.get("CAMPAIGN_ADMIN_NAME", "Marc")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("CAMPAIGN_ADMIN_PASSWORD", "ChangeMe2026!")

# Sessions are bound to a server-side random token. We don't store tokens in
# the DB to keep it simple — we sign them with this secret using HMAC, so a
# valid token decodes back to a user email + role. Rotating SESSION_SECRET
# logs everyone out.
SESSION_SECRET = os.environ.get(
    "CAMPAIGN_SESSION_SECRET",
    "campaign-session-secret-rotate-this-on-prod"
).encode()

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


def _hash_password(password, salt=None):
    """PBKDF2-HMAC-SHA256, 200k iterations. Returns 'salt$hash' both hex.
    Stdlib only — no bcrypt dependency to add."""
    if salt is None:
        salt = secrets.token_bytes(16)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt.hex() + "$" + digest.hex()


def _verify_password(password, stored):
    """Compare a password against the stored 'salt$hash'."""
    try:
        salt_hex, _ = stored.split("$", 1)
        return hmac.compare_digest(stored, _hash_password(password, salt_hex))
    except Exception:
        return False


def _init_db_once():
    """Idempotent schema migration. Safe to call on every import."""
    # Create the parent directory if DB_PATH points at a not-yet-mounted volume.
    # Render disks may not exist on first deploy; the dir is created lazily.
    db_path = _db_path()
    parent = os.path.dirname(db_path) or "."
    try: os.makedirs(parent, exist_ok=True)
    except Exception as exc: print(f"[campaign_api] could not create {parent}: {exc}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS campaign_entities (
            name TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            seeded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaign_pipeline (
            entity_name TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'INVITED',
            notes TEXT NOT NULL DEFAULT '',
            next_action_date TEXT NOT NULL DEFAULT '',
            literature_sent TEXT NOT NULL DEFAULT '[]',
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
        CREATE TABLE IF NOT EXISTS campaign_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'sales',
            product_id TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            status TEXT NOT NULL DEFAULT 'pending',     -- 'pending' | 'active' | 'suspended'
            profession TEXT NOT NULL DEFAULT '',
            invite_token TEXT                            -- the token they used (for audit)
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON campaign_users(email);
        CREATE INDEX IF NOT EXISTS idx_users_status ON campaign_users(status);

        CREATE TABLE IF NOT EXISTS campaign_invites (
            token TEXT PRIMARY KEY,
            created_by TEXT NOT NULL,         -- admin email
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',    -- what the admin labelled the invite for
            used_by_email TEXT,
            used_at TEXT
        );
    """)

    # Idempotent column additions for upgrades from earlier schema versions
    for stmt in (
        "ALTER TABLE campaign_users ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'",
        "ALTER TABLE campaign_users ADD COLUMN profession TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE campaign_users ADD COLUMN invite_token TEXT",
        # Tracking — when product was assigned, by whom
        "ALTER TABLE campaign_users ADD COLUMN product_assigned_at TEXT",
        "ALTER TABLE campaign_users ADD COLUMN product_assigned_by TEXT",
    ):
        try: cur.execute(stmt)
        except sqlite3.OperationalError: pass

    # Per-entity assignments table (which staff gets which entities)
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS campaign_assignments (
            user_id INTEGER NOT NULL,
            entity_name TEXT NOT NULL,
            assigned_at TEXT NOT NULL,
            assigned_by TEXT NOT NULL,
            PRIMARY KEY (user_id, entity_name)
        );
        CREATE INDEX IF NOT EXISTS idx_assign_user ON campaign_assignments(user_id);
    """)

    # Bootstrap admin if no users exist yet — admin is auto-active.
    cur.execute("SELECT COUNT(*) FROM campaign_users")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO campaign_users (email, name, role, product_id, password_hash, created_at, status, profession) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (BOOTSTRAP_ADMIN_EMAIL.lower(), BOOTSTRAP_ADMIN_NAME, "admin",
             "solarpro-ghana", _hash_password(BOOTSTRAP_ADMIN_PASSWORD), time.strftime("%Y-%m-%d"),
             "active", "Admin"),
        )
        print(f"[campaign_api] bootstrapped admin: {BOOTSTRAP_ADMIN_EMAIL}")
    else:
        # Pre-existing rows from an earlier schema have status='pending' default —
        # nudge any admin role to active so they don't get locked out by the
        # status check.
        cur.execute("UPDATE campaign_users SET status='active' WHERE role='admin' AND status='pending'")
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


# Update Access-Control-Allow-Headers to include the new session header
def _cors_headers_with_session(resp):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Campaign-Key, X-Campaign-Rep, X-Campaign-Session"
        resp.headers["Access-Control-Max-Age"] = "600"
    return resp


# Replace the registered after_request to use the session-aware version
_cors_headers = _cors_headers_with_session


def _check_key():
    """Accept EITHER a valid session token OR the legacy X-Campaign-Key.
    Sessions are the new way; the API key remains as a fallback."""
    if _session_from_request():
        return
    if request.headers.get("X-Campaign-Key") == CAMPAIGN_API_KEY:
        return
    abort(401, description="login required")


def _rep():
    """The rep's display name from session cookie or X-Campaign-Rep fallback."""
    sess = _session_from_request()
    if sess:
        return sess["name"]
    return (request.headers.get("X-Campaign-Rep") or "anon").strip()[:80]


# ---------------------------------------------------------------------------
# Session tokens (signed, stateless — no session table needed)

def _make_session_token(user_row):
    """Make a signed session token: 'email|role|name|issued_at|sig'."""
    payload = f"{user_row['email']}|{user_row['role']}|{user_row['name']}|{int(time.time())}"
    sig = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return payload + "|" + sig


def _decode_session_token(token):
    """Return {email, role, name, issued_at} or None if invalid/tampered."""
    if not token or token.count("|") < 4:
        return None
    *parts, sig = token.split("|")
    payload = "|".join(parts)
    expected = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    email, role, name, issued = parts[0], parts[1], parts[2], parts[3]
    # 30-day session window
    if (time.time() - int(issued)) > 30 * 86400:
        return None
    return {"email": email, "role": role, "name": name, "issued_at": int(issued)}


def _session_from_request():
    """Look up the current session from X-Campaign-Session header."""
    tok = request.headers.get("X-Campaign-Session", "")
    return _decode_session_token(tok)


def _require_user():
    """Require any logged-in user — returns the decoded session or 401."""
    s = _session_from_request()
    if not s:
        abort(401, description="login required")
    return s


def _require_admin():
    """Require admin role — returns the decoded session or 403."""
    s = _require_user()
    if s.get("role") != "admin":
        abort(403, description="admin only")
    return s


# ---------------------------------------------------------------------------
# Routes

@campaign_bp.route("/health", methods=["GET"])
def health():
    return jsonify(ok=True, ts=int(time.time()))


# ---------------------------------------------------------------------------
# Auth + user management

@campaign_bp.route("/login", methods=["POST"])
def login():
    """email + password → session token. No X-Campaign-Key required to log in."""
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or not password:
        abort(400, description="email and password required")
    cur = _conn().execute("SELECT * FROM campaign_users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        abort(401, description="invalid credentials")
    if row["status"] == "pending":
        abort(403, description="account pending admin approval")
    if row["status"] == "suspended":
        abort(403, description="account suspended")
    # Touch last_login (best effort)
    try:
        _conn().execute("UPDATE campaign_users SET last_login=? WHERE id=?",
                        (time.strftime("%Y-%m-%dT%H:%M:%S"), row["id"]))
        _conn().commit()
    except Exception:
        pass
    return jsonify({
        "token": _make_session_token(row),
        "user": {"email": row["email"], "name": row["name"],
                 "role": row["role"], "product_id": row["product_id"]},
    })


@campaign_bp.route("/invites", methods=["POST"])
def create_invite():
    """Admin creates an invitation. Body: { note?, expires_days? (default 14) }
    Returns the token + URL to share via WhatsApp/email.
    """
    s = _require_admin()
    body = request.get_json(silent=True) or {}
    note = (body.get("note") or "").strip()[:120]
    expires_days = int(body.get("expires_days") or 14)
    token = secrets.token_urlsafe(20)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    expires = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + expires_days * 86400))
    _conn().execute(
        "INSERT INTO campaign_invites (token, created_by, created_at, expires_at, note) "
        "VALUES (?,?,?,?,?)",
        (token, s["email"], now, expires, note),
    )
    _conn().commit()
    return jsonify({"token": token, "expires_at": expires, "note": note})


@campaign_bp.route("/invites", methods=["GET"])
def list_invites():
    _require_admin()
    cur = _conn().execute(
        "SELECT token, created_by, created_at, expires_at, note, used_by_email, used_at "
        "FROM campaign_invites ORDER BY created_at DESC"
    )
    return jsonify([dict(r) for r in cur.fetchall()])


@campaign_bp.route("/invites/<token>", methods=["DELETE"])
def revoke_invite(token):
    _require_admin()
    _conn().execute("DELETE FROM campaign_invites WHERE token=?", (token,))
    _conn().commit()
    return jsonify(ok=True)


@campaign_bp.route("/invite/<token>", methods=["GET"])
def check_invite(token):
    """Public — the signup page calls this to verify the invite is still valid."""
    cur = _conn().execute("SELECT * FROM campaign_invites WHERE token=?", (token,))
    inv = cur.fetchone()
    if not inv:
        abort(404, description="invitation not found")
    if inv["used_by_email"]:
        abort(410, description="invitation already used")
    if inv["expires_at"] < time.strftime("%Y-%m-%dT%H:%M:%S"):
        abort(410, description="invitation expired")
    return jsonify({"ok": True, "expires_at": inv["expires_at"], "note": inv["note"]})


@campaign_bp.route("/invite/<token>/accept", methods=["POST"])
def accept_invite(token):
    """Public — the invitee submits name + email + password + profession.
    Creates a PENDING user; admin must approve before sign-in works.
    """
    cur = _conn().execute("SELECT * FROM campaign_invites WHERE token=?", (token,))
    inv = cur.fetchone()
    if not inv:
        abort(404, description="invitation not found")
    if inv["used_by_email"]:
        abort(410, description="invitation already used")
    if inv["expires_at"] < time.strftime("%Y-%m-%dT%H:%M:%S"):
        abort(410, description="invitation expired")

    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()
    password = body.get("password") or ""
    profession = (body.get("profession") or "").strip()[:80]
    if not email or not name or not password or not profession:
        abort(400, description="email, name, password, profession required")
    if len(password) < 6:
        abort(400, description="password must be at least 6 characters")

    try:
        _conn().execute(
            "INSERT INTO campaign_users (email, name, role, product_id, password_hash, created_at, "
            "status, profession, invite_token) VALUES (?,?,?,?,?,?,?,?,?)",
            (email, name, "sales", "", _hash_password(password),
             time.strftime("%Y-%m-%d"), "pending", profession, token),
        )
        _conn().execute(
            "UPDATE campaign_invites SET used_by_email=?, used_at=? WHERE token=?",
            (email, time.strftime("%Y-%m-%dT%H:%M:%S"), token),
        )
        _conn().commit()
    except sqlite3.IntegrityError:
        abort(409, description="that email is already registered")
    return jsonify({"ok": True, "message": "Account created. An admin will review and assign your product."})


@campaign_bp.route("/pending", methods=["GET"])
def list_pending():
    """Admin — users awaiting approval."""
    _require_admin()
    cur = _conn().execute(
        "SELECT id, email, name, profession, role, created_at, invite_token "
        "FROM campaign_users WHERE status='pending' ORDER BY created_at ASC"
    )
    return jsonify([dict(r) for r in cur.fetchall()])


@campaign_bp.route("/users/<int:uid>/approve", methods=["POST"])
def approve_user(uid):
    """Admin — activate a pending user, assign product + role, and assign entities.

    Body: {
      product_id (required),
      role? (sales|manager|admin),
      entities? (list of entity names; default = ALL entities of that product)
    }
    Every assignment is timestamped with assigned_at + assigned_by (admin email).
    """
    s = _require_admin()
    body = request.get_json(silent=True) or {}
    product_id = (body.get("product_id") or "").strip()
    role = body.get("role", "sales")
    requested_entities = body.get("entities")  # None => all
    if not product_id:
        abort(400, description="product_id required")
    if role not in ("admin", "sales", "manager"):
        abort(400, description="role must be admin|sales|manager")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    conn = _conn()
    cur = conn.execute(
        "UPDATE campaign_users SET status='active', product_id=?, role=?, "
        "product_assigned_at=?, product_assigned_by=? WHERE id=? AND status='pending'",
        (product_id, role, now, s["email"], uid),
    )
    if cur.rowcount == 0:
        abort(404, description="no pending user with that id")

    # Default to assigning every entity if the admin didn't pick a subset
    if requested_entities is None:
        cur = conn.execute("SELECT name FROM campaign_entities")
        requested_entities = [r["name"] for r in cur.fetchall()]

    # Clear any previous assignments (shouldn't exist for a pending user, but be safe)
    conn.execute("DELETE FROM campaign_assignments WHERE user_id=?", (uid,))
    for name in requested_entities:
        conn.execute(
            "INSERT OR IGNORE INTO campaign_assignments (user_id, entity_name, assigned_at, assigned_by) "
            "VALUES (?,?,?,?)",
            (uid, name, now, s["email"]),
        )
    conn.commit()
    return jsonify(ok=True, assigned_entities=len(requested_entities), at=now)


@campaign_bp.route("/users/<int:uid>/assignments", methods=["GET"])
def list_assignments(uid):
    """Admin OR the user themselves — see what entities a user is assigned."""
    s = _require_user()
    if s.get("role") != "admin":
        # Sales can only see their own
        me = _conn().execute("SELECT id FROM campaign_users WHERE email=?", (s["email"],)).fetchone()
        if not me or me["id"] != uid:
            abort(403)
    cur = _conn().execute(
        "SELECT entity_name, assigned_at, assigned_by FROM campaign_assignments "
        "WHERE user_id=? ORDER BY entity_name", (uid,))
    return jsonify([dict(r) for r in cur.fetchall()])


@campaign_bp.route("/users/<int:uid>/assignments", methods=["POST"])
def set_assignments(uid):
    """Admin — replace a user's entity assignments.
    Body: { entities: [name, name, ...] }
    Old assignments are removed; new ones get fresh assigned_at/by.
    """
    s = _require_admin()
    body = request.get_json(silent=True) or {}
    names = body.get("entities") or []
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    conn = _conn()
    conn.execute("DELETE FROM campaign_assignments WHERE user_id=?", (uid,))
    for n in names:
        conn.execute(
            "INSERT OR IGNORE INTO campaign_assignments (user_id, entity_name, assigned_at, assigned_by) "
            "VALUES (?,?,?,?)", (uid, n, now, s["email"]),
        )
    conn.commit()
    return jsonify(ok=True, count=len(names), at=now)


@campaign_bp.route("/me", methods=["GET"])
def me():
    """Return the logged-in user including product + assignment tracking."""
    s = _require_user()
    cur = _conn().execute(
        "SELECT id, email, name, role, product_id, profession, product_assigned_at, product_assigned_by, created_at, last_login "
        "FROM campaign_users WHERE email=?", (s["email"],))
    row = cur.fetchone()
    if not row:
        abort(401)
    # Pull assignment count too
    a = _conn().execute("SELECT COUNT(*) AS n FROM campaign_assignments WHERE user_id=?", (row["id"],)).fetchone()
    out = dict(row)
    out["assigned_entities_count"] = a["n"] if a else 0
    return jsonify(out)


@campaign_bp.route("/users", methods=["GET"])
def list_users():
    """Admin-only — list all staff."""
    _require_admin()
    cur = _conn().execute(
        "SELECT id, email, name, role, product_id, created_at, last_login FROM campaign_users ORDER BY created_at DESC"
    )
    return jsonify([dict(r) for r in cur.fetchall()])


@campaign_bp.route("/users", methods=["POST"])
def create_user():
    """Admin-only — add a new staff member.
    Body: { email, name, password, role?, product_id? }
    """
    _require_admin()
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    name = (body.get("name") or "").strip()
    password = body.get("password") or ""
    role = body.get("role", "sales")
    product_id = body.get("product_id", "solarpro-ghana")
    if not email or not name or not password:
        abort(400, description="email, name, password required")
    if role not in ("admin", "sales", "manager"):
        abort(400, description="role must be admin|sales|manager")
    try:
        _conn().execute(
            "INSERT INTO campaign_users (email, name, role, product_id, password_hash, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (email, name, role, product_id, _hash_password(password), time.strftime("%Y-%m-%d")),
        )
        _conn().commit()
    except sqlite3.IntegrityError:
        abort(409, description="email already exists")
    return jsonify(ok=True)


@campaign_bp.route("/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    """Admin-only — remove a staff member."""
    s = _require_admin()
    # Sanity: don't let admin delete themselves
    cur = _conn().execute("SELECT email FROM campaign_users WHERE id=?", (uid,))
    row = cur.fetchone()
    if not row:
        abort(404)
    if row["email"] == s["email"]:
        abort(400, description="cannot delete yourself")
    _conn().execute("DELETE FROM campaign_users WHERE id=?", (uid,))
    _conn().commit()
    return jsonify(ok=True)


@campaign_bp.route("/users/<int:uid>/reset-password", methods=["POST"])
def reset_password(uid):
    """Admin-only — set a new password for a user.
    Body: { password }"""
    _require_admin()
    body = request.get_json(silent=True) or {}
    pw = body.get("password") or ""
    if not pw:
        abort(400, description="password required")
    _conn().execute("UPDATE campaign_users SET password_hash=? WHERE id=?", (_hash_password(pw), uid))
    _conn().commit()
    return jsonify(ok=True)


def _allowed_entities_for_session(s):
    """Return the set of entity names this session is allowed to see.
    Admin → all. Sales/manager → only entities in campaign_assignments.
    Returns None to mean 'no filter' (admin)."""
    if not s or s.get("role") == "admin":
        return None
    u = _conn().execute("SELECT id FROM campaign_users WHERE email=?", (s["email"],)).fetchone()
    if not u:
        return set()
    rows = _conn().execute("SELECT entity_name FROM campaign_assignments WHERE user_id=?", (u["id"],)).fetchall()
    return {r["entity_name"] for r in rows}


@campaign_bp.route("/entities", methods=["GET"])
def list_entities():
    """Entity master list, filtered to the caller's assignments unless they're admin."""
    s = _session_from_request()
    allowed = _allowed_entities_for_session(s)
    cur = _conn().execute("SELECT payload FROM campaign_entities ORDER BY name")
    items = []
    # Pull assignment metadata for the caller so the UI can render 'assigned by/at'
    uid = None
    if s:
        u = _conn().execute("SELECT id FROM campaign_users WHERE email=?", (s["email"],)).fetchone()
        uid = u["id"] if u else None
    meta = {}
    if uid:
        for r in _conn().execute("SELECT entity_name, assigned_at, assigned_by FROM campaign_assignments WHERE user_id=?", (uid,)):
            meta[r["entity_name"]] = {"assigned_at": r["assigned_at"], "assigned_by": r["assigned_by"]}
    for r in cur.fetchall():
        e = json.loads(r["payload"])
        if allowed is not None and e["name"] not in allowed:
            continue
        if e["name"] in meta:
            e["_assigned_at"] = meta[e["name"]]["assigned_at"]
            e["_assigned_by"] = meta[e["name"]]["assigned_by"]
        items.append(e)
    return jsonify({"generated": time.strftime("%Y-%m-%d"), "entities": items})


@campaign_bp.route("/state", methods=["GET"])
def get_state():
    """One snapshot — pipeline + feedback, filtered to caller's assignments."""
    s = _session_from_request()
    allowed = _allowed_entities_for_session(s)
    cur = _conn().execute("SELECT * FROM campaign_pipeline")
    pipeline = {}
    for r in cur.fetchall():
        if allowed is not None and r["entity_name"] not in allowed:
            continue
        pipeline[r["entity_name"]] = {
            "status": r["status"], "notes": r["notes"],
            "next_action_date": r["next_action_date"],
            "literature_sent": json.loads(r["literature_sent"] or "[]"),
            "last_updated": r["last_updated"],
            "last_updated_by": r["last_updated_by"],
        }
    cur = _conn().execute("SELECT * FROM campaign_feedback ORDER BY id DESC")
    feedback = {}
    for r in cur.fetchall():
        if allowed is not None and r["entity_name"] not in allowed:
            continue
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
