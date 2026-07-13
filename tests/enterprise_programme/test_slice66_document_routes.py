"""Slice 6.6 over HTTP -- the pages the owner actually uses.

The services are tested in test_slice66_lifecycle_documents.py. This drives the real routes:
the five lifecycle stages render with their activities, ticking activities and pressing
Generate produces a PDF, uploading a source document works, and the questions the app raises
come back as an answerable form.
"""

from __future__ import annotations

import io
import os
import sqlite3
import tempfile

import pytest

import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import documents, flags  # noqa: E402

# The enterprise routes are registered by wsgi.py, not by web_app.py -- importing web_app
# alone gives an app with no /enterprise routes at all, and every request 404s.
if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )


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
    os.environ.setdefault("SECRET_KEY", "test-secret-key-enterprise-66")
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
        " plan, is_admin, name) VALUES ('owen','owen@example.com','',1,'free',0,'Owen')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='owen'").fetchone()[0]
    conn.close()

    with wa.app.test_client() as client:
        yield client, wa, uid

    wa.DB_PATH = original_db
    flags.clear_cache()


@pytest.fixture(scope="module")
def programme(ent):
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
    return pid


def test_the_page_renders_the_five_lifecycle_stages(ent, programme):
    """Initiation / Planning / Implementation / Monitoring / Closure -- the owner's model."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.get(f"/enterprise/programmes/{programme}/lifecycle-documents")
    assert r.status_code == 200
    body = r.data.decode()
    for stage in ("Initiation", "Planning", "Implementation", "Monitoring", "Closure"):
        assert stage in body


def test_the_activities_are_checkboxes_grouped_under_their_stage(ent, programme):
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    # An activity from Initiation and one from Planning, each a real checkbox.
    assert 'name="activities" value="P01_A01"' in body
    assert 'name="activities" value="P03_A01"' in body
    # And the stage select-all is wired to the stage class the boxes carry.
    assert 'data-scope="sS2_PLANNING"' in body
    assert "sS2_PLANNING" in body


def test_ticking_activities_and_generating_OPENS_the_report(ent, programme):
    """THE feature: tick activities -> the app writes the document and OPENS it as a report.

    It used to push the PDF straight at the browser as a download. The owner asked for the
    report page instead (2026-07-13: "open it in html page with pdf and email, just like we
    did in the start project design report") -- so the document is now something you read,
    with the PDF and the email offered beside it.
    """
    client, _wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "title": "Concept Pack",
              "activities": ["P01_A01", "P01_A02", "P03_A01"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert not r.data.startswith(b"%PDF-")
    body = r.data.decode()
    assert "Concept Pack" in body
    assert "Download PDF" in body        # the PDF is still one click away


def test_generating_with_nothing_ticked_is_refused(ent, programme):
    client, _wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "activities": []}, follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Tick at least one" in r.data


def test_uploading_a_source_document_then_using_it(ent, programme):
    """The second half of the ask: my document becomes the lifecycle document's material."""
    client, _wa, uid = ent
    _login(client, uid)

    src = (b"Funding Sources\n\n"
           b"Funding is provided by the Ghana Infrastructure Investment Fund as a "
           b"concessional facility repaid over fifteen years.\n")
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/upload",
        data={"_csrf": "testtoken", "title": "Ministry Brief",
              "document": (io.BytesIO(src), "brief.txt")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Ministry Brief" in r.data


def test_the_questions_the_app_raises_come_back_as_an_answerable_form(ent, programme):
    """generate -> the app asks -> the page shows the question -> answering fills it in."""
    client, wa, uid = ent
    _login(client, uid)

    # Generate something the app holds NO fact for, so a question is raised under the
    # section it wrote. (P02_A09 "define approval authorities" no longer qualifies: the app
    # now writes it from the organisation's own type and country. P01_A01, "register the
    # programme idea", is a genuine gap.)
    client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "activities": ["P01_A01"]},
        follow_redirects=True,
    )

    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()
    assert "need your answer" in body
    assert 'name="answer[P01_A01]"' in body

    # Answer it.
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/answers",
        data={"_csrf": "testtoken",
              "answer[P01_A01]": "The idea was tabled by the Ministry in 2026."},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"answer(s) saved" in r.data

    # THIS question is gone -- not "no questions exist". The fixture is module-scoped, so
    # earlier tests in this file have raised their own questions against the same programme,
    # and they are legitimately still open. Asserting an empty list would be asserting that
    # answering one question silently closed three others.
    with wa.get_db() as c:
        tid = c.execute("SELECT id FROM enterprise_tenants "
                        "WHERE legal_name='Ministry of Energy'").fetchone()[0]
        still_open = {q["activity_code"]
                      for q in documents.outstanding_questions(c, tid, programme)}
        assert "P01_A01" not in still_open

        doc_id = documents.generate_document(
            c, tid, uid, programme, activity_codes=["P01_A01"], use_ai=False,
        )
        md = documents.get_document(c, tid, doc_id)["markdown"]

    # The answer IS the section now, and the section no longer asks anything.
    assert "The idea was tabled by the Ministry in 2026." in md
    assert documents.THIN_SECTION_MARKER not in md
