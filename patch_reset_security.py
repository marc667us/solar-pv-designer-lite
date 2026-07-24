# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# Fix the 3 security findings Codex raised on the re-enabled legacy reset flow:
#  1. Email ENUMERATION + reset-URL LEAK: forgot_password() showed a different
#     flash when the email existed vs not, and on send-failure it flashed the
#     live reset URL into the requester's browser (account-takeover risk). Now:
#     ONE generic message regardless of existence/outcome; a send failure is
#     logged server-side only, never surfaced.
#  2. reset_password() had NO rate limit -> add @limiter.limit("10 per hour").
#
# Asserts each target matches exactly once; the file must byte-compile.

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

# ── 1. enumeration + URL leak ────────────────────────────────────────────────
OLD1 = (
    b'                if ok:\r\n'
    b'                    flash(\r\n'
    b'                        "Reset link sent! Check your inbox (and spam folder).", "success")\r\n'
    b'                else:\r\n'
    b'                    # SMTP not configured \xe2\x80\x94 show link directly so admins can share it securely\r\n'
    b'                    flash(\r\n'
    b'                        f"SMTP not configured on the server. "\r\n'
    b'                        f"Admin: share this link securely with the user \xc3\xa2\xe2\x80\xa0\' {reset_url}", "warning")\r\n'
    b'            else:\r\n'
    b'                # Always show the same message to avoid email enumeration\r\n'
    b'                flash(\r\n'
    b'                    "If that email address is registered, a reset link has been sent.", "info")'
)
NEW1 = (
    b'                if not ok:\r\n'
    b'                    # Do NOT expose the reset URL to the requester (account-\r\n'
    b'                    # takeover risk); log server-side only. The same generic\r\n'
    b'                    # message is shown to everyone below (Codex).\r\n'
    b'                    try:\r\n'
    b'                        app.logger.error("password reset email send failed uid=%s", user["id"])\r\n'
    b'                    except Exception:\r\n'
    b'                        pass\r\n'
    b'        # Same message whether or not the email exists / the send succeeded --\r\n'
    b'        # never leak account existence or the reset URL (Codex).\r\n'
    b'        flash("If that email address is registered, a reset link has been sent. "\r\n'
    b'              "Check your inbox and spam folder.", "info")'
)
assert data.count(OLD1) == 1, "forgot_password flash block not unique/found"
data = data.replace(OLD1, NEW1)

# ── 2. rate-limit reset_password ─────────────────────────────────────────────
OLD2 = b'@app.route("/reset-password/<token>", methods=["GET", "POST"])\r\ndef reset_password(token):'
NEW2 = (b'@app.route("/reset-password/<token>", methods=["GET", "POST"])\r\n'
        b'@limiter.limit("10 per hour")\r\n'
        b'def reset_password(token):')
assert data.count(OLD2) == 1, "reset_password route not unique/found"
data = data.replace(OLD2, NEW2)

open(PATH, "wb").write(data)
py_compile.compile(PATH, doraise=True)
print("OK: fixed enumeration + URL leak + rate-limited reset_password; byte-compiles clean.")
