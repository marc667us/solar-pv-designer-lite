"""Slice 6 — LLM tie-break tests for the marketplace classification agent.

Covers:
  - Strong keyword match → deterministic wins, LLM is never called.
  - Weak / no keyword match → LLM rescue path is invoked.
  - LLM returns an invalid category code → keep deterministic verdict.
  - LLM returns low confidence (< 0.55) → keep deterministic verdict.
  - LLM is fully unreachable (both backends return None) → deterministic fallback.
  - parse_json_classification handles JSON-with-prose padding.
  - call_zero_cost_llm chains: OpenRouter first, Ollama on fall-through.
"""
from __future__ import annotations

from typing import Optional

import pytest

from engine.agents.marketplace import classify_product
from engine.agents.marketplace import product_classification_agent as pca
from engine.agents.marketplace import _llm


# ───────────────────────── classifier escalation ─────────────────────────


def test_strong_keyword_skips_llm(monkeypatch):
    """When deterministic confidence >= 0.55, the LLM helper must NOT be called.
    Keeps the hot path free + zero-cost for bulk supplier uploads."""
    called = {"n": 0}

    def fake_llm(prompt, system=""):
        called["n"] += 1
        return '{"category": "sockets", "confidence": 1.0}'

    monkeypatch.setattr(pca, "call_zero_cost_llm", fake_llm)
    code, conf = classify_product(
        "ABB 500 kVA Distribution Transformer", "11/0.433 kV Dyn11 ONAN", "ABB"
    )
    assert code == "transformers"
    assert conf >= 0.55
    assert called["n"] == 0, "LLM was called even though keyword confidence was strong"


def test_weak_keyword_escalates_to_llm(monkeypatch):
    """A product the keyword classifier misses must be rescued by the LLM.
    The famous example from the Slice 2 demo: 'MK 13A Twin Switched Socket'
    failed deterministic and returned ('', 0.0)."""
    def fake_llm(prompt, system=""):
        return '{"category": "sockets", "confidence": 0.92}'

    monkeypatch.setattr(pca, "call_zero_cost_llm", fake_llm)
    code, conf = classify_product("MK 13A Twin Switched Socket", "", "MK")
    assert code == "sockets"
    assert conf >= 0.92


def test_llm_invalid_category_is_rejected(monkeypatch):
    """If the LLM hallucinates a category code we don't have, fall back to
    the deterministic verdict (even if that's ('', 0.0)) — never accept
    a fabricated taxonomy entry into our DB."""
    def fake_llm(prompt, system=""):
        return '{"category": "quantum_flux", "confidence": 0.99}'

    monkeypatch.setattr(pca, "call_zero_cost_llm", fake_llm)
    code, conf = classify_product("Quantum Flux Doohickey", "reverses polarity", "Acme")
    assert code == ""
    assert conf == 0.0


def test_llm_low_confidence_is_rejected(monkeypatch):
    """LLM verdict < 0.55 confidence is no better than 'no match'. Keep
    the deterministic verdict so we err toward 'route to human review'
    instead of 'commit a guess'."""
    def fake_llm(prompt, system=""):
        return '{"category": "sockets", "confidence": 0.20}'

    monkeypatch.setattr(pca, "call_zero_cost_llm", fake_llm)
    code, conf = classify_product("Mysterious Widget", "", "Acme")
    assert (code, conf) == ("", 0.0)


def test_llm_unreachable_falls_back(monkeypatch):
    """Both LLM backends down → deterministic verdict. Never raises."""
    monkeypatch.setattr(pca, "call_zero_cost_llm", lambda prompt, system="": None)
    # The transformer phrasing still classifies via keywords — confirms the
    # LLM-down case doesn't break the deterministic core.
    code, conf = classify_product("ABB Distribution Transformer", "", "ABB")
    assert code == "transformers"
    assert conf >= 0.55


def test_llm_supplements_only_when_higher(monkeypatch):
    """Even on a weak-keyword case, if the LLM returns LOWER confidence
    than the keyword classifier, keep the keyword verdict."""
    def fake_llm(prompt, system=""):
        return '{"category": "transformers", "confidence": 0.40}'

    monkeypatch.setattr(pca, "call_zero_cost_llm", fake_llm)
    # "Transformer" is a single-word keyword hit → kw confidence ~0.60.
    # 0.40 LLM verdict shouldn't override.
    code, conf = classify_product("Random Transformer Widget", "", "Acme")
    assert code == "transformers"
    # Confidence stays at keyword level (0.6), not lowered by the LLM.
    assert conf >= 0.55
    assert conf > 0.40


