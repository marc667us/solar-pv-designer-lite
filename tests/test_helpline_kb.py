"""The Helpline rule-based KB answers the right question.

WHY THIS FILE EXISTS
--------------------
`_KB` is a list of (keywords, answer) pairs scanned in order, FIRST MATCH WINS. That makes
ORDER load-bearing, and the repo already carries a patch whose whole job was to fix an
ordering mistake (patch_helpline_topic_training_reorder.py). Nothing guarded it: there was
no test for the assistant at all.

The specific trap this pins: the word "enterprise" belongs to the PRICING-PLAN tuple.
  - Before 2026-07-13, "how do I run an enterprise programme?" was answered with
    subscription-tier copy, because the plan tuple matched first.
  - The naive fix -- give the new Enterprise Programme entries the keyword "enterprise" and
    put them first -- simply REVERSES the bug: "what does the Enterprise plan cost?" would
    start returning programme-management copy.

Both directions must work, so both are asserted here.

`_KB` and `_rule_reply` are defined INSIDE the assistant_chat() route, so they cannot be
imported. The KB literal is lifted out of the source with `ast`, and the matcher below is
the documented one from web_app.py (leading \\b, NO trailing \\b, so "plan" matches "plans"
and "calcul" matches "calculate", while "load" does not fire on "download").
"""
from __future__ import annotations

import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _extract_kb() -> list[tuple[list[str], str]]:
    """Lift the `_KB` list literal out of web_app.py without importing the app."""
    # utf-8-SIG: web_app.py starts with a BOM, which ast.parse rejects as U+FEFF.
    src = open(os.path.join(ROOT, "web_app.py"),
               encoding="utf-8-sig", errors="replace").read()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_KB":
                    return ast.literal_eval(node.value)
    raise AssertionError("_KB not found in web_app.py")


KB = _extract_kb()


def rule_reply(msg_lower: str):
    """The matcher exactly as web_app.py documents it. First match wins."""
    for keywords, answer in KB:
        for k in keywords:
            if re.search(r"\b" + re.escape(k), msg_lower):
                return answer
    return None


def _index_of(keyword: str) -> int:
    for i, (keywords, _a) in enumerate(KB):
        if keyword in keywords:
            return i
    raise AssertionError(f"no KB entry owns the keyword {keyword!r}")


# --- shape -------------------------------------------------------------------

def test_kb_is_well_formed():
    assert KB, "the KB is empty"
    for i, entry in enumerate(KB):
        assert isinstance(entry, tuple) and len(entry) == 2, f"entry {i} is not a 2-tuple"
        keywords, answer = entry
        assert isinstance(keywords, list) and keywords, f"entry {i}: no keywords"
        assert all(isinstance(k, str) and k for k in keywords), f"entry {i}: bad keyword"
        assert isinstance(answer, str) and answer.strip(), f"entry {i}: empty answer"


# --- the two-way false positive ---------------------------------------------

def test_an_enterprise_programme_question_is_not_answered_with_pricing():
    """THE BUG. 'enterprise' belongs to the plan tuple, so this used to return plan copy."""
    answer = rule_reply("how do i run an enterprise programme?")
    assert answer is not None, "no KB entry matched an enterprise programme question"
    assert "/enterprise" in answer, (
        "an enterprise-programme question was answered with something that is not about "
        f"the Enterprise Programme module: {answer[:120]!r}"
    )
    assert "Free Trial" not in answer, "answered with pricing-plan copy"


def test_an_enterprise_PLAN_question_still_reaches_the_plan_answer():
    """THE REVERSE BUG, which is what claiming the bare word 'enterprise' would have caused."""
    answer = rule_reply("what does the enterprise plan cost?")
    assert answer is not None
    assert "/enterprise" not in answer, (
        "a PRICING question was hijacked by the Enterprise Programme entry -- the new "
        f"entries must not claim the bare word 'enterprise': {answer[:120]!r}"
    )


def test_no_new_entry_claims_the_bare_word_enterprise():
    """Structural guard: only the plan tuple may own bare 'enterprise'."""
    owners = [i for i, (kws, _a) in enumerate(KB) if "enterprise" in kws]
    assert len(owners) == 1, (
        f"{len(owners)} KB entries claim the bare keyword 'enterprise'. Exactly one (the "
        f"pricing-plan tuple) may. Use a phrase like 'enterprise programme' instead."
    )
    assert "plan" in KB[owners[0]][0], "the sole owner of 'enterprise' should be the plan tuple"


def test_enterprise_entries_precede_the_plan_tuple():
    """Order is load-bearing: first match wins."""
    plan_i = _index_of("plan")
    prog_i = _index_of("enterprise programme")
    assert prog_i < plan_i, (
        f"the Enterprise Programme entry (index {prog_i}) must come BEFORE the pricing-plan "
        f"tuple (index {plan_i}), or every enterprise question gets answered with plan copy."
    )


# --- the new feature areas actually answer ------------------------------------

@pytest.mark.parametrize("question, must_mention", [
    ("how do i import beneficiaries from a spreadsheet?", "staged"),
    ("which site should we build first?",                 "priority"),
    ("what are the stage gates?",                         "named role"),
    ("what is the reference design?",                     "one reference design"),
    ("how do i design a solar farm?",                     "/large-scale-solar"),
    ("show me the 3d digital twin",                       "digital-twin"),
    ("can you walk me through this page?",                "Help & Tutorial"),
])
def test_new_feature_areas_are_answered(question, must_mention):
    answer = rule_reply(question)
    assert answer is not None, f"no KB entry matched: {question!r}"
    assert must_mention.lower() in answer.lower(), (
        f"{question!r} -> answer does not mention {must_mention!r}: {answer[:140]!r}"
    )


def test_the_assistant_system_prompt_knows_the_new_modules():
    """The LLM path (not the fallback) reads _ASSISTANT_SYSTEM. It must be current too."""
    # utf-8-SIG: web_app.py starts with a BOM, which ast.parse rejects as U+FEFF.
    src = open(os.path.join(ROOT, "web_app.py"),
               encoding="utf-8-sig", errors="replace").read()
    start = src.index("_ASSISTANT_SYSTEM")
    end = src.index("_KB = [")
    prompt = src[start:end]
    for marker in ("=== ENTERPRISE PROGRAMME",
                   "=== GENERATION STATION",
                   "=== 3D DIGITAL TWIN",
                   "=== PROJECT FUNDING",
                   "=== IN-APP TUTORIALS"):
        assert marker in prompt, f"_ASSISTANT_SYSTEM is missing the section {marker!r}"
