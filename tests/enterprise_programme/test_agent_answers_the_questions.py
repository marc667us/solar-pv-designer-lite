"""The AGENT answers the lifecycle questions. The operator edits them.

OWNER, 2026-07-14:
  "the benefit of using the app is that an agent will answer the questions"
  "take all the questions across each phase and provide default answers and give the user
   access to edit your answer if needed and save"

THE BUG UNDERNEATH THIS
-----------------------
The app HAD an agent. It had been mute for weeks and nobody noticed. `_ai_write` asked
OpenRouter for `meta-llama/llama-3.1-8b-instruct:free`, which OpenRouter RETIRED; every call
404'd, the chain fell through Ollama (not on Render) and GitHub Models (not configured) to
`rule_based`; and the writer correctly refuses to pass a canned fallback string off as a
drafted section, so it returned None for every activity and raised a QUESTION instead. The
app interrogated the operator because its agent was dead, and said nothing about it --
`/api/health/ai` still reported "configured", because a key was set.

See tests/test_openrouter_free_models.py for the guard on that.

WHAT A DRAFT IS, AND IS NOT
---------------------------
A drafted answer is stored with `answer` set and `answered_at` NULL. So the database can
tell the machine's words from the operator's, and:
  * the document writer does not give a draft the authority of an operator's answer;
  * the question stays outstanding until a human confirms it;
  * pressing Save stamps `answered_at` and the same text becomes the operator's own.

Presenting the machine's draft as the operator's statement would put a sentence in a ministry
document that no person ever made. That is the distinction these tests defend.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.enterprise_programme import (
    beneficiaries, documents, rbac, tenancy, workflows,
)
from app.enterprise_programme.constants import PHASE_ACTIVITIES
from app.enterprise_programme.gates import EnterpriseGateError
from app.security import audit as audit_mod

OWNER = 1
READER = 2          # a member with no `programme.edit`


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
    c.execute("PRAGMA foreign_keys=ON")
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
def prog(db):
    pid = workflows.create_programme(
        db, db.org, OWNER, code="GH-1", name="Ghana Schools Solar",
        design_strategy="standard", sponsor_user_id=OWNER, country="Ghana",
        audit=_audit(db),
        description=("Rooftop solar for 100 rural schools in the Volta Region, "
                     "financed by the Ministry of Energy."),
    )
    db.commit()
    return pid


# --- the agent answers --------------------------------------------------------

def test_no_two_activities_get_the_SAME_STATEMENT(db, prog):
    """THE OWNER'S BUG, 2026-07-14: "the agent just answered every question with the same
    statement -- fix it, and don't use my information".

    Two causes, both structural:
      * the fact writer keyed on the TOPIC, not the activity, so every activity that mentioned
        money received the same paragraph about the budget; and
      * when no topic matched at all it echoed the operator's OWN programme description back
        at them -- which is what "don't use my information" means.

    A fact is now stated ONCE, under the activity that reaches it first. Anything that would
    repeat it is left unanswered with its question showing. This test is the whole complaint.
    """
    documents.draft_answers(db, db.org, OWNER, prog, use_ai=False, audit=_audit(db))

    answers = [a["answer"].strip()
               for ph in documents.answer_sheet(db, db.org, prog)
               for a in ph["activities"] if a["answer"].strip()]

    assert len(answers) == len(set(answers)), (
        "the same statement was written under more than one question -- exactly what the "
        "owner reported"
    )

    desc = "Rooftop solar for 100 rural schools"
    assert not [a for a in answers if desc in a], (
        "the operator's own programme description was echoed back at them as an answer"
    )


def test_the_agent_answers_what_it_CAN_and_says_what_it_cannot(db, prog):
    """Every activity is accounted for: answered, or left open and COUNTED as left open.

    The old contract was "no box is ever empty", and it was wrong -- it was satisfiable by
    boilerplate, and a non-empty box that answers nothing reads as done and buries the gap.
    An empty box with its question under it is the honest failure; the count is what makes it
    visible instead of silent.
    """
    r = documents.draft_answers(db, db.org, OWNER, prog,
                                phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))

    n = len(PHASE_ACTIVITIES["P01_CONCEPT"])
    assert r["drafted"] >= 1, "the agent answered nothing at all"
    assert r["drafted"] + r["unanswered"] == n, (
        "activities went missing -- each is either answered or reported as unanswered"
    )

    sheet = {ph["phase_code"]: ph for ph in documents.answer_sheet(db, db.org, prog)}
    written = [a for a in sheet["P01_CONCEPT"]["activities"] if a["answer"].strip()]
    assert len(written) == r["drafted"]


def test_it_can_answer_every_phase_at_once(db, prog):
    """"Take all the questions across each phase" -- all 16 of them."""
    r = documents.draft_answers(db, db.org, OWNER, prog, use_ai=False, audit=_audit(db))

    total = sum(len(v) for v in PHASE_ACTIVITIES.values())
    assert r["drafted"] + r["unanswered"] == total
    assert len(documents.answer_sheet(db, db.org, prog)) == 16


def test_the_answers_are_ABOUT_THIS_PROGRAMME(db, prog):
    """A default answer that could belong to any programme is not an answer.

    Without this the writer could satisfy every other test in this file by emitting the same
    piece of process boilerplate 453 times.
    """
    documents.draft_answers(db, db.org, OWNER, prog,
                            phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    sheet = {ph["phase_code"]: ph for ph in documents.answer_sheet(db, db.org, prog)}
    texts = [a["answer"] for a in sheet["P01_CONCEPT"]["activities"]]

    assert any("Ghana Schools Solar" in t for t in texts), (
        "not one answer names the programme it is supposedly about"
    )
    assert any("Volta" in t or "school" in t.lower() for t in texts), (
        "the programme's own description was never used"
    )


# --- a draft is not an answer -------------------------------------------------

def _first_drafted(db, prog):
    """An activity the fact writer actually answered.

    Not every activity gets one now, so a test that hardcodes P01_A01 would be asserting about
    the writer's topic table rather than about drafts.
    """
    for ph in documents.answer_sheet(db, db.org, prog):
        for a in ph["activities"]:
            if a["answer"].strip():
                return a["code"]
    raise AssertionError("nothing was drafted at all")


def test_a_drafted_answer_is_NOT_recorded_as_the_operators_answer(db, prog):
    """The machine's words must never be attributed to a person who never said them."""
    documents.draft_answers(db, db.org, OWNER, prog,
                            phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    code = _first_drafted(db, prog)

    a = documents.get_answers(db, db.org, prog)[code]
    assert a["answer"], "nothing was drafted"
    assert a["answered"] is False, (
        "a machine draft is being reported as the operator's own answer"
    )

    # ...and the sheet says so out loud, because the screen renders this flag.
    sheet = {ph["phase_code"]: ph for ph in documents.answer_sheet(db, db.org, prog)}
    row = next(x for x in sheet["P01_CONCEPT"]["activities"] if x["code"] == code)
    assert row["drafted"] is True and row["answered"] is False


def test_saving_a_draft_makes_it_the_operators_own(db, prog):
    """"give the user access to edit your answer if needed and save"."""
    documents.draft_answers(db, db.org, OWNER, prog,
                            phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    code = _first_drafted(db, prog)
    drafted = documents.get_answers(db, db.org, prog)[code]["answer"]

    edited = drafted + " The Ministry has confirmed the shortlist."
    n = documents.save_answers(db, db.org, OWNER, prog, {code: edited},
                               audit=_audit(db))
    assert n == 1

    a = documents.get_answers(db, db.org, prog)[code]
    assert a["answer"] == edited
    assert a["answered"] is True, "a saved answer is the operator's, and must be marked so"


def test_redrafting_NEVER_overwrites_an_answer_the_operator_gave(db, prog):
    """The one thing that would make this feature hostile.

    An operator who spends an hour answering Feasibility by hand, then presses "answer
    everything" to fill in the rest, must not lose a word of their own work.
    """
    documents.save_answers(db, db.org, OWNER, prog,
                           {"P01_A01": "MY OWN WORDS, TYPED BY A HUMAN."},
                           audit=_audit(db))

    r = documents.draft_answers(db, db.org, OWNER, prog, use_ai=False, audit=_audit(db))
    assert r["skipped_answered"] == 1

    a = documents.get_answers(db, db.org, prog)["P01_A01"]
    assert a["answer"] == "MY OWN WORDS, TYPED BY A HUMAN.", (
        "the agent overwrote the operator's own answer -- this destroys their work"
    )
    assert a["answered"] is True

    # ...and the rest of the programme was still worked through: every other activity is
    # either drafted or honestly reported as one the app cannot answer.
    total = sum(len(v) for v in PHASE_ACTIVITIES.values())
    assert r["drafted"] + r["unanswered"] + 1 == total


def test_redrafting_DOES_replace_an_earlier_draft(db, prog):
    """A draft is disposable. Only a human answer is sacred."""
    first = documents.draft_answers(db, db.org, OWNER, prog,
                                    phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    r = documents.draft_answers(db, db.org, OWNER, prog,
                                phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    # The same activities are re-drafted -- a draft is disposable -- and re-running does NOT
    # quietly grow the phase by pasting paragraph one under the activities it left open.
    assert r["drafted"] == first["drafted"]
    assert r["skipped_answered"] == 0


# --- the model's contribution, and its limits ---------------------------------

def test_a_model_answer_is_used_when_the_model_answers(db, prog, monkeypatch):
    """The AI is the point of the feature -- when it is reachable, it writes."""
    monkeypatch.setattr(
        documents, "_draft_batch_ai",
        lambda activities, facts, deadline=None: {activities[0][0]: "A specific, model-written answer."})

    r = documents.draft_answers(db, db.org, OWNER, prog,
                                phase_code="P01_CONCEPT", use_ai=True, audit=_audit(db))

    assert r["ai"] >= 1
    assert r["from_facts"] == r["drafted"] - r["ai"]
    assert (documents.get_answers(db, db.org, prog)["P01_A01"]["answer"]
            == "A specific, model-written answer.")


def test_a_dead_model_degrades_to_facts_and_ADMITS_the_rest(db, prog, monkeypatch):
    """A mute agent must degrade honestly -- not disappear, and not bluff.

    When the model is unreachable the app writes what its records actually support and REPORTS
    what they do not. The earlier version of this test demanded that no box be left empty, and
    that demand is precisely what the boilerplate was built to satisfy. A count of what could
    not be answered is worth more to the operator than a paragraph that answers nothing.
    """
    monkeypatch.setattr(documents, "_draft_batch_ai", lambda activities, facts, deadline=None: {})

    r = documents.draft_answers(db, db.org, OWNER, prog,
                                phase_code="P01_CONCEPT", use_ai=True, audit=_audit(db))

    assert r["ai"] == 0
    assert r["drafted"] >= 1, "a dead model must still leave the operator better off"
    assert r["drafted"] + r["unanswered"] == len(PHASE_ACTIVITIES["P01_CONCEPT"])

    # Whatever it did write is real and distinct -- never the same sentence twice.
    sheet = {ph["phase_code"]: ph for ph in documents.answer_sheet(db, db.org, prog)}
    written = [a["answer"].strip() for a in sheet["P01_CONCEPT"]["activities"]
               if a["answer"].strip()]
    assert len(written) == len(set(written))


def test_a_model_that_invents_an_activity_code_is_ignored(db, prog, monkeypatch):
    """A code we never asked about would be stored against somebody else's activity."""
    monkeypatch.setattr(
        documents, "_draft_batch_ai",
        lambda activities, facts, deadline=None: {"P09_A99": "an answer to an activity that was not asked"})

    documents.draft_answers(db, db.org, OWNER, prog,
                            phase_code="P01_CONCEPT", use_ai=True, audit=_audit(db))
    assert "P09_A99" not in documents.get_answers(db, db.org, prog)


def test_the_real_batch_parser_drops_codes_it_was_not_asked_about(monkeypatch):
    """The filter above lives in _draft_batch_ai. Test it against a real model reply."""
    import api_manager

    class _FakeAI:
        def chat(self, *a, **k):
            return ('```json\n{"P01_A01": "Grounded answer.", '
                    '"P01_A02": "INSUFFICIENT", '
                    '"P07_A01": "not one of the activities asked about"}\n```',
                    "openrouter")

    monkeypatch.setattr(api_manager.api, "ai", _FakeAI())

    got = documents._draft_batch_ai(
        [("P01_A01", "Register the programme idea."),
         ("P01_A02", "Identify the sponsoring institution.")],
        {"name": "P", "code": "C", "phase_code": "P01_CONCEPT"})

    assert got == {"P01_A01": "Grounded answer."}, (
        "the parser must survive a code fence, drop INSUFFICIENT, and drop a code it never "
        f"asked about -- got {got}"
    )


# --- permissions --------------------------------------------------------------

def test_a_reader_cannot_make_the_agent_write_into_the_programme(db, prog):
    """Drafting WRITES to the programme. It needs `programme.edit`, not merely a login."""
    assert not rbac.has_permission(db, db.org, READER, "programme.edit",
                                   programme_id=prog)
    with pytest.raises(rbac.EnterprisePermissionError):
        documents.draft_answers(db, db.org, READER, prog,
                                phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))


def test_another_tenants_programme_is_invisible_not_forbidden(db, prog):
    """C13. Drafting must answer 'no such programme', never 'not allowed'."""
    # The C13 guard raises EnterpriseGateError; DocumentError is a SUBCLASS of it, so a
    # test (or a route) that catches only the subclass misses the cross-tenant case entirely.
    with pytest.raises(EnterpriseGateError) as e:
        documents.draft_answers(db, "some-other-tenant", OWNER, prog,
                                phase_code="P01_CONCEPT", use_ai=False, audit=_audit(db))
    assert e.value.control == "C13"


def test_an_unknown_phase_is_refused(db, prog):
    with pytest.raises(documents.DocumentError):
        documents.draft_answers(db, db.org, OWNER, prog,
                                phase_code="P99_NOPE", use_ai=False, audit=_audit(db))
