"""A document the app WRITES must be a document the gate ACCEPTS.

THE SCANDAL THIS ENDS
---------------------
gates.py refuses to sign a gate without the one document that gate reads. Under Revision 4
that is each phase's own approval/closure document -- five gates, five named documents
(rev4_phases.DELIVERABLE_GATE_DOC_TYPE). Those are exactly the documents the owner wants the
app to write.

But generate_document() stamped EVERY document it produced with doc_type
"lifecycle_document" -- a type no gate looks for. So the app could write a flawless approval
request and the Initiation gate would still refuse to open. The only thing that could open it
was workflows.register_document(), which stores a doc_type and a TITLE STRING: no file, no
content, nothing checked.

The result: a stage gate -- the control that exists so a programme cannot proceed without
its evidence -- was passed by TYPING A NAME INTO A BOX, while the one artefact with real
content in it counted for nothing.

So the test is not "can it generate a document" (it always could). It is:

    does the document the app wrote actually SATISFY the gate that demanded it?

and its mirror, which is the part that must never regress:

    does typing a name still not count as evidence?
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, documents, gates, rev4_phases, tenancy, workflows,
)
from app.enterprise_programme.documents import DocumentError
from app.enterprise_programme.gates import EnterpriseGateError


class AuditSpy:
    def __call__(self, action: str, **kw) -> bool:
        return True


class _Conn(sqlite3.Connection):
    org: str


@pytest.fixture()
def db():
    c = sqlite3.connect(":memory:", factory=_Conn)
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, email TEXT)")
    c.execute("INSERT INTO users (id, username) VALUES (1, 'alice')")
    tenancy.ensure_schema(c)
    workflows.ensure_schema(c)
    beneficiaries.ensure_schema(c)   # build_markdown reads the site register for its facts
    documents.ensure_schema(c)
    tenancy.get_or_create_personal_tenant(c, 1, "alice")
    org = tenancy.create_organisation(c, 1, "Ministry of Energy", "ministry", "Ghana")
    c.commit()
    c.org = org  # type: ignore[attr-defined]
    yield c
    c.close()


@pytest.fixture()
def programme(db):
    return workflows.create_programme(
        db, db.org, 1, code="GH-SCHOOLS-01", name="Ghana Schools Solar",
        design_strategy="standard", sponsor_user_id=1, audit=AuditSpy(),
    )


def _generate(db, programme, deliverable: str):
    return documents.generate_document(
        db, db.org, 1, programme,
        deliverable_code=deliverable,
        use_ai=False,                      # deterministic: no network in a unit test
        audit=AuditSpy(),
    )


# --------------------------------------------------------------- the deliverable model

def test_every_gate_document_can_be_produced_by_some_deliverable(db):
    """A gate demanding a document nothing can produce is a dead end in the lifecycle.

    This is the invariant that makes the whole module honest, so it is asserted against the
    LIVE gate table rather than a copy of it: whatever gates.py demands today, a deliverable
    must exist that produces it.
    """
    demanded = set()
    for preds in gates.GATE_PREDICATES.values():
        for p in preds:
            doc_type = getattr(p, "required_doc_type", None)
            if doc_type:
                demanded.add(doc_type)

    # A guard that inspects nothing passes forever. gates.py publishes `required_doc_type`
    # on each predicate precisely so this can read the REAL demands; if that ever stops
    # working, `demanded` goes empty and the assertion below would be vacuously true.
    # Revision 4 has five gates and each demands exactly one document, so five is the whole
    # demand -- not a floor.
    assert len(demanded) == len(rev4_phases.GATE_CODES) == 5, (
        f"expected to find one gate document per Rev 4 gate by introspection, found "
        f"{len(demanded)} -- this test is not actually checking anything"
    )

    producible = set(rev4_phases.DELIVERABLE_GATE_DOC_TYPE.values())
    missing = demanded - producible
    assert not missing, (
        f"these gates demand a document that NO deliverable can produce, so the programme "
        f"can never get past them: {sorted(missing)}"
    )


def test_the_deliverable_carries_the_gates_doc_type(db):
    # The five deliverables that open Revision 4's five gates are stored under the doc_type
    # their gate reads, not under their own code.
    assert rev4_phases.deliverable_doc_type("R4P1_D12") == "programme_approval_request"
    assert rev4_phases.deliverable_doc_type("R4P6_D14") == "programme_closure_certificate"
    # A deliverable no gate demands is stored under its own code -- unique, and unable to
    # collide with a reserved gate type.
    assert rev4_phases.deliverable_doc_type("R4P1_D01") == "R4P1_D01"


def test_an_unknown_deliverable_is_refused_not_silently_downgraded(db, programme):
    """A typo must not produce a document that looks right and opens nothing."""
    with pytest.raises(DocumentError):
        _generate(db, programme, "P99_D99")


# ------------------------------------------------------- the headline: writing opens a gate

def test_generating_the_programme_approval_request_OPENS_the_initiation_gate(db, programme):
    """Before: the app wrote the gate's document and the gate still refused. That was the bug.

    Revision 4's Initiation gate reads ONE document -- the Programme Approval Request
    (R4P1_D12) -- and that document is a deliverable button the app itself writes.
    """
    # The gate is shut, and it says why.
    with pytest.raises(EnterpriseGateError) as before:
        gates.evaluate_gate(db, db.org, programme, "R4G1_INITIATION")
    assert "programme approval request" in str(before.value).lower()

    _generate(db, programme, "R4P1_D12")         # the app WRITES it

    # ...and now the gate opens, because the document it demanded actually exists.
    gates.evaluate_gate(db, db.org, programme, "R4G1_INITIATION")


def test_the_generated_document_is_stored_under_the_gates_type_with_real_content(db, programme):
    doc_id = _generate(db, programme, "R4P1_D12")

    row = db.execute(
        "SELECT doc_type, title, doc_kind, markdown FROM enterprise_documents WHERE id=?",
        (doc_id,),
    ).fetchone()
    doc_type, title, kind, markdown = row

    assert doc_type == "programme_approval_request", (
        "the document must be stored as the type the gate reads"
    )
    assert title == "Programme Approval Request", (
        "it must be named as the owner's spec (section 9) names it"
    )
    assert kind == "generated"
    # The whole point: unlike register_document(), there is a DOCUMENT here.
    assert markdown and len(markdown) > 50, (
        "a gate-opening document must have content -- a title with nothing behind it is "
        "what this change exists to abolish"
    )


def test_a_document_for_the_WRONG_deliverable_does_not_open_the_gate(db, programme):
    """Writing some other deliverable must not open the gate that wants the approval request.

    If it did, the doc_type would be decorative and any generated document would open any
    gate -- which is the same hole as before, just harder to see.

    Uses the Programme Concept Note (R4P1_D01): it is in the same phase as the gate's own
    document, and it is written by the deliverable writer rather than the design engine. An
    ENGINE-written deliverable would be refused outright on a programme with no approved
    reference design, and the refusal -- not the doc_type -- would be what kept the gate shut.
    That would make this test pass for the wrong reason.
    """
    _generate(db, programme, "R4P1_D01")         # not a gate document

    with pytest.raises(EnterpriseGateError):
        gates.evaluate_gate(db, db.org, programme, "R4G1_INITIATION")


def test_the_owners_four_documents_are_all_bound_to_an_engine():
    """The owner: "create program technical and financial proposal, implementation plan,
    ... monitor". Each must be produced by an existing engine, not hand-typed."""
    engine = rev4_phases.DELIVERABLE_ENGINE
    assert engine["R4P2_D07"] == "technical"             # Programme Feasibility Study
    assert engine["R4P2_D16"] == "financial"             # Programme Cost Plan
    assert engine["R4P2_D25"] == "implementation_plan"   # Programme Implementation Plan
    assert engine["R4P4_D19"] == "monitoring"            # Executive Status Report


def test_all_114_revision_4_deliverables_are_encoded():
    """The owner's spec (sections 9-14) named 112 deliverables across six phases; it is 114
    since 2026-07-18, when revision xx201 appended Programme Business Case and Official
    Programme Plan to Initiation (12 -> 14). Originally: 12 for
    Initiation, 27 Planning, 21 Execution, 19 Monitoring, 17 Value Realisation, 16 Closure."""
    # 114 since 2026-07-18, not the original 112: revision xx201 s39 needs four Initiation reports and two of them -- Programme Business Case (R4P1_D13) and Official Programme Plan (R4P1_D14) -- did not exist. They are APPENDED, so every pre-existing code still resolves to the same deliverable it always did.
    assert sum(len(v) for v in rev4_phases.PHASE_DELIVERABLES.values()) == 114
    assert len(rev4_phases.PHASE_DELIVERABLES) == 6
    # every phase in the lifecycle has at least one named deliverable button
    assert set(rev4_phases.PHASE_DELIVERABLES) == set(rev4_phases.PHASE_CODES)
