"""Zero-cost LLM helper for the 4 marketplace ADK agents.

Per the FOSS stack rule + memory `[[feedback-zero-cost-apis]]`, the
marketplace must use only free-tier LLMs for tie-break decisions on
ambiguous supplier-uploaded data. Solar's api_manager has Claude in its
chain — explicitly NOT what we want here.

Chain (cascading fallback):
  1. OpenRouter free Nemotron (env: OPENROUTER_API_KEY,
     OPENROUTER_MODEL — default `nvidia/nemotron-nano-9b-v2:free`)
  2. Ollama local llama3.2 (env: OLLAMA_URL — default localhost:11434)
  3. None — caller falls back to the deterministic keyword core

Returns `None` cleanly when every backend is unreachable. Never raises.
Total wall time capped at ~6 s combined across both backends so a slow
network can't lock the classification pipeline.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OLLAMA_DEFAULT_URL = "http://localhost:11434"

_TIMEOUT_OPENROUTER = 5.0
_TIMEOUT_OLLAMA = 3.0


# Hard zero-cost gate. OpenRouter marks every free-tier model with the
# `:free` suffix in its model ID. We enforce that ANY model id used here
# must either end with `:free` OR appear in this explicit allowlist.
#
# Without this, an operator could set OPENROUTER_MODEL=anthropic/claude-opus-4
# and silently flip the marketplace onto a paid backend — violating the
# Free / Open-Source Stack Rule (memory `[[feedback-zero-cost-apis]]`).
_OPENROUTER_FREE_ALLOWLIST = frozenset({
    # Curated known-free models that ship without the `:free` suffix today.
    # Add new entries here as OpenRouter's free tier evolves.
})


def _is_free_openrouter_model(model_id: str) -> bool:
    return model_id.endswith(":free") or model_id in _OPENROUTER_FREE_ALLOWLIST


def call_zero_cost_llm(prompt: str, system: str = "") -> Optional[str]:
    """Try OpenRouter free, then Ollama. Return text reply or None.

    Both calls swallow every exception (network, timeout, JSON, key
    missing) and return the next in the chain so callers never have to
    `try/except` around this. This is on the hot path of supplier
    uploads — a flaky LLM must not block the deterministic fallback."""
    msg = call_openrouter(prompt, system)
    if msg:
        return msg
    msg = call_ollama(prompt, system)
    if msg:
        return msg
    return None


def call_openrouter(prompt: str, system: str = "") -> Optional[str]:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get(
        "OPENROUTER_MODEL", "nvidia/nemotron-nano-9b-v2:free"
    ).strip()
    # Zero-cost gate (Codex Slice 6 finding): refuse anything that isn't
    # explicitly a free-tier OpenRouter model. Returning None falls through
    # to the Ollama backend or the deterministic core.
    if not _is_free_openrouter_model(model):
        return None
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    body = json.dumps(
        {"model": model, "messages": messages, "max_tokens": 200, "temperature": 0.1}
    ).encode("utf-8")
    req = urllib.request.Request(
        _OPENROUTER_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://solarpro.aiappinvent.com",
            "X-Title": "SolarPro Marketplace",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_OPENROUTER) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip() or None
    except Exception:
        return None


def call_ollama(prompt: str, system: str = "") -> Optional[str]:
    base = os.environ.get("OLLAMA_URL", _OLLAMA_DEFAULT_URL).rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2")
    body = json.dumps(
        {
            "model": model,
            "prompt": (system + "\n\n" + prompt) if system else prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 200},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_OLLAMA) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip() or None
    except Exception:
        return None


def parse_json_classification(reply: Optional[str]) -> Optional[dict]:
    """Pull the first JSON object out of an LLM reply.

    LLMs often pad their JSON with prose ("Sure, here is the answer:
    {...}"). This grabs the first {..} block and parses it. Returns
    None on any failure so callers can fall back."""
    if not reply:
        return None
    start = reply.find("{")
    end = reply.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = reply[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None
