# patch_form_expired_csrf.py
#
# THE BUG THE OWNER REPORTED
#   "if user click create new program it sends user to hiccup page, the server say owner
#    is not authorised to access some resources"
#
# WHAT IT ACTUALLY WAS -- PROVED, NOT GUESSED
#   Two theories were tested against the live database and BOTH were refuted:
#     * "the owner holds no programme.create"  -> refuted. `Diag Enterprise Permissions`
#       shows every enterprise user holds it, and the MOE owner holds all 11 roles.
#     * "create_programme rejects it later"    -> refuted. It has one authorisation check
#       and it is the same one the route already passed.
#   Then the live repro (`Repro Enterprise 403`) settled it:
#     GET  /enterprise/programmes/new           -> 200   (in BOTH tenants)
#     POST with a STALE _csrf token             -> 403   <- the owner's page
#
#   The owner was NEVER unauthorised. Their form's CSRF token no longer matched their
#   session, and csrf_protect() (web_app.py:274) answered with a bare abort(403). Werkzeug's
#   default 403 description is "You don't have the permission to access the requested
#   resource" -- which the friendly error handler then printed at them. The app accused the
#   owner of a permissions problem it had invented.
#
# WHY THE TOKEN GOES STALE
#   /auth/login and /auth/callback both call session.clear() (app/auth/oidc_routes.py:316,
#   :539). Any re-authentication -- signing in again, a second tab, an expired Keycloak
#   session on a free-tier instance -- rotates the session and therefore _csrf. A form that
#   was rendered BEFORE that point still carries the old token. Nothing is wrong with the
#   user, their roles, or their data.
#
# AND IT WAS A TRAP WITH NO EXIT
#   error.html auto-redirects to document.referrer after 5s (error.html:132) and offers a
#   "Go Back" button -- both of which return the user to the CACHED form, still carrying the
#   SAME dead token. Resubmitting 403s again. The owner could not get out of it by doing the
#   obvious thing, which is exactly why this reads as "the module is broken".
#
# THE FIX
#   1. A CSRF failure is no longer an accusation. It raises FormExpired -- still a 403 to
#      any machine reading the status code, but carrying an honest description.
#   2. A dedicated handler renders a page that SAYS what happened ("you signed in again;
#      nothing was lost") and gives a button that re-opens the form FRESH (a GET of the same
#      path), which is the only action that actually works. No referrer bounce.
#   3. XHR/API callers get JSON with an error code they can branch on, instead of an HTML
#      error page landing inside a fetch().
#
# It does NOT weaken CSRF: a request with a bad token is still rejected, still 403, still
# writes nothing. Only the explanation and the way out change.
#
# web_app.py is CRLF + mojibake -- byte replacement only (CLAUDE.md).

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()
before = len(data)


def apply(old: bytes, new: bytes, label: str) -> None:
    global data
    if new in data:
        print(f"SKIP  {label} -- already applied")
        return
    if old not in data:
        raise SystemExit(f"FAIL  {label} -- anchor not found")
    if data.count(old) != 1:
        raise SystemExit(f"FAIL  {label} -- anchor matches {data.count(old)}x, need exactly 1")
    data = data.replace(old, new, 1)
    print(f"OK    {label}")


OLD = (
    b'def csrf_protect():\r\n'
    b'    """Call at top of POST handlers that mutate state."""\r\n'
    b'    if request.method == "POST":\r\n'
    b'        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")\r\n'
    b'        if not token or token != session.get("_csrf"):\r\n'
    b'            abort(403)\r\n'
)

