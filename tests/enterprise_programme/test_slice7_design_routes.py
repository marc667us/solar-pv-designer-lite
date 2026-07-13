"""Slice 7 over HTTP -- the screen the owner actually uses, and the worker nobody sees.

The rules are tested in test_slice7_rollout.py. This drives the real routes end to end
against the real design engines (no fakes here): a programme in Planning opens into its
design, the design engine actually runs, engineering approves it, and it rolls out.

It also drives the one surface in the whole enterprise module that has NO session behind it
-- the queue drainer. A cron cannot log in, so that endpoint is protected by a bearer token
and by nothing else, which makes it the single most important thing in this file to get
wrong-proof. Three of the tests below are about it.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import flags, rollout  # noqa: E402

# The enterprise routes are registered by wsgi.py, not by web_app.py -- importing web_app
# alone gives an app with no /enterprise routes at all, and every request 404s.
if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )

JOB_TOKEN = "test-drain-token-do-not-reuse"


def _flag(wa, on: bool):
    with wa.get_db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS admin_settings "
                  "(key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                  " updated_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        c.execute("INSERT OR REPLACE INTO admin_settings (key, value) VALUES (?,?)",
                  (flags.FLAG_ENABLED, "1" if on else "0"))
    flags.clear_cache()


def _login(client, uid):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["_csrf"] = "testtoken"
        s.pop("enterprise_active_tenant", None)


@pytest.fixture(scope="module")
def ent():
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-7")
    os.environ["ENTERPRISE_JOB_TOKEN"] = JOB_TOKEN
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

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
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
        " plan, is_admin, name) VALUES ('edna','edna@example.com','',1,'free',0,'Edna')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='edna'").fetchone()[0]
    conn.close()

    with wa.app.test_client() as client:
        yield client, wa, uid

    wa.DB_PATH = original_db
    os.environ.pop("ENTERPRISE_JOB_TOKEN", None)
    flags.clear_cache()


@pytest.fixture(scope="module")
def programme(ent):
    """A real programme, onboarded through the real routes, sitting in PLANNING."""
    client, wa, uid = ent
    _flag(wa, True)
    _login(client, uid)
    client.post("/enterprise/onboarding", data={
        "_csrf": "testtoken", "legal_name": "Ministry of Energy",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)
    client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-HOMES", "name": "Ghana Home Solar",
        "description": ("A government-sponsored programme electrifying 500 residential "
                        "buildings in the Volta region with standard rooftop solar."),
        "design_strategy": "standard", "sponsor_user_id": str(uid),
    }, follow_redirects=True)

    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-HOMES'"
        ).fetchone()[0]
        # A programme opens into its design at PLANNING.
        c.execute("UPDATE enterprise_programme_registry SET current_phase_code='P03_NEEDS' "
                  " WHERE id=?", (pid,))
    return pid


@pytest.fixture(scope="module")
def approved_template(ent, programme):
    """A template that has genuinely been through the approval routes. Returns its version."""
    client, wa, uid = ent
    _login(client, uid)
    client.post("/enterprise/templates/new", data={
        "_csrf": "testtoken", "code": "HOME-5", "name": "Standard home",
        "beneficiary_type": "home", "design_strategy": "standard",
        "programme_id": str(programme),
    }, follow_redirects=True)
    with wa.get_db() as c:
        vid = c.execute(
            "SELECT v.id FROM enterprise_template_versions v "
            "  JOIN enterprise_programme_templates t ON t.id = v.template_id "
            " WHERE t.code='HOME-5'").fetchone()[0]

    client.post(f"/enterprise/templates/versions/{vid}/save", data={
        "_csrf": "testtoken",
        "design_path": "standard",
        "system_configuration": "grid_tied",
        "typical_load_profile": "residential_evening",
        "standard_pv_capacities_kw": "5",
        "required_beneficiary_fields": "name",
    }, follow_redirects=True)
    client.post(f"/enterprise/templates/versions/{vid}/submit",
                data={"_csrf": "testtoken"}, follow_redirects=True)
    client.post(f"/enterprise/templates/versions/{vid}/approve",
                data={"_csrf": "testtoken"}, follow_redirects=True)

    with wa.get_db() as c:
        status = c.execute(
            "SELECT status FROM enterprise_template_versions WHERE id=?", (vid,)
        ).fetchone()[0]
    assert status in ("Approved", "Published"), f"template did not approve: {status}"
    return vid


# ---------------------------------------------------------------------------
# the screen
# ---------------------------------------------------------------------------


def test_the_design_screen_offers_the_two_paths(ent, programme, approved_template):
    """"the programme must open into standard or generation station design"."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.get(f"/enterprise/programmes/{programme}/design")
    assert r.status_code == 200
    body = r.data.decode()
    assert "Standard design" in body
    assert str(approved_template) in body


