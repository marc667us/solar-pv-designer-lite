"""
Static route/auth scanner -- the engine behind the route-auth ratchet.

WHAT
    Walks every live repo-root ``*.py``, finds each ``@<x>.route("<path>", ...)``
    decorator, collects the whole decorator stack attached to the same
    function, and classifies the route as protected or unprotected.

WHY IT IS STATIC (does not import the app)
    Importing ``web_app`` raises ``SystemExit: Set SOLARPRO_ADMIN_PASSWORD``
    during collection on a box without the production env, which makes the
    whole suite report "no tests ran". A static scan has no such dependency,
    so the ratchet runs everywhere -- including CI and a bare dev machine.
    The trade-off is that we see decorators, not the live URL map; routes
    guarded by an in-body token check (CDC drain, SOC ingest, Keycloak
    events) therefore look "unprotected" here and live in the allowlist
    tagged ``reason=in-body-token`` with a ``ref=`` to the check.

SCOPE -- READ THIS BEFORE TRUSTING A GREEN RUN
    The scan covers repo-ROOT ``*.py`` only. Two things are deliberately
    OUT of scope, and a green ratchet says nothing about them:

    1. ``app/**`` subpackages. In particular ``app/auth/oidc_routes.py``
       registers the Keycloak/OIDC Blueprint (``@oidc_bp.route`` for
       /auth/login, /auth/callback, /auth/logout, /auth/refresh). Those
       routes are governed by app/security/decorators.py and are OFF-LIMITS
       to this ratchet by owner instruction (2026-07-20) -- a login outage
       has already been caused here once by touching that flow. Widening the
       scanner into app/** would put the ratchet in a position to demand
       changes to the auth flow, which is exactly what we must not do.

    2. (CLOSED 2026-07-20) ``add_url_rule()`` registrations. This used to be
       a blind spot -- the scanner matched decorators only. When the /api/v1
       aliases introduced the first production ``add_url_rule`` calls, the
       scanner was TAUGHT to parse them rather than the new module being
       exempted from its own guard. Such routes are reported with no
       decorators, because their authorisation lives on the view function
       they alias; they must therefore be justified in the allowlist like
       any other undecorated route.

    3. DUPLICATE KEYS (Codex, 2026-07-20 -- the ratchet's largest hole).
       The tests compare SETS of "<METHODS> <path>" keys. If a key is
       already allowlisted, a SECOND undecorated declaration of the same
       method+path -- in a different module -- is absorbed silently and the
       ratchet stays green. This is not merely theoretical here: new_*.py
       modules are byte-spliced into web_app.py, so legitimate duplicate
       declarations are the norm and cannot simply be banned. Closing it
       properly needs the live url_map, which is out of scope while the
       auth flow is off-limits (see WHY IT IS STATIC). Recorded, not fixed.

    Consequence: a green ratchet means "the undecorated surface has not
    GROWN a new path". It does not mean "every route is authenticated".

INPUT   repo root path
OUTPUT  list[dict] -- one record per route declaration:
        {file, line, path, methods, decorators, protected}

Run the scan by hand:

    python tests/route_auth_scan.py .
"""

from __future__ import annotations

import os
import re

# The head of a route decorator: @app.route(  /  @bp.route(
_RE_ROUTE_HEAD = re.compile(r"^\s*@(\w+)\.route\(\s*(?P<args>.*)$")
# One string literal, so adjacent literals can be concatenated (Python
# implicit concatenation is used in this repo for long route paths).
_RE_STRING = re.compile(r"""\s*(['"])(?P<val>.*?)\1""")
_RE_DECO = re.compile(r"^\s*@(?P<name>[\w.]+)")
_RE_DEF = re.compile(r"^\s*(async\s+)?def\s")
_RE_METHOD = re.compile(r"""['"](GET|POST|PUT|PATCH|DELETE)['"]""")
# app.add_url_rule("/path", ...) -- the imperative registration form.
_RE_ADD_URL_RULE = re.compile(r"^\s*\w+\.add_url_rule\(\s*(?P<args>.*)$")

#: Decorators that constitute a real authn/authz gate. Adding a name here
#: widens what counts as "protected", so it is deliberately explicit -- a
#: new auth decorator must be registered consciously.
#:
#: Every name here is asserted to exist as a real `def` by
#: ``test_auth_decorators_all_exist``. Three names were removed on
#: 2026-07-20 after that check was written: `paid_only`, `staff_required`
#: and `owner_required` never existed, and `_paid_only` is an in-body
#: helper (web_app.py) called inside handlers, not a decorator -- listing
#: it implied a protection the decorator scan can never actually see.
AUTH_DECORATORS = frozenset({
    "login_required",
    "admin_required",
    "supplier_required",
    "procurement_role_required",
    "tech_support_role_required",
    "require_jwt",
    "require_role",
    "require_any_role",
    "require_all_roles",
    "require_scope",
    "require_tenant_match",
    "require_service_account",
})

#: Files excluded from the scan. These are archived route modules kept for
#: reference; they are never imported, so their routes never register.
_SKIP_MARKERS = ("_legacy_", "_pre_v2swap_", "patch_")


def iter_source_files(root: str):
    """Yield the path of every LIVE repo-root .py file.

    Single definition of "a live source file" so the scanner and the
    add_url_rule guard cannot drift apart about what is in scope.
    """
    for name in sorted(os.listdir(root)):
        if not name.endswith(".py"):
            continue
        if name.startswith("test_") or any(s in name for s in _SKIP_MARKERS):
            continue
        yield os.path.join(root, name)


