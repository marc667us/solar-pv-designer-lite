"""
Tier 2-4 prerequisite — add JSON-returning admin API endpoints so the
agent-triage workflow can consume per-item records (ID + body) cleanly
instead of scraping the HTML admin pages.

Three new routes, all @admin_required:

  GET /admin/api/feedback      — beta_feedback rows as JSON list
  GET /admin/api/tickets       — tickets rows as JSON list
  GET /admin/api/beta_signups  — beta_signups rows as JSON list

Each returns the most-recent-first slice up to a `limit` query param
(default 50, max 200). Optional `?since=<id>` filters to id > since
for monotonic agent polling.

Byte-patch needed (CRLF + mojibake constraint per CLAUDE.md). Anchor
is the existing `/admin/feedback` route declaration; insert sits
immediately before it.
"""
from __future__ import annotations
import os, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web_app.py")

ANCHOR = (
    b'@app.route("/admin/feedback")\r\n'
    b'@admin_required\r\n'
    b'def admin_feedback():\r\n'
)

NEW_ROUTES = (
    b'# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 Tier 2-4 agent-triage JSON API \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\r\n'
    b'# JSON-returning siblings to /admin/{feedback,tickets,beta} so the\r\n'
    b'# hourly agent-triage workflow (.github/workflows/agent-triage.yml)\r\n'
    b'# can fetch per-item records (id + body + submitter) without scraping\r\n'
    b'# the Jinja-rendered admin pages.\r\n'
    b'\r\n'
    b'def _rows_to_json(rows):\r\n'
    b'    """Convert sqlite3.Row / DictCursor rows to plain dicts. Strips\r\n'
    b'    nothing \xe2\x80\x94 callers can drop fields per their need (e.g. the\r\n'
    b'    agent only needs id + message + email)."""\r\n'
    b'    out = []\r\n'
    b'    for r in rows:\r\n'
    b'        try:\r\n'
    b'            out.append({k: r[k] for k in r.keys()})\r\n'
    b'        except Exception:\r\n'
    b'            # Fall back to positional access if .keys() unavailable.\r\n'
    b'            out.append(dict(r) if hasattr(r, "keys") else list(r))\r\n'
    b'    return out\r\n'
    b'\r\n'
    b'def _limit_since(default=50, max_=200):\r\n'
    b'    """Parse `?limit=N&since=ID` query params. Server-side clamps\r\n'
    b'    keep an over-eager agent from pulling 10k rows in one call."""\r\n'
    b'    try:\r\n'
    b'        limit = int(request.args.get("limit", default))\r\n'
    b'    except (TypeError, ValueError):\r\n'
    b'        limit = default\r\n'
    b'    limit = max(1, min(max_, limit))\r\n'
    b'    try:\r\n'
    b'        since = int(request.args.get("since", "0"))\r\n'
    b'    except (TypeError, ValueError):\r\n'
    b'        since = 0\r\n'
    b'    return limit, since\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/admin/api/feedback")\r\n'
    b'@admin_required\r\n'
    b'def admin_api_feedback():\r\n'
    b'    limit, since = _limit_since()\r\n'
    b'    with get_db() as c:\r\n'
    b'        rows = c.execute(\r\n'
    b'            "SELECT * FROM beta_feedback WHERE id > ? ORDER BY id DESC LIMIT ?",\r\n'
    b'            (since, limit),\r\n'
    b'        ).fetchall()\r\n'
    b'    return jsonify({"ok": True, "items": _rows_to_json(rows),\r\n'
    b'                    "count": len(rows), "since": since, "limit": limit})\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/admin/api/tickets")\r\n'
    b'@admin_required\r\n'
    b'def admin_api_tickets():\r\n'
    b'    limit, since = _limit_since()\r\n'
    b'    with get_db() as c:\r\n'
    b'        rows = c.execute(\r\n'
    b'            "SELECT t.*, u.email AS submitter_email, u.username AS submitter_username "\r\n'
    b'            "FROM tickets t LEFT JOIN users u ON t.user_id = u.id "\r\n'
    b'            "WHERE t.id > ? ORDER BY t.id DESC LIMIT ?",\r\n'
    b'            (since, limit),\r\n'
    b'        ).fetchall()\r\n'
    b'    return jsonify({"ok": True, "items": _rows_to_json(rows),\r\n'
    b'                    "count": len(rows), "since": since, "limit": limit})\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/admin/api/beta_signups")\r\n'
    b'@admin_required\r\n'
    b'def admin_api_beta_signups():\r\n'
    b'    limit, since = _limit_since()\r\n'
    b'    with get_db() as c:\r\n'
    b'        rows = c.execute(\r\n'
    b'            "SELECT * FROM beta_signups WHERE id > ? ORDER BY id DESC LIMIT ?",\r\n'
    b'            (since, limit),\r\n'
    b'        ).fetchall()\r\n'
    b'    return jsonify({"ok": True, "items": _rows_to_json(rows),\r\n'
    b'                    "count": len(rows), "since": since, "limit": limit})\r\n'
    b'\r\n'
    b'\r\n'
)


def main() -> int:
    data = open(TARGET, "rb").read()
    n = data.count(ANCHOR)
    if n != 1:
        print(f"ERROR: anchor matched {n}x (expected 1)", file=sys.stderr)
        return 2
    if b"/admin/api/feedback" in data:
        print("WARN: JSON endpoints already present \xe2\x80\x94 bailing idempotently")
        return 0
    data = data.replace(ANCHOR, NEW_ROUTES + ANCHOR, 1)
    open(TARGET, "wb").write(data)
    print(f"OK wrote {len(data):,} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
