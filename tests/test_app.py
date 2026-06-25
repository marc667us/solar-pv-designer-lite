"""
SolarPro Global — Pytest test suite.

Tests use an isolated in-memory SQLite DB so they never touch solar.db.
Run:  pytest tests/ -v
"""

import io
import json
import os
import sqlite3
import sys
import tempfile

import pytest


def _verify_user_in_db(db_path, username):
    """Flip the email-verification flag for a test user, bypassing the email-token roundtrip.

    Why: web_app.py:1637 (commit 17e40ee) registers new users with email_verified=0 and
    bounces them from /dashboard, /api/*, /upgrade etc. until they hit /verify-email/<token>.
    These pytest tests don't have a mail inbox — flip the flag directly in the temp DB.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("UPDATE users SET email_verified=1 WHERE username=?", (username,))
        conn.commit()
    finally:
        conn.close()

# ── make sure the project root is importable ──────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_db(tmp_path_factory):
    """Return a path to a temp DB file (unique per test-session)."""
    return str(tmp_path_factory.mktemp("db") / "test_solar.db")


@pytest.fixture(scope="session")
def app_client(tmp_db, monkeypatch_session):
    """
    Create a Flask test client backed by the temp DB.
    Uses the monkeypatch_session fixture to swap DB_PATH once for the whole session.
    """
    monkeypatch_session.setenv("SECRET_KEY", "test-secret-key-12345")
    import web_app as wa
    monkeypatch_session.setattr(wa, "DB_PATH", tmp_db)
    wa.init_db()                          # create schema in temp DB
    wa.app.config["TESTING"] = True
    wa.app.config["WTF_CSRF_ENABLED"] = False
    # Flask-Limiter default 120/min trips on later tests in the same session.
    # Disable for tests only — production config unaffected.
    wa.app.config["RATELIMIT_ENABLED"] = False
    if hasattr(wa, "limiter"):
        try: wa.limiter.enabled = False
        except Exception: pass
    with wa.app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def monkeypatch_session(request):
    """Session-scoped monkeypatch (pytest's built-in is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


# ── SOC 2 M1.1 fallout helpers (2026-06-25) ──────────────────────────────
# After M1.1 the legacy /login + /register POST paths unconditionally
# redirect to Keycloak. Tests that used to POST to /login then read
# session["user_id"] now have to bypass that flow: insert the testuser
# directly into the temp DB + seed session keys via session_transaction
# (the same trick tests/security/ uses).

@pytest.fixture(scope="session", autouse=True)
def _ensure_testuser(app_client, tmp_db):
    """Insert testuser into the temp DB so auth-gated tests have a real
    `users` row to log in as. Replaces the old test_register_and_login
    flow which exercised the bcrypt POST path (closed by M1.1)."""
    conn = sqlite3.connect(tmp_db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO users "
            "(username, email, password_hash, email_verified, plan, is_admin, name) "
            "VALUES (?, ?, '', 1, 'free', 0, ?)",
            ("testuser", "test@example.com", "Test User"),
        )
        conn.commit()
    finally:
        conn.close()
    return "testuser"


def _seed_login(client, tmp_db, username="testuser"):
    """Stand-in for the retired POST /login flow. Reads the user_id out
    of the temp DB and writes the session keys the legacy app code
    expects (mirroring what oidc_routes.py does on KC callback)."""
    conn = sqlite3.connect(tmp_db)
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(username)=?",
            (username.lower(),),
        ).fetchone()
        uid = row[0] if row else None
    finally:
        conn.close()
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["username"] = username
    return uid


# ── Helper: get a fresh CSRF token from a form page ───────────────────────────

def _csrf(client, path="/register"):
    resp = client.get(path)
    # Extract hidden _csrf field from HTML
    html = resp.data.decode("utf-8", errors="replace")
    marker = 'name="_csrf" value="'
    idx = html.find(marker)
    if idx == -1:
        return ""
    start = idx + len(marker)
    end = html.find('"', start)
    return html[start:end]


# ── Auth tests ────────────────────────────────────────────────────────────────

