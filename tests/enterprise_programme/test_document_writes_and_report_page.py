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
specific fact it STILL writes the section and asks underneath for the one thing that would
strengthen it. A question under a section, never a question instead of one.

These tests run with use_ai off, which is the live condition that produced the bug. If the
app can only write when an LLM answers, it cannot write.
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


def _concept_note(client, programme):
    """Generate the concept note exactly as the owner did: pick it, take its phase."""
    return client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "P01_D01",
              # P01's fourteen activities -- what the picker ticks for you.
              "activities": [a for a, _t in
                             __import__("app.enterprise_programme.constants",
                                        fromlist=["x"]).PHASE_ACTIVITIES["P01_CONCEPT"]]},
        follow_redirects=True,
    )


def _latest_markdown(wa, programme):
    with wa.get_db() as c:
        return c.execute(
            "SELECT markdown FROM enterprise_documents WHERE programme_id=? "
            "ORDER BY id DESC LIMIT 1", (programme,)).fetchone()[0]


# ------------------------------------------------------------- (1) IT WRITES

def test_the_concept_note_is_WRITTEN_not_a_list_of_questions(ent, programme):
    """The owner's bug, exactly: 14 activities in, 14 questions out."""
    client, wa, uid = ent
    _login(client, uid)
    r = _concept_note(client, programme)
    assert r.status_code == 200

    md = _latest_markdown(wa, programme)

    # THE REGRESSION GUARD. The old code emitted this marker as the ENTIRE body of a section
    # it could not write. Not one section of a written document may be nothing but a question.
    assert "**QUESTION — awaiting your answer:**" not in md, (
        "the app is still handing the work back to the operator instead of writing"
    )

    # Every activity heading must be followed by prose, not by a bare question.
    body = md.split("---", 1)[-1]
    assert body.count("###") >= 14, "the concept note lost its sections"
    for chunk in body.split("###")[1:]:
        lines = [ln.strip() for ln in chunk.strip().splitlines() if ln.strip()]
        assert len(lines) >= 2, f"a section has a heading and nothing under it: {lines!r}"
        # lines[0] is the heading; lines[1] must be the written section, not an ask.
        assert not lines[1].startswith("**QUESTION"), (
            f"section written as a question: {lines[0]!r}"
        )


def test_it_writes_from_the_programmes_OWN_facts_without_any_llm(ent, programme):
    """Not a template with the activity name pasted in -- this programme's actual record."""
    client, wa, uid = ent
    _login(client, uid)
    _concept_note(client, programme)
    md = _latest_markdown(wa, programme)

    assert "Rural Clinics Solar" in md          # the programme, by name
    assert "Ghana" in md                        # its country
    assert "nadia" in md.lower()                # its sponsor, as a person and not an integer
    assert DESCRIPTION[:40] in md               # its own description, used as material


def test_a_thin_section_still_gets_written_and_asks_underneath(ent, programme):
    """The honest half: a gap is named UNDER a real section, never in place of one."""
    client, wa, uid = ent
    _login(client, uid)
    _concept_note(client, programme)
    md = _latest_markdown(wa, programme)

    if documents.THIN_SECTION_MARKER in md:
        # wherever the app asks, prose must come first
        head, _sep, _rest = md.partition(documents.THIN_SECTION_MARKER)
        assert head.rstrip().splitlines()[-1].strip(), (
            "the strengthen-note must sit under written prose, not replace it"
        )


def test_the_writer_never_invents_a_number(ent, programme):
    """The programme has no budget. The document must not produce one."""
    client, wa, uid = ent
    _login(client, uid)
    _concept_note(client, programme)
    md = _latest_markdown(wa, programme).lower()
    for invented in ("usd ", "ghs ", "$", "estimated cost of", "budget of"):
        assert invented not in md, f"the writer invented a costing: {invented!r}"


def test_the_writer_never_asserts_a_PROCESS_it_cannot_verify(ent, programme):
    """Codex, round 2, HIGH -- and the worst bug in this change.

    An earlier draft padded thin topics with process boilerplate: "risks are recorded in the
    risk register and reviewed at each stage gate", "costs are established from the priced
    Bill of Quantities generated against the approved design", "designs are generated against
    the programme's approved templates and equipment catalogue".

    Every one of those asserts something NOBODY VERIFIED -- this programme has no risk
    register, no BOQ and no approved template. And because the sentences made the section
    non-empty, they set thin=False, so NO QUESTION WAS RAISED: the gap was not merely left
    unfilled, it was HIDDEN behind confident process language. That is strictly worse than
    the bug it was introduced to fix.
    """
    client, wa, uid = ent
    _login(client, uid)
    _concept_note(client, programme)
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
            f"filling the section with it, suppressed the question that should have been "
            f"asked"
        )


def test_a_topic_with_no_stored_fact_ASKS_instead_of_reassuring(ent, programme):
    """The corollary: a gap must surface as a question, not as plausible-sounding filler.

    P02_A22, "establish the programme risk and issue registers", is a RISK-topic activity --
    and this app stores no risk data whatsoever. It is the exact activity the old boilerplate
    answered with "risks are recorded in its risk register and reviewed at each stage gate",
    a sentence that is confident, plausible, and backed by nothing. The section must be
    grounded in the description and must ASK.
    """
    client, wa, uid = ent
    _login(client, uid)
    client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "activities": ["P02_A22"]},
        follow_redirects=True,
    )
    md = _latest_markdown(wa, programme)
    assert "risk register" not in md.lower(), "the risk gap was papered over again"
    assert documents.THIN_SECTION_MARKER in md, (
        "a topic the app holds no data for was filled in rather than asked about"
    )


# --------------------------------------------------- (2) IT OPENS AS A REPORT

def test_generating_opens_the_report_page_with_pdf_and_email(ent, programme):
    """"open it in html page with pdf and email, just like the project design report"."""
    client, _wa, uid = ent
    _login(client, uid)
    r = _concept_note(client, programme)

    assert r.status_code == 200
    assert not r.data.startswith(b"%PDF-"), "it must OPEN, not download"
    body = r.data.decode()
    assert "Programme concept note" in body       # the report, titled
    assert "Download PDF" in body                 # the PDF, offered
    assert "Email" in body                        # the email, offered
    assert "Stage gate G01 evidence" in body      # and what it counts as


def test_the_pdf_is_still_downloadable_from_the_report_page(ent, programme):
    client, wa, uid = ent
    _login(client, uid)
    _concept_note(client, programme)
    with wa.get_db() as c:
        doc_id = c.execute(
            "SELECT id FROM enterprise_documents WHERE programme_id=? ORDER BY id DESC "
            "LIMIT 1", (programme,)).fetchone()[0]

    r = client.get(f"/enterprise/documents/{doc_id}/download")
    assert r.status_code == 200
    assert r.data.startswith(b"%PDF-")


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
