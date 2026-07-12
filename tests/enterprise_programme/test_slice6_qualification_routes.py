"""Slice 6 over HTTP: the scorecard, the decision, and the priority list."""

from __future__ import annotations

import os
import sqlite3

import pytest

# Register at IMPORT time: Flask refuses new routes once the app has served a request.
import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import (  # noqa: E402
    beneficiaries, flags, site_qualification, tenancy,
)

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


@pytest.fixture(scope="module")
def ent(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("ent6") / "ent.db")
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-6")

    wa = _wa
    original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if hasattr(wa, "limiter"):
        try:
            wa.limiter.enabled = False
        except Exception:
            pass

    conn = sqlite3.connect(db_path)
    for name in ("olivia", "sam", "musa"):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
            " plan, is_admin, name) VALUES (?,?,'',1,'free',0,?)",
            (name, f"{name}@example.com", name.title()),
        )
    conn.commit()
    ids = {
        n: conn.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()[0]
        for n in ("olivia", "sam", "musa")
    }
    conn.close()

    with wa.app.test_client() as client:
        yield client, wa, ids

    wa.DB_PATH = original_db


def _login(client, uid):
    with client.session_transaction() as s:
        s.clear()
        s["user_id"] = uid
        s["_csrf"] = "testtoken"


def _flag(wa, on: bool):
    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (flags.FLAG_ENABLED, "1" if on else "0"))
    flags.clear_cache()


SCORES = {
    "technical_suitability": "80", "energy_need": "90", "financial_suitability": "70",
    "social_impact": "85", "implementation_readiness": "60", "security_risk": "100",
    "environmental_risk": "90", "funding_eligibility": "75",
}


