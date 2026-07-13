"""Grant ONBOARDING_OWNER_ROLES to owners of organisations onboarded BEFORE slice 6.5.

WHY THIS EXISTS
---------------
Slice 6.5 (f8abf95) fixed the onboarding-owner lockout: `create_organisation` now grants the
creator a BUNDLE of roles (constants.ONBOARDING_OWNER_ROLES) rather than `enterprise_owner`
alone, because the stage gates check a NAMED ROLE, not a permission -- so no permission-map
change could ever have reached them.

But that grant only fires INSIDE create_organisation. Organisations that were onboarded
before 6.5 shipped still hold `enterprise_owner` and nothing else. The code is fixed; their
DATA is not. On live that is exactly the situation: the Live Enterprise Rebuild Suite reports
"already onboarded -- reusing the existing organisation" and then fails 4 checks, because the
owner of that pre-6.5 organisation still cannot author a template, import a beneficiary, or
score a site.

This is a one-time, idempotent data fix. It is NOT a migration .sql file, deliberately:

  * The grant must be AUDITED (control C12), and audit_logs carries an application-computed
    SHA-256 hash chain (app/security/audit.py). A raw SQL INSERT would either skip the audit
    row or forge one outside the chain. Driving the existing `members.grant()` service instead
    means every grant lands with a real, chained ENTERPRISE_ROLE_GRANTED row.
  * `members.grant()` already permits self-granting on purpose (a tenant.admin holder can
    grant any role to anyone, so refusing to let them name themselves stops nothing), and it
    already REFUSES personal tenants structurally via `_guard_admin`. Reusing it means this
    script cannot invent an authority path the app does not already have.

SCOPE -- READ THIS BEFORE WIDENING IT
-------------------------------------
ONLY real organisations (`enterprise_tenants.legacy_user_id IS NULL`).

Personal tenants ALSO grant `enterprise_owner` (tenancy.get_or_create_personal_tenant), and
every user on the platform has one. Dropping the legacy_user_id filter would therefore hand
all 11 enterprise roles to EVERY USER on the platform. `members.grant()` would refuse anyway
(_guard_admin rejects personal tenants), but do not rely on that alone -- the filter is the
first line and the guard is the second.

Input:  DATABASE_URL (Postgres). --apply to commit; omit it for a dry run.
Output: a per-owner plan on stdout; exit 0 on success, 1 on failure.

Usage:
    python scripts/backfill_onboarding_owner_roles.py             # plan only, no writes
    python scripts/backfill_onboarding_owner_roles.py --rehearse  # REAL grants, then ROLLBACK
    python scripts/backfill_onboarding_owner_roles.py --apply     # commits the grants

--rehearse exists because write_audit_event is non-raising BY CONTRACT: it logs and returns
False. members.grant() turns that False into "the role grant was not saved, because its audit
record could not be written" (control C12) -- a correct, safe failure that tells you nothing
about WHY. Rehearsal runs the real grants against the real database inside one transaction,
surfaces the underlying audit exception, and then rolls the whole thing back. Use it to
diagnose before ever reaching for --apply.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

# The app package must be importable; the script lives in scripts/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db_adapter                                             # noqa: E402
from app.enterprise_programme import members, tenancy         # noqa: E402
from app.enterprise_programme.constants import ONBOARDING_OWNER_ROLES  # noqa: E402


# Owners of REAL organisations only -- see SCOPE above. An owner is a user with an ACTIVE
# membership who holds the tenant-scoped `enterprise_owner` role.
_OWNERS_SQL = """
    SELECT t.id, t.legal_name, m.user_id
      FROM enterprise_tenants t
      JOIN enterprise_tenant_memberships m
        ON m.tenant_id = t.id AND m.status = 'active'
      JOIN enterprise_role_assignments ra
        ON ra.tenant_id = t.id
       AND ra.user_id   = m.user_id
       AND ra.role_code = 'enterprise_owner'
       AND ra.scope_type = 'tenant'
     WHERE t.legacy_user_id IS NULL
       AND t.status = 'active'
     ORDER BY t.legal_name, m.user_id
"""

# `?` placeholders, NOT `%s`. db_adapter doubles literal `%` to `%%` BEFORE it substitutes
# `?` -> `%s`, so a hand-written `%s` here would be mangled into `%%s`. Using `?` also means
# this same SQL runs on SQLite, which is what makes the backfill unit-testable.
_HELD_SQL = """
    SELECT role_code
      FROM enterprise_role_assignments
     WHERE tenant_id = ? AND user_id = ? AND scope_type = 'tenant'
