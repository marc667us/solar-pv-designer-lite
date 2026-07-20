"""
Byte-level patch: /admin/users/refresh-online gets a CSRF check.

THE GAP
    POST /admin/users/refresh-online carried no auth decorator and no CSRF
    check (web_app.py:29067). It was introduced undecorated in a8ed356,
    alongside the online-dot UI -- an original omission, not a regression
    (verified with `git log -S`).

SEVERITY: LOW, and deliberately stated as such
    The handler is self-scoped: it updates only the CALLING session's own
    users.last_seen, resolved from session["user_id"] or the Keycloak
    username/email already in the session -- never from request input.
    Anonymous callers are redirected to /login. So there is no privilege
    escalation and no arbitrary-user write. Codex independently agreed. The
    real defect is a state-changing POST with no CSRF token check.

WHY THE CSRF CHECK IS SAFE TO ADD
    templates/admin_users.html:95 ALREADY submits a `_csrf` hidden field in
    this form, so csrf_protect() rejects only forgeries, never the real
    button. Verified before writing the patch, not assumed.

WHY @admin_required IS **NOT** ADDED -- this was tried and REVERTED
    admin_required (web_app.py:6594) begins:

        if "user_id" not in session:
            return redirect(url_for("login"))

    But this route exists PRECISELY to serve the case where
    session["user_id"] is empty. Its own docstring records the 2026-06-25
    SOC 2 M1.1 fallout: a Keycloak user whose preferred_username does not
    resolve to a SOLAR users row by exact case ends up with no user_id, and
    the handler deliberately falls back to the KC username/email so the
    refresh still works.

    Adding @admin_required would therefore redirect exactly the users this
    route was written for, turning its KC-fallback branch into dead code --
    a real regression dressed up as hardening. The route keeps its own
    self-scoped guard instead.

    Consequence: the route stays in tests/route_auth_allowlist.txt, now
    tagged `reason=in-body-session` with a ref to the guard, rather than
    being silently marked "fixed".

INPUT : web_app.py in the CWD
OUTPUT: web_app.py rewritten in place. Idempotent.
"""

import sys

PATH = "web_app.py"

# Add csrf_protect() as the first statement after the docstring. Anchored on
# the docstring's closing line plus the first statement so the match is
# unambiguous.
OLD = (
    b'    / email so the explicit refresh still works."""\r\n'
    b'    uid = session.get("user_id")\r\n'
)
NEW = (
    b'    / email so the explicit refresh still works."""\r\n'
    b'    # State-changing POST on an /admin/ path: reject a forged cross-site\r\n'
    b'    # submission. templates/admin_users.html already posts the _csrf field,\r\n'
    b'    # so this rejects only forgeries, never the real button.\r\n'
    b'    #\r\n'
    b'    # NOT @admin_required: that decorator redirects when session["user_id"]\r\n'
    b'    # is missing, which is the exact KC case this handler exists to serve\r\n'
    b'    # (see the docstring above). It would make the fallback dead code.\r\n'
    b'    csrf_protect()\r\n'
    b'    uid = session.get("user_id")\r\n'
)


def main() -> int:
    data = open(PATH, "rb").read()
    if NEW in data:
        print("SKIP: already applied")
        return 0
    count = data.count(OLD)
    if count != 1:
        print(f"FAIL: expected exactly 1 match, found {count}")
        return 1
    open(PATH, "wb").write(data.replace(OLD, NEW))
    print("OK: csrf_protect() added to admin_users_refresh_online")
    return 0


if __name__ == "__main__":
    sys.exit(main())
