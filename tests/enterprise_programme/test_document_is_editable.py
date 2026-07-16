"""The agent drafts; the OPERATOR SIGNS.

OWNER, 2026-07-14: "app writes the report for that activity and user preview and edit and
save", and "the owner must be able to walk through without blocks".

A document the app will not let the operator correct is a document they cannot stand behind
-- and FIVE of these documents are the evidence a stage gate will not open without (Revision
4 has five gates, each opened by one deliverable -- rev4_phases.DELIVERABLE_GATE_DOC_TYPE).
So the generated markdown is editable, and the edit is what the PDF, the email and the gate
evidence all read from afterwards.

WHAT MUST STILL HOLD
  * C13 -- another tenant's document is 404, never 403, never editable.
  * `programme.edit` -- reading a report is not permission to rewrite it.
  * An UPLOADED source file is not editable: its `markdown` is text EXTRACTED from somebody's
    PDF, and rewriting it would leave the stored bytes and the app's account of them saying
    different things.
  * An EMPTY save is refused. Blanking a document would silently destroy the evidence a stage
    gate is standing on.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, documents, rbac, tenancy, workflows,
)
from app.enterprise_programme.gates import EnterpriseGateError
from app.security import audit as audit_mod

OWNER = 1
READER = 2          # can read the programme; holds no `programme.edit`

# Revision 4's Programme Approval Request -- Initiation's twelfth deliverable, and the one
# that opens Initiation's stage gate (R4G1_INITIATION). The gate-evidence deliverable is what
# these tests generate on purpose: an edit to an ordinary report is an edit, but an edit to
# the document a gate is standing on is the case that has to hold.
GATE_DELIVERABLE = "R4P1_D12"


class _Conn(sqlite3.Connection):
    org: str


def _audit(c):
    def _hook(action, **kw):
        return audit_mod.write_audit_event(action, conn=c, **kw)
    return _hook


@pytest.fixture()
def db():
    audit_mod.reset_schema_probe()
    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    for uid, name in ((OWNER, "olga"), (READER, "rex")):
        c.execute("INSERT INTO users (id, username) VALUES (?,?)", (uid, name))
    c.execute(
        "CREATE TABLE audit_logs ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT DEFAULT '',"
        " action TEXT NOT NULL, ip_address TEXT DEFAULT '', details TEXT DEFAULT '',"
        " tenant_id TEXT, agent_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
        " prev_hash TEXT, row_hash TEXT)")
    for mod in (tenancy, workflows, beneficiaries, documents):
        mod.ensure_schema(c)
    for uid, name in ((OWNER, "olga"), (READER, "rex")):
        tenancy.get_or_create_personal_tenant(c, uid, name)

    org = tenancy.create_organisation(c, OWNER, "Ministry of Energy", "ministry", "Ghana")
    tenancy.add_member(c, org, READER, "executive_viewer", OWNER)
    c.commit()
    c.org = org
    yield c
    c.close()
    audit_mod.reset_schema_probe()


@pytest.fixture()
def doc(db):
    pid = workflows.create_programme(
        db, db.org, OWNER, code="GH-1", name="Ghana Schools",
        design_strategy="standard", sponsor_user_id=OWNER,
        description="Rooftop solar for 100 rural schools.", audit=_audit(db))
    did = documents.generate_document(
        db, db.org, OWNER, pid,
        deliverable_code=GATE_DELIVERABLE, use_ai=False, audit=_audit(db))
    db.commit()
    return pid, did


def test_the_operator_can_edit_the_document_the_agent_wrote(db, doc):
    _pid, did = doc
    before = documents.get_document(db, db.org, did)["markdown"]

    documents.update_document(db, db.org, OWNER, did,
                              markdown="## Background\n\nThe Ministry approved the shortlist.",
                              title="Programme Approval Request (final)", audit=_audit(db))

    after = documents.get_document(db, db.org, did)
    assert after["markdown"] != before
    assert "the Ministry approved the shortlist".lower() in after["markdown"].lower()
    assert after["title"] == "Programme Approval Request (final)"


def test_the_edit_is_what_the_PDF_and_the_gate_read_afterwards(db, doc):
    """The point of editing. If the PDF still rendered the draft, the edit was theatre."""
    _pid, did = doc
    documents.update_document(db, db.org, OWNER, did,
                              markdown="## Background\n\nEDITED BY THE OPERATOR.",
                              audit=_audit(db))

    after = documents.get_document(db, db.org, did)
    assert "EDITED BY THE OPERATOR" in after["markdown"]
    assert after["byte_size"] == len(after["markdown"].encode("utf-8")), (
        "byte_size still describes the draft, so anything trusting it reads a stale length"
    )
    # the doc_type is untouched, so the gate it opens still finds it
    assert after["doc_type"] == documents.deliverable_doc_type(GATE_DELIVERABLE)
    assert documents.render_pdf(after["markdown"], after["title"])


def test_the_title_is_kept_when_none_is_given(db, doc):
    _pid, did = doc
    original = documents.get_document(db, db.org, did)["title"]
    documents.update_document(db, db.org, OWNER, did, markdown="## X\n\nBody.",
                              audit=_audit(db))
    assert documents.get_document(db, db.org, did)["title"] == original


def test_an_empty_save_is_refused(db, doc):
    """Blanking a document would silently destroy the evidence a stage gate stands on."""
    _pid, did = doc
    before = documents.get_document(db, db.org, did)["markdown"]

    with pytest.raises(documents.DocumentError):
        documents.update_document(db, db.org, OWNER, did, markdown="   \n  ",
                                  audit=_audit(db))

    assert documents.get_document(db, db.org, did)["markdown"] == before


def test_a_reader_cannot_rewrite_the_report_they_are_allowed_to_read(db, doc):
    """Reading a report is not permission to rewrite it."""
    _pid, did = doc
    assert documents.get_document(db, db.org, did)          # she really can read it

    with pytest.raises(rbac.EnterprisePermissionError):
        documents.update_document(db, db.org, READER, did, markdown="## Mine now",
                                  audit=_audit(db))


def test_another_tenants_document_is_invisible_not_forbidden(db, doc):
    """C13. Not-yours and not-there must be the same answer."""
    _pid, did = doc
    with pytest.raises(EnterpriseGateError) as e:
        documents.update_document(db, "some-other-tenant", OWNER, did,
                                  markdown="## Pwned", audit=_audit(db))
    assert e.value.control == "C13"


def test_an_uploaded_source_file_is_not_editable(db, doc):
    """Its markdown is text EXTRACTED from a PDF. Rewriting it would make the app's account
    of the file disagree with the bytes it is still storing."""
    pid, _did = doc
    up = documents.upload_document(
        db, db.org, OWNER, pid, file_name="brief.txt", title="Ministry brief",
        data=b"The ministry intends to electrify 100 schools.", audit=_audit(db),
    )
    assert documents.get_document(db, db.org, up)["doc_kind"] == "uploaded"

    with pytest.raises(documents.DocumentError):
        documents.update_document(db, db.org, OWNER, up, markdown="## Rewritten",
                                  audit=_audit(db))

    # ...and the file's own record is untouched: still an upload, still its own bytes.
    after = documents.get_document(db, db.org, up)
    assert after["doc_kind"] == "uploaded"
    assert "Rewritten" not in (after["markdown"] or "")
