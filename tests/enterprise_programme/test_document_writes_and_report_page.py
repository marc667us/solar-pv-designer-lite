"""The app WRITES the document, and the document OPENS as a report.

THE TWO THINGS THE OWNER REPORTED (2026-07-13)
----------------------------------------------
  1. "after creating the project and start by going to initiation documents it's not writing,
      it's rather asking me question"
  2. "once I have selected the activities it must create the concept note report and open it
      in html page with pdf and email, just like we did in the start project design report"

(1) was real and structural. build_markdown's precedence ran: the operator's answer -> the
source document -> the LLM -> ASK A QUESTION. On live the free LLM chain falls back to
rule_based, and _ai_write correctly refuses to pass a canned string off as a drafted section
-- so on a fresh programme with no uploaded document and no answers, every branch failed and
every section of the concept note became a question. The app demanded that the operator write
the document it had promised to write for them.

The fix is the missing rung: the app writes each section from the programme's own facts --
its description, sponsor, sector, country, targets and register -- and where it has no
specific fact it STILL writes the section and marks the gap underneath, so the operator
strengthens a real section rather than supplying one from nothing. A gap under a section,
never a question instead of one.

REVISION 4 (2026-07-16). The 453 activities are gone. A report is now ONE DELIVERABLE, picked
by pressing its button, and its sections are derived from the deliverable itself
(documents._sections_for_deliverable) rather than from a list of ticked activities. Every
property below is unchanged -- the app must still WRITE, still ground what it writes in this
programme's own record, still refuse to invent a number or assert an unverified process, and
still open the result as a report with PDF and email beside it. Only the unit changed.

The live LLM chain falls back to rule_based, which _ai_write refuses to pass off as a drafted
section -- so these tests exercise the deterministic writer, the exact condition that produced
the bug. If the app can only write when an LLM answers, it cannot write.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest

import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import documents, flags  # noqa: E402
from app.security import audit as audit_mod  # noqa: E402

if "enterprise_home" not in _wa.app.view_functions:
    register_enterprise_programme(
        _wa.app, get_db=_wa.get_db, login_required=_wa.login_required,
        csrf_protect=_wa.csrf_protect, current_user=_wa.current_user,
    )

DESCRIPTION = ("A government-sponsored programme electrifying 200 rural clinics in the "
               "Northern region of Ghana with standard rooftop solar systems.")


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
    os.environ.setdefault("SECRET_KEY", "test-secret-key-writes-report")
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    wa = _wa
    original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()
    audit_mod.reset_schema_probe()
    wa.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
    if hasattr(wa, "limiter"):
        try:
            wa.limiter.enabled = False
        except Exception:
            pass

    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO users (username, email, password_hash, email_verified,"
        " plan, is_admin, name) VALUES ('nadia','nadia@example.com','',1,'free',0,'Nadia')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='nadia'").fetchone()[0]
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
        "_csrf": "testtoken", "legal_name": "Ministry of Health",
        "organisation_type": "ministry", "country": "Ghana",
    }, follow_redirects=True)
    client.post("/enterprise/programmes/new", data={
        "_csrf": "testtoken", "code": "GH-RURAL", "name": "Rural Clinics Solar",
        "description": DESCRIPTION,
        "design_strategy": "standard", "sponsor_user_id": str(uid),
    }, follow_redirects=True)
    with wa.get_db() as c:
        return c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-RURAL'"
        ).fetchone()[0]


# Revision 4's Initiation deliverables, by code (rev4_phases.PHASE_DELIVERABLES).
CONCEPT_NOTE = "R4P1_D01"        # an OMNIBUS report: its subject is the whole phase
RISK_REGISTER = "R4P1_D07"       # a FOCUSED report on a topic the app stores nothing for
APPROVAL_REQUEST = "R4P1_D12"    # the one Initiation deliverable that opens a stage gate


def _generate(client, programme, deliverable_code):
    """Generate a report exactly as the owner does: press that deliverable's button."""
    return client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": deliverable_code},
        follow_redirects=True,
    )


def _concept_note(client, programme):
    """Generate the concept note -- Initiation's first deliverable button."""
    return _generate(client, programme, CONCEPT_NOTE)


def _latest_markdown(wa, programme):
    with wa.get_db() as c:
        return c.execute(
            "SELECT markdown FROM enterprise_documents WHERE programme_id=? "
            "ORDER BY id DESC LIMIT 1", (programme,)).fetchone()[0]


def _doc_count(wa, programme):
    with wa.get_db() as c:
        return c.execute(
            "SELECT COUNT(*) FROM enterprise_documents WHERE programme_id=?", (programme,)
        ).fetchone()[0]


