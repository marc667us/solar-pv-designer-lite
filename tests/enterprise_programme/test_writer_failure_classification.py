"""The writer must say WHY it was unavailable, not merely THAT it was.

The owner hit "the document writer was not available" repeatedly across three sessions with no
way to act on it. Codex (HIGH, 2026-07-18) proved the cause was unknowable from anything
observable: every provider failure -- 401, 429, a retired model id, a timeout, a DNS failure --
was funnelled into one `except Exception` and logged as the single word "error".

These tests pin the two halves of the fix:
  1. The classifier maps an exception to the RIGHT bucket (and a retired model is NOT auth).
  2. The operator message carries that bucket through to the screen, WITHOUT breaking the
     fail-loud contract that `test_route_fails_loudly_when_the_writer_is_unreachable` guards.

They are written to FAIL if the classification is collapsed back into one bucket.
"""

import socket
import time
import urllib.error
import urllib.request

import pytest

import api_manager
from app.enterprise_programme import documents


# The minimum programme facts `_brief()` needs. Passing {} raises KeyError('name')
# INSIDE the try block, which the handler then classifies as "error" -- a green-looking test
# that proves nothing about the path it claims to cover.
_FACTS = {"name": "Takoradi Shops Solar Programme",
          "code": "TKS-SOLAR-001",
          "phase_code": "R4P1_INITIATION",
          "description": "Reduce shop grid electricity cost using solar."}


def _http_error(code):
    """An HTTPError carrying `code`, with no body read -- exactly as production sees it."""
    return urllib.error.HTTPError("https://openrouter.ai", code, "err", {}, None)


class TestClassifier:
    """Each provider failure gets its own bucket."""

    @pytest.mark.parametrize("code,expected", [
        (401, "auth"),
        (403, "auth"),
        (429, "rate_limited"),
        (404, "model_deprecated"),
        (400, "bad_request"),
        (500, "error"),
    ])
    def test_http_status_maps_to_its_own_bucket(self, code, expected):
        assert api_manager._AIClient.classify_ai_failure(_http_error(code)) == expected

    def test_a_retired_model_is_not_reported_as_an_auth_problem(self):
        """THE REGRESSION THIS FILE EXISTS FOR.

        Two of the five free fallbacks are marked "going away 2026-07-19". A retired id returns
        404. If 404 and 401 share a bucket, the operator rotates a perfectly good key and the
        outage continues -- which is precisely the wasted session this classification prevents.
        """
        assert api_manager._AIClient.classify_ai_failure(_http_error(404)) != "auth"
        assert api_manager._AIClient.classify_ai_failure(_http_error(400)) != "auth"

    def test_a_malformed_request_is_not_reported_as_a_retired_model(self):
        """Codex (HIGH): a 400 is usually OUR bad payload. Filing it under "model retired"
        sends the operator to swap healthy model ids while the real defect is in our request.
        """
        assert api_manager._AIClient.classify_ai_failure(_http_error(400)) == "bad_request"
        assert api_manager._AIClient.classify_ai_failure(_http_error(400)) != "model_deprecated"

    def test_rate_limit_is_not_reported_as_an_auth_problem(self):
        assert api_manager._AIClient.classify_ai_failure(_http_error(429)) != "auth"

    def test_timeout_and_network_are_distinguished(self):
        assert api_manager._AIClient.classify_ai_failure(socket.timeout()) == "timeout"
        assert api_manager._AIClient.classify_ai_failure(
            urllib.error.URLError(socket.timeout())) == "timeout"
        assert api_manager._AIClient.classify_ai_failure(
            urllib.error.URLError("no route")) == "network"

    def test_empty_and_malformed_completions_are_distinguished(self):
        # _openrouter raises ValueError("empty completion") for a 200 with nothing in it.
        assert api_manager._AIClient.classify_ai_failure(ValueError("empty completion")) \
            == "empty_completion"
        # A 200 whose JSON is not the shape we expect surfaces as KeyError/IndexError.
        assert api_manager._AIClient.classify_ai_failure(KeyError("choices")) == "bad_response"
        assert api_manager._AIClient.classify_ai_failure(IndexError()) == "bad_response"

    def test_an_unknown_failure_is_never_guessed(self):
        """An unrecognised exception must land in `error`, not be forced into a real bucket.

        A wrong specific answer is worse than an honest "unrecognised": it sends the operator
        to fix something that is not broken.
        """
        assert api_manager._AIClient.classify_ai_failure(RuntimeError("who knows")) == "error"

    def test_the_classifier_never_reads_the_http_body(self):
        """THE LEAK GUARD. Codex (HIGH): the provider's error BODY can echo prompt fragments,
        and this repo leaked five live secrets into PUBLIC CI logs for 35 days on 2026-07-10.

        A body that raises on read proves we never touch it -- if the classifier ever calls
        .read(), this test fails loudly rather than leaking quietly.
        """
        class ExplodingBody:
            def read(self, *a, **k):
                raise AssertionError("the classifier read the HTTP error body")

            # HTTPError closes its fp on teardown; without this the assertion above is drowned
            # in an unrelated AttributeError during garbage collection.
            def close(self):
                pass

        err = urllib.error.HTTPError("https://openrouter.ai", 429, "err", {}, ExplodingBody())
        assert api_manager._AIClient.classify_ai_failure(err) == "rate_limited"


