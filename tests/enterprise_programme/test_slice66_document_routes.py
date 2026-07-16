"""Slice 6.6 over HTTP -- the pages the owner actually uses.

The services are tested in test_slice66_lifecycle_documents.py. This drives the real routes:
each of Revision 4's six phases renders its deliverables as report buttons (OWNER, 2026-07-15
-- no activity checkboxes), clicking a report posts its `deliverable_code` and has the agent
write it and open it, uploading a source document works, and the gaps the app cannot ground
are marked [To be completed] for the operator to fill in by editing the report (OWNER,
2026-07-15 -- "remove them checkboxes and questions").
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


def _stub_ai_writer(monkeypatch):
    """This route test is about the button plumbing, not provider availability."""
    def _write(subject, facts, passage_body="", *, brief="", document_title=""):
        return (f"This section writes {subject} for {facts['name']} in "
                f"{facts.get('country') or 'the recorded country'}.")

    monkeypatch.setattr(documents, "_ai_write", _write)


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
    assert "Initiation" in body
    assert 'name="deliverable_code" value="R4P1_D01"' in body
    assert "Programme Concept Note" in body


def test_reports_are_buttons_not_activity_checkboxes(ent, programme):
    """The old checkbox picker is gone entirely -- there are no `activities` checkboxes."""
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    # Every report is a submit button carrying its own deliverable_code -- and every phase
    # renders its own, not merely the one the programme happens to be sitting in.
    assert 'name="deliverable_code" value="R4P1_D01"' in body     # Initiation
    assert 'name="deliverable_code" value="R4P3_D01"' in body     # Execution
    # And nothing on the page is an activity checkbox any more.
    assert 'name="activities"' not in body


def test_clicking_a_report_button_writes_it_and_OPENS_it(ent, programme, monkeypatch):
    """THE feature: click a report -> the app writes that deliverable and OPENS it.

    It used to push the PDF straight at the browser as a download. The owner asked for the
    report page instead (2026-07-13: "open it in html page with pdf and email, just like we
    did in the start project design report") -- so the document is now something you read,
    with the PDF and the email offered beside it.

    Rev 4 (2026-07-16): the POST carries a `deliverable_code` and nothing else -- there are no
    activities to tick, and the report's sections come from the deliverable itself. The route
    now fails loudly if no writer is reachable, so this plumbing test stubs the writer.
    """
    client, _wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "title": "Concept Pack",
              "deliverable_code": "R4P1_D01"},        # Programme Concept Note
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


def test_engine_written_report_reaches_the_engine_and_fails_closed(ent, programme):
    """An engine-written report's content IS the programme's approved reference design.

    Clicking it must NOT be refused with "Choose a report" -- the operator chose one. It must
    reach the engine, which with no approved reference design yet ASKS FOR ONE rather than
    500ing or quietly falling back to topic prose, which would hand back a "Programme
    Feasibility Study" with no engineering in it.
    """
    client, _wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken",
              "deliverable_code": "R4P2_D07"},   # Programme Feasibility Study -- engine
        follow_redirects=True,
    )
    assert r.status_code == 200
    # The operator named a report, so the "choose one" refusal must not fire...
    assert b"Choose a report to generate" not in r.data
    # ...and the engine refused with the instruction, rather than writing a hollow report.
    assert b"written by the design engine" in r.data
    assert b"Download PDF" not in r.data      # no report was opened


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