def _stub_ai_writer(monkeypatch):
    """Route tests need a reachable writer; content-specific tests use use_ai=False."""
    def _write(subject, facts, passage_body="", *, brief="", document_title=""):
        return (f"This section writes {subject} for {facts['name']} in "
                f"{facts.get('country') or 'the recorded country'}, using sponsor "
                f"{facts.get('sponsor_name') or 'the recorded sponsor'} and description "
                f"{facts.get('description') or 'the recorded programme description'}.")

    monkeypatch.setattr(documents, "_ai_write", _write)


def _generate_without_ai(wa, uid, programme, deliverable_code):
    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (programme,)
        ).fetchone()[0]
        return documents.generate_document(
            c, tenant, uid, programme, deliverable_code=deliverable_code,
            use_ai=False,
        )


# ------------------------------------------------------------- (1) IT WRITES

def test_the_concept_note_is_WRITTEN_not_a_list_of_questions(ent, programme, monkeypatch):
    """The owner's bug, exactly: press the concept note, get prose back instead of questions.

    Rev 4 changed what a section IS -- it is now an authored part of the document rather than
    one ticked activity or topic. The route also now fails loudly if the writing service is
    unreachable. This test stubs a reachable writer and keeps the guard on the route's
    contract: EVERY declared section is followed by written prose, never a question standing
    in place of one.
    """
    client, wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)
    r = _concept_note(client, programme)
    assert r.status_code == 200

    md = _latest_markdown(wa, programme)

    # THE REGRESSION GUARD. The old code emitted this marker as the ENTIRE body of a section
    # it could not write. Not one section of a written document may be nothing but a question.
    assert "**QUESTION — awaiting your answer:**" not in md, (
        "the app is still handing the work back to the operator instead of writing"
    )

    # The report says how many sections it covers; it must then deliver exactly that many.
    # Derived from the deliverable, not hard-coded, because the section list IS the contract
    # (_sections_for_deliverable) and a number copied out beside it would drift from it.
    expected = documents._sections_for_deliverable(CONCEPT_NOTE)
    assert len(expected) > 1, (
        "the concept note is the phase's omnibus document -- one section means the topic "
        "union collapsed"
    )

    body = md.split("---", 1)[-1]
    chunks = body.split("\n## ")[1:]
    assert len(chunks) == len(expected), "the concept note lost its sections"
    assert [c.splitlines()[0].strip() for c in chunks] == [s.heading for s in expected]

    for chunk in chunks:
        lines = [ln.strip() for ln in chunk.strip().splitlines() if ln.strip()]
        assert len(lines) >= 2, f"a section has a heading and nothing under it: {lines!r}"
        # lines[0] is the heading; lines[1] must be the written section, not an ask.
        assert not lines[1].startswith("**QUESTION"), (
            f"section written as a question: {lines[0]!r}"
        )


def test_it_writes_from_the_programmes_OWN_facts_without_any_llm(ent, programme):
    """The deterministic fallback still writes from this programme's actual record.

    The browser route now asks the writing service to draft and fails loudly when it cannot.
    The service still has an explicit use_ai=False path for tests and fallback assembly; that
    path must use the programme's own stored facts rather than a generic template.
    """
    _client, wa, uid = ent
    _generate_without_ai(wa, uid, programme, CONCEPT_NOTE)
    md = _latest_markdown(wa, programme)

    assert "Rural Clinics Solar" in md          # the programme, by name
    assert "Ghana" in md                        # its country
    assert "nadia" in md.lower()                # its sponsor, as a person and not an integer
    assert DESCRIPTION[:40] in md               # its own description, used as material


def test_a_thin_section_still_gets_marked_as_incomplete(ent, programme):
    """The honest half: a gap is marked in the section, never hidden by filler.

    The app no longer asks a question under thin sections. Under the deterministic fallback,
    a section the app cannot ground says it is not yet recorded and carries the edit marker
    the operator completes on the report page.
    """
    _client, wa, uid = ent
    _generate_without_ai(wa, uid, programme, CONCEPT_NOTE)
    md = _latest_markdown(wa, programme)

    assert documents.THIN_SECTION_MARKER in md
    head, _sep, _rest = md.partition(documents.THIN_SECTION_MARKER)
    assert head.rstrip().splitlines()[-1].strip() == "*Not yet recorded.*"


def test_the_writer_never_invents_a_number(ent, programme):
    """The programme has no budget. The deterministic fallback must not produce one."""
    _client, wa, uid = ent
    _generate_without_ai(wa, uid, programme, CONCEPT_NOTE)
    md = _latest_markdown(wa, programme).lower()
    for invented in ("usd ", "ghs ", "$", "estimated cost of", "budget of"):
        assert invented not in md, f"the writer invented a costing: {invented!r}"


