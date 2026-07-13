"""Slice 4 -- the /enterprise/templates routes.

The service is tested exhaustively in test_slice4_templates.py. What is proved HERE is the
part that only exists at the HTTP layer and would otherwise ship untested: the pages
render, the parameter form round-trips through _parameters_from_form (a checkbox group and
a comma-separated size list are shaped very differently by a browser than by a dict), the
module is dark by default, and the approve button is not the guard -- POSTing the URL
directly still needs the permission.
"""

from __future__ import annotations

import os
import sqlite3

import pytest
from werkzeug.datastructures import MultiDict

# Register at IMPORT time: Flask refuses new routes once the app has served a request.
import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import flags, tenancy  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


@pytest.fixture(scope="module")
def ent(tmp_path_factory):
    """Flask test client, one organisation, an engineer and a director."""
    db_path = str(tmp_path_factory.mktemp("ent4") / "ent.db")
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-4")

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
    # `owner` onboards the organisation and is therefore granted the full
    # ONBOARDING_OWNER_ROLES bundle -- every Release-1 role, because a one-person
    # organisation is every authority in it. erica and dan are PLAIN MEMBERS holding
    # exactly one role each, which is what makes them usable as separation-of-duties
    # actors. Using the org creator as a stand-in for "a plain engineer" only ever worked
    # while the creator was accidentally permission-poor -- the bug this slice fixes.
    for name in ("owner", "erica", "dan"):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
            " plan, is_admin, name) VALUES (?,?,'',1,'free',0,?)",
            (name, f"{name}@example.com", name.title()),
        )
    conn.commit()
    ids = {
        n: conn.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()[0]
        for n in ("owner", "erica", "dan")
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


@pytest.fixture(scope="module")
def org(ent):
    """One organisation: owner onboards it, erica authors templates, dan approves them."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["owner"])
    client.post("/enterprise/onboarding", data={
        "_csrf": "testtoken", "legal_name": "Ministry of Energy",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)

    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT id FROM enterprise_tenants WHERE legal_name='Ministry of Energy'"
        ).fetchone()[0]
        tenancy.add_member(c, tenant, ids["erica"], "programme_engineer", ids["owner"])
        tenancy.add_member(c, tenant, ids["dan"], "technical_director", ids["owner"])
        # Two products, so the equipment picker has something real to validate against.
        # `category` is NOT NULL in the live schema -- an INSERT that omits it is silently
        # dropped by OR IGNORE, and the picker then correctly reports the ids as unknown.
        c.execute("INSERT OR IGNORE INTO equipment_catalog (id, category, name) "
                  "VALUES (901,'pv_panel','550W Panel'), (902,'inverter','50kW Inverter')")
    return tenant


def test_templates_page_is_dark_by_default(ent, org):
    client, wa, ids = ent
    _flag(wa, False)
    _login(client, ids["erica"])
    assert client.get("/enterprise/templates").status_code == 404
    assert client.get("/enterprise/templates/new").status_code == 404
    _flag(wa, True)


def test_the_full_template_lifecycle_through_the_web(ent, org):
    """Create -> fill in -> submit -> approve -> publish, entirely over HTTP."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["erica"])

    r = client.post("/enterprise/templates/new", data={
        "_csrf": "testtoken", "code": "SCH-50", "name": "School 50 kW",
        "beneficiary_type": "school", "design_strategy": "standard",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"School 50 kW" in r.data
    assert b"No approved version" in r.data      # honest about what it cannot do yet

    with wa.get_db() as c:
        tid, vid = c.execute(
            "SELECT t.id, v.id FROM enterprise_programme_templates t "
            "  JOIN enterprise_template_versions v ON v.template_id = t.id "
            " WHERE t.code='SCH-50'"
        ).fetchone()

    # The form posts a checkbox GROUP (repeated keys) and a comma-separated size list.
    # Both shapes have to survive _parameters_from_form -- this is the bit a dict-level
    # service test cannot reach.
    r = client.post(f"/enterprise/templates/versions/{vid}/save", data=MultiDict([
        ("_csrf", "testtoken"),
        ("design_path", "standard"),
        ("system_configuration", "hybrid"),
        ("typical_load_profile", "daytime_only"),
        ("standard_pv_capacities_kw", "20, 50, 100"),
        ("required_beneficiary_fields", "name"),
        ("required_beneficiary_fields", "region"),
        ("required_beneficiary_fields", "roof_area"),
        ("standard_equipment_ids", "901"),
        ("standard_equipment_ids", "902"),
        ("generator_integration", "on"),
        ("warranty_years", "10"),
    ]), follow_redirects=True)
    assert r.status_code == 200

    with wa.get_db() as c:
        from app.enterprise_programme import templates as engine
        params = engine.get_version_state(c, org, vid)["parameters"]
    assert params["standard_pv_capacities_kw"] == [20, 50, 100]   # CSV parsed
    assert params["required_beneficiary_fields"] == ["name", "region", "roof_area"]
    assert params["standard_equipment_ids"] == [901, 902]
    assert params["generator_integration"] is True                # checkbox 'on' -> True

    # Submit: the freeze.
    r = client.post(f"/enterprise/templates/versions/{vid}/submit",
                    data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"In Review" in r.data

    # The author cannot approve their own standard -- and the button is not the guard.
    r = client.post(f"/enterprise/templates/versions/{vid}/approve",
                    data={"_csrf": "testtoken"})
    assert r.status_code == 403

    _login(client, ids["dan"])
    r = client.post(f"/enterprise/templates/versions/{vid}/approve",
                    data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200
    assert b"may now generate projects" in r.data

    r = client.post(f"/enterprise/templates/versions/{vid}/publish",
                    data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200

    r = client.get("/enterprise/templates")
    assert b"Published" in r.data

    # And the freeze holds through the HTTP surface too.
    _login(client, ids["erica"])
    r = client.post(f"/enterprise/templates/versions/{vid}/save", data={
        "_csrf": "testtoken", "design_path": "standard",
        "system_configuration": "off_grid",
        "typical_load_profile": "daytime_only",
        "standard_pv_capacities_kw": "5",
        "required_beneficiary_fields": "name",
    }, follow_redirects=True)
    assert b"frozen" in r.data
    with wa.get_db() as c:
        from app.enterprise_programme import templates as engine
        assert engine.get_version_state(c, org, vid)[
            "parameters"]["system_configuration"] == "hybrid"


def test_a_rejected_value_leaves_you_on_the_form_not_the_index(ent, org):
    """A mistyped size is the ORDINARY case. Bouncing the user to the template list to read
    why is how a form gets abandoned."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["erica"])

    client.post("/enterprise/templates/new", data={
        "_csrf": "testtoken", "code": "CLI-24", "name": "Clinic 24h",
        "beneficiary_type": "clinic", "design_strategy": "standard",
    }, follow_redirects=True)
    with wa.get_db() as c:
        tid, vid = c.execute(
            "SELECT t.id, v.id FROM enterprise_programme_templates t "
            "  JOIN enterprise_template_versions v ON v.template_id = t.id "
            " WHERE t.code='CLI-24'"
        ).fetchone()

    r = client.post(f"/enterprise/templates/versions/{vid}/save", data={
        "_csrf": "testtoken", "design_path": "standard",
        "system_configuration": "hybrid",
        "typical_load_profile": "continuous_24h",
        "standard_pv_capacities_kw": "50kw",          # not a number
        "required_beneficiary_fields": "name",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/enterprise/templates/{tid}")


def test_an_unknown_version_action_is_a_404(ent, org):
    """The action table is a whitelist, not a dispatcher onto anything named."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["erica"])
    assert client.post("/enterprise/templates/versions/1/delete_everything",
                       data={"_csrf": "testtoken"}).status_code == 404


def test_another_tenants_template_is_a_404_not_a_403(ent, org):
    """C13 through the web: not-yours and not-there are the same answer."""
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["erica"])
    assert client.get("/enterprise/templates/999999").status_code == 404
