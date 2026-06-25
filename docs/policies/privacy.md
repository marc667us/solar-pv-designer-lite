# Privacy Policy (internal — operational)

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

> This is the **internal** operational privacy policy that engineers
> follow. The **customer-facing** privacy policy is at
> `/data-protection` on the live site.

## Purpose

Define how SolarPro collects, processes, stores, and deletes personal
data to align with GDPR, UK GDPR, and emerging African data-protection
laws (Ghana DPA 2012, Nigeria NDPR).

## Scope

Personal data of customers, prospects, employees, contractors, and
website visitors.

## Policy

1. **Data minimisation** — collect only what's needed for a stated
   purpose. Each new field on a form must justify its existence in
   the PR description.

2. **Lawful basis** — track per-field: consent / contract / legal
   obligation / legitimate interest. Maintained in
   `docs/data_inventory.md` (TODO).

3. **Purpose limitation** — data collected for one purpose (e.g.
   billing) is not repurposed (e.g. marketing) without a fresh basis.

4. **Storage location** — primary data store is Render Postgres
   (EU-West region by default). Backups in GitHub Actions artifacts.
   Customer data does NOT leave EU/UK without an explicit transfer
   mechanism (SCCs or adequacy decision).

5. **Retention** — customer accounts: retained while active + 30 days
   after deletion request. Audit logs: 7 years (SOC 2 + financial
   record requirement). Error logs: 90 days unless escalated.

6. **Subject rights** — every individual whose data we hold can:
   - request access (within 30 days)
   - request rectification
   - request erasure ("right to be forgotten")
   - request portability (export)
   - object to processing

   Implementation today: email `support@aiappinvent.com`. Operational
   target: in-app self-service `/account/privacy` page.

7. **Breach notification** — any data breach involving personal data
   triggers the Incident Response Policy P1/P2 path AND a 72-hour
   notification to the relevant supervisory authority if EU data is
   involved.

8. **PII redaction in logs** — `app/security/audit.py` and
   `error_logs` capture user_id (an integer), not the email or name.
   Stack traces are scrubbed of obvious PII before storage.

9. **DPO** — owner is the named Data Protection Officer until the
   org scales past 250 employees.

## Enforcement

- New fields without a lawful-basis note fail Codex review.
- Logs containing raw emails or full names fail Codex security
  review.

## Review

Annual + on any regulator change (e.g. UK Data Protection and Digital
Information Bill landing).
