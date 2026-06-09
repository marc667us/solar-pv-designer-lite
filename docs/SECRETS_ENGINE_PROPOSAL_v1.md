# Dynamic Secrets Engine — Proposal v1

**Author:** Claude Code (Principal Solution Architect / Principal Security Engineer)
**Date:** 2026-06-09
**Scope:** SolarPro Global (solar-pv-designer-lite). Template for IPPSP, IPPTH, MEP, Claude App Factory after solar validates.
**For review by:** Codex CLI (reviewer) + Claude Code `/security-review` + `/code-review` (supervisor passes)
**Owner requirements (verbatim):** secret engine · credentials on demand · dynamic secret management · no permanent secret credential · scope credentials by time · audit trail

---

## 1. Problem statement

The current secrets surface is **static, broad, and unaudited**:

- **`.env` files on disk** carry long-lived API keys (PAYSTACK_SECRET_KEY, OLLAMA_URL, SOLARPRO_*_PASSWORD, SMTP_*). Anyone with file-system access reads them in plaintext. Lifetime = forever.
- **GitHub Secrets** carry the same keys plus deploy-side (RENDER_API_KEY, BREVO_API_KEY, RESEND_API_KEY, SMTP_*). Lifetime = until manual rotation. Read by every CI run with no scoping per workflow step.
- **Render env vars** mirror the GitHub Secrets in production. Lifetime = forever.
- **`users.resend_api_key`** column in the app DB. Per-user override, plaintext at rest, no rotation cadence.
- **No central audit log of secret reads.** Brevo API key is referenced in api_manager.py, but we have no record of *when* it was read, *by which process*, with what request_id.

Threat model gaps this leaves open:
- **Disk exfiltration** of `.env` → permanent compromise of every key in it.
- **CI log leak** → any workflow that echoes env grants permanent compromise.
- **Insider read** of GitHub Secrets / Render env → undetectable; no audit trail.
- **Stolen `users.resend_api_key`** value → undetectable; runs until rotated by hand.
- **Credentialed session theft** → token valid until SOLARPRO_*_PASSWORD is rotated.

The owner's six requirements all attack one root cause: **secrets exist in a static form for too long, are read without accountability, and have no time-bound scope.**

---

## 2. Architecture — Vault OSS (HashiCorp), self-hosted in Docker

### 2.1 Why Vault OSS specifically

- **Hits every owner requirement out of the box:**
  - Secret engine: built-in KV v2 + dynamic-secret engines (database, AWS, transit, etc.)
  - Credentials on demand: `vault read database/creds/<role>` issues a fresh credential per call
  - Dynamic secret management: TTL-bound, auto-revoked on expiry
  - No permanent secret credential: at-rest secrets are sealed by Vault's master key (Shamir-shared); root token can be revoked after init
  - Scope credentials by time: every issuance carries a TTL; default 1h, max enforceable per role
  - Audit trail: audit devices write every API call (read/write/auth) to a file or syslog with `client_token` + `display_name` + `request.path`
- **Free-tier compatible (FOSS Stack Rule):** Vault OSS is MPL-2.0 / BUSL pre-2024 license, fully self-hostable. Zero cost beyond compute.
- **Mature client libraries:** `hvac` (official Python) — pip-installable.
- **Same skeleton used in production by Anthropic-class orgs:** auditable, well-documented threat model.

