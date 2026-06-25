# Access Control Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Govern how identities are created, granted access, monitored, and revoked
across SolarPro systems.

## Scope

Applies to all human users, service accounts, automated agents, and
background workers. Covers the Flask app, the Keycloak realm, Postgres,
Render dashboard, GitHub repo, Cloudflare DNS, and every third-party
vendor console (Paystack, Brevo, Resend, etc.).

## Policy

1. **Single IDP** — all human authentication routes through Keycloak.
   No platform service accepts a username/password directly. SOC 2 M1.1
   (2026-06-25) closed the last bcrypt bypass; the bcrypt column itself
   is scheduled for removal in Phase B (migration 005).

2. **Least privilege** — every role is scoped to the minimum
   permissions needed for the job function. Role taxonomy is documented
   in `app/security/roles.py` and `keycloak/render/realm-prod.json`.

3. **Tenant isolation** — every tenant-owned table carries `tenant_id`,
   every query filters on it (application layer), and Postgres RLS
   enforces it at the DB layer. Cross-tenant access is denied by default.

4. **MFA for elevated roles** — `platform_super_admin`, `tenant_admin`,
   `finance_officer`, and `read_only` (auditor) must enrol TOTP. See
   `docs/SECURITY_MFA_PROPOSAL_M12.md` for the staged rollout.

5. **Service-account isolation** — service accounts use Keycloak
   client_credentials grant only. Each agent has its own SA client; the
   secret is in Render env / GH Secrets, never in source.

6. **Access reviews** — quarterly: list every user in the realm, every
   role assignment, every active SA. Remove anyone who has changed
   role or left. Output saved to the SOC 2 evidence bundle.

7. **Joiners / movers / leavers** — onboarding adds the user to the
   right KC group; departure revokes via realm + Render dashboard + GH
   org. Same-day SLA for leavers.

## Enforcement

- Every `/admin` and `/api` route MUST carry an auth decorator
  (`@require_role`, `@require_any_role`, `@require_jwt`, `@admin_required`,
  or `@require_service_account`). Routes without are flagged by the
  M2.6 audit check.
- M1.7 request hooks tag every tenant-scoped path; any 2xx response on
  a tenant path WITHOUT `g.kc_ctx` is logged as a structured warning.
- Hidden / unlinked admin pages MUST still be backend-protected. URL
  guessing alone never grants access.

## Review

Annual or after any access-related incident.