class TestAuth:

    def test_register_page_redirects_to_kc(self, app_client):
        """SOC 2 M1.1 (2026-06-25): /register now unconditionally 302s to
        the OIDC blueprint (`/auth/register`). The legacy form is dead."""
        resp = app_client.get("/register", follow_redirects=False)
        assert resp.status_code in (301, 302, 303)
        loc = resp.headers.get("Location", "")
        assert "/auth/register" in loc or "/auth/login" in loc

    def test_login_page_redirects_to_kc(self, app_client):
        """SOC 2 M1.1: /login 302 to /auth/login."""
        resp = app_client.get("/login", follow_redirects=False)
        assert resp.status_code in (301, 302, 303)
        loc = resp.headers.get("Location", "")
        assert "/auth/login" in loc

    @pytest.mark.xfail(reason="SOC 2 M1.1 (2026-06-25): legacy POST /login is closed; KC owns auth. The bcrypt form path is dead.", strict=True)
    def test_register_and_login(self, app_client, tmp_db):
        csrf = _csrf(app_client, "/register")
        app_client.post("/register", data={
            "_csrf":        csrf,
            "username":     "newuser",
            "email":        "new@example.com",
            "password":     "TestPass123!",
            "terms_agreed": "on",
        }, follow_redirects=False)
        # Was: POST /login then assert dashboard. Now /register and /login
        # 302 to KC so neither call ever reaches the legacy handler.
        csrf = _csrf(app_client, "/login")
        resp = app_client.post("/login", data={
            "_csrf":    csrf,
            "username": "newuser",
            "password": "TestPass123!",
        }, follow_redirects=True)
        assert b"dashboard" in resp.data.lower()

    @pytest.mark.xfail(reason="SOC 2 M1.1: legacy POST /register closed.", strict=True)
    def test_duplicate_register_fails(self, app_client):
        csrf = _csrf(app_client, "/register")
        resp = app_client.post("/register", data={
            "_csrf":        csrf,
            "username":     "testuser",
            "email":        "other@example.com",
            "password":     "AnotherPass123!",
            "terms_agreed": "on",
        }, follow_redirects=True)
        assert b"already" in resp.data.lower()

    @pytest.mark.xfail(reason="SOC 2 M1.1: legacy POST /login closed; bad-password handling moved to KC.", strict=True)
    def test_login_wrong_password(self, app_client):
        csrf = _csrf(app_client, "/login")
        resp = app_client.post("/login", data={
            "_csrf":    csrf,
            "username": "testuser",
            "password": "WrongPassword!",
        }, follow_redirects=True)
        assert b"invalid" in resp.data.lower()

    @pytest.mark.xfail(reason="SOC 2 M1.1: legacy POST /login closed; auth is via OIDC PKCE only.", strict=True)
    def test_login_success(self, app_client):
        csrf = _csrf(app_client, "/login")
        resp = app_client.post("/login", data={
            "_csrf":    csrf,
            "username": "testuser",
            "password": "TestPass123!",
        }, follow_redirects=True)
        assert b"dashboard" in resp.data.lower()


# ── Public page tests ─────────────────────────────────────────────────────────

class TestPublicPages:

    def test_landing_page(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_platform_page(self, app_client):
        resp = app_client.get("/platform")
        assert resp.status_code == 200

    def test_forgot_password_redirects_to_kc(self, app_client):
        """SOC 2 M1.1: password reset is owned by Keycloak; the legacy
        /forgot-password handler unconditionally 302s to /auth/login."""
        resp = app_client.get("/forgot-password", follow_redirects=False)
        assert resp.status_code in (301, 302, 303)
        assert "/auth/login" in resp.headers.get("Location", "")

    def test_upgrade_page_loads(self, app_client, tmp_db):
        # /upgrade is login-gated; seed the session directly.
        _seed_login(app_client, tmp_db)
        resp = app_client.get("/upgrade")
        assert resp.status_code == 200


# ── Dashboard / auth-gated pages ─────────────────────────────────────────────

class TestAuthGated:
    """Auth-gated pages. Each test seeds session["user_id"] directly via
    the temp DB -- the legacy /login POST path is closed (SOC 2 M1.1)."""

    @pytest.fixture(autouse=True)
    def _login(self, app_client, tmp_db):
        _seed_login(app_client, tmp_db)

    def test_dashboard_accessible_when_logged_in(self, app_client):
        resp = app_client.get("/dashboard")
        assert resp.status_code == 200

    def test_account_page(self, app_client):
        resp = app_client.get("/account")
        assert resp.status_code == 200

    def test_settings_page(self, app_client):
        resp = app_client.get("/settings")
        assert resp.status_code == 200

    def test_support_page(self, app_client):
        resp = app_client.get("/support")
        assert resp.status_code == 200

    def test_support_user_guide(self, app_client):
        resp = app_client.get("/support/user-guide")
        assert resp.status_code == 200

    def test_support_email_setup(self, app_client):
        resp = app_client.get("/support/email-setup")
        assert resp.status_code == 200

    def test_tickets_page(self, app_client):
        resp = app_client.get("/tickets")
        assert resp.status_code == 200

    def test_unauthenticated_redirects_to_login(self, app_client):
        # M1.8: legacy /logout funnels through /auth/logout.
        app_client.get("/logout")
        with app_client.session_transaction() as s:
            s.clear()
        resp = app_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 303)
        # First hop is /login (legacy login_required) which then 302s to KC.
        # Either /login or /auth/login in Location is acceptable.
        loc = resp.headers.get("Location", "")
        assert "/login" in loc or "/auth/login" in loc


# ── Project creation flow ─────────────────────────────────────────────────────

