"""
Phase 7 patch: byte-patch web_app.py so GET /login redirects to /auth/login
when Keycloak is enabled and ?legacy=1 is not present.

What it does:
  Inserts a small guard at the top of `def login():`. POST handling is
  unchanged. GET handling is unchanged unless KEYCLOAK_ENABLED is truthy
  AND the legacy=1 escape hatch is missing -- in which case the request
  is bounced to the OIDC blueprint endpoint `oidc.auth_login`, preserving
  the original `?next=` query param.

Input:  the working tree's web_app.py (CRLF, mojibake-tolerated).
Output: web_app.py overwritten in place. Prints "patched" on success or
  "already patched" if the marker is already present (idempotent re-runs).

Per CLAUDE.md rule: never use the Edit tool on web_app.py because it
introduces curly-quote mojibake -- byte-patch is the only safe channel.
"""

from pathlib import Path

# Absolute path so this script can be run from any cwd.
APP = Path(__file__).parent / "web_app.py"

# Anchor: the unique function header + first line of POST guard.
# Verified unique by grep before scripting.
OLD = b'def login():\r\n    if request.method == "POST":'

# Replacement: same anchor lines with a Keycloak guard inserted between
# them. The guard reads KEYCLOAK_ENABLED at request time so it tracks
# the live env without restart; the legacy=1 escape hatch falls through
# to the existing auth.html form so marc667us recovery still works.
NEW = (
    b'def login():\r\n'
    b'    # Phase 7 Keycloak guard: when KEYCLOAK_ENABLED is truthy and the\r\n'
    b'    # marc667us escape hatch (?legacy=1) is absent, bounce GET /login\r\n'
    b'    # to the OIDC blueprint so users land on the Keycloak login page.\r\n'
    b'    # POST handling is untouched so the legacy form keeps working.\r\n'
    b'    if request.method == "GET" \\\r\n'
    b'        and os.environ.get("KEYCLOAK_ENABLED", "").lower() in ("1", "true", "yes", "on") \\\r\n'
    b'        and request.args.get("legacy") != "1":\r\n'
    b'        _kc_next = request.args.get("next")\r\n'
    b'        if _kc_next:\r\n'
    b'            return redirect(url_for("oidc.auth_login", next=_kc_next))\r\n'
    b'        return redirect(url_for("oidc.auth_login"))\r\n'
    b'    if request.method == "POST":'
)

# Idempotence marker -- if this comment is already present, skip.
MARKER = b'Phase 7 Keycloak guard:'


def main() -> None:
    data = APP.read_bytes()
    if MARKER in data:
        print("already patched")
        return
    n = data.count(OLD)
    assert n == 1, f"expected exactly 1 anchor match, found {n}"
    data = data.replace(OLD, NEW, 1)
    APP.write_bytes(data)
    print("patched")


if __name__ == "__main__":
    main()
