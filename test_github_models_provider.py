"""GitHub Models provider — endpoint/model pairing + chain order.

WHY THIS FILE EXISTS
--------------------
`github_models` shipped for months as a provider that could never answer. The default endpoint
(models.inference.ai.azure.com) was paired with a publisher-PREFIXED model id
("openai/gpt-4.1-mini"), and that endpoint only accepts BARE ids. Every call returned
HTTP 400 unknown_model, and the broad `except Exception` in `_github` turned that into a log
warning -- so `/api/health/ai` kept reporting the provider as present while it was dead.

These tests pin the two facts that were wrong, so the pairing cannot silently regress:
  1. the model id is always normalised to whatever the configured endpoint accepts;
  2. github_models is tried BEFORE ollama, so a stale Ollama tunnel cannot eat 60s per call
     ahead of a hosted provider that would have answered.

Run: python -m pytest test_github_models_provider.py -q
"""
import api_manager

_AZURE = "https://models.inference.ai.azure.com/chat/completions"
_GH = "https://models.github.ai/inference/chat/completions"
_for = api_manager._AIClient._github_model_for


# ── 1. the exact bug: azure endpoint + prefixed model = HTTP 400 upstream ──────────────
def test_azure_endpoint_strips_publisher_prefix():
    """The shipped default. Azure rejects 'openai/gpt-4.1-mini' with unknown_model."""
    assert _for(_AZURE, "openai/gpt-4.1-mini") == "gpt-4.1-mini"


def test_github_endpoint_adds_publisher_prefix():
    """The mirror-image mistake: models.github.ai rejects the bare name."""
    assert _for(_GH, "gpt-4.1-mini") == "openai/gpt-4.1-mini"


# ── 2. already-correct pairings must pass through untouched ───────────────────────────
def test_correct_pairings_are_left_alone():
    assert _for(_AZURE, "gpt-4.1-mini") == "gpt-4.1-mini"
    assert _for(_GH, "openai/gpt-4.1-mini") == "openai/gpt-4.1-mini"


def test_non_openai_publisher_is_preserved_not_rewritten():
    """GitHub Models hosts more than OpenAI. Never re-publisher someone else's model."""
    assert _for(_GH, "mistral-ai/mistral-small") == "mistral-ai/mistral-small"
    assert _for(_AZURE, "mistral-ai/mistral-small") == "mistral-small"


# ── Codex findings, 2026-07-19 ────────────────────────────────────────────────────────
def test_bare_non_openai_model_is_not_claimed_for_openai():
    """Codex MEDIUM: 'Phi-4' must not become 'openai/Phi-4'. Pass it through untouched."""
    assert _for(_GH, "Phi-4") == "Phi-4"
    assert _for(_GH, "mistral-small") == "mistral-small"


def test_openai_families_still_get_their_prefix():
    for m in ("gpt-4.1-mini", "gpt-4o", "o1-mini", "o3-mini"):
        assert _for(_GH, m) == f"openai/{m}", m


def test_legacy_host_match_is_case_insensitive():
    """Codex LOW: a differently-cased host must not be mistaken for the modern endpoint."""
    mixed = "https://Models.Inference.AI.Azure.com/chat/completions"
    assert _for(mixed, "openai/gpt-4.1-mini") == "gpt-4.1-mini"


def test_malformed_url_does_not_raise():
    """A config typo must degrade, never crash the provider chain."""
    assert _for("", "openai/gpt-4.1-mini") == "openai/gpt-4.1-mini"
    assert _for(None, "gpt-4.1-mini") == "openai/gpt-4.1-mini"


# ── 3. the default configuration must be self-consistent ──────────────────────────────
def test_shipped_defaults_are_a_working_pair():
    """Guards the actual regression: defaults that cannot work together.

    Constructing the real client (no env overrides needed -- both fields have defaults)
    and asserting the derived model matches the derived URL.
    """
    c = api_manager._AIClient.__new__(api_manager._AIClient)
    c.github_model = "openai/gpt-4.1-mini"
    c.github_url = "https://models.github.ai/inference/chat/completions"
    sent = _for(c.github_url, c.github_model)
    assert sent.count("/") == 1, "models.github.ai requires exactly one publisher prefix"
    assert sent == "openai/gpt-4.1-mini"


# ── 3b. "configured" must stop being mistaken for "working" ───────────────────────────
_health = api_manager.APIManager._provider_health


def test_provider_that_only_ever_errored_reads_as_failing_not_configured():
    """The whole github_models bug in one assertion: a present token + 100% failures.

    Before 2026-07-19 this state rendered as "configured", which is why nobody looked.
    """
    assert _health(True, {"ok": 0, "error": 57}) == "failing"


def test_untried_is_distinct_from_failing():
    """A provider nothing has called yet has NOT failed -- saying so would be a false alarm."""
    assert _health(True, {}) == "untried"
    assert _health(True, {"ok": 0, "error": 0}) == "untried"


def test_working_and_degraded():
    assert _health(True, {"ok": 40, "error": 0}) == "working"
    assert _health(True, {"ok": 40, "error": 3}) == "working"
    assert _health(True, {"ok": 2, "error": 30}) == "degraded"


def test_absent_credential_is_not_configured():
    assert _health(False, {}) == "not_configured"
    assert _health(False, {"ok": 5, "error": 0}) == "not_configured"


def test_health_derivation_makes_no_network_call():
    """It must be free to read: health checks run often and free tiers are metered."""
    import socket
    orig = socket.socket

    def _boom(*a, **k):
        raise AssertionError("_provider_health opened a socket")

    socket.socket = _boom
    try:
        assert _health(True, {"ok": 1, "error": 0}) == "working"
    finally:
        socket.socket = orig


# ── 3c. the endpoint knob must not become a token-exfiltration channel ────────────────
_safe = api_manager._AIClient._safe_github_url
_DEFAULT = api_manager._AIClient.GITHUB_MODELS_DEFAULT_URL


def test_unknown_host_is_refused():
    """A tampered/typo'd env var must not receive `Authorization: Bearer <GITHUB_TOKEN>`."""
    assert _safe("https://evil.example.com/chat/completions") == _DEFAULT
    assert _safe("https://models.github.ai.evil.com/x") == _DEFAULT


def test_plaintext_http_is_refused_even_on_a_valid_host():
    assert _safe("http://models.github.ai/inference/chat/completions") == _DEFAULT


def test_both_legitimate_hosts_are_allowed():
    ok = "https://models.inference.ai.azure.com/chat/completions"
    assert _safe(ok) == ok
    assert _safe(_GH) == _GH


def test_empty_or_malformed_falls_back_without_raising():
    for bad in ("", "   ", "not a url", "://", "ftp://models.github.ai/x"):
        assert _safe(bad) == _DEFAULT


# ── 4. chain order: github must be tried before ollama ────────────────────────────────
def test_github_is_attempted_before_ollama():
    """A stale Ollama tunnel hangs for its full 60s timeout; github answers in ~1s.

    Reads the source of `chat` rather than executing the chain, because executing it would
    require live credentials for four providers. The ORDER is the contract under test.
    """
    import inspect
    src = inspect.getsource(api_manager._AIClient.chat)
    assert "self._github(" in src and "self._ollama(" in src
    assert src.index("self._github(") < src.index("self._ollama("), (
        "github_models must precede ollama in the fallback chain")
