"""
API versioning -- slice 1: /api/v1 aliases for the public reference data.

WHAT THIS IS
    This repo had NO API versioning at all: `/api/v1` appeared nowhere
    (verified 2026-07-20). External consumers integrate against unversioned
    paths, which means the shape of those responses can never change without
    breaking them silently.

    This module introduces the /api/v1 namespace as a set of ADDITIVE
    ALIASES. Nothing is moved, renamed, redirected or deprecated: every
    existing unversioned path keeps working exactly as before, forever. A
    caller opts in to the versioned surface by using it.

WHY ALIASES AND NOT NEW HANDLERS
    An alias points at the SAME view function, so v1 cannot drift from the
    behaviour it is meant to describe. When v2 eventually needs different
    behaviour, that is the moment to give it its own handler -- not now.

SCOPE -- deliberately small, and why THESE four
    Only the public, read-only reference-data endpoints are versioned in this
    slice. They are the surface an external integrator would actually consume,
    they take no auth, they mutate nothing, and they return stable engineering
    lookup data.

    Health and ops endpoints are POINTEDLY EXCLUDED. boot_state.py exempts
    "/api/ping", "/api/version" and the "/api/health/" family BY EXACT PATH
    (boot_state.py:112-117) so they keep answering while the database is down.
    A /api/v1/ping would NOT inherit that exemption and would start 503-ing
    during exactly the outage it exists to report. Versioning infrastructure
    probes buys nothing and breaks their one job.

REGISTRATION LIVES IN wsgi.py, NOT SPLICED INTO web_app.py
    web_app.py is CRLF + mojibake and must be byte-patched; a bad splice is
    an import-time crash, i.e. a total outage. Registering from wsgi.py --
    the same route the enterprise blueprint and the CDC drain already take --
    keeps this change out of that file entirely.

ENDPOINT NAMING: a v1 alias gets its OWN endpoint name
    Reusing the source endpoint would let werkzeug's url_for() pick either
    rule when building a URL, so templates could start emitting /api/v1/...
    unpredictably. A distinct "v1_" endpoint keeps url_for() deterministic.

    The cost, MEASURED not assumed (Flask-Limiter 4.1.1, 2026-07-20): the
    alias inherits the source route's @limiter.limit -- the decorator travels
    with the view function, so the alias IS rate limited -- but at its own
    bucket, not a shared one. A 5/min route allowed 5 on the original path
    and then a FRESH 5 on the alias. So a caller using both paths gets 2x the
    budget.

    Acceptable HERE and only here: these four endpoints are read-only public
    reference data served from static lookup tables, with no side effects, no
    secrets and no writes -- 120/min instead of 60/min on a static table is
    not a meaningful exposure.

    Do NOT extend this pattern to a mutating or authenticated endpoint
    without fixing the split first. The tool for that is
    ``limiter.shared_limit(..., scope="<name>")``, which buckets several
    endpoints together; it was not used here because applying it would mean
    byte-patching the source routes in web_app.py, which this design
    deliberately avoids.

SHIPS DARK
    API_V1_ENABLED is read from the environment and defaults to OFF, so the
    first deploy registers nothing and only proves the import is harmless.
    A second deploy flips it on. Routes are registered at import, so this is
    an env var (a redeploy) rather than a DB flag -- and a DB flag would cost
    a fresh connection per request on a public path anyway.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

#: The versioned surface. (source endpoint name, source path, v1 path).
#:
#: Source endpoint names are explicit rather than derived, so adding a route
#: to this list is a deliberate act that names exactly what it exposes.
ALIASES = [
    ("api_solar_regions_public",
     "/api/solar_regions/<country>",
     "/api/v1/solar-regions/<country>"),
    ("api_solar_data_public",
     "/api/solar_data/<country>/<region>",
     "/api/v1/solar-data/<country>/<region>"),
    ("api_purc_tariffs",
     "/api/purc-tariffs",
     "/api/v1/purc-tariffs"),
    ("api_demand_factors",
     "/api/demand-factors",
     "/api/v1/demand-factors"),
]

#: Every endpoint aliased here MUST be public. Aliasing a protected endpoint
#: would need different handling (the alias inherits the target's decorators,
#: which a static route scan cannot see), so it is refused rather than
#: silently allowed. Asserted by test_api_v1.py against the route-auth
#: allowlist, not merely asserted in prose here.
V1_PREFIX = "/api/v1"


def declared_paths() -> list[str]:
    """Every route this module can register, as '<METHODS> <path>' keys.

    Published for the route-auth ratchet. Registration happens in a loop over
    ALIASES, so the add_url_rule call site holds a variable rather than a
    literal and no source scan can resolve it. Declaring the surface here is
    exact where parsing would be guesswork -- and it means these routes are
    checked against the allowlist like any other undecorated route, instead
    of quietly escaping the guard.

    Output: e.g. ["GET /api/v1", "GET /api/v1/purc-tariffs", ...]
    """
    paths = [f"GET {v1}" for _e, _s, v1 in ALIASES]
    paths.append(f"GET {V1_PREFIX}")
    return sorted(paths)


def enabled() -> bool:
    """True when the v1 surface should be registered.

    Defaults to FALSE: the first deploy ships dark and proves only that
    importing this module cannot hurt the app.
    """
    return (os.environ.get("API_V1_ENABLED") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _rule_for(app, endpoint: str):
    """Return the first url_map rule for `endpoint`, or None."""
    for rule in app.url_map.iter_rules():
        if rule.endpoint == endpoint:
            return rule
    return None


def register(app) -> dict:
    """Register the /api/v1 aliases on `app`.

    Input:  the Flask app.
    Output: a summary dict {enabled, registered, skipped, missing} -- returned
            rather than logged-only so a caller (and the tests) can assert on
            what actually happened.

    NEVER RAISES. This runs at import inside wsgi.py; an exception here would
    take the whole app down, and a versioning alias is not worth an outage.
    Each alias is registered independently so one bad entry cannot cost the
    others.
    """
    summary = {"enabled": enabled(), "registered": [], "skipped": [], "missing": []}
    if not summary["enabled"]:
        return summary

    for endpoint, _src_path, v1_path in ALIASES:
        try:
            rule = _rule_for(app, endpoint)
            if rule is None:
                # The source route was renamed or removed. Say so; do not
                # invent a handler.
                summary["missing"].append(endpoint)
                log.warning("api_v1: source endpoint %r not found; alias skipped", endpoint)
                continue

            v1_endpoint = f"v1_{endpoint}"
            if _rule_for(app, v1_endpoint) is not None:
                # Already registered (double import). Idempotent, not an error.
                summary["skipped"].append(v1_path)
                continue

            # methods minus the two werkzeug adds automatically, so we do not
            # re-declare HEAD/OPTIONS and change their handling.
            methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})

            app.add_url_rule(
                v1_path,
                endpoint=v1_endpoint,
                view_func=app.view_functions[endpoint],
                methods=methods or ["GET"],
            )
            summary["registered"].append(v1_path)
        except Exception as e:  # pragma: no cover - defensive
            log.error("api_v1: failed to register alias for %r: %s", endpoint, e)

    # Discovery document. Registered last so a failure here cannot cost the
    # aliases, and only if the aliases exist -- an empty manifest would
    # advertise a surface that is not there.
    try:
        if summary["registered"] or summary["skipped"]:
            if _rule_for(app, "v1_api_manifest") is None:
                from flask import jsonify

                app.add_url_rule(
                    V1_PREFIX,
                    endpoint="v1_api_manifest",
                    view_func=lambda: (jsonify(manifest()), 200),
                    methods=["GET"],
                )
                summary["registered"].append(V1_PREFIX)
    except Exception as e:  # pragma: no cover - defensive
        log.error("api_v1: failed to register the manifest route: %s", e)

    if summary["registered"]:
        log.info("api_v1: registered %d alias(es)", len(summary["registered"]))
    return summary


def manifest() -> dict:
    """The v1 discovery document.

    Kept separate from GET /api/version, which reports BUILD identity (the
    VERSION file + RENDER_GIT_COMMIT) -- a different question from "what API
    versions does this service speak". Extending that endpoint would have
    meant byte-patching web_app.py for no benefit.
    """
    return {
        "version": "v1",
        "status": "stable",
        "note": (
            "Unversioned /api/* paths remain supported and are not deprecated."
        ),
        "endpoints": sorted(v1 for _e, _s, v1 in ALIASES),
    }