Alternative considered + rejected:
- **OpenBao** (Vault fork after HashiCorp's BSL relicense): functionally equivalent now, but smaller community + thinner Python client maturity. *Defer to v2.*
- **Infisical / Doppler / 1Password Connect:** managed, free-tier exists but caps at 5 secrets / 1 project. Violates "free-tier first" once we add IPPSP+IPPTH+MEP. *Reject.*
- **Custom Python broker over `.env`:** doesn't satisfy "no permanent secret credential" — `.env` is still permanent on disk. *Reject as primary; consider as Phase 0 transitional shim only.*

### 2.2 Deployment topology

```
┌─────────────────────────────────────────────────────────────┐
│  Owner laptop / development                                 │
│   - Docker Desktop                                          │
│   - vault:latest container, port 8200                       │
│   - storage backend: file (encrypted volume)                │
│   - audit device: file -> ./vault-audit/audit.log           │
│   - exposed to LAN via Cloudflare Tunnel for shared dev     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ (Vault HTTP API + AppRole auth)
┌─────────────────────────────────────────────────────────────┐
│  SolarPro Flask app (web_app.py)                            │
│   - api_manager.py imports vault client                     │
│   - on startup: AppRole login -> short-lived token          │
│   - on secret read: kv.v2.read_secret_version(path=...)     │
│   - on dynamic creds: secrets/database/creds/solarpro-app   │
│   - falls back to .env ONLY in dev mode if VAULT_ADDR unset │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ (audit log)
┌─────────────────────────────────────────────────────────────┐
│  Audit consumer                                             │
│   - tail /vault/audit/audit.log -> structured JSON          │
│   - shipped to existing solar audit_log table via cron      │
│   - retention: 90 days local file + permanent DB row        │
└─────────────────────────────────────────────────────────────┘
```

**Production option (later):** same Vault container on the user's Hetzner / Cloudflare-fronted VPS (~€3.79/mo — rejected by zero-cost policy). Alternative: Render free service with attached disk for Vault storage. Cost: $0, but Render free spins down after inactivity — only acceptable for low-traffic dev/beta.

### 2.3 Authentication model

- App auths to Vault using **AppRole** — `role_id` + `secret_id`. Both stored as **bootstrap-only** values in `.env` (Phase 1). Phase 2: rotate `secret_id` hourly via a sidecar cron. Phase 3: replace `.env` bootstrap with platform-bound auth (e.g. JWT issued by Render OIDC) — fully eliminates the file.
- App-issued tokens have **default 1h TTL, max 24h**. Sessions are stateless per request: re-login on expiry.
- Audit log captures every login, every read, every renewal.

### 2.4 Secret-engine layout in Vault

```
kv/data/solarpro/payment/paystack         { secret, public }
kv/data/solarpro/payment/stripe           { secret, webhook_secret }
kv/data/solarpro/email/brevo              { api_key }
kv/data/solarpro/email/resend             { api_key }
kv/data/solarpro/email/smtp               { host, port, user, pass, from, tls }
kv/data/solarpro/ai/openrouter            { api_key }
kv/data/solarpro/ai/ollama                { url, model }
kv/data/solarpro/seed/admin               { password }
kv/data/solarpro/seed/marc667us           { password }
kv/data/solarpro/flask                    { secret_key }
database/config/solarpro                  { connection_url, allowed_roles }
database/roles/solarpro-app               { creation_statements, default_ttl: 1h, max_ttl: 24h }
sys/audit/file                            { path: /vault/audit/audit.log }
```

The `database/roles/solarpro-app` role issues a **fresh DB user per app boot**, scoped 1h, revoked on Vault's clock. This is the "no permanent credential" win — the Postgres user that exists for an hour, then is dropped from the DB.

### 2.5 Audit trail schema

Vault's file audit device writes JSON-Lines. A new app table mirrors:

```sql
CREATE TABLE secret_audit (
    id              INTEGER PRIMARY KEY,
    occurred_at     TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    auth_method     TEXT NOT NULL,    -- "approle" | "token"
    accessor        TEXT NOT NULL,    -- Vault accessor (short ID, safe to log)
    display_name    TEXT,             -- "approle-solarpro-app"
    operation       TEXT NOT NULL,    -- "read" | "write" | "delete" | "list"
    path            TEXT NOT NULL,    -- "kv/data/solarpro/email/brevo"
    client_ip       TEXT,
    error           TEXT
);
CREATE INDEX idx_secret_audit_path     ON secret_audit(path);
CREATE INDEX idx_secret_audit_occurred ON secret_audit(occurred_at DESC);
```

Every read is queryable; rotation cadences and anomaly detection (e.g. burst-read alerts) fall out of this.

---

## 3. Phased rollout — bound to the "don't break things" contract

### Phase 0 (this session, ~30 min) — transitional broker shim
- New module `secrets_broker.py`. Single function `get(path, ttl_seconds=300)` that:
  - Reads from `os.environ` (existing source of truth).
  - Returns the value with a wrapping `SecretView` object that records access + TTL into `secret_audit`.
  - Raises `SecretExpired` if a held view is dereferenced after `expires_at`.
- Adds `secret_audit` table to `init_db()`.
- **No callers changed yet.** This is plumbing only. Hits 3/6 of the owner spec (on-demand, scope-by-time, audit). Acceptable as an interim, NOT as the final answer.
- Validates: the broker compiles, audit rows appear, no regression in the 31 passing tests.

### Phase 1 (next session, ~3h) — Vault stand-up
- `docker compose up -d vault` (new `docker-compose.vault.yml` in the solar repo).
- `vault operator init` + `vault operator unseal` × 3 — owner stores unseal keys offline.
- Write secrets into kv/data/solarpro/* paths.
- Update `secrets_broker.py` to read from Vault first (hvac), `.env` fallback only when `VAULT_ADDR` is unset.
- Update **only**: `api_manager.py` (3 reads — Brevo, Resend, SMTP), `web_app.py:559` (seed passwords), `web_app.py:5876` (Paystack secret). All other callers still use `.env` until Phase 2.
- Validates: solar app boots, sends an email, accepts a payment in test mode, all 31 tests still pass. **Live tunnel restart required.**

### Phase 2 (~2h) — finish solar
- Move remaining callers (SECRET_KEY, OLLAMA_*, OpenRouter, Render API, etc.) to broker.
- Delete the env vars from `.env` *after* confirming Vault has them and the app boots without them.
- Add the cron sidecar that rotates `secret_id` hourly.

### Phase 3 (~1d) — dynamic database creds
- Provision Postgres (Render free Postgres or local), wire Vault's `database` engine.
- Cut `web_app.py:get_db()` to fetch a Vault-issued credential each request.
- This is where "no permanent credential" finally becomes literally true.

### Phase 4 (~1d) — templates for other apps
- `docs/SECRETS_ENGINE_INTEGRATION.md` step-by-step for IPPSP/IPPTH/MEP/Claude App Factory.
- `_ai-coworkers-template/` augmented with a `secrets_broker.py` stub.

---

## 4. Cost analysis (FOSS-stack rule)

| Component | License | Cost |
|---|---|---|
| Vault OSS | MPL 2.0 | $0 |
| Docker Desktop | personal use | $0 |
| `hvac` Python client | Apache 2.0 | $0 |
| Cloudflare Tunnel (for shared dev) | free tier | $0 |
| Render free service (Vault prod, deferred) | free tier | $0 |
| **Total monthly** | | **$0** |

No credit card required at any phase. Satisfies `feedback_zero_cost_apis` memory.

---

## 5. Risks + mitigations

| Risk | Probability | Mitigation |
|---|---|---|
| Vault unseal key loss | low, high impact | 3-of-5 Shamir split; owner stores in offline password manager + safe |
| AppRole `secret_id` leak | medium | hourly rotation cron + audit-log alert on anomalous reads |
| App can't reach Vault (network) | medium | broker falls back to last-cached value if `cached_at < TTL`, otherwise hard-fail rather than silently use stale |
| Render free-tier spin-down | high | run Vault locally; only the SolarPro app runs on Render. Vault Tunnel exposes via Cloudflare so prod can reach it. Acceptable for dev/beta; prod migration to paid VPS deferred per zero-cost policy |
| Test suite needs Vault to run | high | tests get a `FakeVault` injected via existing `monkeypatch_session` fixture in `tests/test_app.py` — never hits real Vault, never reads `.env` for seed creds (already fixed in this session) |
| Breaking the running tunnel app | high (per contract) | every phase is gated by `pytest tests/` 31/0/141 AND a smoke restart of the tunnel; rollback = `secrets_broker.py` reverts to `os.environ` |

---

## 6. Open questions for reviewer / supervisor

1. **Should the broker's last-cached fallback be enabled by default, or hard-fail on Vault outage?** Hard-fail is safer (auditable), cached is more available. Recommended: hard-fail in prod, cached in dev (flag in `VAULT_FAIL_OPEN`).
2. **Audit log retention — 90 days local, permanent in DB?** Or rotate the DB rows after 1 year? Compliance unclear at this stage.
3. **Should `users.resend_api_key` (per-user override) also move to Vault under `kv/data/solarpro/users/<user_id>/resend`?** This explodes the secret count but eliminates plaintext at rest in app DB. Probably worth it once Vault is in place.
4. **Render production:** is the zero-cost policy hard, or can we provision $5/mo Hetzner for Vault in Phase 3+? Hetzner gives us a stable static Vault. Owner decision.

---

## 7. Non-goals (explicitly out of scope)

- Hardware Security Module (HSM) — overkill for $0 budget and current user count.
- Vault Enterprise features (namespaces, replication, performance standby) — paid.
- Encrypting `.env` at rest with gpg as a temporary shim — adds friction without solving any of the six requirements.
- Migrating GitHub Secrets out of GitHub — they remain the bootstrap for Vault's AppRole `role_id`; not a real secret in the long run.

---

## 8. Definition of done (Phase 1 — what gets us to "shippable")

- [ ] `docker-compose.vault.yml` boots a sealed Vault on `:8200`.
- [ ] `vault operator unseal` runs cleanly with 3 of 5 keys; owner has all 5 stored offline.
- [ ] `secrets_broker.py` resolves `kv/data/solarpro/payment/paystack` via Vault when `VAULT_ADDR` is set, `.env` otherwise.
- [ ] `secret_audit` table populated by `secrets_broker.py` on every read.
- [ ] `pytest tests/` still **31 passed, 141 skipped, 0 failed**.
- [ ] Tunnel smoke: login, project create, calc, PDF download, email send all work (manual UI walkthrough, ≤5 min).
- [ ] `docs/SECRETS_ENGINE_OPERATIONS.md` covers: unseal, rotate AppRole, query audit log, backup unseal shares.
- [ ] Codex CLI review passes (`./scripts/quality-gate.sh`).
- [ ] `/security-review` skill: no critical findings.

---

**Status:** Draft v1. Awaiting reviewer (Codex) + supervisor (`/security-review` + `/code-review`) passes before any code lands.
