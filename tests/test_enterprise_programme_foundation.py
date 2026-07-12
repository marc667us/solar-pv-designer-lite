"""Enterprise Programme Module -- Phase 1 foundation tests.

Covers the flag (dark by default), organisation bootstrap (idempotent),
programme/phase/beneficiary CRUD, dashboard counts, and the job table.

Tenant isolation + IDOR live in tests/security/test_enterprise_programme_tenant_isolation.py.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import enterprise_programme_jobs as jobs          # noqa: E402
import enterprise_programme_repository as repo    # noqa: E402
import enterprise_programme_services as svc       # noqa: E402

# Register at IMPORT time, not in a fixture. Flask refuses to accept new routes or
# context processors once the app has handled its first request -- and when this
# module runs after another test module that already issued requests, a fixture
# registration would blow up. Import time is before any request, always.
# (Registration is side-effect free: no DB is touched until the first enterprise
# request, so importing this does not create tables in the developer's solar.db.)
import web_app as _wa                             # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


@pytest.fixture(scope="module")
def ent_app(tmp_path_factory):
    """A Flask test client with the enterprise module registered, on a temp SQLite DB."""
    db_path = str(tmp_path_factory.mktemp("entdb") / "ent.db")
    os.environ.pop("DATABASE_URL", None)          # force the SQLite path
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise")

    wa = _wa
    _original_db = wa.DB_PATH          # restored on teardown -- see below
    wa.DB_PATH = db_path
    wa.init_db()
    repo.ensure_enterprise_schema(wa.get_db)
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if hasattr(wa, "limiter"):
        try:
            wa.limiter.enabled = False
        except Exception:
            pass

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified, "
        "plan, is_admin, name) VALUES ('entuser','ent@example.com','',1,'free',0,'Ent User')"
    )
    conn.commit()
    uid = conn.execute(
        "SELECT id FROM users WHERE username='entuser'"
    ).fetchone()[0]
    conn.close()

    with wa.app.test_client() as client:
        with client.session_transaction() as s:
            s["user_id"] = uid
            s["_csrf"] = "testtoken"
        yield client, wa, uid

    # DB_PATH is a module global shared with every other test module. Put it back,
    # or whichever suite runs after this one silently talks to our temp database.
    wa.DB_PATH = _original_db


def _flag_on(wa, on=True):
    """Flip the module's feature flag directly in admin_settings (SQLite: no RLS).

    module_enabled() caches the flag for 60s per process, so the cache must be
    dropped here or the test would assert against a stale value.
    """
    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (repo.FLAG_ENABLED, "1" if on else "0"))
    repo.invalidate_flag_cache()


# --- the flag --------------------------------------------------------------

def test_module_is_dark_by_default(ent_app):
    """With the flag off, the module must not exist -- a 404, not a 403."""
    client, wa, _ = ent_app
    _flag_on(wa, False)
    assert client.get("/enterprise").status_code == 404


def test_module_visible_when_flag_on(ent_app):
    client, wa, _ = ent_app
    _flag_on(wa, True)
    r = client.get("/enterprise")
    assert r.status_code == 200


def test_flag_read_is_cached_and_fails_closed(ent_app):
    """The flag is consulted on EVERY render, so it must be cached and fail closed.

    (Codex gate 1, MEDIUM: an uncached read added a DB connection to every page
    load on a 1-worker free tier, including anonymous public pages.)
    """
    _, wa, _ = ent_app
    _flag_on(wa, True)
    assert repo.module_enabled(wa.get_db) is True

    # A broken DB must leave the module DARK, never accidentally open.
    repo.invalidate_flag_cache()

    def _exploding_db():
        raise RuntimeError("database is down")

    assert repo.module_enabled(_exploding_db) is False

    # The cached value is served without touching the DB at all.
    calls = {"n": 0}

    def _counting_db():
        calls["n"] += 1
        return wa.get_db()

    repo.invalidate_flag_cache()
    repo.module_enabled(_counting_db)          # 1st call -> reads
    first = calls["n"]
    for _ in range(5):
        repo.module_enabled(_counting_db)      # cached -> no further reads
    assert calls["n"] == first, "flag must be served from cache, not re-read per call"


# --- bootstrap -------------------------------------------------------------

def test_bootstrap_creates_org_and_owner_membership(ent_app):
    client, wa, uid = ent_app
    _flag_on(wa, True)

    r = client.post("/enterprise/bootstrap",
                    data={"legal_name": "Ghana Education Service", "_csrf": "testtoken"},
                    follow_redirects=True)
    assert r.status_code == 200

    m = repo.get_active_membership(wa.get_db, uid)
    assert m is not None
    assert m["legal_name"] == "Ghana Education Service"
    assert m["role"] == "enterprise_owner"


def test_bootstrap_is_idempotent(ent_app):
    """Bootstrapping twice must NOT create a second organisation."""
    client, wa, uid = ent_app
    _flag_on(wa, True)

    first = repo.get_active_membership(wa.get_db, uid)["organisation_id"]
    again = repo.bootstrap_organisation(wa.get_db, uid, "Some Other Name")
    assert again == first

    with wa.get_db() as c:
        n = c.execute(
            "SELECT COUNT(*) FROM enterprise_memberships WHERE user_id=?", (uid,)
        ).fetchone()[0]
    assert n == 1


# --- programmes ------------------------------------------------------------

def test_programme_create_and_fetch(ent_app):
    _, wa, uid = ent_app
    org = repo.get_active_membership(wa.get_db, uid)["organisation_id"]

    pid = repo.create_programme(wa.get_db, org, uid, {
        "programme_code": "PRG-001",
        "name": "Ghana National Secondary School Solar Independence Programme",
        "programme_type": "school",
        "design_strategy": "standard",
        "target_beneficiaries": 420,
        "target_capacity_kwp": 250000,
        "currency": "GHS",
        "status": "active",
    })
    assert pid

    p = repo.get_programme(wa.get_db, org, uid, pid)
    assert p["name"].startswith("Ghana National")
    assert p["target_beneficiaries"] == 420


def test_programme_validation_rejects_bad_input(ent_app):
    errors = svc.validate_programme({
        "name": "", "programme_code": "!!bad!!", "design_strategy": "nonsense",
        "target_beneficiaries": "-5",
    })
    assert any("name is required" in e.lower() for e in errors)
    assert any("code must be" in e.lower() for e in errors)
    assert any("design strategy" in e.lower() for e in errors)


# --- phases + beneficiaries + dashboard ------------------------------------

def test_phases_beneficiaries_and_dashboard_counts(ent_app):
    _, wa, uid = ent_app
    org = repo.get_active_membership(wa.get_db, uid)["organisation_id"]
    pid = repo.create_programme(wa.get_db, org, uid, {
        "programme_code": "PRG-KPI", "name": "KPI Programme",
        "design_strategy": "standard", "target_beneficiaries": 10,
    })

    for i, nm in enumerate(["Greater Accra Pilot", "Regional Rollout",
                            "National Completion"], start=1):
        assert repo.add_phase(wa.get_db, org, uid, pid,
                              {"name": nm, "sequence_no": i}) is not None

    for nm in ["Accra Girls SHS", "Tema SHS", "Kumasi SHS"]:
        assert repo.add_beneficiary(wa.get_db, org, uid, pid,
                                    {"name": nm, "beneficiary_type": "school"}) is not None

    view = svc.programme_dashboard(wa.get_db, org, uid, pid)
    assert view["kpi"]["phases"] == 3
    assert view["kpi"]["beneficiaries_registered"] == 3
    assert view["kpi"]["beneficiaries_approved"] == 0
    # 3 registered against a target of 10
    assert view["kpi"]["coverage_pct"] == 30.0


def test_beneficiary_status_change(ent_app):
    _, wa, uid = ent_app
    org = repo.get_active_membership(wa.get_db, uid)["organisation_id"]
    pid = repo.create_programme(wa.get_db, org, uid, {
        "programme_code": "PRG-STATUS", "name": "Status Programme",
        "design_strategy": "standard",
    })
    bid = repo.add_beneficiary(wa.get_db, org, uid, pid, {"name": "Clinic A"})

    assert repo.set_beneficiary_status(wa.get_db, org, uid, pid, bid, "approved")
    rows, _ = repo.list_beneficiaries(wa.get_db, org, uid, pid)
    assert rows[0]["qualification_status"] == "approved"

    # an invalid status is refused rather than written
    assert not repo.set_beneficiary_status(wa.get_db, org, uid, pid, bid, "hacked")


# --- jobs (foundation only) ------------------------------------------------

def test_job_enqueue_is_idempotent_and_claimable(ent_app):
    _, wa, uid = ent_app
    org = repo.get_active_membership(wa.get_db, uid)["organisation_id"]

    j1 = jobs.enqueue(wa.get_db, org, uid, "beneficiary_import",
                      idempotency_key="fixed-key", total=100)
    j2 = jobs.enqueue(wa.get_db, org, uid, "beneficiary_import",
                      idempotency_key="fixed-key", total=100)
    assert j1 == j2, "same idempotency key must not create a second job"

    claimed = jobs.claim_job(wa.get_db, org, uid)
    assert claimed and claimed["id"] == j1
    assert claimed["status"] == jobs.JOB_RUNNING


def test_tick_reports_unhandled_job_type_rather_than_silently_passing(ent_app):
    """Phase 1 registers no handlers -- an unhandled type must FAIL loudly."""
    _, wa, uid = ent_app
    org = repo.get_active_membership(wa.get_db, uid)["organisation_id"]

    jobs.enqueue(wa.get_db, org, uid, "not_a_real_job", idempotency_key="unhandled-1")
    result = jobs.tick(wa.get_db, org, uid)
    assert result["claimed"] is True
    assert result["ok"] is False
