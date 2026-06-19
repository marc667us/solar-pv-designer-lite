"""Phase 2 task 11 smoke test: verify both legs of the parallel-run pilot.

A) KEYCLOAK_ENABLED unset
   -> @require_role is a pass-through.
   -> @admin_required handles the request.
   -> Anonymous caller is redirected to /login (302).

B) KEYCLOAK_ENABLED=true, no Bearer header
   -> @require_role short-circuits with 401 MISSING_BEARER.
   -> @admin_required never runs.

We import the Flask app via importlib so we can flip the env var before
import (`_keycloak_enabled()` re-reads os.environ on every call, but
clearing module caches keeps this safe regardless).
"""
from __future__ import annotations

import importlib
import os
import sys


def _fresh_app(keycloak_enabled: bool):
    """Re-import web_app cleanly so its top-level state is consistent."""
    if keycloak_enabled:
        os.environ["KEYCLOAK_ENABLED"] = "true"
    else:
        os.environ.pop("KEYCLOAK_ENABLED", None)

    # Reset cached modules so import-time side effects aren't doubled.
    for mod in list(sys.modules):
        if mod.startswith("web_app") or mod.startswith("app.security"):
            del sys.modules[mod]

    web_app = importlib.import_module("web_app")
    return web_app.app


def check(label: str, actual: int, expected: int, body: str = "") -> bool:
    ok = actual == expected
    mark = "[ok]" if ok else "[FAIL]"
    print(f"{mark} {label}: status={actual} expected={expected}")
    if not ok and body:
        print(f"      body={body[:200]!r}")
    return ok


def main() -> int:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    failures = 0

    # ── A) KEYCLOAK_ENABLED unset -- old auth path ──────────────────────
    app_a = _fresh_app(keycloak_enabled=False)
    with app_a.test_client() as c:
        r = c.get("/admin/marketplace", follow_redirects=False)
        # admin_required redirects anonymous callers to login.
        if not check("A) KC off, anon -> 302 to /login", r.status_code, 302,
                     body=r.get_data(as_text=True)):
            failures += 1
        else:
            loc = r.headers.get("Location", "")
            if "/login" not in loc:
                print(f"      [FAIL] redirect target was {loc!r}, expected /login")
                failures += 1
            else:
                print(f"      Location: {loc}")

    # ── B) KEYCLOAK_ENABLED=true, no Bearer ─────────────────────────────
    app_b = _fresh_app(keycloak_enabled=True)
    with app_b.test_client() as c:
        r = c.get("/admin/marketplace", follow_redirects=False)
        body = r.get_data(as_text=True)
        # require_role short-circuits with 401 MISSING_BEARER.
        if not check("B) KC on, no Bearer -> 401 MISSING_BEARER",
                     r.status_code, 401, body=body):
            failures += 1
        elif "MISSING_BEARER" not in body:
            print(f"      [FAIL] body did not contain MISSING_BEARER: {body[:200]!r}")
            failures += 1
        else:
            print(f"      body: {body.strip()}")

    # Restore env for any subsequent imports.
    os.environ.pop("KEYCLOAK_ENABLED", None)

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