NEW = (
    b'class FormExpired(_WerkzeugForbidden):\r\n'
    b'    """The submitted CSRF token does not match the session.\r\n'
    b'\r\n'
    b'    THIS IS NOT AN AUTHORISATION FAILURE, and saying that it is put the owner on a page\r\n'
    b'    telling them they were "not authorised to access some resources" when all they had\r\n'
    b'    done was press Register on a form that had been open a while.\r\n'
    b'\r\n'
    b'    /auth/login and /auth/callback both call session.clear() (app/auth/oidc_routes.py),\r\n'
    b'    so ANY re-authentication rotates the session and with it _csrf. A form rendered\r\n'
    b'    before that moment still carries the old token. The user\'s roles, permissions and\r\n'
    b'    data are all fine; the page in front of them is simply out of date.\r\n'
    b'\r\n'
    b'    Still a 403 -- the request is still refused and still writes nothing. Only the\r\n'
    b'    explanation changes, and the user is given the one action that actually works:\r\n'
    b'    re-open the form, which issues a fresh token.\r\n'
    b'    """\r\n'
    b'\r\n'
    b'    description = ("Your form expired. This happens when you sign in again, or when "\r\n'
    b'                   "the page has been open for a while. Nothing was saved and nothing "\r\n'
    b'                   "was lost -- please re-open the form and submit it once more.")\r\n'
    b'\r\n'
    b'\r\n'
    b'def csrf_protect():\r\n'
    b'    """Call at top of POST handlers that mutate state.\r\n'
    b'\r\n'
    b'    Raises FormExpired (a 403) when the token is missing or stale. Do NOT downgrade this\r\n'
    b'    to a pass-through: a bad token is still refused. See patch_form_expired_csrf.py.\r\n'
    b'    """\r\n'
    b'    if request.method == "POST":\r\n'
    b'        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")\r\n'
    b'        if not token or token != session.get("_csrf"):\r\n'
    b'            raise FormExpired()\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.errorhandler(FormExpired)\r\n'
    b'def err_form_expired(e):\r\n'
    b'    """Tell the truth about a stale form, and give the user the way out.\r\n'
    b'\r\n'
    b'    The generic error page auto-redirects to document.referrer and offers "Go Back" --\r\n'
    b'    both of which return the browser to the CACHED form carrying the SAME dead token, so\r\n'
    b'    resubmitting 403s again. That is a loop with no exit. `retry_url` gives the page a\r\n'
    b'    button that re-GETs this same path, which is what mints a fresh token.\r\n'
    b'    """\r\n'
    b'    try:\r\n'
    b'        app.logger.info("FORM_EXPIRED %s %s (stale or missing _csrf)",\r\n'
    b'                        request.method, request.path)\r\n'
    b'    except Exception:\r\n'
    b'        pass\r\n'
    b'    # An XHR caller (the helpline chat posts X-CSRF-Token) must not be handed an HTML\r\n'
    b'    # error page inside its fetch(). Give it something it can branch on.\r\n'
    b'    wants_json = (request.path.startswith("/api/")\r\n'
    b'                  or request.headers.get("X-Requested-With") == "XMLHttpRequest"\r\n'
    b'                  or request.accept_mimetypes.best == "application/json")\r\n'
    b'    if wants_json:\r\n'
    b'        return jsonify(error="FORM_EXPIRED", message=str(e.description)), 403\r\n'
    b'    return render_template("error.html", code=403,\r\n'
    b'        title="Your form expired",\r\n'
    b'        message=str(e.description),\r\n'
    b'        retry_url=request.path,\r\n'
    b'        retry_label="Re-open the form"), 403\r\n'
)

apply(OLD, NEW, "FormExpired + honest CSRF handler")

# The exception subclasses werkzeug's Forbidden so that everything which already treats a
# 403 as a 403 keeps working. Imported under an alias so the name `Forbidden` stays free.
IMPORT_OLD = b'from werkzeug.security import generate_password_hash, check_password_hash\r\n'
IMPORT_NEW = (
    b'from werkzeug.security import generate_password_hash, check_password_hash\r\n'
    b'from werkzeug.exceptions import Forbidden as _WerkzeugForbidden\r\n'
)
apply(IMPORT_OLD, IMPORT_NEW, "import werkzeug Forbidden")

TARGET.write_bytes(data)
print(f"\nwrote web_app.py  ({before} -> {len(data)} bytes, +{len(data) - before})")
