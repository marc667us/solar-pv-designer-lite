"""Slice 6.6 over HTTP -- the pages the owner actually uses.

The services are tested in test_slice66_lifecycle_documents.py. This drives the real routes:
each phase renders its reports as buttons (OWNER, 2026-07-15 -- no activity checkboxes),
clicking a report has the agent write it and open it, uploading a source document works, and
the gaps the app cannot ground come back as an answerable form on the answers page.
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


def test_the_page_renders_reports_as_buttons_grouped_by_phase(ent, programme):
    """OWNER, 2026-07-15: no activity checkboxes. Each phase lists its reports as buttons;
    clicking one has the agent write that report."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.get(f"/enterprise/programmes/{programme}/lifecycle-documents")
    assert r.status_code == 200
    body = r.data.decode()
    # A phase heading and one of its report buttons, straight from the deliverable list.
    assert "Programme Concept and Opportunity Identification" in body
    assert 'name="deliverable_code" value="P01_D01"' in body
    assert "Programme concept note" in body


def test_reports_are_buttons_not_activity_checkboxes(ent, programme):
    """The old checkbox picker is gone entirely -- there are no `activities` checkboxes."""
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    # Every report is a submit button carrying its own deliverable_code.
    assert 'name="deliverable_code" value="P01_D01"' in body
    assert 'name="deliverable_code" value="P03_D01"' in body
    # And nothing on the page is an activity checkbox any more.
    assert 'name="activities"' not in body


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


def test_generating_with_no_report_chosen_is_refused(ent, programme):
    client, _wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken"}, follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Choose a report to generate" in r.data


def test_engine_written_report_bypasses_the_choose_a_report_refusal(ent, programme):
    """An engine-written report (e.g. the technical feasibility report) takes NO activities --
    the design engine IS its content. Clicking it must NOT be refused with "Choose a report";
    it proceeds to the engine, which (with no approved reference design yet) asks for one
    rather than 500ing or falling back to prose."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "P04_D01"},  # engine: technical
        follow_redirects=True,
    )
    assert r.status_code == 200
    # The no-activities refusal did NOT fire -- is_engine_written short-circuits it.
    assert b"Choose a report to generate" not in r.data


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


def test_clicking_a_report_writes_it_and_the_gap_is_answerable(ent, programme):
    """OWNER, 2026-07-15: click a report button -> the agent writes it (covering the whole
    phase) -> anything it cannot ground is answerable on the answers page -> answering it
    fills the section in."""
    client, wa, uid = ent
    _login(client, uid)

    # Click the "Programme concept note" report button. The agent covers the whole Concept
    # phase; P01_A01 ("register the programme idea") is a genuine gap it holds no fact for.
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "P01_D01"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    # It OPENS as a report, it does not push a PDF at the browser -- and it opened as THIS
    # report: the deliverable's own title, with the report actions (PDF) beside it.
    assert not r.data.startswith(b"%PDF-")
    assert b"Programme concept note" in r.data
    assert b"Download PDF" in r.data

    # Every lifecycle question is editable on the answers page, the agent's answer in the box.
    body = client.get(
        f"/enterprise/programmes/{programme}/answers").data.decode()
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
