"""
Route-auth RATCHET.

CONTRACT
    Every route declaration with no recognised auth decorator must appear in
    tests/route_auth_allowlist.txt with a reason. Adding a new unprotected
    route fails this test until someone writes down why it is public.

WHY A RATCHET AND NOT A FIX
    This repo has 800+ route declarations and NO global before_request auth
    or CSRF hook -- enforcement is per-route. Retrofitting a blanket hook
    onto a live app would break working AJAX/webhook/cron flows, so the safe
    first move is to stop the surface from growing, then fix specific routes
    in small reviewed packs.

WHY STATIC
    Importing web_app raises SystemExit("Set SOLARPRO_ADMIN_PASSWORD")
    during collection without production env, which makes the whole suite
    report "no tests ran". See tests/route_auth_scan.py SCOPE for the full
    rationale and the two documented blind spots.

ZERO RUNTIME IMPACT
    This file and route_auth_scan.py are test-only. They import nothing from
    the application and change no application behaviour.
"""

from __future__ import annotations

import os
import re

import pytest

from tests.route_auth_scan import (
    AUTH_DECORATORS,
    iter_source_files,
    read_source,
    route_key,
    scan_repo,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWLIST_PATH = os.path.join(REPO_ROOT, "tests", "route_auth_allowlist.txt")

#: Closed vocabulary for the `reason=` field. Kept here rather than in the
#: scanner because it is a property of the allowlist policy, not of parsing.
VALID_REASONS = frozenset({
    "public-by-design",
    "in-body-token",
    "in-body-session",
    "webhook-hmac",
    "known-gap",
})

#: Reasons that assert a guard exists somewhere the scanner cannot see.
#: These must name it, so a rename cannot leave a dangling justification.
#:
#: `in-body-session` covers a handler that authorises from the SESSION rather
#: than a decorator -- added 2026-07-20 for /admin/users/refresh-online, where
#: @admin_required could not be used because it redirects on a missing
#: session["user_id"], the exact Keycloak case that handler exists to serve.
REASONS_REQUIRING_REF = frozenset({
    "in-body-token", "in-body-session", "webhook-hmac",
})

_RE_ENTRY = re.compile(
    r"^(?P<key>[A-Z,]+ \S+)\s*#\s*reason=(?P<reason>[\w-]+)"
    r"(?:\s+ref=(?P<ref>\S+))?\s*$"
)


# ---------------------------------------------------------------------------
# Module-scoped fixtures.
#
# The scan reads ~5 MB across 138 files, including the 2 MB web_app.py.
# Seven tests need it; scanning per-test re-read and re-parsed the repo seven
# times (~30 MB of redundant I/O). Scanning once per module cuts this file's
# runtime by roughly 80%.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def routes():
    return scan_repo(REPO_ROOT)


@pytest.fixture(scope="module")
def unprot_keys(routes):
    return {route_key(r) for r in routes if not r["protected"]}


@pytest.fixture(scope="module")
def allowlist():
    """Parse the allowlist into {key: (reason, ref)}."""
    entries: dict[str, tuple[str, str | None]] = {}
    malformed: list[str] = []
    with open(ALLOWLIST_PATH, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = _RE_ENTRY.match(line)
            if not m:
                malformed.append(line)
                continue
            entries[m.group("key")] = (m.group("reason"), m.group("ref"))

    assert not malformed, (
        "Malformed allowlist line(s) -- expected "
        "'<METHODS> <path>  # reason=<tag> [ref=<file:line>]':\n\n"
        + "\n".join(f"    {x}" for x in malformed)
    )
    return entries


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_scanner_finds_routes(routes):
    """Guard against the scanner silently matching nothing.

    Without this, a regex break would empty the scan and the ratchet would
    pass vacuously -- the classic tautological green.
    """
    assert len(routes) > 500, (
        f"scanner found only {len(routes)} routes; expected 500+. "
        "The route regex has probably broken."
    )
    assert any(r["protected"] for r in routes), "no protected routes detected"
    assert any(not r["protected"] for r in routes), (
        "every route classified as protected -- the classifier is not "
        "discriminating, so the ratchet cannot fail"
    )


def test_auth_decorators_all_exist():
    """Every name in AUTH_DECORATORS must resolve to a real `def`.

    AUTH_DECORATORS is hand-maintained, so a typo or an aspirational entry
    would silently widen what counts as protected and could mark a route
    safe that is not. This caught three phantoms on 2026-07-20
    (paid_only, staff_required, owner_required -- none ever existed).
    """
    sources = [read_source(p) for p in iter_source_files(REPO_ROOT)]
    # The Keycloak decorators live in app/security/, outside the scan scope.
    kc = os.path.join(REPO_ROOT, "app", "security", "decorators.py")
    if os.path.exists(kc):
        sources.append(read_source(kc))
    blob = "\n".join(sources)

    missing = sorted(
        name for name in AUTH_DECORATORS
        if not re.search(rf"^\s*def {re.escape(name)}\b", blob, re.M)
    )
    assert not missing, (
        "AUTH_DECORATORS names with no `def` anywhere: "
        + ", ".join(missing)
        + "\nRemove them, or fix the typo. An entry that matches nothing "
        "makes the set look authoritative while protecting nothing."
    )


def test_no_new_unprotected_routes(unprot_keys, allowlist):
    """THE RATCHET: every undecorated route must be in the allowlist."""
    new = sorted(unprot_keys - set(allowlist))
    assert not new, (
        "New route(s) with NO auth decorator detected:\n\n"
        + "\n".join(f"    {k}" for k in new)
        + "\n\nMOST LIKELY: this route IS guarded, but by a decorator the "
        "scanner does not know about -- add that decorator's name to "
        "AUTH_DECORATORS in tests/route_auth_scan.py.\n"
        "OR: protect it with one of:\n    "
        + ", ".join(sorted(AUTH_DECORATORS))
        + "\nONLY IF it is genuinely public by design, add it to\n"
        "    tests/route_auth_allowlist.txt\n"
        "with a reason= tag explaining why."
    )


def test_allowlist_has_no_stale_entries(unprot_keys, allowlist):
    """Keep the allowlist honest.

    An entry matching no unprotected route means the route was deleted or
    has since been protected. Either way the exemption is dead and must go,
    or it will silently pre-authorise a future route that reuses the path.

    Declared dynamic routes count as live: they exist at runtime but cannot
    appear in a source scan (computed paths), so excluding them here would
    report every /api/v1 alias as stale.
    """
    stale = sorted(set(allowlist) - unprot_keys - _declared_dynamic_keys())
    assert not stale, (
        "Allowlist entries matching no unprotected route (route removed, or "
        "now protected -- drop these lines):\n\n"
        + "\n".join(f"    {k}" for k in stale)
    )


def test_allowlist_reasons_are_valid(allowlist):
    """Every entry carries a reason from the closed vocabulary, and any
    entry claiming an invisible guard names where that guard lives."""
    bad_reason = sorted(
        f"{k} (reason={r})"
        for k, (r, _) in allowlist.items()
        if r not in VALID_REASONS
    )
    assert not bad_reason, (
        "Unknown reason= tag(s); allowed: "
        + ", ".join(sorted(VALID_REASONS))
        + "\n\n" + "\n".join(f"    {x}" for x in bad_reason)
    )

    missing_ref = sorted(
        f"{k} (reason={r})"
        for k, (r, ref) in allowlist.items()
        if r in REASONS_REQUIRING_REF and not ref
    )
    assert not missing_ref, (
        "These claim a guard the scanner cannot see, so they must name it "
        "with ref=<file:line>:\n\n"
        + "\n".join(f"    {x}" for x in missing_ref)
    )

    dangling = []
    for key, (reason, ref) in allowlist.items():
        if not ref:
            continue
        fname = ref.split(":")[0]
        if not os.path.exists(os.path.join(REPO_ROOT, fname)):
            dangling.append(f"{key} -> {ref}")
    assert not dangling, (
        "ref= points at a file that does not exist (renamed or deleted?):\n\n"
        + "\n".join(f"    {x}" for x in sorted(dangling))
    )


#: Modules that register routes IMPERATIVELY with a computed path, which no
#: source-text scan can resolve. Each must PUBLISH its surface so the ratchet
#: can check it: {module name: (import path, attribute holding the v1 paths)}.
#:
#: This is the honest answer to a real limit. new_api_v1_routes registers in a
#: loop over its ALIASES table, so the add_url_rule call site contains a
#: variable, not a literal. Regex-parsing it would be guesswork; reading the
#: module's own declaration is exact.
DYNAMIC_ROUTE_MODULES = {
    "new_api_v1_routes.py": ("new_api_v1_routes", "declared_paths"),
}


def _declared_dynamic_keys() -> set[str]:
    """Every route key published by a dynamic-registration module.

    These exist at runtime but never in a source scan, so both the
    stale-entry check and the sensitive-prefix check must treat them as
    live routes rather than phantom allowlist entries.
    """
    import importlib

    keys: set[str] = set()
    for mod_name, attr in DYNAMIC_ROUTE_MODULES.values():
        try:
            mod = importlib.import_module(mod_name)
        except Exception:  # pragma: no cover - a broken module fails elsewhere
            continue
        keys.update(getattr(mod, attr)())
    return keys


def test_add_url_rule_routes_are_accounted_for(routes):
    """No add_url_rule() registration may escape the ratchet.

    Until 2026-07-20 this was a documented blind spot: the scan matched
    decorators only. When the /api/v1 aliases introduced the first production
    add_url_rule calls, the scanner was taught to parse the literal-path form
    rather than the new module being exempted from its own guard.

    A module registering with a COMPUTED path cannot be parsed, so it must
    instead declare its routes via DYNAMIC_ROUTE_MODULES. Either way, every
    imperatively-registered route is accounted for -- none is silently
    invisible.
    """
    scanned_files = {r["file"] for r in routes}

    for path in iter_source_files(REPO_ROOT):
        name = os.path.basename(path)
        src = read_source(path)
        # A real call, not the word appearing in prose.
        if not re.search(r"^\s*\w+\.add_url_rule\(", src, re.M):
            continue
        if name in scanned_files or name in DYNAMIC_ROUTE_MODULES:
            continue
        pytest.fail(
            f"{name} registers routes with add_url_rule() but contributed "
            "NOTHING to the scan and does not declare them.\n"
            "Either use a literal path (which the scanner parses), or publish "
            "the paths and add the module to DYNAMIC_ROUTE_MODULES -- "
            "otherwise those routes are invisible to the ratchet."
        )


@pytest.mark.parametrize("module_file", sorted(DYNAMIC_ROUTE_MODULES))
def test_declared_dynamic_routes_are_allowlisted(module_file, allowlist):
    """Routes declared by a dynamic-registration module must be justified.

    They carry no decorator (their authorisation lives on the view function
    they alias), so they go through the allowlist like everything else.
    """
    import importlib

    mod_name, attr = DYNAMIC_ROUTE_MODULES[module_file]
    mod = importlib.import_module(mod_name)
    declared = getattr(mod, attr)()

    missing = sorted(set(declared) - set(allowlist))
    assert not missing, (
        f"{module_file} declares route(s) absent from the allowlist:\n\n"
        + "\n".join(f"    {k}" for k in missing)
        + "\n\nAdd them to tests/route_auth_allowlist.txt with a reason=."
    )


def test_auth_blueprint_is_out_of_scope_and_untouched(routes):
    """Document, executably, that the OIDC Blueprint is NOT covered.

    A green ratchet must not be mistaken for "the Keycloak routes are
    verified". They are deliberately excluded (owner instruction
    2026-07-20: do not touch the auth flow, especially KC). If someone
    later moves those routes to repo root -- which WOULD pull them into the
    ratchet's scope and into the blast radius of an auth change -- this
    fails and forces the conversation.
    """
    oidc = os.path.join(REPO_ROOT, "app", "auth", "oidc_routes.py")
    assert os.path.exists(oidc), (
        "app/auth/oidc_routes.py has moved. The ratchet's scope assumption "
        "no longer holds -- re-read SCOPE in tests/route_auth_scan.py."
    )
    assert "oidc_routes.py" not in {r["file"] for r in routes}, (
        "The OIDC Blueprint is now inside the ratchet's scan scope. That is "
        "a deliberate boundary -- see SCOPE in tests/route_auth_scan.py."
    )


@pytest.mark.parametrize("sensitive_prefix", ["/admin/", "/staff/", "/me/"])
def test_sensitive_prefixes_are_protected(sensitive_prefix, unprot_keys, allowlist):
    """No route under an operator-only prefix may be simply PUBLIC.

    Stricter than the ratchet: under these prefixes, `public-by-design` is
    never an acceptable justification. A route here must either carry an auth
    decorator, or name the guard that protects it (in-body-token /
    in-body-session / webhook-hmac, each of which requires a ref=), or be
    tagged as an explicitly tracked `known-gap`.

    The tolerated set is DERIVED from the allowlist rather than hardcoded, so
    fixing a route and deleting its line tightens this test automatically
    instead of leaving a stale exemption alive in test code.

    Live example: /admin/users/refresh-online is tagged in-body-session. It
    cannot take @admin_required, because that decorator redirects when
    session["user_id"] is missing -- the exact Keycloak case the handler
    exists to serve (web_app.py:6594 vs the handler docstring). Codex
    independently confirmed that adding the decorator would redirect the very
    users the route was written for. It authorises from the session instead.
    """
    guarded_reasons = REASONS_REQUIRING_REF | {"known-gap"}
    tolerated = {
        k for k, (r, _) in allowlist.items() if r in guarded_reasons
    }

    offenders = {
        k for k in unprot_keys
        if k.split(" ", 1)[1].startswith(sensitive_prefix)
    } - tolerated

    assert not offenders, (
        f"Undecorated route(s) under {sensitive_prefix}. A route here may NOT "
        "be justified as reason=public-by-design. Either give it an auth "
        "decorator, or -- if it authorises some other way the scanner cannot "
        "see -- tag it with the guard that protects it "
        f"({', '.join(sorted(REASONS_REQUIRING_REF))}) plus a ref=, or "
        "reason=known-gap if it is a real gap you are tracking:\n\n"
        + "\n".join(f"    {k}" for k in sorted(offenders))
    )
