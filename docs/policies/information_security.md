# Information Security Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Define the security program for SolarPro Global so customer data, billing
data, and internal operations are protected against unauthorised access,
disclosure, alteration, or destruction.

## Scope

Applies to every SolarPro system, every employee + contractor, every
contracted vendor, and every device used to develop, deploy, or operate
the platform.

## Policy

1. **Security objectives** — confidentiality, integrity, and availability
   of customer + platform data are first-order engineering concerns. No
   feature ships without addressing them.

2. **Risk register** — top platform risks reviewed at least quarterly
   and documented in `docs/IMPLEMENTATION_LOG.md`. Today's top risks:
   cross-tenant data leak via missed RLS predicate; KC outage (no
   bcrypt fallback after M1.1); credential leak via env-var sprawl.

3. **Defence in depth** — every tenant resource is protected by JWT
   middleware (layer 1), role decorator (layer 2), application-level
   WHERE clause (layer 3), Postgres RLS (layer 4), audit log (layer 5).
   See `docs/architecture/rls_layer.md` for the diagram.

4. **Open-source first** — security controls use FOSS where possible
   (Keycloak for IDP, Postgres RLS, semgrep/bandit/gitleaks for CI,
   GlitchTip/Sentry for errors) to avoid vendor lock-in + reduce cost.

5. **Continuous compliance** — controls land in code, not in PDFs.
   `docs/SOC2_IMPLEMENTATION_PLAN.md` tracks the live posture; the SOC 2
   audit dashboard at `/admin/soc2/report` shows the score against the
   13+ active checks.

6. **Incident handling** — every High-severity finding (internal,
   pen-test, or auditor) opens an incident per the Incident Response
   Policy. Resolution is logged in `docs/IMPLEMENTATION_LOG.md`.

## Enforcement

- Violations by employees are subject to formal review by the Engineering
  Lead. Wilful or grossly negligent violations may result in revocation
  of access + termination.
- Violations by vendors trigger the Vendor Management Policy.

## Controls implemented (live)

| Control | Where |
|---|---|
| Centralised IDP (Keycloak OIDC) | `auth.aiappinvent.com` |
| RBAC (20 roles, role taxonomy) | `app/security/roles.py`, `app/security/decorators.py` |
| Tenant isolation (RLS) | `migrations/003_rls_tenant.sql`, `migrations/007_rls_boq_hierarchy.sql` |
| Audit log (immutable target) | `audit_logs` table + `app/security/audit.py` |
| Error tracking | `error_logs` table + `/admin/errors` |
| Security CI | `.github/workflows/security.yml` |
| Daily backup | `.github/workflows/backup-postgres.yml` |

## Review

This policy is reviewed annually or after any High-severity incident.
