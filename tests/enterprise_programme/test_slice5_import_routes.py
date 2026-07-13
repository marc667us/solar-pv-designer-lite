"""Slice 5 -- the register and importer over HTTP.

The services are tested exhaustively in test_slice5_beneficiaries.py. What is proved HERE
is the part that only exists at the HTTP layer: a real multipart file upload, the mapping
form round-tripping through `map__<header>` fields, the preview showing what WOULD happen
without having done any of it, and the module being dark by default.
"""

from __future__ import annotations

import io
import os
import sqlite3

import pytest

# Register at IMPORT time: Flask refuses new routes once the app has served a request.
import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import beneficiaries, flags, tenancy  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )

CSV = (
    "School Name,Site Code,Region,Town,Students,Roof Area (m2)\n"
    "Kpando Senior High,KP-01,Volta,Kpando,820,900\n"
    "Hohoe Technical,HO-02,Volta,Hohoe,610,700\n"
    "Broken School,BR-03,Volta,Ho,not-a-number,540\n"
).encode()


@pytest.fixture(scope="module")
def ent(tmp_path_factory):
    """Flask test client; an officer who imports and a manager who approves."""
    db_path = str(tmp_path_factory.mktemp("ent5") / "ent.db")
    os.environ.pop("DATABASE_URL", None)
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-5")

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
    # `owner` onboards the organisation and therefore holds every Release-1 role (see
    # constants.ONBOARDING_OWNER_ROLES). olivia and musa are PLAIN MEMBERS with one role
    # each, so "the officer who registers cannot approve" is a test of the control rather
    # than an accident of the creator being permission-poor.
    for name in ("owner", "olivia", "musa"):
        conn.execute(
            "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
            " plan, is_admin, name) VALUES (?,?,'',1,'free',0,?)",
            (name, f"{name}@example.com", name.title()),
        )
    conn.commit()
    ids = {
        n: conn.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()[0]
        for n in ("owner", "olivia", "musa")
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
def programme(ent):
    """One organisation, one programme, the two roles.

    The OWNER onboards and registers the programme (they hold programme.create); olivia
    and musa are single-role members, so the register-vs-approve split is exercised by two
    people who genuinely hold one authority each.
    """
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
        tenancy.add_member(c, tenant, ids["olivia"], "beneficiary_officer", ids["owner"])
        tenancy.add_member(c, tenant, ids["musa"], "programme_manager", ids["owner"])

    client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-SCH", "name": "Ghana Schools",
        "design_strategy": "standard", "sponsor_user_id": str(ids["owner"]),
    }, follow_redirects=True)

    with wa.get_db() as c:
        pid = c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-SCH'"
        ).fetchone()[0]
    return tenant, pid


def test_the_register_is_dark_by_default(ent, programme):
    client, wa, ids = ent
    _tenant, pid = programme
    _flag(wa, False)
    _login(client, ids["olivia"])
    assert client.get(f"/enterprise/programmes/{pid}/beneficiaries").status_code == 404
    _flag(wa, True)


def test_upload_preview_commit(ent, programme):
    """The whole point of the slice, over HTTP: upload writes NOTHING; the preview says what
    would happen; the commit is what actually writes."""
    client, wa, ids = ent
    tenant, pid = programme
    _flag(wa, True)
    _login(client, ids["olivia"])

    r = client.post(
        f"/enterprise/programmes/{pid}/import",
        data={"_csrf": "testtoken", "default_type": "school",
              "file": (io.BytesIO(CSV), "schools.csv")},
        content_type="multipart/form-data", follow_redirects=False,
    )
    assert r.status_code == 302
    batch_id = int(r.headers["Location"].rstrip("/").split("/")[-1])

    # NOTHING has been written to the register yet. This is the property.
    with wa.get_db() as c:
        assert beneficiaries.list_beneficiaries(c, tenant, pid) == []

    r = client.get(f"/enterprise/imports/{batch_id}")
    assert r.status_code == 200
    assert b"Nothing has been written to the register" in r.data
    assert b"Kpando Senior High" in r.data
    assert b"Broken School" in r.data
    # The bad row explains ITSELF, on the row -- "3 errors" with no reasons is unfixable.
    assert b"is not a number" in r.data

    r = client.post(f"/enterprise/imports/{batch_id}/commit",
                    data={"_csrf": "testtoken"}, follow_redirects=True)
    assert r.status_code == 200

    with wa.get_db() as c:
        register = beneficiaries.list_beneficiaries(c, tenant, pid)
    assert {b["code"] for b in register} == {"KP-01", "HO-02"}     # the broken row is out
    assert all(b["status"] == "Beneficiary Registered" for b in register)