class TestProjectFlow:

    @pytest.fixture(autouse=True)
    def login(self, app_client, tmp_db):
        # SOC 2 M1.1: legacy POST /login closed; seed session directly.
        _seed_login(app_client, tmp_db)

    def test_new_project_page_loads(self, app_client):
        resp = app_client.get("/project/new")
        assert resp.status_code == 200

    def test_create_project(self, app_client):
        csrf = _csrf(app_client, "/project/new")
        resp = app_client.post("/project/new", data={
            "_csrf":        csrf,
            "name":         "Test Solar Project",
            "system_type":  "hybrid",
            "phase":        "single",
            "description":  "Automated test project",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_project_list_shows_project(self, app_client):
        resp = app_client.get("/dashboard")
        assert resp.status_code == 200
        assert b"Test Solar Project" in resp.data


# ── API endpoints ─────────────────────────────────────────────────────────────

class TestAPIEndpoints:

    def test_regions_api_valid_country(self, app_client):
        resp = app_client.get("/api/regions/Ghana")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_regions_api_unknown_country(self, app_client):
        # Unknown country returns 400 (bad request) — that is the expected behaviour
        resp = app_client.get("/api/regions/UnknownCountryXYZ")
        assert resp.status_code == 400

    def test_solar_data_api(self, app_client, tmp_db):
        # /api/solar is login-gated; seed session directly (SOC 2 M1.1).
        _seed_login(app_client, tmp_db)
        reg_resp = app_client.get("/api/regions/Ghana")
        regions = json.loads(reg_resp.data)
        region = regions[0] if regions else "Accra"
        resp = app_client.get(f"/api/solar/Ghana/{region}")
        assert resp.status_code in (200, 400)   # 400 if region not in dataset


# ── Calculation engine (unit tests — no Flask needed) ─────────────────────────

class TestCalculationEngine:

    def test_calc_economics_basic(self):
        """Smoke-test the economics calculation function."""
        import web_app as wa
        eco = wa.calc_economics(
            pv_kw=5.0,
            num_panels=12,
            bat_kwh=10.0,
            num_bat=2,
            inv_kw=5.0,
            daily_kwh=20.0,
            tariff=0.15,
            currency="USD",
            symbol="$",
            cost_usd_kwp=800,
            fx_usd=1.0,
            autonomy=1,
            boq_total_local=50000,
        )
        assert "npv" in eco
        assert "irr_pct" in eco
        assert "payback" in eco
        assert eco["annual_kwh"] == pytest.approx(20.0 * 365, rel=1e-3)
        assert eco["payback"] > 0

    def test_calc_economics_zero_demand(self):
        """Zero daily demand should not crash."""
        import web_app as wa
        eco = wa.calc_economics(
            pv_kw=0.0,
            num_panels=0,
            bat_kwh=0.0,
            num_bat=0,
            inv_kw=0.0,
            daily_kwh=0.0,
            tariff=0.15,
            currency="USD",
            symbol="$",
            cost_usd_kwp=800,
            fx_usd=1.0,
            boq_total_local=1000,
        )
        assert "payback" in eco

    def test_temp_derating_returns_float(self):
        """Temperature derating helper should return a valid factor."""
        from config.global_solar_data import temp_derating
        factor = temp_derating(35.0)
        assert 0.5 < factor <= 1.0

    def test_get_countries_nonempty(self):
        """Country list must not be empty."""
        from config.global_solar_data import get_countries
        countries = get_countries()
        assert len(countries) > 10

    def test_get_regions_returns_list(self):
        """Regions for a known country must be a list."""
        from config.global_solar_data import get_regions
        regions = get_regions("Ghana")
        assert isinstance(regions, list)
        assert len(regions) > 0


# ── Settings save ─────────────────────────────────────────────────────────────

class TestSettings:

    @pytest.fixture(autouse=True)
    def login(self, app_client, tmp_db):
        # SOC 2 M1.1: legacy POST /login closed; seed session directly.
        _seed_login(app_client, tmp_db)

    def test_settings_save_org(self, app_client):
        csrf = _csrf(app_client, "/settings")
        resp = app_client.post("/settings", data={
            "_csrf":       csrf,
            "_section":    "profile",
            "org_name":    "My Solar Co",
            "org_address": "123 Sun Street",
            "org_email":   "info@mysolar.com",
            "org_phone":   "+1-555-0100",
            "org_website": "https://mysolar.com",
            "timezone":    "UTC",
        }, follow_redirects=True)
        assert resp.status_code == 200

    def test_settings_datetime_format(self, app_client):
        csrf = _csrf(app_client, "/settings")
        resp = app_client.post("/settings", data={
            "_csrf":        csrf,
            "_section":     "datetime",
            "date_format":  "DD/MM/YYYY",
            "time_format":  "24h",
        }, follow_redirects=True)
        assert resp.status_code == 200