"""


def backfill(conn, apply: bool = False, out=print) -> dict:
    """Grant each organisation owner the roles slice 6.5 would have given them at onboarding.

    Input:  an open connection (Postgres in production, SQLite under test), and `apply`
            -- False (default) plans without writing anything.
    Output: {"owners": int, "missing": int, "granted": int}. Does NOT commit; the caller does.

    Idempotent: a role the owner already holds is never re-granted, so re-running is a no-op.
    """
    owners = conn.execute(_OWNERS_SQL).fetchall()
    if not owners:
        out("No organisation owners found. Nothing to do.")
        return {"owners": 0, "missing": 0, "granted": 0}

    total_missing = 0
    granted = 0

    for tenant_id, legal_name, user_id in owners:
        held = {r[0] for r in conn.execute(_HELD_SQL, (tenant_id, user_id)).fetchall()}
        missing = [r for r in ONBOARDING_OWNER_ROLES if r not in held]

        out(f"-- {legal_name}  (tenant {tenant_id}, owner user_id={user_id})")
        out(f"   holds {len(held)}: {', '.join(sorted(held)) or '(none)'}")
        if not missing:
            out("   OK -- already holds the full bundle. Nothing to grant.")
            out("")
            continue

        total_missing += len(missing)
        out(f"   MISSING {len(missing)}: {', '.join(missing)}")

        if not apply:
            out("   (dry run -- not granted)")
            out("")
            continue

        # Publish the GUC the way a real request would, so this keeps working the day the
        # enterprise RLS policies are FORCEd (today they are ENABLE'd only, and the app
        # connects as the table owner, so they are inert).
        tenancy.apply_enterprise_guc(conn, user_id)

        for role_code in missing:
            # Self-grant by the owner: they hold tenant.admin, so this is an authority they
            # already have. It lands an audited, hash-chained ENTERPRISE_ROLE_GRANTED row.
            members.grant(conn, tenant_id, user_id, user_id, role_code)
            granted += 1
            out(f"   granted {role_code}")
        out("")

    return {"owners": len(owners), "missing": total_missing, "granted": granted}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Commit the grants. Without it, nothing is written.")
    ap.add_argument("--rehearse", action="store_true",
                    help="Perform the REAL grants against the real DB, print what happened, "
                         "then ROLL BACK. Writes nothing. Use to diagnose an audit failure.")
    args = ap.parse_args()

    if args.apply and args.rehearse:
        print("ERROR: --apply and --rehearse are mutually exclusive.", file=sys.stderr)
        return 1

    # write_audit_event never raises -- it logs and returns False, and members.grant() turns
    # that into a bare "audit record could not be written". Without a handler on the audit
    # logger, the actual psycopg2 exception is dropped on the floor and the failure is
    # undiagnosable. Send it to stdout.
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
                        format="   [%(levelname)s %(name)s] %(message)s")

    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        print("ERROR: DATABASE_URL must be a Postgres URL.", file=sys.stderr)
        return 1

    writing = args.apply or args.rehearse
    mode = ("APPLY" if args.apply else
            "REHEARSAL (real grants, then ROLLBACK -- nothing is kept)" if args.rehearse else
            "DRY RUN (nothing will be written)")
    print(f"== Backfill onboarding owner roles -- {mode} ==")
    print(f"   bundle: {len(ONBOARDING_OWNER_ROLES)} roles -> {', '.join(ONBOARDING_OWNER_ROLES)}")
    print()

    conn = db_adapter.open_postgres(url)
    try:
        stats = backfill(conn, apply=writing)
    except Exception:
        if args.rehearse:
            conn.rollback()
            print()
            print("== REHEARSAL FAILED -- rolled back, nothing was written ==")
        raise

    print("== Summary ==")
    print(f"   organisation owners examined: {stats['owners']}")
    print(f"   roles missing:                {stats['missing']}")
    if args.apply:
        print(f"   roles granted:                {stats['granted']}")
        conn.commit()
        print("   COMMITTED.")
    elif args.rehearse:
        print(f"   roles granted (then rolled back): {stats['granted']}")
        conn.rollback()
        print("   ROLLED BACK -- the database is unchanged.")
        print("   The grants worked. Re-run with --apply to keep them.")
    else:
        print("   roles granted:                0 (dry run)")
        print("   Re-run with --rehearse to prove it works, then --apply to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