def test_the_mapping_can_be_corrected_before_committing(ent, programme):
    client, wa, ids = ent
    tenant, pid = programme
    _flag(wa, True)
    _login(client, ids["olivia"])

    ambiguous = b"School Name,Location\nAdidome Senior High,Adidome\n"
    r = client.post(
        f"/enterprise/programmes/{pid}/import",
        data={"_csrf": "testtoken", "default_type": "school",
              "file": (io.BytesIO(ambiguous), "ambiguous.csv")},
        content_type="multipart/form-data",
    )
    batch_id = int(r.headers["Location"].rstrip("/").split("/")[-1])

    # "Location" is genuinely ambiguous, so it is NOT guessed -- the operator says.
    r = client.post(f"/enterprise/imports/{batch_id}/remap", data={
        "_csrf": "testtoken",
        "map__School Name": "name",
        "map__Location": "community",
        "default_type": "school",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"1 valid" in r.data

    client.post(f"/enterprise/imports/{batch_id}/commit", data={"_csrf": "testtoken"},
                follow_redirects=True)
    with wa.get_db() as c:
        site = [b for b in beneficiaries.list_beneficiaries(c, tenant, pid)
                if b["name"] == "Adidome Senior High"][0]
    assert site["community"] == "Adidome"


def test_registering_is_not_approving_over_http(ent, programme):
    """The officer's Approve button does not exist, and POSTing the URL does not work."""
    client, wa, ids = ent
    tenant, pid = programme
    _flag(wa, True)
    _login(client, ids["olivia"])

    with wa.get_db() as c:
        bid = [b for b in beneficiaries.list_beneficiaries(c, tenant, pid)
               if b["code"] == "KP-01"][0]["id"]

    r = client.get(f"/enterprise/beneficiaries/{bid}")
    assert r.status_code == 200
    assert b"Admit to the programme" not in r.data       # the officer is not offered it

    r = client.post(f"/enterprise/beneficiaries/{bid}/transition",
                    data={"_csrf": "testtoken", "target": "Qualification Pending"})
    assert r.status_code == 403                          # ...and cannot do it anyway

    _login(client, ids["musa"])
    r = client.post(f"/enterprise/beneficiaries/{bid}/transition",
                    data={"_csrf": "testtoken", "target": "Qualification Pending"},
                    follow_redirects=True)
    assert r.status_code == 200
    with wa.get_db() as c:
        assert beneficiaries.get_beneficiary(c, tenant, bid)["status"] == \
            "Qualification Pending"


def test_another_tenants_import_is_a_404(ent, programme):
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["olivia"])
    assert client.get("/enterprise/imports/999999").status_code == 404
    assert client.get("/enterprise/beneficiaries/999999").status_code == 404


def test_a_file_of_the_wrong_type_is_refused(ent, programme):
    client, wa, ids = ent
    _tenant, pid = programme
    _flag(wa, True)
    _login(client, ids["olivia"])
    r = client.post(
        f"/enterprise/programmes/{pid}/import",
        data={"_csrf": "testtoken", "file": (io.BytesIO(b"%PDF-1.4"), "sites.pdf")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"unsupported file type" in r.data


def test_a_programme_that_is_not_yours_is_a_404_even_before_your_role_is_checked(
        ent, programme):
    """Codex MED (C13) -- the register form asked "may you?" before it asked "is it yours?".

    Musa is a programme_manager: no `beneficiary.import`. Asking for a programme id that is
    not in his tenant must come back 404 -- the shape of a stranger's data, including
    whether it exists at all, is not his to learn. Answering 403 confirms the row is there.
    """
    client, wa, ids = ent
    _flag(wa, True)
    _login(client, ids["musa"])
    r = client.get("/enterprise/programmes/999999/beneficiaries/new")
    assert r.status_code == 404


def test_a_read_only_viewer_is_not_offered_a_save_button_that_will_403(ent, programme):
    """Codex round 2 (LOW) -- the detail page was handed `can_edit` and ignored it.

    Musa is a programme_manager: he may APPROVE a site but not edit one. He was shown a full
    editable form whose Save button 403s. Telling him at the top of the page costs nothing;
    letting him retype an address first and then refusing is contempt.
    """
    client, wa, ids = ent
    tenant, pid = programme
    _flag(wa, True)

    _login(client, ids["olivia"])                       # the officer registers a site
    client.post(f"/enterprise/programmes/{pid}/beneficiaries/new", data={
        "_csrf": "testtoken", "code": "RO-01", "name": "Read Only Basic",
        "beneficiary_type": "school",
    }, follow_redirects=True)
    with wa.get_db() as c:
        bid = beneficiaries.list_beneficiaries(c, tenant, pid)[-1]["id"]

    _login(client, ids["musa"])                         # the manager only looks
    body = client.get(f"/enterprise/beneficiaries/{bid}").get_data(as_text=True)
    assert "read-only" in body.lower()
    assert "Save Changes" not in body

    # ...and the server agrees, which is the part that actually matters.
    r = client.post(f"/enterprise/beneficiaries/{bid}", data={
        "_csrf": "testtoken", "name": "Renamed By Someone Who May Not",
    })
    assert r.status_code == 403