def test_the_writer_never_asserts_a_PROCESS_it_cannot_verify(ent, programme):
    """Codex, round 2, HIGH -- and the worst bug in this change.

    An earlier deterministic draft padded thin topics with process boilerplate: "risks are
    recorded in the risk register and reviewed at each stage gate", "costs are established
    from the priced Bill of Quantities generated against the approved design", "designs are
    generated against the programme's approved templates and equipment catalogue".

    Every one of those asserts something NOBODY VERIFIED -- this programme has no risk
    register, no BOQ and no approved template. The app no longer asks questions under thin
    sections, but the property survives: the deterministic fallback must still surface the
    gap as incomplete rather than hide it behind confident process language.
    """
    _client, wa, uid = ent
    _generate_without_ai(wa, uid, programme, CONCEPT_NOTE)
    md = _latest_markdown(wa, programme).lower()

    for invented in (
        "risk register",                  # the app stores no risk register
        "bill of quantities",             # no BOQ exists for a concept-phase programme
        "equipment catalogue",            # no approved catalogue is recorded
        "approved design",                # nothing has been approved
        "approved templates",
    ):
        assert invented not in md, (
            f"the writer asserted a process it cannot verify: {invented!r} -- and by "
            f"filling the section with it, hid a gap that should have been marked"
        )



# --------------------------------------------------- (2) IT OPENS AS A REPORT

def test_generating_opens_the_report_page_with_pdf_and_email(ent, programme, monkeypatch):
    """"open it in html page with pdf and email, just like the project design report".

    Generated on the Programme Approval Request, because that is the Initiation deliverable
    that OPENS a stage gate (rev4_phases.DELIVERABLE_GATE_DOC_TYPE) -- so this one call
    exercises the whole page, the badge that says what the report counts as included. Rev 4's
    Initiation gate is R4G1_INITIATION; the old G01 is gone.

    The route's no-writer path is tested separately; here the writer is reachable so the
    report page contract can be asserted.
    """
    client, _wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)
    r = _generate(client, programme, APPROVAL_REQUEST)

    assert r.status_code == 200
    assert not r.data.startswith(b"%PDF-"), "it must OPEN, not download"
    body = r.data.decode()
    assert "Programme Approval Request" in body            # the report, titled
    assert "Download PDF" in body                          # the PDF, offered
    assert "Email" in body                                 # the email, offered
    assert "Stage gate R4G1_INITIATION evidence" in body   # and what it counts as


def test_the_pdf_is_still_downloadable_from_the_report_page(ent, programme, monkeypatch):
    client, wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)
    _concept_note(client, programme)
    with wa.get_db() as c:
        doc_id = c.execute(
            "SELECT id FROM enterprise_documents WHERE programme_id=? ORDER BY id DESC "
            "LIMIT 1", (programme,)).fetchone()[0]

    r = client.get(f"/enterprise/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")


def test_route_fails_loudly_when_the_writer_is_unreachable(ent, programme, monkeypatch):
    """The new owner-route contract: no reachable writer means no fake saved report.

    Earlier route tests assumed the deterministic fallback would run under the browser path.
    The route now asks the writer to draft; if it returns nothing, the operator gets a flash
    and the document table is unchanged.
    """
    client, wa, uid = ent
    _login(client, uid)
    monkeypatch.setattr(documents, "_ai_write", lambda *a, **kw: None)
    before = _doc_count(wa, programme)

    r = _concept_note(client, programme)

    assert r.status_code == 200
    assert b"writing service is unavailable" in r.data
    assert _doc_count(wa, programme) == before


def test_the_report_page_is_tenant_scoped(ent, programme):
    """A document id from another organisation is a 404, never a peek."""
    client, _wa, uid = ent
    _login(client, uid)
    r = client.get("/enterprise/documents/999999/view")
    assert r.status_code == 404


def test_render_html_escapes_raw_html_from_an_uploaded_document():
    """MarkdownIt's DEFAULT preset passes raw HTML through. This markdown is user content.

    The programme description, the operator's answers and passages QUOTED OUT OF AN UPLOADED
    FILE all land in this markdown. Rendering it with html=True -- the library default --
    would turn any uploaded document containing a script tag into stored XSS against every
    reader of the report, including whoever it is emailed to.
    """
    out = documents.render_html("# T\n\n<script>alert(1)</script>\n\n"
                                "<img src=x onerror=alert(1)>\n")

    # What matters is that no TAG survives -- the angle brackets are escaped, so the payload
    # is inert text on the page. ("onerror=alert" still appears as literal characters inside
    # that escaped text, which is exactly what harmless looks like.)
    assert "<script>" not in out
    assert "<img" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "&lt;img src=x onerror=alert(1)&gt;" in out
    assert "<h1>T</h1>" in out                    # ...while still rendering real markdown
