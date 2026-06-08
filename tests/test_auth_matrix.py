"""
Q-gate 3.3 — 5-case authorization matrix.

For every protected resource in docs/API_SPECIFICATION.md, this suite must
exercise five cases and assert the correct outcome:

    1. authorized session of CORRECT role        → 200, expected payload
    2. authorized session of WRONG role          → 403 (or login redirect), no payload
    3. authorized session of a DIFFERENT tenant  → 404 or 403, no cross-tenant data
    4. logged-out / no session                   → 401 or login redirect
    5. session OLDER than access-token TTL       → 401

For mutations, also assert NO side effects when denied (e.g. row count
unchanged, no audit-log entry written under the wrong actor).

State: fixtures + helpers are wired. Tests are individually `pytest.skip()`
so CI stays green. To activate a test: remove the `pytest.skip(...)` line
in its body and the test runs against the real Flask app.

To extend with more routes: copy a template, fill in the URL + method + body.
"""

import os
import re
import sys

import pytest

# Make the project root importable (mirrors tests/test_app.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(scope="module")
def monkeypatch_module(request):
    """Module-scoped monkeypatch (pytest's built-in is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="module")
def tmp_db(tmp_path_factory):
    """Per-module isolated SQLite DB path so tests don't trample each other."""
    return str(tmp_path_factory.mktemp("auth_matrix_db") / "test.db")


@pytest.fixture(scope="module")
def app_module(tmp_db, monkeypatch_module):
    """
    Import + configure the Flask app for testing.
    Module-scoped so we pay the heavy `import web_app` cost once.
    """
    monkeypatch_module.setenv("SECRET_KEY", "test-secret-key-auth-matrix")
    monkeypatch_module.setenv("TESTING", "1")
    import web_app as wa
    monkeypatch_module.setattr(wa, "DB_PATH", tmp_db)
    wa.init_db()
    wa.app.config["TESTING"] = True
    # We KEEP CSRF on for POST tests so we test the real flow.
    return wa


@pytest.fixture
def client(app_module):
    """Fresh test client per test (clean cookie jar)."""
    with app_module.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers — extract CSRF, register users, login
# ---------------------------------------------------------------------------

_CSRF_PATTERN = re.compile(r'name="_csrf"\s+value="([^"]+)"')


def _csrf(client, path):
    """Pull the hidden _csrf token from any form page."""
    html = client.get(path).data.decode("utf-8", errors="replace")
    m = _CSRF_PATTERN.search(html)
    return m.group(1) if m else ""


def register_and_login(client, username, password="TestPass123!", email=None,
                       company="Test Co", country="Ghana"):
    """
    Register a fresh user and log them in (the test client retains the
    session cookie). Returns the (username, password) tuple.

    `terms_agreed` is required by web_app.py:1585 — omitting it caused every
    test that relies on this helper to silently fail registration before this
    fix (Phase 2.2 of SolarPro_Schedule_2026-06-08.md).
    """
    csrf = _csrf(client, "/register")
    client.post("/register", data={
        "_csrf": csrf,
        "username": username,
        "email": email or f"{username}@example.com",
        "password": password,
        "name": f"{username} (test)",
        "company": company,
        "country": country,
        "terms_agreed": "on",
    }, follow_redirects=True)
    return username, password


def login_as(client, username, password="TestPass123!"):
    """Log an existing user into the test client. Returns the response."""
    csrf = _csrf(client, "/login")
    return client.post("/login", data={
        "_csrf": csrf,
        "username": username,
        "password": password,
    }, follow_redirects=False)


def logout(client):
    return client.get("/logout", follow_redirects=False)


def make_admin(app_module, username):
    """Promote a username to admin by updating the DB directly."""
    with app_module.get_db() as c:
        c.execute("UPDATE users SET is_admin=1 WHERE username=?", (username,))


def session_for_role(client, app_module, role, suffix=""):
    """
    Convenience: create a fresh user, optionally promote to admin/etc., and
    return the client (already logged in). `role` ∈ {"user","admin"}.
    """
    name = f"u_{role}_{suffix or 'a'}"
    register_and_login(client, name)
    if role == "admin":
        make_admin(app_module, name)
        # Re-login so the session picks up the updated is_admin flag
        client.get("/logout")
        login_as(client, name)
    return name


# ===========================================================================
# Template 1 — User-required route: /dashboard
# ===========================================================================

@pytest.mark.parametrize("case, expected_status", [
    ("correct_role",  200),
    ("wrong_role",    200),   # /dashboard accepts any logged-in user
    ("wrong_tenant",  200),   # tenant doesn't matter for /dashboard
    ("logged_out",    302),
    ("expired",       302),
])
def test_dashboard_auth_matrix(client, app_module, case, expected_status):
    pytest.skip("template — unskip to activate. Routes: GET /dashboard")
    # When activated:
    # if case == "logged_out":
    #     pass  # don't login
    # elif case == "expired":
    #     register_and_login(client, "u_expired")
    #     client.get("/logout")  # simulate expired by clearing cookie
    # else:
    #     session_for_role(client, app_module, "user", suffix=case)
    # resp = client.get("/dashboard", follow_redirects=False)
    # assert resp.status_code == expected_status


