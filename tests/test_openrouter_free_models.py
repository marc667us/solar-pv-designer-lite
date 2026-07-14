"""The AI chain must not be one deprecation away from silence.

WHAT HAPPENED (2026-07-14). The app asked OpenRouter for
`meta-llama/llama-3.1-8b-instruct:free`. OpenRouter retired it. Every call 404'd, the chain
fell through Ollama (not running on Render) and GitHub Models (not configured) to
`rule_based` -- and the enterprise document writer, which correctly refuses to present a
canned fallback string as a drafted section, returned None for every activity and asked the
operator a question instead.

The owner reported it as "it's not writing, it's rather asking me questions". Nothing
crashed. Nothing was logged as an outage. `/api/health/ai` still reported "configured",
because a key was set. The feature was simply gone.

TWO FAILURES, AND THE TESTS BELOW GUARD BOTH:

  1. A SINGLE HARDCODED MODEL ID is a standing dependency on a third party's deprecation
     schedule. The fix is a LIST, so one retirement costs a fallback rather than the feature.
  2. THE ZERO-COST RULE (CLAUDE.md) has to be ENFORCED, not merely observed. An operator who
     points OPENROUTER_MODEL at a paid id would start billing the project silently, one
     document at a time.

`test_every_configured_model_still_exists_on_openrouter` is the one that would actually have
caught the outage. It talks to the network, so it SKIPS when offline rather than failing --
a guard that goes red on a train is a guard people learn to ignore.
"""

from __future__ import annotations

import importlib
import json
import os
import urllib.request

import pytest

import api_manager


@pytest.fixture()
def client(monkeypatch):
    """A fresh _AIClient, with the operator's env vars cleared."""
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    importlib.reload(api_manager)
    c = api_manager._AIClient(api_manager._Store())
    return c


def test_the_chain_tries_more_than_one_model(client):
    """The whole point. One id is one deprecation away from an outage."""
    assert len(client.openrouter_models) >= 3, (
        "the OpenRouter fallback list is too short to survive a model retirement -- which is "
        "the failure this list exists to prevent"
    )


def test_the_retired_model_is_gone(client):
    """The specific id that broke it. Nobody puts this back by accident."""
    assert "meta-llama/llama-3.1-8b-instruct:free" not in client.openrouter_models


def test_a_paid_model_is_refused_even_when_the_operator_asks_for_it(monkeypatch):
    """CLAUDE.md zero-cost rule. A paid id must not bill the project silently."""
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o")        # paid: no `:free`
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    c = api_manager._AIClient(api_manager._Store())

    assert "openai/gpt-4o" not in c.openrouter_models
    assert c.openrouter_models, (
        "dropping the paid model took the whole chain down -- refusing to spend money is "
        "never a reason to remove the feature; it should fall back to the free list"
    )
    assert all(m.endswith(":free") for m in c.openrouter_models)


def test_the_operators_free_choice_is_honoured_and_goes_first(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/qwen3-coder:free")
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    c = api_manager._AIClient(api_manager._Store())

    assert c.openrouter_models[0] == "qwen/qwen3-coder:free"
    assert c.openrouter_model == "qwen/qwen3-coder:free"
    # ...and the fallbacks are still behind it, so their retirement story is unchanged.
    assert len(c.openrouter_models) > 1


def test_no_duplicates(monkeypatch):
    """A model listed twice would be retried twice on the same 429, for no gain."""
    monkeypatch.setenv("OPENROUTER_MODEL", api_manager._AIClient.OPENROUTER_FREE_FALLBACKS[0])
    monkeypatch.delenv("OPENROUTER_MODELS", raising=False)
    c = api_manager._AIClient(api_manager._Store())
    assert len(c.openrouter_models) == len(set(c.openrouter_models))


@pytest.mark.skipif(os.environ.get("NO_NETWORK_TESTS") == "1", reason="network disabled")
def test_every_configured_model_still_exists_on_openrouter(client):
    """THE GUARD THAT WOULD HAVE CAUGHT THE OUTAGE.

    Asks OpenRouter which models it actually serves, and checks ours are among them. No API
    key needed -- the catalogue is public.

    It SKIPS when the network is unreachable. A test that fails on a train is a test people
    learn to ignore, and this one is worth listening to.
    """
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=30) as r:
            live = {m["id"] for m in json.loads(r.read())["data"]}
    except Exception as e:                                    # offline, DNS, rate limit
        pytest.skip(f"OpenRouter catalogue unreachable: {e}")

    assert live, "OpenRouter returned an empty catalogue; the check would pass vacuously"

    dead = [m for m in client.openrouter_models if m not in live]
    assert not dead, (
        f"OpenRouter no longer serves {dead}. Every call to these 404s. If the whole list "
        f"rots, the AI chain silently degrades to `rule_based` and the enterprise document "
        f"writer stops writing and starts interrogating the operator -- which is exactly the "
        f"bug this file exists to prevent. Replace them from "
        f"https://openrouter.ai/api/v1/models (ids ending `:free`)."
    )


def test_a_deadline_bounds_the_SOCKET_not_merely_the_loop(monkeypatch):
    """CODEX HIGH, 2026-07-14. The budget must bound the HTTP call, not just the loop.

    "Answer everything" had a 55s AI budget checked BETWEEN batches. But one batch calls
    chat() once, and chat()'s OpenRouter path tries five fallback models at 30s each -- 150
    seconds inside a single call, past gunicorn's 120s timeout, on a single-instance free
    tier. The owner pressing the button would hang the app for everybody.

    Here every model is SLOW: each hangs for its full timeout. A fake clock advances by
    exactly that, so the budget really runs out -- which is the case the fix is for.
    """
    c = api_manager._AIClient(api_manager._Store())
    c.openrouter_key = "sk-test"
    c.openrouter_models = ["a:free", "b:free", "c:free", "d:free", "e:free"]

    now = [1000.0]
    monkeypatch.setattr(api_manager.time, "time", lambda: now[0])

    seen = []

    def _fake_urlopen(req, timeout=None):
        seen.append(timeout)
        now[0] += timeout          # the model hung for the whole timeout, as a slow one does
        raise OSError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    deadline = now[0] + 55.0                       # the drafting budget
    assert c._openrouter([{"role": "user", "content": "x"}], "", 100,
                         deadline=deadline) is None

    assert seen, "no request was attempted at all"
    assert sum(seen) <= 55.0 + 0.01, (
        f"the call spent {sum(seen)}s of wall clock against a 55s budget -- the deadline is "
        f"being treated as advice, not as a ceiling, and gunicorn will kill the request"
    )
    assert now[0] <= deadline + 0.01
    assert len(seen) < 5, (
        "it kept opening sockets after the budget was spent; the loop must stop"
    )


def test_without_a_deadline_the_old_per_model_timeout_stands(monkeypatch):
    """A background job has no request to hang. It should not be crippled by the fix."""
    c = api_manager._AIClient(api_manager._Store())
    c.openrouter_key = "sk-test"
    c.openrouter_models = ["a:free"]

    seen = []

    def _fake_urlopen(req, timeout=None):
        seen.append(timeout)
        raise OSError("nope")

    import urllib.request as ur
    monkeypatch.setattr(ur, "urlopen", _fake_urlopen)

    c._openrouter([{"role": "user", "content": "x"}], "", 100)   # no deadline
    assert seen == [30]
