"""A document the app WRITES must be a document the gate ACCEPTS.

THE SCANDAL THIS ENDS
---------------------
gates.py refuses to sign Gate 1 without a document of doc_type "concept_note", Gate 2
without "programme_charter", Gate 4 without "business_case", and so on -- nine gates, nine
named documents. Those are exactly the documents the owner wants the app to write.

But generate_document() stamped EVERY document it produced with doc_type
"lifecycle_document" -- a type no gate looks for. So the app could write a flawless concept
note and Gate 1 would still refuse to open. The only thing that could open it was
workflows.register_document(), which stores a doc_type and a TITLE STRING: no file, no
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
    beneficiaries, constants, documents, gates, tenancy, workflows,
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


def _generate(db, programme, deliverable: str, activities=("P01_A01",)):
    return documents.generate_document(
        db, db.org, 1, programme,
        activity_codes=list(activities),
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
    assert len(demanded) >= 9, (
        f"expected to find the 9 gate documents by introspection, found {len(demanded)} -- "
        f"this test is not actually checking anything"
    )

    producible = set(constants.DELIVERABLE_GATE_DOC_TYPE.values())
    missing = demanded - producible
    assert not missing, (
        f"these gates demand a document that NO deliverable can produce, so the programme "
        f"can never get past them: {sorted(missing)}"
    )


def test_the_deliverable_carries_the_gates_doc_type(db):
    assert constants.deliverable_doc_type("P01_D01") == "concept_note"
    assert constants.deliverable_doc_type("P05_D01") == "master_plan"
    # A deliverable no gate demands is stored under its own code -- unique, and unable to
    # collide with a reserved gate type.
    assert constants.deliverable_doc_type("P04_D03") == "P04_D03"


def test_an_unknown_deliverable_is_refused_not_silently_downgraded(db, programme):
    """A typo must not produce a document that looks right and opens nothing."""
    with pytest.raises(DocumentError):
        _generate(db, programme, "P99_D99")


# ------------------------------------------------------- the headline: writing opens a gate

def test_generating_the_concept_note_OPENS_gate_1(db, programme):
    """Before: the app wrote the concept note and Gate 1 still refused. That was the bug."""
    # Gate 1 is shut, and it says why.
    with pytest.raises(EnterpriseGateError) as before:
        gates.evaluate_gate(db, db.org, programme, "G01")
    assert "concept note" in str(before.value).lower()

    _generate(db, programme, "P01_D01")          # the app WRITES it

    # ...and now the gate opens, because the document it demanded actually exists.
    gates.evaluate_gate(db, db.org, programme, "G01")


def test_the_generated_document_is_stored_under_the_gates_type_with_real_content(db, programme):
    doc_id = _generate(db, programme, "P01_D01")

    row = db.execute(
        "SELECT doc_type, title, doc_kind, markdown FROM enterprise_documents WHERE id=?",
        (doc_id,),
    ).fetchone()
    doc_type, title, kind, markdown = row

    assert doc_type == "concept_note", "the document must be stored as the type the gate reads"
    assert title == "Programme concept note", "it must be named as doc 2 names it"
    assert kind == "generated"
    # The whole point: unlike register_document(), there is a DOCUMENT here.
    assert markdown and len(markdown) > 50, (
        "a gate-opening document must have content -- a title with nothing behind it is "
        "what this change exists to abolish"
    )


def test_a_document_for_the_WRONG_deliverable_does_not_open_the_gate(db, programme):
    """Writing some other deliverable must not open the gate that wants a concept note.

    If it did, the doc_type would be decorative and any generated document would open any
    gate -- which is the same hole as before, just harder to see.

    Uses P01_D02 rather than the economic assessment (P04_D03): that one is ENGINE-written
    now, so on a programme with no approved reference design it is refused outright, and the
    refusal -- not the doc_type -- would be what kept the gate shut. That would make this
    test pass for the wrong reason.
    """
    _generate(db, programme, "P01_D02", activities=("P01_A01",))   # not a gate document

    with pytest.raises(EnterpriseGateError):
        gates.evaluate_gate(db, db.org, programme, "G01")


def test_the_owners_four_documents_are_all_bound_to_an_engine():
    """The owner: "create program technical and financial proposal, implementation plan,
    ... monitor". Each must be produced by an existing engine, not hand-typed."""
    assert constants.DELIVERABLE_ENGINE["P04_D01"] == "technical"            # technical proposal
    assert constants.DELIVERABLE_ENGINE["P04_D02"] == "financial"            # financial proposal
    assert constants.DELIVERABLE_ENGINE["P05_D01"] == "implementation_plan"  # implementation plan
    assert constants.DELIVERABLE_ENGINE["P15_D01"] == "monitoring"           # monitor


def test_all_144_key_outputs_are_encoded():
    assert sum(len(v) for v in constants.PHASE_DELIVERABLES.values()) == 144
    assert len(constants.PHASE_DELIVERABLES) == 16
    # every phase in the lifecycle has at least one named output
    assert set(constants.PHASE_DELIVERABLES) == set(constants.PHASE_CODES)
