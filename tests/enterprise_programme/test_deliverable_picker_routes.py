"""The deliverable picker, over HTTP -- the half that made the model reachable.

The deliverables model landed with no way to reach it from a browser. `generate_document`
accepted a `deliverable_code`, and every gate would honour the document it produced -- but
the Lifecycle Documents page never sent one, so in the live app EVERY generated document was
still stamped "lifecycle_document", still opened no gate, and the only thing that could open
a gate was still a typed-in title with nothing behind it. A feature the UI cannot reach is a
feature the owner does not have.

So these tests drive the ROUTES, not the service (the service is covered by
test_deliverables_open_gates.py). They ask the three questions that decide whether the model
is actually wired:

  * does the page OFFER Revision 4's 112 deliverables, and say which five open a gate?
  * does choosing one in the form make the generated document open that gate?
  * does a bad choice get REFUSED, rather than quietly downgraded to a document that looks
    right and opens nothing?

REVISION 4 (2026-07-16): the model behind this page is now six phases of deliverable BUTTONS
(rev4_phases), and the 453 lifecycle activities are gone. So is the invariant this module
used to close last -- "no phase holds more activities than one document may cover" -- because
nothing is ticked and nothing is derived any more: a report's sections come from the
deliverable itself. A report is one of the 112 or it is refused; there is no free-form path
left to downgrade to.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile

import pytest

import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import documents, flags, gates, rbac, rev4_phases  # noqa: E402
from app.security import audit as audit_mod                             # noqa: E402

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
    os.environ.setdefault("SECRET_KEY", "test-secret-key-deliverable-picker")
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    wa = _wa
    original_db = wa.DB_PATH
    wa.DB_PATH = db_path
    wa.init_db()

    # The audit module probes `audit_logs`' columns ONCE per process and caches the answer.
    # This module gets a brand-new temp database whose audit_logs may differ in shape from
    # whichever database happened to prime that cache first -- and a wrong probe makes every
    # audit INSERT fail, which under C12 ("audit or nothing") silently rolls back programme
    # creation and leaves this module's fixtures with no programme at all. Passing alone and
    # failing in the full suite is exactly what that looks like.
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
        " plan, is_admin, name) VALUES ('dora','dora@example.com','',1,'free',0,'Dora')")
    conn.commit()
    uid = conn.execute("SELECT id FROM users WHERE username='dora'").fetchone()[0]
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
        "_csrf": "testtoken", "code": "GH-CLINICS", "name": "Ghana Clinics Solar",
        "description": ("A government-sponsored programme electrifying 200 rural clinics "
                        "in the Northern region with standard rooftop solar."),
        "design_strategy": "standard", "sponsor_user_id": str(uid),
    }, follow_redirects=True)

    with wa.get_db() as c:
        return c.execute(
            "SELECT id FROM enterprise_programme_registry WHERE code='GH-CLINICS'"
        ).fetchone()[0]


def _doc_type_of(wa, doc_id: int) -> str:
    with wa.get_db() as c:
        return c.execute(
            "SELECT doc_type FROM enterprise_documents WHERE id=?", (doc_id,)
        ).fetchone()[0]


def _latest_doc_id(wa, programme: int) -> int:
    with wa.get_db() as c:
        return c.execute(
            "SELECT id FROM enterprise_documents WHERE programme_id=? "
            "ORDER BY id DESC LIMIT 1", (programme,)
        ).fetchone()[0]


def _doc_count(wa, programme: int) -> int:
    with wa.get_db() as c:
        return c.execute(
            "SELECT COUNT(*) FROM enterprise_documents WHERE programme_id=?", (programme,)
        ).fetchone()[0]


def _stub_ai_writer(monkeypatch):
    """Route tests are about routing; the writing service is stubbed as reachable."""
    def _write(subject, facts, passage_body="", *, brief="", document_title=""):
        return (f"This section writes {subject} for {facts['name']} in "
                f"{facts.get('country') or 'the recorded country'}.")

    monkeypatch.setattr(documents, "_ai_write", _write)


# ------------------------------------------------------------------ the page offers them

def test_the_page_offers_every_one_of_the_112_deliverables(ent, programme):
    """A deliverable the operator cannot select is a document the app cannot be asked for."""
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    assert 'name="deliverable_code"' in body, "the picker is not on the page at all"
    missing = [code for code in rev4_phases.DELIVERABLE_INDEX
               if f'value="{code}"' not in body]
    assert not missing, f"deliverables the operator cannot choose: {sorted(missing)[:10]}"


def test_the_page_names_the_gate_each_of_the_five_opens(ent, programme):
    """The operator must know, BEFORE clicking, which report is a gate's evidence.

    OWNER 2026-07-15: reports are BUTTONS now, not <option>s. The gate must still be
    announced ON THE REPORT'S OWN BUTTON -- not merely somewhere on the page, which would
    pass even if the gate badge sat on the wrong report.

    Revision 4 has five gates rather than fourteen, and each asks for exactly one document:
    its phase's own approval/closure report (rev4_phases.DELIVERABLE_GATE_DOC_TYPE).
    """
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    for code, doc_type in rev4_phases.DELIVERABLE_GATE_DOC_TYPE.items():
        gate = gates.GATE_OF_DOC_TYPE[doc_type]
        # the <button> for THIS deliverable, from its value to the closing tag
        m = re.search(rf'<button[^>]*value="{code}"[^>]*>(.*?)</button>', body, re.S)
        assert m, f"{code} is not a report button on the page"
        assert gate in m.group(1), (
            f"{code}'s own button does not announce that it opens {gate}: {m.group(0)[:200]}"
        )
    assert "opens stage gate R4G1_INITIATION" in body


def test_free_form_is_no_longer_offered_reports_are_buttons(ent, programme):
    """OWNER 2026-07-15: reports are buttons; the free-form picker option is gone.

    The old page offered a "free-form document" option that satisfied no gate. The owner
    replaced the whole picker with report buttons, so free-form is no longer offered on the
    page -- and under Revision 4 the route no longer accepts an empty deliverable_code either
    (see test_omitting_the_deliverable_is_REFUSED_and_writes_nothing).
    """
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()
    assert "free-form document" not in body
    assert 'name="deliverable_code"' in body           # the report buttons are present
    assert 'type="checkbox" name="activities"' not in body   # no activity checkboxes


# ------------------------------------------------- choosing one in the form opens the gate

def test_choosing_the_planning_approval_request_in_the_FORM_opens_gate_2(
        ent, programme, monkeypatch):
    """The end-to-end claim: a browser POST is what must open the gate.

    Gate 2 (R4G2_PLANNING) is used rather than Gate 1 because its only demand IS the document
    -- Gate 1 also requires the programme to name a sponsor -- so if the gate opens, it opened
    because of what the form sent, and nothing else.

    The route now fails loudly if the writing service is unreachable. This test is not about
    that outage path, so it stubs the writer as reachable and keeps the assertion on the route:
    the posted deliverable becomes the gate document.
    """
    client, wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)

    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (programme,)
        ).fetchone()[0]
        with pytest.raises(gates.EnterpriseGateError):
            # shut, for want of the Planning Approval Request
            gates.evaluate_gate(c, tenant, programme, "R4G2_PLANNING")

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "R4P2_D27"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    # The document OPENS as a report (owner, 2026-07-13) rather than landing in the
    # downloads folder -- with the PDF and the email offered from that page.
    assert b"Planning Approval Request" in r.data
    assert b"Download PDF" in r.data

    assert (_doc_type_of(wa, _latest_doc_id(wa, programme))
            == "planning_approval_request")

    with wa.get_db() as c:
        gates.evaluate_gate(c, tenant, programme, "R4G2_PLANNING")   # ...and now it opens


def test_omitting_the_deliverable_is_REFUSED_and_writes_nothing(ent, programme):
    """REV 4: there is no free-form document any more, so there is nothing to fall back to.

    The route used to accept an empty deliverable_code and write a "lifecycle_document" --
    evidence for nothing, but a document. Revision 4's model is a phase of deliverable
    BUTTONS: every button posts its own code, so a POST with no code is a broken form, not a
    request for a general-purpose document. It is refused with an instruction, and nothing is
    written -- the same discipline as an unknown code below.
    """
    client, wa, uid = ent
    _login(client, uid)
    before = _doc_count(wa, programme)

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "", "title": "Working Notes"},
        follow_redirects=True,
    )
    assert r.status_code == 200, "an empty form is a user error, not a 500"
    assert b"Choose a report to generate." in r.data
    assert _doc_count(wa, programme) == before, "a document was written with no deliverable"


def test_an_unknown_deliverable_from_the_browser_is_refused_not_downgraded(ent, programme):
    """A tampered or stale form must not yield a document that opens nothing in silence.

    Silently falling back to a generic "lifecycle_document" would give the operator a document
    that looks right, is named right, and satisfies no gate -- the exact failure the
    deliverable model exists to end, wearing a better disguise. It must be refused, out loud.

    The code below is shaped like a Rev 4 code and is not one: a form left over from the old
    16-phase page, or one edited by hand, must be caught by what the app KNOWS rather than by
    what the string looks like.
    """
    client, wa, uid = ent
    _login(client, uid)
    before = _doc_count(wa, programme)

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "R4P9_D99"},
        follow_redirects=True,
    )
    assert r.status_code == 200, "a bad code is a user error, not a 500"
    assert b"unknown deliverable" in r.data.lower()
    assert _doc_count(wa, programme) == before, "nothing may be written for a bad code"


def test_the_register_says_what_each_document_counts_as(ent, programme, monkeypatch):
    """A document's whole purpose is what it is evidence FOR. The register must say."""
    client, _wa, uid = ent
    _login(client, uid)
    _stub_ai_writer(monkeypatch)
    client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "R4P2_D27"},
        follow_redirects=True,
    )
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()
    # The Planning Approval Request generated above, which is R4G2_PLANNING's evidence.
    # OWNER 2026-07-15: a document that is not one of the deliverables is now simply labelled
    # a "Report"; the old "Free-form -- satisfies no gate" wording went with the picker option
    # it described, and Revision 4 removed the free-form path that produced such documents.
    assert "Gate R4G2_PLANNING evidence" in body
    assert "Free-form — satisfies no gate" not in body


