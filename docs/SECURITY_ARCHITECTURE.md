# Security Architecture — SolarPro Global

Authoritative checklist lives in `SECURITY.md`. This file is the architectural summary + the Q-gate gap log.

---

## Layers

1. **Network** — TLS via Render/Railway-issued cert. Cloudflare planned in front of Railway for static-routing redundancy.
2. **Application auth** — Flask session (`username` field). Brute-force lockout: 5 failed attempts → 15 min cool-down per `web_app.py`.
3. **Application authorization** — `@login_required` + `@admin_required` decorators on every protected route. CSRF (`_csrf` form field; `X-CSRF-Token` header on JSON).
4. **Tenant filter (app)** — every tenant-owned query filters `organization_id = current_tenant_id()`. **Status: SQLite runtime does not actually do this — see Q-gate 1.1 gap.**
5. **Row Level Security (DB)** — PostgreSQL RLS, ENABLED + FORCED per `migrations/002` + `migrations/003`. Not yet applied (Postgres not provisioned).
6. **Audit log** — `audit_log` table + `logging_config/structured_logger.py` (JSON `audit.log` / `security.log` / `app.log` / `ai.log` / `queue.log`).
7. **Payment webhook integrity** — Paystack signature verification on `/paystack/webhook`.

## Roles (target)

`super_admin`, `platform_admin`, `sales_manager`, `engineer`, `proposal_officer`, `support_officer`, `installer_user`, `consultant_user`, `supplier_user`, `customer`. Currently the runtime only distinguishes `is_admin` boolean. Role-level enforcement is a future task.

## Secrets

- All secrets in GitHub Actions Secrets + Render env vars. None in repo.
- Q-gate 0.1 — admin password for the campaign portal was previously committed in `campaign_api.py` (default) and `.github/workflows/test-browser-flow.yml` (literal). Both removed in working tree but not yet committed + history-purged. Browser test workflow now reads from `CAMPAIGN_TEST_EMAIL` / `CAMPAIGN_TEST_PASSWORD` Secrets.

## Known gaps (Q-gate 2026-06-06)

| ID | Gap | Status |
|---|---|---|
| 0.1 | Plaintext admin creds + git history | user-deferred this session |
| 0.2 | `campaign_api.py` startup secrets default | file deleted in working tree; commit pending |
| 0.3 | `/entities` + `/state` no auth | file deleted in working tree; commit pending |
| 1.1 | Runtime on SQLite, RLS dormant | blocked on Postgres URL |
| 1.2 | Per-tx tenant context never set | blocked on 1.1 |
| 1.3 | RLS not FORCED | **closed (migration 003)** |
| 1.4 | `assessment_requests` cross-tenant PII | **closed (migration 003)** |
| 1.5 | `installers` cross-tenant PII | **closed (migration 003)** |
| 1.6 | `uploaded_files` public writable | **closed (migration 003)** |
| 1.7 | `users` self-update privilege escalation | column-grant scaffold in 003; SECURITY DEFINER admin fn TBD |
| 1.8 | `audit_log` WITH CHECK (TRUE) | **closed (migration 003)** |
| 1.9–1.15 | Schema hardening (FKs, NOT NULL, CHECKs, indexes) | **closed (migration 004)** |
| 2.1 | Stateless 30-day tokens; no revocation | blocked on `web_app.py` edit consent |
| 2.2 | `revoke-all-sessions` lies | blocked on `web_app.py` edit consent |
| 2.3 | No object-level auth on campaign writes | moot if portal deleted |
| 3.3–3.7 | Test coverage matrix | multi-session work |
| 6.1 | Audit log writes missing | partial — campaign deletion removes some |

## Threat model summary

- **External attacker:** mostly hampered by TLS + CSRF + lockout. Hidden routes are backend-protected. Biggest live risk = the still-deployed `campaign_api.py` (until teardown commit lands).
- **Authenticated tenant:** can currently see cross-tenant data in SQLite runtime because there's no tenant filter at all. RLS migration is the fix.
- **Authenticated user, same tenant:** can in theory self-elevate `is_admin` until the Postgres column-grant lands. Currently mitigated by application code only.
- **Insider with repo access:** previously could read prod admin creds from `campaign_api.py` defaults. Removed in working tree; awaiting commit + history purge.
