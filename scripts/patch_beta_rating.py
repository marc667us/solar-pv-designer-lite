"""
Beta rating feature — add 3-axis evaluator scores (perf / creativity / value).

Two byte-patches into web_app.py:

  1. init_db ALTER block: add 3 INTEGER columns to beta_feedback so existing
     SQLite installs pick them up via the standard try/except wrapped
     ALTER. Mirror schema migration is updated separately.

  2. New /rate routes (GET form + POST submit) right after /feedback POST.
     The submit writes a row to beta_feedback with type='rating' and the
     three score columns populated. Reuses _send_email for the admin
     notification — same plumbing as /feedback.

Byte-patch needed because web_app.py is CRLF + mojibake (Edit corrupts
quotes per CLAUDE.md).
"""
from __future__ import annotations
import os, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web_app.py")


# ── Patch 1 — extend the cumulative ALTER block ────────────────────────
# Anchor: the closing `pass` of the date_format/time_format SMTP-settings
# block at lines 580-581 (right before the seed phase comment). Inserting
# a new for-loop with the rating columns keeps the existing additive
# pattern.
ALTER_ANCHOR = b'''            try:
                with get_db() as c:
                    c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {defval}")
            except Exception:
                pass

    # \xe2\x94\x80\xe2\x94\x80 Seed phase \xe2\x80\x94 runs on BOTH backends \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80'''

# We don't need to match the unicode dash exactly — instead match a shorter
# anchor that's still unique.
# Anchor up to and including the blank line. Insert sits BEFORE the
# "    # ── Seed phase" comment so we don't have to splice the unicode
# box-drawing characters into a Python bytes literal.
ALTER_ANCHOR_SHORT = (
    b'            try:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT {defval}")\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'\r\n'
)

# Body to insert RIGHT BEFORE the "    # ── Seed phase" line. Note the
# leading 8 spaces — we're inside the `if not _is_postgres:` block which
# already runs the previous ALTER loops at this indentation.
ALTER_INSERT = (
    b'        # Migrate: beta_feedback rating columns (3 axes for evaluators).\r\n'
    b'        # Wrapped in try/except per column so reruns are idempotent on SQLite.\r\n'
    b'        for col in ["perf_score", "creativity_score", "value_score"]:\r\n'
    b'            try:\r\n'
    b'                with get_db() as c:\r\n'
    b'                    c.execute(f"ALTER TABLE beta_feedback ADD COLUMN {col} INTEGER")\r\n'
    b'            except Exception:\r\n'
    b'                pass\r\n'
    b'\r\n'
)


# ── Patch 2 — add /rate GET + POST routes ──────────────────────────────
# Anchor: the closing of /feedback POST, then a blank line, then the next
# route decorator. We insert before the next `@app.route` line that comes
# after /feedback's return.
FEEDBACK_END_ANCHOR = (
    b'    return jsonify({"ok": True, "msg": "Feedback submitted. Thank you!"})\r\n'
    b'\r\n'
    b'\r\n'
)

