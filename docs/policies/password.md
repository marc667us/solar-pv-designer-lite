# Password Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Define password requirements for SolarPro systems.

## Scope

Human user accounts in Keycloak; vendor console accounts (Render,
GitHub, Cloudflare, Paystack, Brevo, Resend, Anthropic, OpenRouter).
Service accounts use client-credentials grants and are out of scope.

## Policy

1. **Length** — minimum 12 characters. Keycloak realm policy enforces
   this for user-set passwords.

2. **Complexity** — Keycloak's default policy (`notUsername`,
   `notEmail`) plus a custom rule: at least one upper, one lower, one
   digit. Special characters not required (NIST 800-63B guidance).

3. **No reuse** — Keycloak tracks the last 5 password hashes per user
   and refuses reuse.

4. **No expiry by clock** — passwords are rotated only on incident,
   leaver event, or owner request. (NIST 800-63B explicitly recommends
   against arbitrary expiry.)

5. **MFA for elevated roles** — TOTP required for `platform_super_admin`,
   `tenant_admin`, `finance_officer`, `read_only`. See M1.2 proposal.

6. **Storage** — Keycloak stores password hashes using PBKDF2-SHA256
   with realm-default iterations (>= 27,500). The legacy
   `users.password_hash` column on solarpro-postgres is being retired
   (Phase B migration 005, owner-pending ≥ 2026-06-30).

7. **Recovery** — handled by Keycloak. Reset emails come from KC realm
   SMTP config; the SolarPro app forwards every `/forgot-password`
   request to Keycloak (no app-side bcrypt path).

8. **Brute force** — Keycloak realm bruteForceProtected=true. Default
   30-failure / 12-hour lockout.

## Enforcement

- Live enforcement is in `auth.aiappinvent.com` Keycloak realm policy.
- Workflow `Sync KC Seed Passwords` is the only allowed mechanism to
  rotate the master admin password; manual edits via KC console are
  audit-logged.

## Review

Annual.