# -------------------------------------------------- producing evidence is an EDIT, not a report

def test_report_generate_alone_cannot_manufacture_gate_evidence():
    """A read-only auditor must not be able to produce a "signed contract".

    Found by the Supervisor security review. A gate predicate is a bare existence check on
    doc_type, and every other way of creating such a row (workflows.register_document, the
    upload path) has always required `programme.edit`. `report.generate` is deliberately held
    by roles with NO edit power -- auditor, executive_viewer, esg_officer -- and by
    programme_sponsor and steering_committee, who are the people who SIGN the gates.

    Had generate_document stamped a gate doc_type under `report.generate` alone:
      * an auditor could have manufactured a programme's closure certificate, and
      * a sponsor could have generated a gate's evidence and then approved that same gate,
        which collapses the separation between producing evidence and signing it.
    """
    from app.enterprise_programme import constants as k

    offenders = {
        role for role, perms in k.ROLE_PERMISSIONS.items()
        if "report.generate" in perms and "programme.edit" not in perms
    }
    # If this is empty the test proves nothing -- the two permissions would be equivalent.
    assert offenders, "report.generate and programme.edit are no longer distinguishable"

    # The roles that can SIGN a gate must not also be able to mint its evidence on their own.
    signers = {r for r in offenders if "programme.approve" in k.ROLE_PERMISSIONS[r]}
    assert signers, "expected sponsor/steering_committee among them"