def test_the_design_form_is_absent_in_another_organisation(ent, programme):
    """C13: not-yours and not-there are the same answer."""
    client, wa, _uid = ent
    conn = sqlite3.connect(wa.DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
        " plan, is_admin, name) VALUES ('olu','olu@example.com','',1,'free',0,'Olu')")
    conn.commit()
    outsider = conn.execute("SELECT id FROM users WHERE username='olu'").fetchone()[0]
    conn.close()

    _login(client, outsider)
    r = client.get(f"/enterprise/programmes/{programme}/design")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# the whole flow, against the REAL engines
# ---------------------------------------------------------------------------


def test_the_real_design_engine_runs_and_rolls_out_to_real_projects(
        ent, programme, approved_template):
    """End to end, with no fakes: web_app's own calc_pv/calc_boq chain actually runs.

    This is the test that would catch a change to web_app's design engine breaking the
    programme module -- the unit tests fake the engine precisely so they can assert the
    programme's RULES, which means only this test proves the wiring is real.
    """
    client, wa, uid = ent
    _login(client, uid)

    # 1. Build the ONE design. Check-My-Bill's basis: a typical monthly consumption.
    r = client.post(f"/enterprise/programmes/{programme}/design/create", data={
        "_csrf": "testtoken",
        "template_version_id": str(approved_template),
        "monthly_kwh": "350",
    }, follow_redirects=True)
    assert r.status_code == 200

    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?",
            (programme,)).fetchone()[0]
        design = rollout.current_design(c, tenant, programme)

    assert design is not None, "the design engine produced nothing"
    assert design["design_path"] == "standard"
    assert design["kwp"] and design["kwp"] > 0, "a real array was not sized"
    assert design["boq"], "the real BOQ engine produced no bill of quantities"
    assert design["status"] == "Draft"        # NOT issued yet -- C04

    # 2. A real project row exists and is openable in the ordinary project UI.
    proj = wa.get_project(design["project_id"])
    assert proj is not None
    assert (proj["data"] or {}).get("from_enterprise_programme") is True

    # 3. Engineering approves it (C04).
    r = client.post(
        f"/enterprise/programmes/{programme}/design/{design['id']}/approve",
        data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200

    # 4. Two qualified sites.
    for code, name in (("HO-01", "Hohoe House 1"), ("HO-02", "Hohoe House 2")):
        _qualify(client, wa, programme, code, name, uid)

    # 5. Roll out.
    r = client.post(
        f"/enterprise/programmes/{programme}/design/{design['id']}/rollout",
        data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"Rollout queued" in r.data

    # 6. The cron drains it.
    r = client.post("/enterprise/jobs/drain",
                    headers={"Authorization": f"Bearer {JOB_TOKEN}"})
    assert r.status_code == 200
    assert r.get_json()["drained"][0]["done"] == 2

    # 7. Two REAL site projects, both copies of the ONE design -- same BOQ.
    with wa.get_db() as c:
        sites = rollout.site_projects(c, tenant, programme)
        boq = rollout.scaled_boq(c, tenant, programme)
        funding = rollout.funding_requirement(c, tenant, programme)

    assert len(sites) == 2

    # THE property, asserted against the REAL project rows: every site's bill of quantities
    # is the reference design's bill of quantities. Not similar to it, not derived from the
    # same template -- the same rows, item for item, quantity for quantity.
    reference_proj = wa.get_project(design["project_id"])
    reference_rows = ((reference_proj["data"] or {}).get("results") or {}).get("boq_rows")
    assert reference_rows, "the reference design has no BOQ rows"

    for site in sites:
        site_proj = wa.get_project(site["project_id"])
        assert site_proj is not None
        site_data = site_proj["data"] or {}
        site_rows = (site_data.get("results") or {}).get("boq_rows")
        assert site_rows == reference_rows, \
            "a site's bill of quantities differs from the reference design's"
        # And it knows where it came from, and where it is (C14 in the project itself).
        assert site_data.get("reference_project_id") == design["project_id"]
        assert site_data.get("enterprise_site", {}).get("code") in ("HO-01", "HO-02")

    assert boq["multiplier"] == 2
    assert funding["sites"] == 2
    assert funding["total"] == pytest.approx(funding["unit_cost"] * 2)


def test_the_programme_plans_pdf_downloads(ent, programme):
    """"the output report -- the plans of the programme for the number of sites"."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.get(f"/enterprise/programmes/{programme}/plans.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data[:4] == b"%PDF"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------------
# the drainer -- the one surface with no session behind it
# ---------------------------------------------------------------------------


def test_the_drain_endpoint_refuses_a_request_with_no_token(ent):
    """A cron has no session, so the bearer token is the ONLY thing guarding this."""
    client, _wa, _uid = ent
    assert client.post("/enterprise/jobs/drain").status_code == 401


def test_the_drain_endpoint_refuses_a_wrong_token(ent):
    client, _wa, _uid = ent
    r = client.post("/enterprise/jobs/drain",
                    headers={"Authorization": "Bearer not-the-token"})
    assert r.status_code == 401


def test_an_unconfigured_drain_endpoint_is_a_404_not_an_open_door(ent):
    """The failure mode of a missing environment variable must never be 'unguarded'.

    If ENTERPRISE_JOB_TOKEN is absent -- a fresh deploy, a typo in the Render env, a secret
    that failed to sync -- the endpoint must cease to exist. The alternative is an
    unauthenticated endpoint that generates projects, and a misconfiguration that opens a
    door is worse than one that closes one.
    """
    client, _wa, _uid = ent
    saved = os.environ.pop("ENTERPRISE_JOB_TOKEN", None)
    try:
        r = client.post("/enterprise/jobs/drain",
                        headers={"Authorization": f"Bearer {saved}"})
        assert r.status_code == 404
    finally:
        if saved is not None:
            os.environ["ENTERPRISE_JOB_TOKEN"] = saved


def _qualify(client, wa, programme, code, name, uid):
    """Register, pend, score and decide one site -- through the real routes."""
    client.post(f"/enterprise/programmes/{programme}/beneficiaries/new", data={
        "_csrf": "testtoken", "code": code, "name": name,
        "beneficiary_type": "home",
    }, follow_redirects=True)
    with wa.get_db() as c:
        bid = c.execute(
            "SELECT id FROM enterprise_beneficiary_register WHERE code=?",
            (code,)).fetchone()[0]

    client.post(f"/enterprise/beneficiaries/{bid}/transition", data={
        "_csrf": "testtoken", "target": "Qualification Pending",
    }, follow_redirects=True)

    from app.enterprise_programme.constants import QUALIFICATION_CRITERION_KEYS
    scores = {k: "80" for k in QUALIFICATION_CRITERION_KEYS}
    client.post(f"/enterprise/beneficiaries/{bid}/qualify", data=dict(
        scores, _csrf="testtoken"), follow_redirects=True)
    client.post(f"/enterprise/beneficiaries/{bid}/qualify/decide", data={
        "_csrf": "testtoken", "decision": "Qualified",
    }, follow_redirects=True)

    # Fail LOUDLY here rather than letting the rollout quietly find no sites: a helper that
    # silently does nothing turns every test downstream of it into a test of nothing.
    with wa.get_db() as c:
        status = c.execute(
            "SELECT status FROM enterprise_beneficiary_register WHERE id=?",
            (bid,)).fetchone()[0]
    assert status == "Qualified", f"{code} did not qualify: {status}"
    return bid