def read_source(path: str) -> str:
    """Read a source file as text.

    Decoded latin-1 on purpose: web_app.py is CRLF + mojibake (UTF-8 dashes
    stored as Windows-1252) and raises UnicodeDecodeError under a strict
    utf-8 read. We only ever pattern-match ASCII, so a byte-preserving
    codec is both safe and sufficient.
    """
    with open(path, "rb") as fh:
        return fh.read().decode("latin-1")


def _extract_path(args: str) -> str | None:
    """Pull the route path out of the text following ``.route(``.

    Handles Python implicit string concatenation -- this repo splits long
    route paths across adjacent literals, e.g.

        @app.route("/large-scale-solar/<int:pid>/dt"
                   "/object-action", methods=["POST"])

    Taking only the first literal would record a path that does not exist,
    so the allowlist key would name a route the app never serves.
    """
    parts: list[str] = []
    rest = args
    while True:
        m = _RE_STRING.match(rest)
        if not m:
            break
        parts.append(m.group("val"))
        rest = rest[m.end():]
    return "".join(parts) if parts else None


def _scan_file(path: str) -> list[dict]:
    """Scan one .py file for route declarations."""
    raw = read_source(path)
    # Cheap pre-filter: ~40% of repo-root modules declare no routes at all,
    # and splitting a 2 MB file into 40k lines to find nothing is pure waste.
    if ".route(" not in raw and ".add_url_rule(" not in raw:
        return []

    lines = raw.replace("\r\n", "\n").split("\n")
    found: list[dict] = []

    for i, line in enumerate(lines):
        # Imperative registration: app.add_url_rule("/path", ..., methods=[...]).
        # Reported with NO decorators, because authorisation lives on the view
        # function being registered -- which this static scan cannot resolve.
        # Such a route must therefore be justified in the allowlist, exactly
        # like any other undecorated route.
        rule = _RE_ADD_URL_RULE.match(line)
        if rule:
            args = rule.group("args")
            # Pull methods from the following few lines too -- the call is
            # usually wrapped across several.
            window = "\n".join(lines[i:i + 8])
            rule_path = _extract_path(args)
            if rule_path and rule_path.startswith("/"):
                found.append({
                    "file": os.path.basename(path),
                    "line": i + 1,
                    "path": rule_path,
                    "methods": sorted(set(_RE_METHOD.findall(window))) or ["GET"],
                    "decorators": [],
                    "protected": False,
                })
            continue

        head = _RE_ROUTE_HEAD.match(line)
        if not head:
            continue

        route_path = _extract_path(head.group("args"))
        if route_path is None:
            continue

        methods = _RE_METHOD.findall(head.group("args"))
        decorators: list[str] = []

        # Look AHEAD over the rest of the decorator stack to the def. This is
        # a lookahead, never a consume: `i` still advances one line at a time,
        # so a SECOND @app.route stacked on the same function is emitted as
        # its own record rather than being swallowed as a decorator named
        # "route". Stacked routes are real here --
        # new_price_sheet_export_routes.py:10-11 puts .../export.xlsx and
        # ....xlsx on one handler.
        j = i + 1
        while j < len(lines) and j < i + 40:
            deco = _RE_DECO.match(lines[j])
            if deco:
                decorators.append(deco.group("name").split(".")[-1])
                j += 1
                continue
            if _RE_DEF.match(lines[j]):
                break
            stripped = lines[j].strip()
            if stripped and not stripped.startswith("#"):
                # Continuation line of a multi-line route decorator --
                # methods=[...] often lands here.
                methods.extend(_RE_METHOD.findall(lines[j]))
            j += 1

        found.append({
            "file": os.path.basename(path),
            "line": i + 1,
            "path": route_path,
            "methods": sorted(set(methods)) or ["GET"],
            "decorators": decorators,
            "protected": bool(set(decorators) & AUTH_DECORATORS),
        })
    return found


def scan_repo(root: str) -> list[dict]:
    """Scan every live repo-root *.py and return all route records."""
    routes: list[dict] = []
    for path in iter_source_files(root):
        routes.extend(_scan_file(path))
    return routes


def route_key(record: dict) -> str:
    """Stable identity for a route, used as the allowlist key.

    Includes methods so that adding a POST to a previously GET-only public
    route trips the ratchet instead of silently inheriting its exemption.
    """
    return f"{','.join(record['methods'])} {record['path']}"


def unprotected(root: str) -> list[dict]:
    """All route records with no recognised auth decorator."""
    return [r for r in scan_repo(root) if not r["protected"]]


def report(root: str = ".") -> None:
    """Human-readable summary -- for running the scan by hand."""
    all_routes = scan_repo(root)
    unprot = [r for r in all_routes if not r["protected"]]
    print(f"live route declarations : {len(all_routes)}")
    print(f"  protected             : {len(all_routes) - len(unprot)}")
    print(f"  unprotected           : {len(unprot)}")
    for r in sorted(unprot, key=route_key):
        print(f"    {route_key(r):<60} {r['file']}:{r['line']}")


if __name__ == "__main__":
    import sys
    report(sys.argv[1] if len(sys.argv) > 1 else ".")
