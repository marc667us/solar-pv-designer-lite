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

  * does the page OFFER the 144 deliverables, and say which nine open a gate?
  * does choosing one in the form make the generated document open that gate?
  * does a bad choice get REFUSED, rather than quietly downgraded to a free-form document
    that looks right and opens nothing?

And one invariant the picker's convenience depends on: selecting a deliverable ticks its
phase's activities for the operator, so no phase may hold more activities than one document
is allowed to cover -- otherwise the friendliest button on the page would be a guaranteed
error.
"""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile

import pytest

import web_app as _wa  # noqa: E402
from enterprise_programme_routes import register_enterprise_programme  # noqa: E402

from app.enterprise_programme import constants, documents, flags, gates, rbac  # noqa: E402
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


# ------------------------------------------------------------------ the page offers them

def test_the_page_offers_every_one_of_the_144_deliverables(ent, programme):
    """A Key Output the operator cannot select is a document the app cannot be asked for."""
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    assert 'name="deliverable_code"' in body, "the picker is not on the page at all"
    missing = [code for code in constants.DELIVERABLE_INDEX
               if f'value="{code}"' not in body]
    assert not missing, f"deliverables the operator cannot choose: {sorted(missing)[:10]}"


def test_the_page_names_the_gate_each_of_the_nine_opens(ent, programme):
    """The operator must know, BEFORE clicking, which report is a gate's evidence.

    OWNER 2026-07-15: reports are BUTTONS now, not <option>s. The gate must still be
    announced ON THE REPORT'S OWN BUTTON -- not merely somewhere on the page, which would
    pass even if the gate badge sat on the wrong report.
    """
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()

    for code, doc_type in constants.DELIVERABLE_GATE_DOC_TYPE.items():
        gate = gates.GATE_OF_DOC_TYPE[doc_type]
        # the <button> for THIS deliverable, from its value to the closing tag
        m = re.search(rf'<button[^>]*value="{code}"[^>]*>(.*?)</button>', body, re.S)
        assert m, f"{code} is not a report button on the page"
        assert gate in m.group(1), (
            f"{code}'s own button does not announce that it opens {gate}: {m.group(0)[:200]}"
        )
    assert "opens stage gate G01" in body


def test_free_form_is_no_longer_offered_reports_are_buttons(ent, programme):
    """OWNER 2026-07-15: reports are buttons; the free-form picker option is gone.

    The old page offered a "free-form document" option that satisfied no gate. The owner
    replaced the whole picker with report buttons, so free-form is no longer offered on the
    page (the route still accepts an empty deliverable_code for back-compat -- that is
    covered by test_omitting_the_deliverable_still_generates_a_free_form_document).
    """
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()
    assert "free-form document" not in body
    assert 'name="deliverable_code"' in body           # the report buttons are present
    assert 'type="checkbox" name="activities"' not in body   # no activity checkboxes


# ------------------------------------------------- choosing one in the form opens the gate

def test_choosing_the_charter_in_the_FORM_opens_gate_2(ent, programme):
    """The end-to-end claim: a browser POST is what must open the gate.

    Gate 2 is used rather than Gate 1 because its only demand IS the document -- so if the
    gate opens, it opened because of what the form sent, and nothing else.
    """
    client, wa, uid = ent
    _login(client, uid)

    with wa.get_db() as c:
        tenant = c.execute(
            "SELECT tenant_id FROM enterprise_programme_registry WHERE id=?", (programme,)
        ).fetchone()[0]
        with pytest.raises(gates.EnterpriseGateError):
            gates.evaluate_gate(c, tenant, programme, "G02")   # shut, for want of a charter

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "P02_D01",
              "activities": ["P02_A01", "P02_A02"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    # The document OPENS as a report (owner, 2026-07-13) rather than landing in the
    # downloads folder -- with the PDF and the email offered from that page.
    assert b"Programme charter" in r.data
    assert b"Download PDF" in r.data

    assert _doc_type_of(wa, _latest_doc_id(wa, programme)) == "programme_charter"

    with wa.get_db() as c:
        gates.evaluate_gate(c, tenant, programme, "G02")       # ...and now it opens


def test_omitting_the_deliverable_still_generates_a_free_form_document(ent, programme):
    """The old behaviour is intact -- and stamped as evidence for nothing."""
    client, wa, uid = ent
    _login(client, uid)
    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "", "title": "Working Notes",
              "activities": ["P01_A01"]},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert _doc_type_of(wa, _latest_doc_id(wa, programme)) == "lifecycle_document"


def test_an_unknown_deliverable_from_the_browser_is_refused_not_downgraded(ent, programme):
    """A tampered or stale form must not yield a document that opens nothing in silence.

    Silently falling back to "lifecycle_document" would give the operator a document that
    looks right, is named right, and satisfies no gate -- the exact failure the deliverable
    model exists to end, wearing a better disguise. It must be refused, out loud.
    """
    client, wa, uid = ent
    _login(client, uid)
    before = _latest_doc_id(wa, programme)

    r = client.post(
        f"/enterprise/programmes/{programme}/lifecycle-documents/generate",
        data={"_csrf": "testtoken", "deliverable_code": "P99_D99",
              "activities": ["P01_A01"]},
        follow_redirects=True,
    )
    assert r.status_code == 200, "a bad code is a user error, not a 500"
    assert b"unknown deliverable" in r.data.lower()
    assert _latest_doc_id(wa, programme) == before, "nothing may be written for a bad code"


def test_the_register_says_what_each_document_counts_as(ent, programme):
    """A document's whole purpose is what it is evidence FOR. The register must say."""
    client, _wa, uid = ent
    _login(client, uid)
    body = client.get(
        f"/enterprise/programmes/{programme}/lifecycle-documents").data.decode()
    # The charter generated above (G02), and the free-form document that opens nothing.
    # OWNER 2026-07-15: a document that is not one of the 144 is now simply labelled a
    # "Report"; the old "Free-form -- satisfies no gate" wording went with the picker option.
    assert "Gate G02 evidence" in body
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
      * an auditor could have manufactured the evidence for Gate 8, and
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
        data={"_csrf": "testtoken", "deliverable_code": "P08_D07",   # -> signed_contract
              "activities": ["P08_A01"]},
    )
    assert r.status_code == 403, "an auditor minted stage-gate evidence"
    assert _latest_doc_id(wa, programme) == before, "a document was written anyway"

    _login(client, uid)          # restore the module-scoped fixture's user


