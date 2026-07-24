# Byte-level patch (web_app.py is CRLF + mojibake -- never Edit directly).
#
# Re-enable the LEGACY password-reset flow when Keycloak is OFF.
#
# On 2026-06-25 (SOC 2 M1.1) forgot_password() and reset_password() were
# neutered to always redirect to Keycloak, leaving the real email-token flow as
# dead code. But KEYCLOAK_ENABLED is OFF on live -- so a legacy user (incl. the
# owner marc667us) who forgets their password has NO way to reset it:
# /forgot-password just bounces to /auth/login -> /login?legacy=1, no email is
# ever sent. That is a single point of total lockout.
#
# Fix: gate the KC-redirect on KEYCLOAK_ENABLED (same env-aware anti-lockout
# rule web_app.py login() uses). When KC is on, KC still owns reset; when off,
# the legacy email-token flow below serves again. The block is identical in both
# handlers, so this patches BOTH. All the flow's dependencies are intact
# (password_reset_tokens table, _send_system_email, forgot_password.html /
# reset_password.html).

import py_compile

PATH = "web_app.py"
data = open(PATH, "rb").read()

OLD = (
    b'# SOC 2 M1.1 (2026-06-25): Keycloak owns password reset. Always redirect.\r\n'
    b'    flash("Password reset is now managed by the SolarPro identity service. '
    b'Use the \\"Forgot password?\\" link on the login page.", "info")\r\n'
    b'    return redirect(url_for("oidc.auth_login"))'
)
NEW = (
    b'# KC owns reset when enabled; when it is OFF the legacy email-token flow\r\n'
    b'    # below serves again -- otherwise a legacy user who forgets their password\r\n'
    b'    # has NO way to reset it (single point of lockout). Same env-aware rule as login().\r\n'
    b'    if os.environ.get("KEYCLOAK_ENABLED", "").strip().lower() in ("1", "true", "yes"):\r\n'
    b'        flash("Password reset is now managed by the SolarPro identity service. '
    b'Use the \\"Forgot password?\\" link on the login page.", "info")\r\n'
    b'        return redirect(url_for("oidc.auth_login"))'
)

n = data.count(OLD)
assert n == 2, f"expected 2 identical neuter blocks (forgot + reset), found {n}"
data = data.replace(OLD, NEW)
open(PATH, "wb").write(data)
py_compile.compile(PATH, doraise=True)
print("OK: legacy password-reset re-enabled when KC is off (both handlers); byte-compiles clean.")