RATE_ROUTES = (
    b'@app.route("/rate", methods=["GET"])\r\n'
    b'@login_required\r\n'
    b'def rate_form():\r\n'
    b'    """GET the beta rating form. The submit POSTs to /rate which\r\n'
    b'    writes to beta_feedback with type=\'rating\' and the three score\r\n'
    b'    columns populated."""\r\n'
    b'    return render_template("rate.html", user=current_user())\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/rate", methods=["POST"])\r\n'
    b'@login_required\r\n'
    b'def submit_rating():\r\n'
    b'    """Persist a 3-axis beta rating into beta_feedback. The three\r\n'
    b'    scores are clamped to 1..5 server-side so the slider UI cannot\r\n'
    b'    bypass the contract. Optional comment lives in the message column."""\r\n'
    b'    csrf_protect()\r\n'
    b'    def _clamp(name):\r\n'
    b'        try:\r\n'
    b'            v = int(request.form.get(name, "0"))\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            v = 0\r\n'
    b'        return max(1, min(5, v))\r\n'
    b'    perf       = _clamp("perf_score")\r\n'
    b'    creativity = _clamp("creativity_score")\r\n'
    b'    value      = _clamp("value_score")\r\n'
    b'    comment    = (request.form.get("message") or "").strip()\r\n'
    b'    page       = (request.form.get("page") or "").strip()\r\n'
    b'    if not any([perf, creativity, value]):\r\n'
    b'        return jsonify({"ok": False, "msg": "Pick at least one score"}), 400\r\n'
    b'    with get_db() as c:\r\n'
    b'        u = c.execute("SELECT username, email FROM users WHERE id=?",\r\n'
    b'                      (session["user_id"],)).fetchone()\r\n'
    b'    username = u["username"] if u else ""\r\n'
    b'    uemail   = u["email"]    if u else ""\r\n'
    b'    # Compose a short summary line into the message column too, so the\r\n'
    b'    # admin /admin/feedback view shows the rating context at a glance.\r\n'
    b'    summary = f"Performance={perf}/5  Creativity={creativity}/5  Value={value}/5"\r\n'
    b'    full_msg = summary + ("\\n\\n" + comment if comment else "")\r\n'
    b'    with get_db() as c:\r\n'
    b'        c.execute(\r\n'
    b'            "INSERT INTO beta_feedback (user_id, username, email, type, message, "\r\n'
    b'            "page, perf_score, creativity_score, value_score) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?,?,?)",\r\n'
    b'            (session["user_id"], username, uemail, "rating", full_msg, page,\r\n'
    b'             perf, creativity, value))\r\n'
    b'    _send_email(\r\n'
    b'        EMAIL_SUPPORT,\r\n'
    b'        "[RATING] " + summary + " from " + username,\r\n'
    b'        "<h3>Beta Rating</h3><p><b>From:</b> " + username + " (" + uemail + ")<br>"\r\n'
    b'        "<b>Page:</b> " + (page or "N/A") + "</p>"\r\n'
    b'        "<table style=\\"border-collapse:collapse\\"><tr><td style=\\"padding:4px 12px\\"><b>Performance</b></td><td style=\\"padding:4px 12px\\">"\r\n'
    b'        + str(perf) + "/5</td></tr><tr><td style=\\"padding:4px 12px\\"><b>Creativity</b></td><td style=\\"padding:4px 12px\\">"\r\n'
    b'        + str(creativity) + "/5</td></tr><tr><td style=\\"padding:4px 12px\\"><b>Value</b></td><td style=\\"padding:4px 12px\\">"\r\n'
    b'        + str(value) + "/5</td></tr></table>"\r\n'
    b'        + ("<p><b>Comment:</b><br>" + comment + "</p>" if comment else "")\r\n'
    b'        + "<p><a href=\\"https://solarpro.aiappinvent.com/admin/feedback\\">View ratings</a></p>",\r\n'
    b'        from_addr=EMAIL_SUPPORT)\r\n'
    b'    return jsonify({"ok": True, "msg": "Rating submitted. Thank you!"})\r\n'
    b'\r\n'
    b'\r\n'
)


def main() -> int:
    data = open(TARGET, "rb").read()

    # ---- Patch 1 ----
    n = data.count(ALTER_ANCHOR_SHORT)
    if n != 1:
        print(f"ERROR: ALTER anchor matched {n}x (expected 1)", file=sys.stderr)
        return 2
    if b"ALTER TABLE beta_feedback ADD COLUMN" in data:
        print("WARN: beta_feedback ALTERs already present — skipping patch 1")
    else:
        # Replace `ANCHOR` with `ANCHOR + INSERT`. The original file then
        # continues with `    # ── Seed phase ...` after our insert.
        data = data.replace(ALTER_ANCHOR_SHORT, ALTER_ANCHOR_SHORT + ALTER_INSERT, 1)

    # ---- Patch 2 ----
    n = data.count(FEEDBACK_END_ANCHOR)
    if n != 1:
        print(f"ERROR: /feedback end anchor matched {n}x (expected 1)", file=sys.stderr)
        return 3
    if b'@app.route("/rate"' in data:
        print("WARN: /rate route already present — skipping patch 2")
    else:
        data = data.replace(FEEDBACK_END_ANCHOR, FEEDBACK_END_ANCHOR + RATE_ROUTES, 1)

    open(TARGET, "wb").write(data)
    print(f"OK wrote {len(data):,} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
