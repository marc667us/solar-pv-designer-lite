"""Plain English for the Ops Center.

OWNER, 2026-07-18: "queue to configured error" and "the test results must also have plain
english to explain at the opcenter test result pane".

THE DEFECT: the Ops Center showed a red light for the background queue, which does not exist
on this plan BY DESIGN -- Render's free tier has no Redis and no Celery, and the project's own
cost rules say we do not pay for them yet. Nothing was broken. The operator was being shown a
failure for a deliberate decision, in the same column as failures that mean something, with no
way to tell the two apart.

The rule these tests protect: SEVERITY IS DECIDED BY WHAT THE APP NEEDS, not by the word the
check happened to return.
"""

import pytest

import ops_support as ops

# IMPORTED AT MODULE SCOPE, ON PURPOSE. `wsgi` registers the support routes onto the shared
# Flask app, and Flask refuses to add a route once that app has served its first request. All
# test modules are imported during collection, BEFORE any test runs, so importing here is the
# only point at which registration is guaranteed to succeed -- exactly as it is in production,
# where wsgi.py is the entry point and registers before the first request arrives.
#
# Importing it inside a test instead made these pass alone and fail in the full suite (found
# 2026-07-18). That is worth knowing beyond the tests: wsgi.py wraps this registration in a
# try/except for boot resilience, so a late import would be SWALLOWED and merely logged --
# the feature would be silently absent, which is how ops_support came to be dead code in the
# first place.
import wsgi as _wsgi


class TestAbsentByDesignIsNotAFailure:
    """The owner's actual complaint."""

    @pytest.mark.parametrize("check", ["ping/queue", "ping/redis",
                                       "admin/ops/ping/queue", "/admin/ops/ping/redis"])
    def test_the_queue_and_redis_are_not_reported_as_errors(self, check):
        e = ops.explain(check, "not_configured")
        assert e.severity == ops.INFO, (
            f"{check} absent is a plan decision, not a fault -- it must not be red")

    @pytest.mark.parametrize("raw", ["not_configured", "unavailable", "warn", "error", ""])
    def test_however_the_check_words_it(self, raw):
        """Different checks word absence differently. All of them mean the same thing here."""
        assert ops.explain("ping/queue", raw).severity == ops.INFO

    def test_it_explains_the_consequence_rather_than_just_saying_fine(self):
        """"Nothing is broken" is not enough -- reports really are slower without a queue, and
        an operator who is told only "fine" will be surprised later.
        """
        plain = ops.explain("ping/queue", "not_configured").plain.lower()
        assert "queue" in plain
        assert "slow" in plain or "inside the web request" in plain

    def test_it_does_not_offer_a_button_that_cannot_work(self):
        """No button can provision Redis. Pretending otherwise is worse than saying so."""
        e = ops.explain("ping/redis", "not_configured")
        assert e.fix_id == ""
        assert e.manual, "it must say what a human would have to do instead"


class TestTheSameWordCanMeanOppositeThings:
    """Why severity cannot be copied from the raw status."""

    def test_not_configured_is_fine_for_the_queue_and_fatal_for_the_writer(self):
        queue = ops.explain("ping/queue", "not_configured")
        ai = ops.explain("ping/ai", "not_configured")
        assert queue.severity == ops.INFO
        assert ai.severity == ops.ERROR, (
            "the app HAS a feature that needs an AI provider, so absent means broken")

    def test_the_ai_explanation_names_the_symptom_the_owner_actually_sees(self):
        """It should connect to "the writing service is unavailable" -- the words on screen --
        rather than talk about providers in the abstract.
        """
        assert "writing service is unavailable" in ops.explain("ping/ai", "error").plain


