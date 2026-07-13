"""A stale CSRF token is still REFUSED -- but it is not an accusation.

WHY THIS TEST EXISTS
--------------------
The owner reported that pressing "Register" on the create-programme form sent them to an
error page saying they were "not authorised to access some resources". They were not: they
held every required role (proved against live data), and the GET rendered 200. Their form's
CSRF token had simply gone stale -- /auth/login and /auth/callback both call session.clear(),
so any re-authentication rotates _csrf -- and csrf_protect() answered a stale token with a
bare abort(403), whose default Werkzeug description is a permissions accusation.

There are TWO things to protect here and they pull in opposite directions, which is exactly
why they are pinned together in one file:

  1. SECURITY: a request with a missing or wrong token must still be REFUSED. It would be
     very easy to "fix the owner's bug" by making csrf_protect lenient. That would be a
     CSRF vulnerability, not a fix.

  2. HONESTY: the refusal must not claim the user lacks permission, and it must offer a way
     out. The old page auto-redirected to document.referrer -- the cached form, carrying the
     same dead token -- so the obvious next click 403'd again. A loop with no exit.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
    os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")
    os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    os.environ.pop("DATABASE_URL", None)          # SQLite, not Postgres
    web_app = importlib.import_module("web_app")
    web_app.app.config["TESTING"] = True
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    return web_app.app


def _post_with_token(app, token: str | None):
    """POST to a CSRF-protected route with the given token (None = omit it entirely)."""
    with app.test_client() as client:
        # Establish a session that has its OWN _csrf, different from whatever we submit.
        with client.session_transaction() as s:
            s["_csrf"] = "the-real-token-for-this-session"
            s["user_id"] = 1
        # A route whose FIRST act is csrf_protect(), with no other precondition that could
        # abort first. (The enterprise routes call _require_module() ahead of it, which 404s
        # while the feature flag is dark -- so they would never reach the CSRF check here.)
        data = {}
        if token is not None:
            data["_csrf"] = token
        return client.post("/newsletter/dismiss-prompt", data=data,
                           follow_redirects=False)


def test_stale_token_is_still_refused(app):
    """SECURITY: the whole point of CSRF is that a wrong token does not get through."""
    r = _post_with_token(app, "a-token-from-a-dead-session")
    assert r.status_code == 403, (
        "a stale CSRF token MUST still be refused -- if this is not 403, the 'friendly "
        "error' change has turned into a CSRF vulnerability"
    )


def test_missing_token_is_still_refused(app):
    r = _post_with_token(app, None)
    assert r.status_code == 403, "a POST with no CSRF token at all must be refused"


def test_the_refusal_does_not_accuse_the_user(app):
    """HONESTY: this is the sentence that sent the owner looking for a permissions bug.

    Werkzeug's default 403 description is "You don't have the permission to access the
    requested resource". For an expired form that is simply false, and it cost two people
    a day of chasing roles that were never missing.
    """
    r = _post_with_token(app, "a-token-from-a-dead-session")
    body = r.get_data(as_text=True).lower()

    assert "have the permission to access" not in body, (
        "an expired form is being reported as a PERMISSIONS failure -- that is the exact "
        "wording that made the owner believe they were not authorised"
    )
    assert "expired" in body, "the page must say what actually happened: the form expired"
    assert "nothing was lost" in body or "nothing was saved" in body, (
        "the page must reassure the user that their data survived -- it did"
    )


def test_the_user_is_given_a_way_out(app):
    """The old page's exits (auto-redirect to referrer, 'Go Back', 'Try again') ALL return
    to the cached form with the same dead token. The only escape is a fresh GET of the form,
    which mints a new token -- so that link must be on the page."""
    r = _post_with_token(app, "a-token-from-a-dead-session")
    body = r.get_data(as_text=True)

    assert "/newsletter/dismiss-prompt" in body, (
        "the error page must link back to the form's own URL so a fresh GET issues a new "
        "CSRF token -- without it the user is stuck in a 403 loop"
    )
    assert "Taking you back in" not in body, (
        "the auto-redirect must be suppressed: it sends the browser to the referrer, which "
        "is the stale form, which 403s again"
    )


def test_xhr_callers_get_json_not_an_html_error_page(app):
    """The helpline chat POSTs with X-CSRF-Token via fetch(). Handing it an HTML error page
    inside a JSON parse is how a stale token becomes an unexplained silent failure."""
    with app.test_client() as client:
        with client.session_transaction() as s:
            s["_csrf"] = "the-real-token"
            s["user_id"] = 1
        r = client.post("/api/assistant/chat",
                        headers={"X-CSRF-Token": "stale", "X-Requested-With": "XMLHttpRequest"},
                        json={"message": "hi"})
    assert r.status_code == 403
    assert r.is_json, "an XHR caller must get JSON, not an HTML error page"
    assert r.get_json().get("error") == "FORM_EXPIRED"