@pytest.fixture(scope="module")
def programme(ent):
    """One org, one programme, a surveyor and a manager, one site awaiting a decision."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["olivia"])
    client.post("/enterprise/onboarding", data={
        "_csrf": "testtoken", "legal_name": "Ministry of Energy",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)

    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT id FROM enterprise_tenants WHERE legal_name='Ministry of Energy'"
        ).fetchone()[0]
        tenancy.add_member(c, tenant, ids["olivia"], "beneficiary_officer", ids["olivia"])
        tenancy.add_member(c, tenant, ids["sam"], "surveyor", ids["olivia"])
        tenancy.add_member(c, tenant, ids["musa"], "programme_manager", ids["olivia"])

    client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-SCH", "name": "Ghana Schools",
        "design_strategy": "standard", "sponsor_user_id": str(ids["olivia"]),
    }, follow_redirects=True)

    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCH'"
        ).fetchone()[0]

    client.post(f"/enterprise/programmes/{pid}/beneficiaries/new", data={
        "_csrf": "testtoken", "code": "KP-01", "name": "Kpando Senior High",
        "beneficiary_type": "school", "community": "Kpando",
    }, follow_redirects=True)

    with wa.get_db() as c:
        bid = beneficiaries.list_beneficiaries(c, tenant, pid)[0]["id"]
        beneficiaries.transition_beneficiary(c, tenant, ids["musa"], bid,
                                             "Qualification Pending")
    return tenant, pid, bid


def test_qualification_is_dark_by_default(ent, programme):
    client, wa, ids = ent
    _tenant, pid, bid = programme
    _flag(wa, False)
    _login(client, ids["sam"])
    assert client.get(f"/enterprise/programmes/{pid}/priority").status_code == 404
    assert client.get(f"/enterprise/beneficiaries/{bid}/qualify").status_code == 404
    _flag(wa, True)


def test_score_then_decide_over_http(ent, programme):
    """The whole slice end to end: the surveyor scores, the manager decides, and only THEN
    is the site qualified."""
    client, wa, ids = ent
    tenant, pid, bid = programme
    _flag(wa, True)

    # The manager tries to decide FIRST, on a site nobody has been to. Control C02.
    _login(client, ids["musa"])
    client.post(f"/enterprise/beneficiaries/{bid}/qualify/decide",
                data={"_csrf": "testtoken", "decision": "Qualified"},
                follow_redirects=True)
    with wa.get_db() as c:
        assert beneficiaries.get_beneficiary(c, tenant, bid)["status"] \
            == "Qualification Pending", "a site nobody scored must not become Qualified"

    # The surveyor goes and looks.
    _login(client, ids["sam"])
    r = client.post(f"/enterprise/beneficiaries/{bid}/qualify",
                    data=dict(SCORES, _csrf="testtoken", notes="Good roof."),
                    follow_redirects=True)
    assert r.status_code == 200
    with wa.get_db() as c:
        card = site_qualification.get_qualification(c, tenant, bid)
        assert card["total_score"] == pytest.approx(80.25)
        assert card["decision"] is None            # scoring is not deciding
        assert beneficiaries.get_beneficiary(c, tenant, bid)["status"] \
            == "Qualification Pending"

    # Now the manager decides.
    _login(client, ids["musa"])
    client.post(f"/enterprise/beneficiaries/{bid}/qualify/decide",
                data={"_csrf": "testtoken", "decision": "Qualified",
                      "notes": "Committee approved."},
                follow_redirects=True)
    with wa.get_db() as c:
        assert site_qualification.get_qualification(c, tenant, bid)["decision"] == "Qualified"
        assert beneficiaries.get_beneficiary(c, tenant, bid)["status"] == "Qualified"


def test_the_manager_is_not_offered_a_scorecard_they_cannot_fill(ent, programme):
    """A programme_manager has `qualification.approve` but not `qualification.score`. Say so
    on the page rather than serving a form whose Save button 403s."""
    client, wa, ids = ent
    _tenant, _pid, bid = programme
    _flag(wa, True)
    _login(client, ids["musa"])

    body = client.get(f"/enterprise/beneficiaries/{bid}/qualify").get_data(as_text=True)
    assert "read-only" in body.lower() or "decided" in body.lower()

    r = client.post(f"/enterprise/beneficiaries/{bid}/qualify",
                    data=dict(SCORES, _csrf="testtoken"))
    assert r.status_code == 403


def test_the_scorecard_says_which_way_the_risk_rows_run(ent, programme):
    """The sign trap, on the surface the surveyor actually reads. If the page does not say
    it, the code cannot save them."""
    client, wa, ids = ent
    _tenant, _pid, bid = programme
    _flag(wa, True)
    _login(client, ids["sam"])

    body = client.get(f"/enterprise/beneficiaries/{bid}/qualify").get_data(as_text=True)
    assert "100 means NO risk" in body or "100 means <strong>NO risk</strong>" in body
    assert "higher is always better" in body.lower()


def test_the_priority_list_renders(ent, programme):
    client, wa, ids = ent
    _tenant, pid, _bid = programme
    _flag(wa, True)
    _login(client, ids["sam"])

    r = client.get(f"/enterprise/programmes/{pid}/priority")
    assert r.status_code == 200
    assert "Kpando Senior High" in r.get_data(as_text=True)


def test_another_tenants_site_is_a_404_and_never_a_403(ent, programme):
    """Control C13, tested against a REAL beneficiary in a REAL other tenant.

    The first version of this test used id 999999 -- which 404s because nothing with that id
    exists, not because of any tenancy logic. It would have passed against a module with no
    C13 at all (Supervisor slice-6). So build the stranger's site for real.

    404, never 403: a 403 would confirm the row is there, which is itself the leak.
    """
    client, wa, ids = ent
    _flag(wa, True)

    # A rival ministry, with its own programme and its own school. Nothing to do with us.
    with wa.get_db() as c:
        rival = tenancy.create_organisation(c, ids["musa"], "Rival Ministry", "ministry")
        tenancy.add_member(c, rival, ids["musa"], "programme_manager", ids["musa"])
        # He also has to be able to REGISTER the school -- programme_manager cannot
        # (it has no beneficiary.import). The separation of duties, doing its job.
        tenancy.add_member(c, rival, ids["musa"], "beneficiary_officer", ids["musa"])
        from app.enterprise_programme import workflows
        rival_pid = workflows.create_programme(
            c, rival, ids["musa"], code="RV-1", name="Rival Programme",
            sponsor_user_id=ids["musa"])
        rival_bid = beneficiaries.create_beneficiary(
            c, rival, ids["musa"], rival_pid, code="RV-01", name="Rival School",
            beneficiary_type="school")

    _login(client, ids["sam"])          # our surveyor, in OUR tenant
    for method, url in (
        ("get",  f"/enterprise/beneficiaries/{rival_bid}/qualify"),
        ("get",  f"/enterprise/programmes/{rival_pid}/priority"),
    ):
        r = getattr(client, method)(url)
        assert r.status_code == 404, f"{url} leaked {r.status_code}"

    _login(client, ids["musa"])         # musa IS in the rival tenant, but is acting in ours
    r = client.post(f"/enterprise/beneficiaries/{rival_bid}/qualify",
                    data=dict(SCORES, _csrf="testtoken"))
    assert r.status_code == 404
    r = client.post(f"/enterprise/beneficiaries/{rival_bid}/qualify/decide",
                    data={"_csrf": "testtoken", "decision": "Qualified"},
                    follow_redirects=False)
    assert r.status_code == 404

    # And the stranger's site is untouched.
    with wa.get_db() as c:
        assert beneficiaries.get_beneficiary(c, rival, rival_bid)["status"]             == "Beneficiary Registered"
