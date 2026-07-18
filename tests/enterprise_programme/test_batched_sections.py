"""Tests for batched section generation.

WHAT THIS IS PROTECTING. Asking for four sections in one model call is a QUOTA measure --
OpenRouter's free tier allows 50 requests a day, so one-call-per-section capped the whole
platform at about five documents a day and then reported the writer as unavailable. Batching
takes a concept note from 10 calls to 3.

The risk it introduces is that the reply has to be SPLIT back apart, and a bad split does not
error -- it hands one section another section's prose, or silently loses one. Every test here
is about that split, or about the batch not being allowed to bypass a guard the single-section
path enforces.
"""
import re
import pytest

from app.enterprise_programme import documents as D


# The keys `_brief` actually requires -- `name`, `code` and `phase_code` are read
# unconditionally, so a fixture missing any of them fails inside the writer rather than
# testing it.
FACTS = {
    "name": "Rural Electrification Programme",
    "code": "REP-001",
    "phase_code": "P1",
    "country": "Ghana",
    "description": "Solar mini-grids for off-grid communities.",
}


def _fake_chat(reply, provider="openrouter", capture=None):
    """Stand in for api.ai.chat, returning a canned reply."""
    def chat(messages, **kw):
        if capture is not None:
            capture.append((messages, kw))
        return reply, provider
    return chat


@pytest.fixture
def api(monkeypatch):
    """Give documents.py an api_manager whose .ai.chat we control."""
    import api_manager
    monkeypatch.setattr(api_manager.api.ai, "last_failure_reason", "", raising=False)
    return api_manager.api


def _marked(*pairs):
    """Build a reply in the marker format the batch prompt asks the model for."""
    return "\n\n".join(f"<<<SECTION:{h}>>>\n{body}" for h, body in pairs)


def test_splits_each_section_to_its_own_heading(api, monkeypatch):
    """The core promise: section A's prose goes to A, B's to B."""
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(
        ("Background", "The programme addresses rural access."),
        ("Objectives", "The objective is 5000 connections."),
    )))
    out = D._ai_write_many([("Background", "b"), ("Objectives", "o")],
                           FACTS, document_title="Concept Note")
    assert out["Background"] == "The programme addresses rural access."
    assert out["Objectives"] == "The objective is 5000 connections."


def test_reordered_reply_still_maps_correctly(api, monkeypatch):
    """Models reorder. Slicing to the NEXT REQUESTED heading rather than the next MARKER
    would hand 'Background' the objectives text -- a wrong document, not a failed one."""
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(
        ("Objectives", "Objectives prose."),
        ("Background", "Background prose."),
    )))
    out = D._ai_write_many([("Background", "b"), ("Objectives", "o")],
                           FACTS, document_title="Concept Note")
    assert out["Background"] == "Background prose."
    assert out["Objectives"] == "Objectives prose."


def test_missing_section_is_absent_not_empty(api, monkeypatch):
    """A section the model skipped must be ABSENT, so the caller writes it individually.
    Returning "" would ship a blank section under a heading."""
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(
        ("Background", "Background prose."),
    )))
    out = D._ai_write_many([("Background", "b"), ("Objectives", "o")],
                           FACTS, document_title="Concept Note")
    assert "Objectives" not in out
    assert out["Background"] == "Background prose."


def test_prose_containing_hashes_is_not_split_on(api, monkeypatch):
    """Why the marker is not a markdown heading: prose can legitimately contain '##'."""
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(
        ("Background", "Costs are tracked under ## line items ## in the budget."),
        ("Objectives", "Objectives prose."),
    )))
    out = D._ai_write_many([("Background", "b"), ("Objectives", "o")],
                           FACTS, document_title="Concept Note")
    assert out["Background"] == "Costs are tracked under ## line items ## in the budget."
    assert out["Objectives"] == "Objectives prose."


def test_safety_guard_still_applies_to_batched_prose(api, monkeypatch):
    """A batch must not be a way around the output guard. A section claiming the programme
    is APPROVED when the facts do not say so is dropped, exactly as in the single path."""
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(
        ("Background", "The programme has been approved and funded by the Ministry."),
        ("Objectives", "The objective is 5000 connections."),
    )))
    out = D._ai_write_many([("Background", "b"), ("Objectives", "o")],
                           FACTS, document_title="Concept Note")
    assert "Background" not in out, "a settled-fact claim was allowed through the batch path"
    assert out["Objectives"] == "The objective is 5000 connections."


def test_rule_based_provider_is_not_treated_as_written(api, monkeypatch):
    """`rule_based`/`capped` mean no model wrote this. Accepting it would put boilerplate
    into a document under the model's name."""
    monkeypatch.setattr(api.ai, "chat",
                        _fake_chat(_marked(("Background", "x")), provider="rule_based"))
    assert D._ai_write_many([("Background", "b")], FACTS,
                            document_title="Concept Note") == {}


def test_provider_exception_returns_empty_not_raise(api, monkeypatch):
    """The batch is an optimisation. If it explodes, the caller must still be able to write
    each section on its own -- so it returns {} rather than propagating."""
    def boom(*a, **kw):
        raise RuntimeError("provider down")
    monkeypatch.setattr(api.ai, "chat", boom)
    assert D._ai_write_many([("Background", "b")], FACTS,
                            document_title="Concept Note") == {}


def test_empty_input_makes_no_call(api, monkeypatch):
    """Quota is the whole point; an empty batch must not spend a request."""
    calls = []
    monkeypatch.setattr(api.ai, "chat", _fake_chat("", capture=calls))
    assert D._ai_write_many([], FACTS, document_title="Concept Note") == {}
    assert calls == []


def test_batch_asks_for_every_requested_heading(api, monkeypatch):
    """The prompt must actually carry all four briefs -- otherwise the batch quietly
    degrades into a one-section call that costs the same as a batch."""
    calls = []
    monkeypatch.setattr(api.ai, "chat", _fake_chat(_marked(("A", "x")), capture=calls))
    D._ai_write_many([("A", "brief-a"), ("B", "brief-b")], FACTS,
                     document_title="Concept Note")
    prompt = calls[0][0][0]["content"]
    for heading, brief in (("A", "brief-a"), ("B", "brief-b")):
        assert f"<<<SECTION:{heading}>>>" in prompt
        assert brief in prompt


def test_call_count_is_bounded_by_batch_size(api, monkeypatch):
    """THE MEASURED CLAIM. A 10-section document must cost ceil(10/4)=3 calls, not 10.
    This is the number the whole change exists to produce, so it is asserted directly."""
    calls = []

    def chat(messages, **kw):
        calls.append(messages)
        # Answer whatever was asked for in this batch.
        asked = re.findall(r"<<<SECTION:(.+?)>>>", messages[0]["content"])
        return _marked(*[(h, f"Prose for {h}.") for h in asked]), "openrouter"

    monkeypatch.setattr(api.ai, "chat", chat)
    sections = [(f"Section {i}", f"brief {i}") for i in range(10)]

    out = {}
    for i in range(0, len(sections), D.AI_BATCH_SECTIONS):
        out.update(D._ai_write_many(sections[i:i + D.AI_BATCH_SECTIONS], FACTS,
                                    document_title="Concept Note"))

    assert len(calls) == 3, f"10 sections should cost 3 calls, cost {len(calls)}"
    assert len(out) == 10, "every section must still be written"