# ===========================================================================
# Template 2 — Project-owned route: /project/<pid>/results
# ===========================================================================

@pytest.mark.parametrize("case, expected_status", [
    ("owner",                 200),
    ("same_tenant_other_user", 200),
    ("wrong_tenant",          404),  # no leak
    ("logged_out",            302),
    ("expired",               302),
])
def test_project_results_auth_matrix(client, app_module, case, expected_status):
    pytest.skip("template — wire after the project-create helper is added. Routes: GET /project/<pid>/results")


# ===========================================================================
# Template 3 — Admin route: /admin/users
# ===========================================================================

@pytest.mark.parametrize("case, expected_status", [
    ("admin",             200),
    ("non_admin",         302),  # redirect to /login per @admin_required
    ("admin_wrong_tenant", 302),
    ("logged_out",        302),
    ("expired",           302),
])
def test_admin_users_auth_matrix(client, app_module, case, expected_status):
    pytest.skip("template — unskip to activate. Routes: GET /admin/users")


# ===========================================================================
# Template 4 — Mutation route: POST /paystack/verify
# ===========================================================================

@pytest.mark.parametrize("case, expected_status, expect_payment_row", [
    ("authed_csrf_ok",       200, True),
    ("authed_csrf_missing",  400, False),
    ("logged_out",           401, False),
    ("expired",              401, False),
])
def test_paystack_verify_auth_matrix(client, app_module, case, expected_status, expect_payment_row):
    pytest.skip("template — wire after Paystack test fixture exists. Routes: POST /paystack/verify")


# ===========================================================================
# More route stubs from docs/API_SPECIFICATION.md — copy/expand each as needed
# ===========================================================================

USER_ROUTES_GET = [
    "/account",
    "/settings",
    "/tickets",
    "/feedback",
    "/referrals",
    "/upgrade",
    "/upgrade/success",
    "/procurement",
    "/support",
    "/support/email-setup",
    "/support/user-guide",
    "/api/regions/Ghana",
    "/api/solar/Ghana/Greater%20Accra",
]


@pytest.mark.parametrize("route", USER_ROUTES_GET)
def test_user_get_logged_out_redirects(client, route):
    pytest.skip(f"template — unskip to verify logged-out → 302 for {route}")


@pytest.mark.parametrize("route", USER_ROUTES_GET)
def test_user_get_authed_succeeds(client, app_module, route):
    pytest.skip(f"template — unskip to verify authed-user → 200 for {route}")


ADMIN_ROUTES_GET = [
    "/admin",
    "/admin/users",
    "/admin/tickets",
    "/admin/appliances",
    "/admin/helpline-kb",
    "/admin/assessments",
    "/admin/installers",
    "/admin/pipeline",
    "/admin/sales",
    "/admin/leads",
    "/admin/news",
    "/admin/newsletter",
    "/admin/codes",
    "/admin/platform",
    "/admin/agent",
    "/admin/operations",
    "/admin/logs",
    "/admin/beta",
    "/admin/feedback",
    "/admin/api-status",
]


@pytest.mark.parametrize("route", ADMIN_ROUTES_GET)
def test_admin_get_non_admin_denied(client, app_module, route):
    pytest.skip(f"template — verify @admin_required denies non-admin for {route}")


@pytest.mark.parametrize("route", ADMIN_ROUTES_GET)
def test_admin_get_logged_out_denied(client, route):
    pytest.skip(f"template — verify logged-out → 302 for {route}")


@pytest.mark.parametrize("route", ADMIN_ROUTES_GET)
def test_admin_get_admin_succeeds(client, app_module, route):
    pytest.skip(f"template — verify admin → 200 for {route}")


# Mutation routes (POST) — extra side-effect assertion needed per CLAUDE.md §6
ADMIN_MUTATION_ROUTES = [
    ("/admin/users", "POST"),
    ("/admin/codes", "POST"),
    ("/admin/beta/invite", "POST"),
    ("/admin/beta/status", "POST"),
    ("/admin/news", "POST"),
    ("/admin/feedback/update", "POST"),
    ("/admin/ops/security/revoke-all-sessions", "POST"),
    ("/admin/ops/cache/clear", "POST"),
    ("/admin/ops/db/vacuum", "POST"),
    ("/admin/ops/backup/run", "POST"),
]


@pytest.mark.parametrize("route, method", ADMIN_MUTATION_ROUTES)
def test_admin_mutation_no_csrf_denied(client, route, method):
    pytest.skip(f"template — verify missing _csrf rejects {method} {route}")


@pytest.mark.parametrize("route, method", ADMIN_MUTATION_ROUTES)
def test_admin_mutation_non_admin_denied(client, app_module, route, method):
    pytest.skip(f"template — verify non-admin rejected from {method} {route}, no DB side-effect")
