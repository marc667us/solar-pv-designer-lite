"""
Phase 7 patch: byte-patch web_app.py so GET /register redirects to
/auth/register when Keycloak is enabled and ?legacy=1 is absent.

Mirror of patch_login_kc_redirect.py. POST handling is untouched so
the marc667us emergency-form path still works via ?legacy=1.

Input:  web_app.py (CRLF, mojibake-tolerated).
Output: web_app.py overwritten in place. Prints "patched" on success
        or "already patched" if the idempotence marker is present.
"""

from pathlib import Path

APP = Path(__file__).parent / "web_app.py"

OLD = b'def register():\r\n    if request.method == "POST":'

NEW = (
    b'def register():\r\n'
    b'    # Phase 7 Keycloak guard: when KEYCLOAK_ENABLED is truthy and the\r\n'
    b'    # marc667us escape hatch (?legacy=1) is absent, bounce GET /register\r\n'
    b'    # to the OIDC blueprint so users land on the Keycloak registration\r\n'
    b'    # page. POST handling is untouched so the legacy form keeps working.\r\n'
    b'    if request.method == "GET" \\\r\n'
    b'        and os.environ.get("KEYCLOAK_ENABLED", "").lower() in ("1", "true", "yes", "on") \\\r\n'
    b'        and request.args.get("legacy") != "1":\r\n'
    b'        _kc_next = request.args.get("next")\r\n'
    b'        if _kc_next:\r\n'
    b'            return redirect(url_for("oidc.auth_register", next=_kc_next))\r\n'
    b'        return redirect(url_for("oidc.auth_register"))\r\n'
    b'    if request.method == "POST":'
)

MARKER = b'Phase 7 Keycloak guard: when KEYCLOAK_ENABLED is truthy and the\r\n    # marc667us escape hatch (?legacy=1) is absent, bounce GET /register'


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
