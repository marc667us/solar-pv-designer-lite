# Vendor Management Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Govern how SolarPro selects, monitors, and offboards third-party vendors
that touch customer data or production infrastructure.

## Scope

Every vendor that has access to or processes SolarPro data.

## Current vendor register

| Vendor | Service | Data | Compliance |
|---|---|---|---|
| Render | App + Postgres hosting | All app data | SOC 2 Type II (vendor) |
| Keycloak | self-hosted on Render — not a vendor | — | — |
| Cloudflare | DNS + edge | DNS queries, request metadata | SOC 2 Type II |
| GitHub | Repo + CI runners + secrets | Source + workflow artifacts | SOC 2 Type II |
| Paystack | Payments | Card metadata (no full PAN) | PCI DSS |
| Brevo | Transactional email | Email addresses + content | GDPR aligned |
| Resend | Transactional email | Email addresses + content | GDPR aligned |
| Anthropic | LLM API | Prompt content (engineering helper) | SOC 2 Type II |
| OpenRouter | LLM API gateway | Prompt content | Provider-dependent |
| Let's Encrypt | TLS cert issuer | Domain names | Not applicable |
| open.er-api.com | FX rate feed | Public, no customer data | Not applicable |

## Policy

1. **Onboarding** — every new vendor with access to customer data
   must:
   - Have a documented data-processing agreement OR SOC 2 report
     reviewed by the Engineering Lead.
   - Be added to the register above.
   - Use scoped credentials (API key, not full account password).

2. **Credential rotation** — vendor secrets rotate annually OR on any
   breach involving that vendor.

3. **Monitoring** — vendor outages affecting production are tracked
   in `docs/IMPLEMENTATION_LOG.md`.

4. **Offboarding** — when a vendor is dropped:
   - Revoke API keys at the vendor side.
   - Remove from Render env + GitHub Secrets.
   - Remove from this register.
   - If they held customer data, request deletion in writing.

5. **Sub-processor disclosure** — customers asking for our vendor
   list get this table.

6. **Data residency** — vendors selected with EU + UK regions
   available where supported. Cloudflare + Render are present in
   multiple regions; default deployment is EU-West.

## Enforcement

- Adding a vendor without owner approval is a policy violation.
- Vendor credentials in source code are an incident.

## Review

Annual + on any vendor change.