class TestUnknownChecksAreNotGuessedAt:

    def test_an_unrecognised_check_says_so_instead_of_inventing_a_diagnosis(self):
        e = ops.explain("ping/something-new", "weird")
        assert "no plain-English explanation" in e.plain
        assert "weird" in e.plain, "the raw result must still be shown"

    def test_an_unknown_failure_is_still_ranked_as_a_failure(self):
        assert ops.explain("ping/whatever", "error").severity == ops.ERROR


class TestFixAll:

    def _mixed(self):
        return {
            "ping/backend": ops.explain("ping/backend", "ok"),
            "ping/queue":   ops.explain("ping/queue", "not_configured"),
            "ping/storage": ops.explain("ping/storage", "warn"),
            "ping/ai":      ops.explain("ping/ai", "error"),
        }

    def test_the_worst_problem_is_fixed_first(self):
        """If a run is interrupted, the thing that mattered most has already been tried."""
        order = ops.fixable(self._mixed())
        assert order[0] == "ai_recheck"

    def test_a_remedy_is_never_offered_twice(self):
        exps = {"a": ops.explain("ping/storage", "warn"),
                "b": ops.explain("ping/storage", "warn")}
        assert ops.fixable(exps) == ["clear_cache"]

    def test_healthy_and_by_design_checks_contribute_no_fixes(self):
        exps = {"ping/backend": ops.explain("ping/backend", "ok"),
                "ping/queue": ops.explain("ping/queue", "not_configured")}
        assert ops.fixable(exps) == []

    def test_every_offered_fix_names_a_ROUTE_THAT_EXISTS_in_the_app(self):
        """A fix id with no implementation behind it is a button that lies.

        THIS TEST USED TO LIE TOO. It asserted only that the id appeared in a dict -- and that
        dict held nothing but LABELS, so every button would have rendered and done NOTHING.
        The owner asked directly whether the tech-support agent could actually fix anything
        (2026-07-18) and the honest answer was no. It now walks the app's real URL map, so a
        fix whose endpoint does not exist fails here rather than on the operator's screen.
        """
        rules = {str(r.rule): r.methods for r in _wsgi.app.url_map.iter_rules()}

        for fix_id, fix in ops.FIXES.items():
            assert fix.endpoint in rules, (
                f"{fix_id} points at {fix.endpoint}, which is not a route in this app")
            assert fix.method in rules[fix.endpoint], (
                f"{fix_id} calls {fix.endpoint} with {fix.method}, which that route refuses "
                f"(it allows {sorted(rules[fix.endpoint] - {'HEAD', 'OPTIONS'})})")

    def test_every_recommended_fix_id_is_registered(self):
        for exp in self._mixed().values():
            if exp.fix_id:
                assert exp.fix_id in ops.FIXES, f"{exp.fix_id} has no registered action"


class TestTheSummaryLine:

    def test_by_design_absences_are_counted_separately_from_healthy(self):
        """"Everything passed" would hide that three services are off; lumping them in with OK
        is how a cost decision starts looking like a fault -- the thing this module exists to
        stop.
        """
        exps = {"ping/queue": ops.explain("ping/queue", "not_configured"),
                "ping/redis": ops.explain("ping/redis", "not_configured"),
                "ping/backend": ops.explain("ping/backend", "ok")}
        s = ops.summarise(exps)
        assert "not part of this plan" in s
        assert "expected" in s

    def test_failures_lead_the_summary(self):
        exps = {"ping/ai": ops.explain("ping/ai", "error"),
                "ping/queue": ops.explain("ping/queue", "not_configured")}
        assert ops.summarise(exps).startswith("1 problem")

    def test_all_clear_says_so_plainly(self):
        exps = {"ping/backend": ops.explain("ping/backend", "ok")}
        assert ops.summarise(exps) == "Everything passed."

    def test_nothing_run_yet_is_not_reported_as_success(self):
        assert "No checks" in ops.summarise({})