def test_a_generator_without_edit_rights_is_REFUSED_a_gate_deliverable(ent, programme):
    """The service, not merely the template, is what refuses. Over HTTP."""
    client, wa, uid = ent

    # A second user, admitted to the organisation as an AUDITOR -- a role that holds
    # report.generate and no edit power at all. Added through the real membership API rather
    # than a hand-written INSERT, so the test cannot drift from the schema.
    from app.enterprise_programme import tenancy

    with wa.get_db() as c:
        c.execute("INSERT OR IGNORE INTO users (username, email, password_hash, "
                  "email_verified, plan, is_admin, name) "
                  "VALUES ('ada','ada@example.com','',1,'free',0,'Ada')")
        aid = c.execute("SELECT id FROM users WHERE username='ada'").fetchone()[0]
        tid = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (programme,)
        ).fetchone()[0]
        tenancy.add_member(c, tid, aid, "auditor", uid)
        c.commit()

    # The premise: this role really can generate reports, and really cannot edit.
    with wa.get_db() as c:
        assert rbac.has_permission(c, tid, aid, "report.generate", programme_id=programme)
        assert not rbac.has_permission(c, tid, aid, "programme.edit", programme_id=programme)

    _login(client, aid)
    before = _latest_doc_id(wa, programme)

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        # -> programme_approval_request, the evidence R4G1_INITIATION will not open without
        data={"_csrf": "testtoken", "deliverable_code": "R4P1_D12"},
    )
    assert r.status_code == 403, "an auditor minted stage-gate evidence"
    assert _latest_doc_id(wa, programme) == before, "a document was written anyway"

    _login(client, uid)          # restore the module-scoped fixture's user


# ---------------------------------------------------------------------- the picker's promise

def test_gate_of_doc_type_is_derived_from_the_real_predicates():
    """The page's "opens stage gate R4Gx" promise must not be a hand-kept copy that can go
    stale."""
    assert len(gates.GATE_OF_DOC_TYPE) == 5, (
        "expected Revision 4's 5 gate documents by introspection -- if this is empty, every "
        "claim the picker makes about gates is unverified"
    )
    for doc_type, gate in gates.GATE_OF_DOC_TYPE.items():
        assert any(getattr(p, "required_doc_type", None) == doc_type
                   for p in gates.GATE_PREDICATES[gate]), (
            f"{gate} is advertised as opened by {doc_type}, but its predicates do not "
            f"demand it"
        )
