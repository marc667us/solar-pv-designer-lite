# Data Classification Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Classify the data SolarPro processes so storage, transit, and access
controls scale with sensitivity.

## Scope

All data on SolarPro systems.

## Classification tiers

| Tier | Examples | Storage | Transit | Access |
|---|---|---|---|---|
| **Public** | Marketing site, product names, public datasheets | Any | TLS not required | Anyone |
| **Internal** | Internal docs, engineering plans, ADRs, non-personal telemetry | Render Postgres or repo | TLS required | Employees + Codex/Supervisor agents |
| **Confidential** | Customer projects, BOQ data, BOM data, supplier prices, AI conversations, error stacks | Render Postgres (RLS-enforced) | TLS required | Tenant members + platform admins |
| **Restricted** | Bank details, supplier API keys, financial models, payment metadata, refresh tokens, audit logs | Render Postgres (RLS + field-level encryption planned M2.1) | TLS required | Owner + finance_officer + read_only auditor |

## Policy

1. **Labelling** — every new table joins one of the four tiers. The
   tier is recorded as a comment in the migration that creates it.

2. **Storage rules**
   - Public: any storage with TLS-in-transit.
   - Internal: encrypted-at-rest by Render Postgres defaults.
   - Confidential: encrypted-at-rest + RLS-enforced + audit logged.
   - Restricted: encrypted-at-rest + RLS + audit + field-level
     AES-256-GCM (planned M2.1) + access restricted to elevated roles.

3. **Transit rules** — TLS 1.2+ for everything that crosses a
   network. No internal "fast path" over plaintext.

4. **Logging rules**
   - Confidential / Restricted data MUST NOT be logged verbatim.
   - Identifiers (user_id, tenant_id, agent_id) are loggable; raw
     values (full names, bank account numbers) are not.

5. **Backups** — backups inherit the classification of the highest
   tier they contain. The nightly Postgres backup is therefore
   Restricted and stays inside GitHub Actions encrypted-at-rest
   storage.

6. **Sharing externally**
   - Public — fine.
   - Internal — only after redaction.
   - Confidential — only under an active customer request + audit
     log entry.
   - Restricted — only the owner can authorise an external share.

## Enforcement

- A new `SELECT *` over a Restricted table without an explicit
  reason field in the PR description fails Codex review.
- A new column that holds Restricted data without M2.1 field-level
  encryption is a defect to be tracked.

## Review

Annual + after any incident involving misclassified data.
