"""
Strip the 13 test users out of docs/keycloak/realm-export.json and write
a production-safe variant at keycloak/render/realm-prod.json.

What it does:
  * Reads the canonical realm export (used by docker-compose for local
    development; carries test fixtures that must never reach production).
  * Identifies test users by the `email` field ending in
    `test.solarpro.local` (matches the convention in plan §5.1).
  * Writes a new JSON file with the `users` list reduced to []. Real
    users land via `scripts/migrate_users_to_keycloak.py --apply` after
    Keycloak is up.
  * Re-running is safe: the input file is never mutated; the output is
    overwritten.

Input:  docs/keycloak/realm-export.json
Output: keycloak/render/realm-prod.json
Exit:   0 on success; 1 if the input is missing or no test users found
        (the latter would mean the test convention drifted -- bail loudly
        so we don't ship a realm with real-looking test creds by accident).

Run:
  python keycloak/render/build_realm_prod.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Resolve paths relative to the repo root so the script is invocable
# from any cwd (CI, local, Docker build context).
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "docs" / "keycloak" / "realm-export.json"
DST = REPO_ROOT / "keycloak" / "render" / "realm-prod.json"

# All test users in plan §5.1 use this email domain. If a future change
# adds test fixtures without this suffix we want to fail closed.
TEST_EMAIL_SUFFIX = "test.solarpro.local"


def main() -> int:
    if not SRC.exists():
        print(f"missing input: {SRC}", file=sys.stderr)
        return 1

    realm = json.loads(SRC.read_text(encoding="utf-8"))
    users = realm.get("users", []) or []

    test_users = [u for u in users if (u.get("email") or "").endswith(TEST_EMAIL_SUFFIX)]
    real_users = [u for u in users if not (u.get("email") or "").endswith(TEST_EMAIL_SUFFIX)]

    if not test_users:
        # The canonical export should always carry 13 test fixtures.
        # If we read 0, the file was already production-cleaned (unsafe
        # for local dev) or the suffix convention changed.
        print(
            "FAIL: no test users matched suffix "
            f"{TEST_EMAIL_SUFFIX!r}. Refusing to write realm-prod.json "
            "to avoid silently shipping unfiltered users.",
            file=sys.stderr,
        )
        return 1

    # Strip the users list. Roles / clients / groups / clientScopes stay.
    # Real users join later via partial-import (admin REST).
    realm["users"] = real_users  # empty list expected

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(realm, indent=2) + "\n", encoding="utf-8")

    print(f"stripped {len(test_users)} test users; wrote {DST}")
    print(f"realm: {realm.get('realm')!r} | "
          f"roles: {len(realm.get('roles', {}).get('realm', []))} | "
          f"clients: {len(realm.get('clients', []))} | "
          f"groups: {len(realm.get('groups', []))} | "
          f"users now: {len(realm['users'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
