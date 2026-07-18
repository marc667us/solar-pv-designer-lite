"""Plain English for the Ops Center, and a fix where a fix exists.

OWNER, 2026-07-18:
  "in the app operation center when a test fail or gives error there must be a button to fix
   it and a button to fix all -- this must be one of the agent tech support"
  "the test results must also have plain english to explain at the opcenter test result pane"
  "queue to configured error"

THE PROBLEM THIS SOLVES, and the last line names it exactly. The Ops Center reports a raw
status per check. "Queue: not_configured" is rendered as a FAILURE -- but on Render's free
tier there is no Redis and no Celery, by design and by the project's own cost rules. Nothing
is broken. The operator is being shown a red light for a service they deliberately do not pay
for, next to red lights that DO mean something, and the two are indistinguishable.

A check result has to answer three questions the raw status never does:

  1. WHAT DOES THIS MEAN, in a sentence someone can act on.
  2. IS IT ACTUALLY A PROBLEM, or is it absent-by-design on this tier.
  3. CAN IT BE FIXED FROM HERE, and if so, by doing what.

Severity is therefore NOT the provider's word for it. `not_configured` for Redis is
informational; `not_configured` for the AI provider is a real fault, because the app has a
feature that needs it. Same raw word, different meaning, and only this module knows which.

WHAT "FIX" MEANS HERE, deliberately narrow. A fix button runs an action this app can safely
perform on itself: clear a cache, restart a worker, re-run a seed. It NEVER provisions
infrastructure, spends money, or edits deployment configuration -- those need a human
decision, so the plain English says what to do instead of pretending a button could do it.
An honest "here is what you would have to do" beats a button that silently fails.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

# --- severities, in the order an operator should care about them --------------
OK = "ok"          # working
INFO = "info"      # absent, and that is correct on this tier -- NOT a failure
WARN = "warn"      # degraded, or working but worth knowing
ERROR = "error"    # broken, and it matters

SEVERITY_ORDER = (ERROR, WARN, INFO, OK)


class Explanation(NamedTuple):
    """What one check result means, in words, plus what can be done about it.

    severity  -- OK / INFO / WARN / ERROR, decided HERE and not taken from the raw status.
    plain     -- one or two sentences an operator can act on. No jargon, no status codes.
    fix_id    -- the id to POST to the fix endpoint, or "" when nothing can be fixed remotely.
    fix_label -- what the button should say.
    manual    -- what a human must do when there is no button. Empty when a button exists.
    """

    severity: str
    plain: str
    fix_id: str = ""
    fix_label: str = ""
    manual: str = ""


# --- the services this deployment deliberately does not have ------------------
#
# Render's free tier has no Redis and no Celery, and the FOSS/cost rule in CLAUDE.md says we
# do not pay for them pre-launch. A check that reports them absent is reporting the truth
# about a decision, not a fault, and it must not sit in the same red column as a real outage.
ABSENT_BY_DESIGN = {
    "redis": ("Redis is not part of this deployment. The app uses in-process caching instead, "
              "which is slower under load but entirely correct. Nothing is broken."),
    "queue": ("There is no background queue on this plan, so jobs that would normally be "
              "queued run inside the web request instead. Long reports can therefore be slow, "
              "but nothing is failing."),
    "celery": ("Celery workers are not part of this deployment. Background work runs inline."),
}


def _looks_absent(raw: str) -> bool:
    return str(raw or "").strip().lower() in (
        "not_configured", "not configured", "unavailable", "absent", "disabled", "none", "")


def explain(check_id: str, status: str, detail: str = "") -> Explanation:
    """Turn one raw ops result into something an operator can act on.

    Input:  check_id -- e.g. "ping/queue"; status -- the raw word the check returned;
            detail   -- any extra text the check produced.
    Output: an Explanation.

    Unknown checks are NOT guessed at. They pass through with their raw status and a plain
    statement that this check has no explanation yet -- which is honest, and visibly different
    from a check that has been thought about.
    """
    key = (check_id or "").strip().lower().lstrip("/")
    key = key.replace("admin/ops/", "")
    raw = (status or "").strip().lower()
    service = key.split("/")[-1]

    # 1. ABSENT BY DESIGN -- the owner's "queue to configured error".
    if service in ABSENT_BY_DESIGN and (_looks_absent(raw) or raw in ("warn", "error")):
        return Explanation(
            severity=INFO,
            plain=ABSENT_BY_DESIGN[service],
            manual=("If you later need it, it comes with a paid Render plan -- that is a cost "
                    "decision, not something this page should switch on for you."))

    # 2. THINGS THAT ARE FINE
    if raw in ("ok", "pass", "passed", "healthy", "up", "connected", "configured", "200"):
        return Explanation(OK, _ok_sentence(service))

    # 3. THINGS THAT ARE GENUINELY BROKEN, each with its own remedy
    handler = _BROKEN.get(service)
    if handler:
        return handler(raw, detail)

    # 4. UNKNOWN -- say so rather than invent a diagnosis
    return Explanation(
        severity=WARN if raw not in ("error", "fail", "failed") else ERROR,
        plain=(f"This check reported '{status}'. There is no plain-English explanation for "
               f"'{check_id}' yet, so treat the raw result as the source of truth."),
        manual="Ask for this check to be explained if you hit it often.")


def _ok_sentence(service: str) -> str:
    return {
        "frontend": "The public site answered normally.",
        "backend":  "The application answered its own health check.",
        "database": "The database accepted a read and a write.",
        "storage":  "There is disk space and the app can write to it.",
        "ai":       "An AI provider is configured and reachable.",
        "redis":    "Redis answered.",
        "queue":    "The background queue answered.",
    }.get(service, "This check passed.")


# --- the broken cases ---------------------------------------------------------

def _database(raw: str, detail: str) -> Explanation:
    return Explanation(
        ERROR,
        "The app could not read from or write to the database. Every page that stores or "
        "loads data will fail until this recovers.",
        manual=("Check the database is awake and the connection string is current. On Render "
                "a free Postgres instance expires after 90 days and must be recreated."))


def _ai(raw: str, detail: str) -> Explanation:
    return Explanation(
        ERROR,
        "No AI provider is usable, so the report writer cannot produce documents. This is the "
        "failure behind 'the writing service is unavailable'.",
        fix_id="ai_recheck",
        fix_label="Re-test the AI provider",
        manual=("If it stays down, the API key is missing, rejected, or every free model is "
                "rate-limited. The writer names which one when it fails."))


def _frontend(raw: str, detail: str) -> Explanation:
    return Explanation(
        ERROR,
        "The public site did not answer. Visitors are seeing an error or nothing at all.",
        manual="Check the most recent deploy finished and the service is running.")


def _backend(raw: str, detail: str) -> Explanation:
    return Explanation(
        ERROR,
        "The application did not answer its own health check, so it is not serving requests.",
        manual="Check the most recent deploy and the runtime logs.")


def _storage(raw: str, detail: str) -> Explanation:
    return Explanation(
        WARN,
        "Disk space is low or not writable. Uploads, generated PDFs and backups will start "
        "failing before anything else does.",
        fix_id="clear_cache",
        fix_label="Clear cached files")


def _email(raw: str, detail: str) -> Explanation:
    return Explanation(
        WARN,
        "Email could not be sent. Invitations, report notifications and password resets will "
        "not arrive, though the rest of the app is unaffected.",
        manual=("Render blocks outbound SMTP, so email must go through an HTTPS provider. "
                "Check the Brevo key is set and the sender address is verified."))


_BROKEN: dict[str, Callable[[str, str], Explanation]] = {
    "database": _database,
    "ai": _ai,
    "frontend": _frontend,
    "backend": _backend,
    "storage": _storage,
    "email": _email,
    "status": _email,          # /admin/ops/email/status
}


# --- fixes --------------------------------------------------------------------
#
# A fix is something this app can safely do TO ITSELF. Provisioning, spending and deployment
# config are not on this list on purpose: a button that cannot really do the thing is worse
# than a sentence telling you what the thing is.
class Fix(NamedTuple):
    """A remedy the app can actually carry out on itself.

    label     -- what the button says.
    endpoint  -- the EXISTING ops endpoint that does the work. Nothing here reimplements an
                 action; every fix delegates to a route that is already tested and already
                 permission-checked, so a button can never do something the operator could
                 not already do by hand.
    method    -- how that endpoint must be called.
    done      -- what to tell the operator afterwards.
    """

    label: str
    endpoint: str
    method: str
    done: str


# THE REGISTRY IS EXECUTABLE, NOT DECORATIVE.
#
# This was a dict of LABELS when first written on 2026-07-18, and a test called
# `test_every_offered_fix_is_one_the_app_can_actually_perform` asserted only that an id
# appeared in it. That assertion proved nothing: the buttons would have rendered and done
# NOTHING. The owner asked "check if the agent technical support are still working and able to
# catch and fix the issues" -- and the honest answer was no.
#
# Every entry now names the real endpoint that performs it, and a test walks these endpoints
# against the app's actual URL map, so an id with no route behind it fails the suite.
FIXES: dict[str, Fix] = {
    "clear_cache": Fix("Clear the application cache",
                       "/admin/ops/cache/clear", "POST",
                       "Cached files were cleared."),
    "ai_recheck":  Fix("Re-test the AI provider",
                       "/admin/ops/ping/ai", "GET",
                       "The AI provider was tested again."),
    "vacuum_db":   Fix("Compact the database",
                       "/admin/ops/db/vacuum", "POST",
                       "The database was compacted."),
}


def fixable(explanations: dict[str, Explanation]) -> list[str]:
    """The fix ids worth offering, worst severity first, each only once.

    Input:  {check_id: Explanation}.
    Output: fix ids in the order "Fix All" should run them.

    Ordered by severity so that if one fix fails the run has already attempted the ones that
    matter most -- and de-duplicated, because two checks can recommend the same remedy and an
    operator should not watch the cache be cleared twice.
    """
    seen: list[str] = []
    for sev in SEVERITY_ORDER:
        for exp in explanations.values():
            if exp.severity == sev and exp.fix_id and exp.fix_id not in seen:
                seen.append(exp.fix_id)
    return seen


def summarise(explanations: dict[str, Explanation]) -> str:
    """One sentence for the top of the pane.

    Counts INFO separately from OK, because "three things are off and that is correct" is a
    different message from "everything is on", and lumping them together is how a deliberate
    cost decision starts looking like a fault.
    """
    if not explanations:
        return "No checks have been run yet."
    n = {s: sum(1 for e in explanations.values() if e.severity == s) for s in SEVERITY_ORDER}
    if n[ERROR]:
        return (f"{n[ERROR]} problem(s) need attention"
                + (f", {n[WARN]} warning(s)" if n[WARN] else "") + ".")
    if n[WARN]:
        return f"No failures. {n[WARN]} thing(s) worth a look."
    if n[INFO]:
        return (f"Everything that should be running is running. {n[INFO]} service(s) are not "
                f"part of this plan, which is expected.")
    return "Everything passed."


__all__ = ["Explanation", "OK", "INFO", "WARN", "ERROR", "SEVERITY_ORDER",
           "explain", "fixable", "summarise", "FIXES", "ABSENT_BY_DESIGN"]