# ---------------------------------------------------------------------- the picker's promise

def test_no_phase_holds_more_activities_than_one_document_may_cover():
    """Selecting a deliverable ticks its phase for you. That must never be an instant error.

    The page's one-click convenience is auto-ticking the deliverable's phase. If a phase held
    more than MAX_ACTIVITIES_PER_DOCUMENT activities, the friendliest button on the page
    would produce a document the server always refuses -- which is what already happens with
    "select the whole stage" (Planning holds 183), and is why that path now warns instead of
    failing.
    """
    for phase_code, _no, name in constants.PHASES:
        n = len(constants.PHASE_ACTIVITIES[phase_code])
        assert n <= documents.MAX_ACTIVITIES_PER_DOCUMENT, (
            f"phase {name} holds {n} activities but a document may cover only "
            f"{documents.MAX_ACTIVITIES_PER_DOCUMENT} -- auto-ticking it would always fail"
        )


def test_gate_of_doc_type_is_derived_from_the_real_predicates():
    """The page's "opens gate G0x" promise must not be a hand-kept copy that can go stale."""
    assert len(gates.GATE_OF_DOC_TYPE) == 9, (
        "expected the 9 gate documents by introspection -- if this is empty, every claim "
        "the picker makes about gates is unverified"
    )
    for doc_type, gate in gates.GATE_OF_DOC_TYPE.items():
        assert any(getattr(p, "required_doc_type", None) == doc_type
                   for p in gates.GATE_PREDICATES[gate]), (
            f"{gate} is advertised as opened by {doc_type}, but its predicates do not "
            f"demand it"
        )
