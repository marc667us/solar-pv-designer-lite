"""
SolarPro Global — Pytest test suite.

Tests use an isolated in-memory SQLite DB so they never touch solar.db.
Run:  pytest tests/ -v
"""

import io
import json
import os
import sys
import tempfile

import pytest

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
    with wa.app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def monkeypatch_session(request):
    """Session-scoped monkeypatch (pytest's built-in is function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


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

    def test_register_page_loads(self, app_client):
        resp = app_client.get("/register")
        assert resp.status_code == 200
        assert b"Register" in resp.data or b"register" in resp.data

    def test_login_page_loads(self, app_client):
        resp = app_client.get("/login")
        assert resp.status_code == 200

    def test_register_and_login(self, app_client):
        csrf = _csrf(app_client, "/register")
        resp = app_client.post("/register", data={
            "_csrf":    csrf,
            "username": "testuser",
            "email":    "test@example.com",
            "password": "TestPass123!",
            "name":     "Test User",
            "company":  "Test Co",
            "country":  "Ghana",
        }, follow_redirects=True)
        assert resp.status_code == 200
        # Should land on dashboard after registration
        assert b"dashboard" in resp.data.lower() or b"Dashboard" in resp.data

    def test_duplicate_register_fails(self, app_client):
        csrf = _csrf(app_client, "/register")
        resp = app_client.post("/register", data={
            "_csrf":    csrf,
            "username": "testuser",        # already exists from above
            "email":    "other@example.com",
            "password": "AnotherPass123!",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"already" in resp.data.lower() or b"registered" in resp.data.lower()

    def test_login_wrong_password(self, app_client):
        csrf = _csrf(app_client, "/login")
        resp = app_client.post("/login", data={
            "_csrf":    csrf,
            "username": "testuser",
            "password": "WrongPassword!",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"Invalid" in resp.data or b"invalid" in resp.data or b"incorrect" in resp.data.lower()

    def test_login_success(self, app_client):
        csrf = _csrf(app_client, "/login")
        resp = app_client.post("/login", data={
            "_csrf":    csrf,
            "username": "testuser",
            "password": "TestPass123!",
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert b"dashboard" in resp.data.lower() or b"Dashboard" in resp.data


# ── Public page tests ─────────────────────────────────────────────────────────

class TestPublicPages:

    def test_landing_page(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_platform_page(self, app_client):
        resp = app_client.get("/platform")
        assert resp.status_code == 200

    def test_forgot_password_page(self, app_client):
        resp = app_client.get("/forgot-password")
        assert resp.status_code == 200

    def test_upgrade_page_loads(self, app_client):
        resp = app_client.get("/upgrade")
        assert resp.status_code == 200


# ── Dashboard / auth-gated pages ─────────────────────────────────────────────

class TestAuthGated:
    """These tests run after the testuser is logged-in from TestAuth."""

    def test_dashboard_accessible_when_logged_in(self, app_client):
        # Log in first
        csrf = _csrf(app_client, "/login")
        app_client.post("/login", data={
            "_csrf": csrf, "username": "testuser", "password": "TestPass123!"
        })
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
        # Log out first
        app_client.get("/logout")
        resp = app_client.get("/dashboard", follow_redirects=False)
        assert resp.status_code in (302, 303)
        assert "/login" in resp.headers.get("Location", "")


# ── Project creation flow ─────────────────────────────────────────────────────

class TestProjectFlow:

    @pytest.fixture(autouse=True)
    def login(self, app_client):
        csrf = _csrf(app_client, "/login")
        app_client.post("/login", data={
            "_csrf": csrf, "username": "testuser", "password": "TestPass123!"
        })

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

    def test_solar_data_api(self, app_client):
        # /api/solar is login-gated; log in first, then call with a known region
        csrf = _csrf(app_client, "/login")
        app_client.post("/login", data={
            "_csrf": csrf, "username": "testuser", "password": "TestPass123!"
        })
        # Get a real region for Ghana from the regions API
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
    def login(self, app_client):
        csrf = _csrf(app_client, "/login")
        app_client.post("/login", data={
            "_csrf": csrf, "username": "testuser", "password": "TestPass123!"
        })

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