class TestEveryExplanationIsActuallyPlain:
    """The owner asked for plain English. That is testable."""

    CHECKS = [("ping/queue", "not_configured"), ("ping/redis", "not_configured"),
              ("ping/ai", "error"), ("ping/database", "error"),
              ("ping/frontend", "error"), ("ping/backend", "error"),
              ("ping/storage", "warn"), ("email/status", "error"),
              ("ping/backend", "ok")]

    @pytest.mark.parametrize("check,raw", CHECKS)
    def test_no_jargon_leaks_into_the_sentence(self, check, raw):
        plain = ops.explain(check, raw).plain
        for jargon in ("not_configured", "HTTP 5", "traceback", "None", "null",
                       "exception", "stderr"):
            assert jargon not in plain, f"{check}: '{jargon}' is not plain English"

    @pytest.mark.parametrize("check,raw", CHECKS)
    def test_it_is_a_sentence_not_a_status_word(self, check, raw):
        plain = ops.explain(check, raw).plain
        assert plain.endswith("."), f"{check}: not a sentence"
        assert len(plain.split()) >= 5, f"{check}: too terse to explain anything"

    @pytest.mark.parametrize("check,raw", CHECKS)
    def test_anything_without_a_button_says_what_a_human_should_do(self, check, raw):
        e = ops.explain(check, raw)
        if e.severity in (ops.ERROR, ops.WARN, ops.INFO) and not e.fix_id:
            assert e.manual, f"{check}: no button and no guidance leaves the operator stuck"


class TestTheSupportSurfaceIsActuallyReachable:
    """The owner asked directly: "check if the agent technical support are still working".

    It was NOT. `ops_support` was imported by nothing, so on the live site it did precisely
    nothing -- tested logic behind no route is not a feature. These tests exist so that can
    never be true again silently: if the routes stop being registered, or stop being
    admin-only, the suite says so.
    """

    def _client(self):
        return _wsgi.app.test_client()

    def test_both_routes_are_registered(self):
        rules = {str(r.rule) for r in _wsgi.app.url_map.iter_rules()}
        assert "/admin/ops/support/sweep" in rules
        assert "/admin/ops/support/fix/<fix_id>" in rules

    def test_an_anonymous_caller_cannot_run_diagnostics(self):
        """A sweep names what is broken and how. That is a map for an attacker, not a
        public page.
        """
        assert self._client().get("/admin/ops/support/sweep").status_code != 200

    def test_an_anonymous_caller_cannot_run_a_fix(self):
        """Far worse than reading: this one CHANGES the running system."""
        assert self._client().post(
            "/admin/ops/support/fix/clear_cache").status_code != 200

    def test_an_admin_gets_every_check_explained(self):
        c = self._client()
        with c.session_transaction() as s:
            s.update({"user_id": 1, "username": "admin", "is_admin": True})
        r = c.get("/admin/ops/support/sweep")
        assert r.status_code == 200

        data = r.get_json()
        assert data["summary"]
        assert data["results"], "a sweep with no results is not a sweep"
        for row in data["results"]:
            assert row["plain"], f"{row['id']} came back with no explanation"
            assert row["severity"] in ops.SEVERITY_ORDER

    def test_the_queue_is_not_red_on_this_plan(self):
        """The owner's original report -- 'queue to configured error' -- asserted against the
        real endpoint rather than against the explainer in isolation.
        """
        c = self._client()
        with c.session_transaction() as s:
            s.update({"user_id": 1, "username": "admin", "is_admin": True})
        rows = {r["id"]: r for r in c.get("/admin/ops/support/sweep").get_json()["results"]}
        assert rows["ping/queue"]["severity"] != ops.ERROR

    def test_an_unknown_fix_id_is_refused_not_attempted(self):
        """This endpoint must never become a way to call arbitrary routes."""
        c = self._client()
        with c.session_transaction() as s:
            s.update({"user_id": 1, "username": "admin", "is_admin": True})
        r = c.post("/admin/ops/support/fix/../../etc/passwd")
        assert r.status_code in (400, 404, 405)
