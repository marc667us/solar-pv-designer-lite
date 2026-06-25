# Acceptable Use Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Define what employees + contractors may and may not do on SolarPro
systems.

## Scope

All employees, contractors, vendors, and devices used to access
SolarPro systems.

## Policy

1. **Use systems only for SolarPro work.** Casual browsing on the
   production Postgres console, the Render dashboard, or the
   Keycloak admin is forbidden.

2. **No production data on personal devices.** Code review on a
   laptop is fine; exporting `pg_dump` output to a personal cloud
   drive is not.

3. **No shared credentials.** Each engineer has their own KC user,
   GitHub user, Render seat (when the team grows). Service accounts
   are for machines only.

4. **Strong personal accounts.** Engineers' GitHub + Google +
   Render + KC accounts MUST have a unique password manager entry
   and MFA enabled.

5. **No installing unsanctioned tooling on shared infra.** Code
   that runs in production (Dockerfile, requirements.txt) must go
   through the standard PR review. No "let me just SSH in and pip
   install" — there is no SSH access to Render.

6. **Reporting** — anyone who suspects a security issue MUST report
   to the Engineering Lead within 24 hours. There is no penalty
   for reporting in good faith.

7. **No data exfiltration.** Customer data does not leave the
   platform via email, Slack, screenshots, or copy-paste except
   under an active incident-response need + owner approval.

8. **Disclosure** — public talks / blog posts about SolarPro
   architecture must avoid leaking exact rate limits, exact role
   names, customer counts, or anything that aids an attacker.

## Enforcement

Violations are reviewed by the Engineering Lead. Wilful or repeated
violations may result in revocation of access + termination.

## Review

Annual.
