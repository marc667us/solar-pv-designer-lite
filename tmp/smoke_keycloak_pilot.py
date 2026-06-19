"""Phase 2 + 3 smoke test for the parallel-run Keycloak pilot.

Phase 2 — pilot route /admin/marketplace
  A) KC off, anon -> 302 to /login  (admin_required still gates)
  B) KC on, no Bearer -> 401 MISSING_BEARER  (require_role short-circuits)

Phase 3 — SA-only route /api/agents/internal/heartbeat
  C) KC off, anon POST -> 200 OK  (require_service_account is a no-op)
  D) KC on, no Bearer POST -> 401 MISSING_BEARER

The 200-with-valid-SA-JWT and 403-with-human-JWT legs need a running
Keycloak that can sign a real JWT for solarpro-catalogue-agent. Those
are exercised by the unit tests in tests/security/test_decorators.py
(test_correct_service_account_allowed / test_human_denied_on_service_account_route)
against synthetic JWTs, and by tests/security/test_service_account_client.py
against a mocked token endpoint.

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

    # ── B) KEYCLOAK_ENABLED=true, no Bearer (Phase 2 pilot) ─────────────
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

        # ── D) Phase 3 -- KC on, no Bearer on /api/agents/internal/heartbeat ──
        r = c.post("/api/agents/internal/heartbeat")
        body = r.get_data(as_text=True)
        if not check("D) KC on, no Bearer -> 401 MISSING_BEARER (heartbeat)",
                     r.status_code, 401, body=body):
            failures += 1
        elif "MISSING_BEARER" not in body:
            print(f"      [FAIL] body did not contain MISSING_BEARER: {body[:200]!r}")
            failures += 1
        else:
            print(f"      body: {body.strip()}")

    # ── C) Phase 3 -- KC off, anon POST -> 200 (pass-through) ───────────
    # Done after B so we don't pollute the previous fresh-app session.
    app_c = _fresh_app(keycloak_enabled=False)
    with app_c.test_client() as c:
        r = c.post("/api/agents/internal/heartbeat")
        body = r.get_data(as_text=True)
        if not check("C) KC off, anon -> 200 OK (heartbeat pass-through)",
                     r.status_code, 200, body=body):
            failures += 1
        else:
            print(f"      body: {body.strip()}")

    # Restore env for any subsequent imports.
    os.environ.pop("KEYCLOAK_ENABLED", None)

    print(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
