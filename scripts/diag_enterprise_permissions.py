"""READ-ONLY diagnostic: who can create a programme, and who gets a 403?

WHY THIS EXISTS
---------------
The owner reported that clicking "Create new programme" lands on the friendly error
page saying they are not authorised. That page is what abort(403) renders through the
catch-all handler, and the only abort(403) on that route is:

    enterprise_programme_routes.enterprise_programme_new
        if not rbac.has_permission(c, active, uid, "programme.create"): abort(403)

So the 403 is a fact about DATA, not code: some (user, active_tenant) pair holds no
role carrying `programme.create`. The dry-run backfill proved the MOE owner (user_id=2)
holds all 11 roles -- so the 403 belongs to a DIFFERENT user, or to the same user acting
in a DIFFERENT tenant. Guessing which is how the last two sessions were lost; this
reproduces the route's own decision against live data instead.

WHAT IT DOES
------------
For every user with any enterprise membership it prints:
  * every tenant they belong to, and the roles they hold there
  * whether those roles carry `programme.create`
  * WHICH TENANT `_tenant()` WOULD SELECT ON A FRESH SESSION -- the routes' default:
    exactly one organisation -> that org; otherwise the first tenant listed, which is
    the personal one. This default is reimplemented here from the route, because it is
    the step that decides which tenant the permission is checked against.
  * the verdict: would this user see the form, or the 403?

WRITES NOTHING. No confirm gate needed -- it opens the connection, SELECTs, and closes.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

from app.enterprise_programme.constants import permissions_for_roles  # noqa: E402


def main() -> int:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # Every tenant, with the flag that distinguishes a real organisation (legacy_user_id
    # IS NULL) from a personal workspace.
    cur.execute(
        "SELECT id, legal_name, organisation_type, legacy_user_id, status "
        "  FROM enterprise_tenants"
    )
    tenants = {r[0]: {"name": r[1], "type": r[2], "legacy_user_id": r[3], "status": r[4]}
               for r in cur.fetchall()}

    # Active memberships only: a revoked membership grants nothing (rbac.roles_for_user
    # JOINs on status='active', so this diagnostic must too or it would disagree with the app).
    cur.execute(
        "SELECT m.user_id, m.tenant_id, m.status, "
        "       COALESCE(u.username, '?'), COALESCE(u.email, '') "
        "  FROM enterprise_tenant_memberships m "
        "  LEFT JOIN users u ON u.id = m.user_id "
        " ORDER BY m.user_id"
    )
    memberships = cur.fetchall()

    # Tenant-scoped, unexpired role assignments -- the same three conditions rbac applies.
    cur.execute(
        "SELECT tenant_id, user_id, role_code FROM enterprise_role_assignments "
        " WHERE scope_type = 'tenant' "
        "   AND (starts_at IS NULL OR starts_at <= CURRENT_TIMESTAMP) "
        "   AND (ends_at   IS NULL OR ends_at   >  CURRENT_TIMESTAMP)"
    )
    roles: dict[tuple[str, int], set[str]] = {}
    for tid, uid, rc in cur.fetchall():
        roles.setdefault((tid, uid), set()).add(rc)

    users: dict[int, dict] = {}
    for uid, tid, status, username, email in memberships:
        u = users.setdefault(uid, {"username": username, "email": email, "tenants": []})
        if status == "active":
            u["tenants"].append(tid)

    print(f"== tenants on live: {len(tenants)} "
          f"({sum(1 for t in tenants.values() if t['legacy_user_id'] is None)} real organisations) ==")
    print(f"== users with an enterprise membership: {len(users)} ==\n")

    blocked = []

    for uid in sorted(users):
        u = users[uid]
        print(f"user_id={uid}  {u['username']}  <{u['email']}>")

        if not u["tenants"]:
            print("   NO ACTIVE MEMBERSHIP -- would fall back to a personal tenant\n")
            blocked.append((uid, u["username"], "no active membership"))
            continue

        for tid in u["tenants"]:
            t = tenants.get(tid, {})
            held = roles.get((tid, uid), set())
            perms = permissions_for_roles(held)
            kind = "PERSONAL" if t.get("legacy_user_id") is not None else "ORG"
            can = "programme.create" in perms
            print(f"   [{kind}] {t.get('name', tid)}  ({tid})")
            print(f"        roles ({len(held)}): {', '.join(sorted(held)) or '(NONE)'}")
            print(f"        programme.create: {'YES' if can else 'NO  <-- this tenant 403s'}")

        # Reimplementation of enterprise_programme_routes._tenant()'s fresh-session default.
        # A user in exactly ONE organisation is dropped into that ORG, not their personal
        # workspace. That is the branch that decides which tenant the 403 is judged against.
        orgs = [tid for tid in u["tenants"]
                if tenants.get(tid, {}).get("legacy_user_id") is None]
        if len(orgs) == 1:
            active = orgs[0]
            why = "member of exactly ONE org -> routed into the org"
        else:
            personal = [tid for tid in u["tenants"]
                        if tenants.get(tid, {}).get("legacy_user_id") is not None]
            active = (personal or u["tenants"])[0]
            why = f"{len(orgs)} orgs -> falls back to the personal workspace"

        held = roles.get((active, uid), set())
        can = "programme.create" in permissions_for_roles(held)
        print(f"   FRESH SESSION lands in: {tenants.get(active, {}).get('name', active)}  ({why})")
        print(f"   VERDICT: {'sees the form' if can else '*** 403 -- THIS IS THE REPORTED BUG ***'}\n")
        if not can:
            blocked.append((uid, u["username"], tenants.get(active, {}).get("name", active)))

    print("== SUMMARY ==")
    if blocked:
        print(f"{len(blocked)} user(s) would be 403'd on /enterprise/programmes/new:")
        for uid, name, where in blocked:
            print(f"   user_id={uid}  {name}  -> active tenant: {where}")
    else:
        print("No user is 403'd. The bug is NOT reproducible from role data alone --")
        print("look at the session's carried tenant id, not the fresh-session default.")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