# ───────────────────────── helper unit tests ─────────────────────────────


def test_parse_json_classification_handles_padded_reply():
    """LLMs often wrap JSON in prose. parse_json_classification grabs the
    first {...} block and parses it."""
    reply = "Sure! Here is the classification: {\"category\": \"sockets\", \"confidence\": 0.9} Hope that helps."
    parsed = _llm.parse_json_classification(reply)
    assert parsed == {"category": "sockets", "confidence": 0.9}


def test_parse_json_classification_handles_none():
    assert _llm.parse_json_classification(None) is None
    assert _llm.parse_json_classification("") is None
    assert _llm.parse_json_classification("no json here") is None


def test_parse_json_classification_handles_broken_json():
    assert _llm.parse_json_classification("{this is not json}") is None


def test_call_zero_cost_llm_chain(monkeypatch):
    """OpenRouter first, Ollama on fall-through."""
    calls = []

    def fake_openrouter(prompt, system=""):
        calls.append("openrouter")
        return None  # OpenRouter unreachable

    def fake_ollama(prompt, system=""):
        calls.append("ollama")
        return "ok from ollama"

    monkeypatch.setattr(_llm, "call_openrouter", fake_openrouter)
    monkeypatch.setattr(_llm, "call_ollama", fake_ollama)
    out = _llm.call_zero_cost_llm("hi", "you are an agent")
    assert out == "ok from ollama"
    assert calls == ["openrouter", "ollama"]


def test_call_zero_cost_llm_short_circuits_on_openrouter_success(monkeypatch):
    """If OpenRouter answers, Ollama must NOT be called."""
    calls = []
    monkeypatch.setattr(_llm, "call_openrouter",
                        lambda p, s="": (calls.append("openrouter"), "ok from openrouter")[1])
    monkeypatch.setattr(_llm, "call_ollama",
                        lambda p, s="": calls.append("ollama") or "should not be called")
    out = _llm.call_zero_cost_llm("hi")
    assert out == "ok from openrouter"
    assert calls == ["openrouter"]


# ───────────────────── integration with the row-pipeline ─────────────────


def test_openrouter_refuses_non_free_model(monkeypatch):
    """Codex Slice 6 finding (high severity): OPENROUTER_MODEL was
    unrestricted. Setting it to a paid model would silently flip the
    marketplace onto a paid backend. The fix: refuse anything that
    isn't tagged :free or in the explicit allowlist."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-key")
    # A paid model id must short-circuit and return None.
    for paid in (
        "anthropic/claude-opus-4",
        "openai/gpt-4",
        "google/gemini-pro-1.5",
        "meta-llama/llama-3.3-70b-instruct",  # no :free suffix
    ):
        monkeypatch.setenv("OPENROUTER_MODEL", paid)
        out = _llm.call_openrouter("classify this", system="you are an agent")
        assert out is None, f"paid model '{paid}' was not blocked"


def test_openrouter_accepts_free_models(monkeypatch):
    """Free-tier models (everything ending in :free) must be allowed."""
    def fake_urlopen(req, timeout=None):
        class _Resp:
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
            def read(self_):
                import json
                return json.dumps({
                    "choices": [{"message": {"content": "ok from free model"}}]
                }).encode()
        return _Resp()
    monkeypatch.setattr(_llm.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-fake-key")
    for free in (
        "nvidia/nemotron-nano-9b-v2:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
    ):
        monkeypatch.setenv("OPENROUTER_MODEL", free)
        out = _llm.call_openrouter("hi", system="agent")
        assert out == "ok from free model", f"free model '{free}' was blocked"


def test_llm_rescue_flows_through_classify_extracted_row(monkeypatch):
    """The Supplier Product Agent orchestrator (classify_extracted_row) must
    honour the LLM rescue path — if classification confidence is high enough,
    the verdict promotes from 'review' to 'accept'."""
    monkeypatch.setattr(
        pca, "call_zero_cost_llm",
        lambda p, s="": '{"category": "sockets", "confidence": 0.95}',
    )
    from engine.agents.marketplace import classify_extracted_row
    row = {
        "name": "MK 13A Twin Switched Socket",
        "brand": "MK",
        "spec": "13A twin switched socket, white, flush",
        "price": "$14",
        "current_rating": "13A",
        "gang": "2",
    }
    out = classify_extracted_row(row)
    assert out["classification"]["category"] == "sockets"
    assert out["classification"]["confidence"] >= 0.55
    # With a strong classification, the verdict should NOT be 'reject';
    # 'accept' or 'review' (for missing spec fields) is acceptable.
    assert out["verdict"] in ("accept", "review")