class TestNoRawProviderTextIsLogged:
    """api_logs must receive an ENUM, never the exception text.

    Codex gap (2026-07-18): nothing proved `_openrouter` stopped passing `str(e)` to
    `_Store.log`. The classifier being clean is not the same as the CALLER being clean, and it
    is the caller that writes to the database.
    """

    def test_openrouter_logs_the_enum_not_the_exception_text(self, monkeypatch):
        client = api_manager._AIClient.__new__(api_manager._AIClient)
        client.openrouter_key = "sk-test"
        client.openrouter_models = ["meta-llama/llama-3.3-70b-instruct:free"]
        client.openrouter_model = client.openrouter_models[0]

        logged = []

        class _Spy:
            def log(self, provider, operation, status, duration_ms=0, error=""):
                logged.append(error)

        client._s = _Spy()

        # A secret-shaped payload in the exception text. If ANY of it reaches the log, the
        # 2026-07-10 leak class is back.
        #
        # Assembled at runtime rather than written as a literal: a hard-coded string of this
        # shape trips GitHub secret scanning and reads like a real leak to anyone auditing the
        # repo. The canary works the same either way -- what matters is that this value never
        # reaches api_logs, not what it spells.
        secret = "sk-" + "or-v1-" + ("NOT" "A" "REAL" "KEY") + "0123456789abcdef"

        def _boom(*a, **k):
            raise urllib.error.HTTPError(
                f"https://openrouter.ai?key={secret}", 429, f"denied {secret}", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", _boom)

        assert client._openrouter([{"role": "user", "content": "x"}], "", 100) is None
        assert logged, "the failure was not logged at all"
        for entry in logged:
            assert secret not in str(entry), f"secret leaked into api_logs: {entry!r}"
            assert str(entry) == "rate_limited", (
                f"expected the enum, got raw provider text: {entry!r}")


class TestReasonIsRequestLocal:
    """One operator must never be shown another operator's failure cause.

    Codex (MEDIUM, 2026-07-18): both slots were process-global, so concurrent generation could
    cross the wires. A confidently WRONG diagnosis is worse than the generic message this work
    replaces -- it sends someone to fix healthy config.
    """

    def test_two_contexts_do_not_share_a_writer_reason(self):
        import concurrent.futures

        def _worker(reason):
            # Each thread runs in its own context, as a request does.
            documents._record_writer_failure(reason)
            time.sleep(0.02)  # force interleaving
            return documents.last_writer_failure()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(_worker, "auth")
            b = pool.submit(_worker, "rate_limited")
            assert a.result() == "auth"
            assert b.result() == "rate_limited"

    def test_two_contexts_do_not_share_a_provider_reason(self):
        import concurrent.futures

        client = api_manager._AIClient.__new__(api_manager._AIClient)

        def _worker(reason):
            client.last_failure_reason = reason
            time.sleep(0.02)
            return client.last_failure_reason

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(_worker, "auth")
            b = pool.submit(_worker, "capped:x")
            assert a.result() == "auth"
            assert b.result() == "capped:x"


class TestTheModelChainOrder:
    """The chain must not spend the quota rediscovering which models are rate-limited.

    Measured 2026-07-18 against the live key: four of the five free models returned 429 and
    the only one answering sat FOURTH. Every section therefore paid three failed round trips
    before reaching the model that worked -- thirty wasted requests on a ten-section report,
    against a free allowance the failures plausibly count towards themselves.
    """

    def setup_method(self):
        api_manager._AIClient._last_good_model = ""

    def teardown_method(self):
        api_manager._AIClient._last_good_model = ""

    def _client(self):
        c = api_manager._AIClient.__new__(api_manager._AIClient)
        c.openrouter_models = list(api_manager._AIClient.OPENROUTER_FREE_FALLBACKS)
        return c

    def test_the_model_that_last_answered_is_tried_first(self):
        c = self._client()
        later = c.openrouter_models[3]
        assert c._ordered_models()[0] != later, "precondition: not already first"

        api_manager._AIClient._last_good_model = later
        assert c._ordered_models()[0] == later

    def test_no_model_is_ever_dropped(self):
        """A rate limit is TEMPORARY. A model that 429s now may be the only one answering in
        an hour, so promoting a winner must never mean discarding a loser.
        """
        c = self._client()
        api_manager._AIClient._last_good_model = c.openrouter_models[2]
        assert sorted(c._ordered_models()) == sorted(c.openrouter_models)

    def test_a_stale_hint_naming_a_retired_model_is_ignored(self):
        """The hint outlives deployments and free-tier line-ups change. A hint naming a model
        no longer in the list must not inject it back into the chain.
        """
        c = self._client()
        api_manager._AIClient._last_good_model = "some/retired-model:free"
        assert c._ordered_models() == c.openrouter_models

    def test_the_default_order_leads_with_a_model_that_was_measured_working(self):
        """Guards against someone re-sorting this tuple by preference rather than evidence."""
        first = api_manager._AIClient.OPENROUTER_FREE_FALLBACKS[0]
        assert first == "nvidia/nemotron-3-super-120b-a12b:free", (
            "the lead model is set by measurement, not taste -- re-measure before changing it")

    def test_every_candidate_is_still_free(self):
        """The zero-cost rule (CLAUDE.md). Reordering must never smuggle in a paid model."""
        for m in api_manager._AIClient.OPENROUTER_FREE_FALLBACKS:
            assert m.endswith(":free"), f"{m} is not a free model"


class TestOperatorMessage:
    """The bucket has to survive the trip to the operator's screen."""

    def setup_method(self):
        documents._record_writer_failure("")

    def test_the_fail_loud_contract_is_preserved(self):
        """`test_route_fails_loudly_when_the_writer_is_unreachable` asserts the byte substring
        "writing service is unavailable". Every message this function can produce must contain
        it, or the fail-loud guarantee silently stops being tested.
        """
        for reason in ("", "auth", "rate_limited", "model_deprecated", "timeout",
                       "empty_completion", "bad_response", "network", "output_rejected",
                       "bad_request", "error", "capped:daily cap", "something_unmapped"):
            documents._record_writer_failure(reason)
            assert "writing service is unavailable" in documents._writer_unavailable_message()

    def test_each_cause_produces_a_distinguishable_message(self):
        """If two causes read identically the operator cannot act on them differently, which
        is the whole defect this work fixes.
        """
        seen = {}
        for reason in ("auth", "rate_limited", "model_deprecated", "bad_request", "timeout",
                       "network", "output_rejected", "capped:x"):
            documents._record_writer_failure(reason)
            seen[reason] = documents._writer_unavailable_message()
        assert len(set(seen.values())) == len(seen), f"messages collide: {seen}"

    def test_an_exhausted_internal_cap_is_not_blamed_on_the_provider(self):
        """Codex rated the app's OWN cap a better permanent-failure candidate than a provider
        quota, because a daily quota resets and this does not. The fix is config here -- so the
        message must point at the cap, not at a key or a model.
        """
        documents._record_writer_failure("capped:monthly spend")
        msg = documents._writer_unavailable_message()
        assert "budget cap" in msg
        assert "OPENROUTER_API_KEY" not in msg

    def test_our_own_refusal_is_not_blamed_on_the_provider(self):
        """A draft rejected by the safety check means the provider ANSWERED. Reporting that as
        a provider outage sends the operator hunting a dead key that is alive.
        """
        documents._record_writer_failure("output_rejected")
        msg = documents._writer_unavailable_message()
        assert "safety check" in msg
        assert "provider" in msg  # names who did NOT fail

    def test_no_reason_recorded_falls_back_to_the_original_message(self):
        documents._record_writer_failure("")
        assert documents._writer_unavailable_message() == (
            "the writing service is unavailable; try again later")

    def test_ai_write_records_our_refusal_when_the_safety_check_rejects_a_draft(self,
                                                                               monkeypatch):
        """THE RECORDING, not merely the formatting.

        Found by mutation testing: deleting the `_record_writer_failure("output_rejected")`
        call left every test in this file green, because they all set the reason by hand. A
        message formatter proven correct on inputs nothing produces is not proof of anything.
        This drives `_ai_write` itself.
        """
        class _FakeAI:
            last_failure_reason = ""

            def chat(self, *a, **k):
                # The provider ANSWERED. Everything after this is our own decision.
                return "The World Bank approved funding on 1 July 2026.", "openrouter"

        monkeypatch.setattr(api_manager.api, "ai", _FakeAI())
        monkeypatch.setattr(documents, "_ai_output_violation",
                            lambda prose, facts: "settled-fact claim")

        documents._record_writer_failure("")
        out = documents._ai_write("Subject", _FACTS, brief="b", document_title="t")

        assert out is None, "a rejected draft must not be returned as prose"
        assert documents.last_writer_failure() == "output_rejected"
        assert "safety check" in documents._writer_unavailable_message()

    def test_ai_write_records_the_providers_reason_when_the_chain_falls_through(self,
                                                                               monkeypatch):
        """The provider layer classified the failure at the only point the HTTP status was in
        scope. `_ai_write` must carry that value, not overwrite it with a generic one.
        """
        class _FakeAI:
            last_failure_reason = "rate_limited"

            def chat(self, *a, **k):
                return "I'm having trouble connecting to AI services right now.", "rule_based"

        monkeypatch.setattr(api_manager.api, "ai", _FakeAI())

        documents._record_writer_failure("")
        assert documents._ai_write("Subject", _FACTS, brief="b",
                                   document_title="t") is None
        assert documents.last_writer_failure() == "rate_limited"

    def test_the_reason_slot_never_grows_without_bound(self):
        """The slot is written from provider-adjacent strings; cap it so a pathological value
        cannot bloat an error page.
        """
        documents._record_writer_failure("x" * 5000)
        assert len(documents.last_writer_failure()) <= 120
