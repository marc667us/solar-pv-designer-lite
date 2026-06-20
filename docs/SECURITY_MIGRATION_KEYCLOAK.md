# SolarPro Security Migration — Keycloak Authentication & Authorization Plan

**Author:** Claude Code (Principal Solution Architect / Principal Security Engineer)
**Date:** 2026-06-19
**Scope:** SolarPro Global (`solarpro.aiappinvent.com`). Template for IPPSP, IPPTH, MEP, and other apps once SolarPro validates.
**Source brief (verbatim):** `C:\Users\USER\Documents\pvsolar1\kubernates\secmigrate.txt` (18 sections + 11-section RBAC supplement + recommended 30–50 page expansion topics).
**Reads alongside:**
- `docs/SECURITY_ARCHITECTURE.md` — current architecture + Q-gate gap log.
- `docs/SECRETS_ENGINE_PROPOSAL_v3.md` — Vault-based credential broker (Phase 0 of any auth migration).
- `docs/ARCHITECTURE_DECISIONS.md` — ADRs (the Keycloak adoption decision lands here).
- `docs/DATABASE_DESIGN.md` — tenant column model + RLS policies.
- `docs/IMPLEMENTATION_LOG.md` — append per-task entries while executing this plan.
- `CLAUDE.md` Marketplace section — current authn/authz surface that this plan replaces.

---

## 0. Document control + change log

| Version | Date | Author | Change |
|---|---|---|---|
| v1.0 | 2026-06-19 | Claude Code | Initial draft. Captures every section of `secmigrate.txt` verbatim plus the recommended 30–50 page expansion topics. No code shipped yet — implementation tracked under `docs/IMPLEMENTATION_LOG.md` once owner approves Phase 1. |

This plan is **a specification, not a deploy**. No production keys are touched, no live route is rewritten, no real user is migrated until the owner explicitly signs off Phase 1 (see §4 Phase Plan). Every section ends with an "Implementation note" and a clear hand-off for the next session.

---

## 1. Executive summary

SolarPro today manages identity in `web_app.py`: a single `users` table seeded from `SOLARPRO_ADMIN_PASSWORD` / `SOLARPRO_OWNER_PASSWORD` envs, Flask session cookies, `@login_required` / `@admin_required` / `@supplier_required` / `@procurement_role_required` decorators, a stateless 30-day session token with no real revocation, and an `is_admin` boolean as the only role distinction. The marketplace work in session 2026-06-19 (this session) introduced supplier and procurement-specialist roles, but they are still booleans stored on `users.role`, not centrally managed.

This plan migrates SolarPro to **Keycloak** as the single OIDC identity provider for every human user, every supplier, every engineer, every electrician, every marketplace admin, every internal AI agent, and every backend job. After the migration:

- SolarPro never sees a password. Keycloak owns hashing, rotation, MFA, brute-force lockout, password reset, and account recovery.
- Every protected route validates a Keycloak-issued JWT and checks role + tenant + permission scope.
- Multi-tenant isolation is enforced at three layers: Keycloak group/attribute, application-level `tenant_id` filter, and PostgreSQL RLS policy.
- The 13-role RBAC model from the brief is the authoritative permission scheme; the boolean `is_admin` and ad-hoc decorators disappear.
- AI agents and backend jobs use Keycloak service accounts with scoped client credentials, not shared API keys.
- Audit logging is unified across Keycloak admin events and SolarPro's `audit_log` table.
- Zero licensing cost (Keycloak is Apache 2.0).

**Non-goals.** This document does NOT switch the live deployment over to Keycloak in one shot — that is reckless. Instead it lays out a phased migration with explicit acceptance criteria per phase, a parallel-run window where the old Flask session and the new Keycloak JWT both work, and a deprecation gate before the old code is removed.

---

## 2. Target architecture

### 2.1 High-level flow (per brief §1, expanded)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Any SolarPro user — Engineer · Electrician · Supplier · Procurement │
│           Specialist · Marketplace Admin · Customer · AI Agent       │
└──────────────────────────────────────────────────────────────────────┘
                                  ↓
                       SolarPro Frontend (Flask + Jinja today;
                                 Next.js planned)
                                  ↓
                       Redirect to Keycloak login page
                                  ↓
                       Keycloak validates credentials + MFA
                                  ↓
                       Issues OIDC tokens: access (5–15 min)
                                          refresh (30–120 min)
                                          ID token (display only)
                                  ↓
                       SolarPro Backend (Flask routes)
                                  ↓
                       ────────────────────────────────────
                       │ JWT middleware on every route:    │
                       │   1. signature verify (Keycloak  │
                       │      JWKS, cached + rotated)     │
                       │   2. expiry                       │
                       │   3. issuer                       │
                       │   4. audience                     │
                       │   5. user role                    │
                       │   6. tenant_id match              │
                       │   7. permission scope             │
                       ────────────────────────────────────
                                  ↓
                       SolarPro Services
                       (PV design · BOQ/BOM · Marketplace ·
                        Procurement Centre · RFQ · Reports ·
                        Admin)
                                  ↓
                       PostgreSQL (RLS-FORCED, tenant context
                       SET per transaction, every read filtered)
                                  ↓
                       Audit log (Keycloak admin events +
                       SolarPro audit_log table + Loki)
```

### 2.2 Why Keycloak (per brief §1)

The brief opens with "Keycloak supports OAuth 2.0, OpenID Connect, and SAML, and is designed to secure applications and services through standard identity protocols." That is the decision. Concretely:

- **Standards.** OIDC is the universal contract — every frontend (Flask Jinja today, Next.js tomorrow, mobile React Native eventually) and every backend can validate the same JWT shape.
- **Cost.** Apache 2.0 license. Free to run on the existing infrastructure. Matches the FOSS Stack Rule in `CLAUDE.md`.
- **Maturity.** Production-grade since 2014. Battle-tested at multi-million-user scale (the Red Hat SSO product is the same codebase).
- **Self-hostable.** No vendor lock-in. Docker for dev, Kubernetes for prod, Postgres-backed.
- **MFA, passkeys, brute-force lockout, password reset.** Out of the box. We do not write any of this in `web_app.py`.
- **Fine-grained authorization.** Keycloak Authorization Services give us policy-based access control beyond plain RBAC when we need ABAC (resource ownership, time-windowed permission, IP-restricted admin actions).
- **Service account model.** Every AI agent gets its own client credentials grant — no shared API keys, every action attributable.

### 2.3 What replaces what in SolarPro today

| Today (`web_app.py`) | After Keycloak |
|---|---|
| `users.password_hash` (bcrypt) | Keycloak `credentials` (Argon2id by default in Keycloak 26). SolarPro `users.password_hash` deleted. |
| `users.is_admin` boolean | Keycloak realm role `platform_super_admin` (or `tenant_admin`). |
| `users.role` free-text (`supplier_admin`, `procurement_specialist`, …) | Keycloak realm roles in the 13-role list (§7.2). |
| `session["user_id"]` Flask cookie | Keycloak access token in `Authorization: Bearer <jwt>` header; refresh token in HttpOnly secure cookie. |
| `@login_required` decorator | `@require_jwt()` middleware that calls Keycloak JWKS verifier. |
| `@admin_required` | `@require_role("platform_super_admin")` or `@require_role("tenant_admin")` depending on scope. |
| `@supplier_required` | `@require_role("supplier_admin")` + `@require_tenant_match("supplier_id")`. |
| `@procurement_role_required` | `@require_role("procurement_specialist")` (with `tenant_admin` fallback). |
| Brute-force lockout per `web_app.py` | Keycloak realm "Brute Force Detection" policy. |
| Password reset via email + custom token | Keycloak "Forgot Password" flow. |
| 30-day session token, no revocation | Short-lived access token (5–15 min) + refresh token + Keycloak session-version invalidation. |
| `SOLARPRO_ADMIN_PASSWORD` env-seed | Bootstrap admin in Keycloak's master realm only; created once during install. |
| No MFA | Keycloak OTP / WebAuthn (passkey) per-role policy. |
| No audit log of permission denials | Keycloak admin events + SolarPro `audit_log` writer on every denial. |

### 2.4 Implementation note

This is the **target picture**. We get there over 8 phases (§4). The phase 0 inventory step is a hard prerequisite — until we know every place `@login_required` / `session["user_id"]` / `is_admin` is used, we cannot rewrite them safely.

---

## 3. Current state vs. target state gap analysis

This section is the single source of truth for "what needs to change". The remainder of the plan references back to this gap list.

### 3.1 Authentication gaps

| Gap | Today | After Keycloak | Severity |
|---|---|---|---|
| Password hashing controlled by SolarPro | bcrypt in `_seed_pwd()` and supplier registration | Keycloak (Argon2id, configurable cost) | HIGH — password rotation requires code rebuild |
| Single seed admin per env var | `SOLARPRO_ADMIN_PASSWORD` rewrites the hash on every cold start | Keycloak admin user, set once during realm import | MEDIUM |
| Stateless 30-day session | Flask `session` cookie, signed with `SECRET_KEY` | Short-lived JWT + refresh token + Keycloak session-version | HIGH — revocation today is a lie (Q-gate 2.1, 2.2) |
| No MFA | None | OTP (TOTP) + WebAuthn passkey, per-role policy | HIGH for admin / finance / marketplace admin |
| Password reset | Custom token email, in-app | Keycloak "Forgot Password" with email verification | LOW (works today, but moves to Keycloak for consistency) |
| Brute-force lockout | `web_app.py`: 5 failed → 15 min cool-down (per `SECURITY_ARCHITECTURE.md`) | Keycloak Brute Force Detection (configurable, per-realm) | MEDIUM |
| Account recovery | Email-only | Email + admin override + WebAuthn fallback | MEDIUM |

### 3.2 Authorization gaps

| Gap | Today | After Keycloak | Severity |
|---|---|---|---|
| Role model | `is_admin` boolean + `users.role` free-text | 13 realm roles (§7.2) | HIGH — role-explosion is unmanageable today |
| Permission granularity | Decorator-per-route | 27 permission scopes (§7.4) checked at middleware | HIGH |
| Tenant isolation in application | No filter at all on SQLite runtime (Q-gate 1.1, 1.2) | `tenant_id` claim on JWT + `WHERE tenant_id = :ctx_tenant` everywhere | CRITICAL |
| Tenant isolation in database | RLS migration written but not applied (blocked on Postgres) | RLS FORCED + per-tx `SET app.current_tenant = :tid` | CRITICAL |
| Fine-grained ABAC | None | Keycloak Authorization Services for ownership / time / IP policies | MEDIUM |
| Hidden-route protection | Backend `@admin_required` only | Middleware verifies role *and* tenant *and* scope, audited on denial | MEDIUM |

### 3.3 Operational gaps

| Gap | Today | After Keycloak | Severity |
|---|---|---|---|
| Audit log of login events | App log only, partial | Keycloak admin events + SolarPro `audit_log` table + Loki sink | HIGH |
| Audit log of permission denials | None systematic (Q-gate 6.1) | Middleware writes on every 401/403 | HIGH |
| Service accounts for AI agents | Shared OpenRouter API key | Per-agent Keycloak client credentials with minimum scope | HIGH (shared key = attribution gap) |
| Backend job auth | None — jobs run unauthenticated in-process | Service account JWTs introspected on every webhook | MEDIUM |
| SSO across apps | None | Keycloak realm shared across SolarPro / IPPSP / IPPTH / MEP / Factory | LOW (forward-looking) |

### 3.4 Implementation note

The gaps marked **CRITICAL** must be closed before any external beta scale-up. Gap 1.1 / 1.2 (tenant filter on runtime) was already blocking the Postgres cutover in session 2026-06-13; Keycloak addresses it by putting `tenant_id` on every JWT so the backend has a trustworthy source of truth per request. Gap 3.2 row 4 (RLS migration applied) is unblocked the moment Phase 4 below runs.

---

## 4. Phase plan + milestones

Eight phases, **not** to be telescoped. Each ends with a verification step before the next begins. Numbers in brackets are calendar-day estimates assuming Claude Code + owner availability.

| Phase | Goal | Acceptance | Est. (days) |
|---|---|---|---|
| **0** | Inventory + ADR | Every `@login_required`, `@admin_required`, `session["user_id"]`, `users.role`, `is_admin` callsite catalogued in `docs/auth_inventory.csv`. ADR-0007 "Adopt Keycloak as identity provider" approved by owner. | 1 |
| **1** | Local Keycloak + realm bootstrap | Keycloak runs locally via Docker Compose. `solarpro` realm imports clean from `docs/keycloak/realm-export.json`. Test users for each of the 13 roles created. | 1 |
| **2** | Backend JWT middleware (parallel-run) | `app/security/keycloak_middleware.py` validates JWTs against local Keycloak. `@require_jwt`, `@require_role`, `@require_tenant_match`, `@require_scope` decorators implemented. Old `@login_required` still works in parallel. | 2 |
| **3** | Service accounts for AI agents | Each AI agent client created in realm. Agents fetch tokens via client credentials grant. Old shared OpenRouter key removed. | 1 |
| **4** | Tenant filter + RLS activation | `tenant_id` from JWT claim drives every query via `current_tenant_id()`. RLS migration applied to Postgres. Q-gate 1.1/1.2/3.2 closed. | 2 |
| **5** | Frontend OIDC integration (Flask Jinja) | `/login` redirects to Keycloak; callback handler stores tokens; `base.html` shows logged-in user name from ID token. Old Flask `/login` form kept available for marc667us emergency only. | 2 |
| **6** | MFA + audit unification | OTP enforced for `platform_super_admin`, `tenant_admin`, `marketplace_admin`, `finance_officer`. Audit writer hooks Keycloak admin events into `audit_log` table. | 1 |
| **7** | User migration | All 200+ live users exported, mapped to roles + tenants, imported into Keycloak with `requiredActions=["UPDATE_PASSWORD"]`. Old `users.password_hash` column dropped. Old auth code removed. Deploy to production. | 3 |

**Total estimated effort: 13 days** of focused engineering, plus owner sign-off windows at the end of phase 0, 4, and 7.

### 4.1 Phase 0 — Inventory + ADR (HARD prerequisite)

**Deliverables:**

1. `docs/auth_inventory.csv` — every callsite of: `@login_required`, `@admin_required`, `@supplier_required`, `@procurement_role_required`, `session["user_id"]`, `current_user()`, `is_admin`, `users.role`, `_seed_pwd`, `SOLARPRO_*_PASSWORD`. One row per callsite with file + line + replacement plan.
2. `docs/ARCHITECTURE_DECISIONS.md` entry: **ADR-0007 — Adopt Keycloak as identity provider.**
3. `docs/keycloak/realm-design.md` — draft of the realm export (clients, roles, groups, attributes).
4. Owner sign-off recorded in `docs/IMPLEMENTATION_LOG.md`.

**Why this is hard prerequisite:** `web_app.py` is ~17 000 lines. Without the inventory we will miss callsites and the migration will leak unauthenticated routes. The inventory is the working set for Phases 2, 4, 5, 7.

**Estimate:** half a day of `grep` + half a day to write the ADR + 1 review pass.

### 4.2 Phase 1 — Local Keycloak + realm bootstrap

**Deliverables:**

- `docker-compose.keycloak.yml` at repo root — Keycloak + Postgres for dev.
- `docs/keycloak/realm-export.json` — full realm config (clients, roles, groups, password policy, OTP policy, brute-force settings).
- `scripts/keycloak/bootstrap.sh` — bring up Keycloak, import realm, create test users.
- `scripts/keycloak/teardown.sh` — clean shutdown + volume wipe.

**Acceptance:** running `bash scripts/keycloak/bootstrap.sh` produces a working Keycloak at `http://localhost:8080`, the `solarpro` realm visible, and `curl` against the token endpoint returns a valid JWT for each test user.

### 4.3 Phase 2 — Backend JWT middleware (parallel-run)

**Deliverables:**

- `app/security/keycloak_middleware.py` — JWT verifier (JWKS cached + rotated; `iss`, `aud`, `exp`, `nbf` checks).
- `app/security/decorators.py` — `@require_jwt`, `@require_role("name")`, `@require_any_role([...])`, `@require_tenant_match("path_param_name")`, `@require_scope("verb:resource")`.
- One pilot route migrated: `GET /admin/marketplace` (low blast radius; admin-only).
- Old `@admin_required` still wraps the route; new `@require_role` runs first and short-circuits on success. This is the **parallel-run window** — both auth stacks accept the user.

**Acceptance:** in `docker-compose.keycloak.yml` mode, the pilot route returns 200 when called with a `marketplace_admin` JWT, 403 with `supplier_admin`, 401 with no token. With the Flask session cookie alone, the route also returns 200 (old behaviour preserved).

### 4.4 Phase 3 — Service accounts for AI agents

**Deliverables:**

- 5 client credentials clients in the realm (per brief §14): `solarpro-catalogue-agent`, `solarpro-tender-agent`, `solarpro-report-agent`, `solarpro-email-agent`, `solarpro-payment-agent`.
- Each client has only the scopes it actually uses (§7.4 + §12).
- `app/security/service_account_client.py` — token-fetch + cache helper.
- `engine/agents/marketplace/_llm.py` and similar agent loaders rewritten to fetch a service-account JWT and pass it on internal API calls.
- Old shared API key for inter-service auth removed.

**Acceptance:** agent → backend call without a valid service-account JWT returns 401. With a valid JWT, audit log shows `agent_id` of the service account, not a human user id.

### 4.5 Phase 4 — Tenant filter + RLS activation

**Deliverables:**

- `app/security/tenant_context.py` — extracts `tenant_id` from JWT, sets `app.current_tenant` and `app.current_user` Postgres GUCs for the duration of each request.
- Every tenant-owned query in `web_app.py` rewritten to drop the historical `_current_user_id()` filter and rely on RLS (the application code is still defence in depth; the SQL filter remains).
- RLS migration `migrations/003_rls_tenant.sql` applied to the live Postgres.
- Tests: cross-tenant access denied at app layer AND DB layer.

**Acceptance:** the cross-tenant test in `tests/security/test_tenant_isolation.py` passes. Q-gate 1.1, 1.2, 3.2 closed.

### 4.6 Phase 5 — Frontend OIDC integration

**Deliverables:**

- `app/auth/oidc_routes.py` — `/auth/login` (redirect to Keycloak), `/auth/callback` (exchange code → tokens, set HttpOnly secure cookie with refresh token, ID token claims into Flask `session`), `/auth/logout` (Keycloak end-session + local cookie wipe).
- `base.html` updates to read username from JWT's `preferred_username` claim.
- `templates/login.html` becomes a redirect page; old form kept behind `?legacy=1` query string for the marc667us emergency channel.
- `engine/agents/*` and webhook handlers updated to honour the `Authorization` header.

**Acceptance:** click "Login" → Keycloak page → enter creds → land back on `/dashboard` with the same user context as before.

### 4.7 Phase 6 — MFA + audit unification

**Deliverables:**

- Keycloak realm OTP policy: required for `platform_super_admin`, `tenant_admin`, `marketplace_admin`, `finance_officer`. Optional but recommended for `solar_engineer`, `senior_engineer`, `procurement_specialist`.
- Keycloak event listener configured to POST admin events to a SolarPro webhook (`/api/keycloak/events`); SolarPro writes them to `audit_log`.
- SolarPro middleware writes a denial event to `audit_log` on every 401/403.

**Acceptance:** an `marketplace_admin` user attempting to log in without setting up OTP is forced through the OTP-setup wizard. Failed login by any user creates a row in `audit_log` with `action='LOGIN_FAILED'`.

### 4.8 Phase 7 — User migration + cutover

**Deliverables:**

- `scripts/migrate_users_to_keycloak.py` — exports `users` table, builds Keycloak partial-import JSON with `requiredActions=["UPDATE_PASSWORD"]`, calls Keycloak admin REST API.
- Email broadcast to all 200+ users explaining the change + the password-reset link.
- `ALTER TABLE users DROP COLUMN password_hash`.
- Old `_seed_pwd`, `@login_required`, `@admin_required`, `@supplier_required`, `@procurement_role_required` deleted from `web_app.py`.
- Production deploy + smoke test.

**Acceptance:** every user can log in via Keycloak. Old `/login` form (without `?legacy=1`) redirects to Keycloak. Cross-tenant access still denied. 25/25 live smoke test passes (see `tmp/live_smoke_test_2026-06-19.py` for the pattern).

---

## 5. Keycloak deployment

### 5.1 Development environment (per brief §2 Phase 1 + §16)

Single-container Keycloak with embedded H2 — fine for local dev only.

```bash
docker run --rm -p 8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=StrongAdminPassword \
  -e KC_DB=dev-mem \
  quay.io/keycloak/keycloak:26.0 start-dev
```

For SolarPro dev we prefer `docker-compose.keycloak.yml` with Postgres so the realm survives container restarts:

```yaml
# docker-compose.keycloak.yml (committed to repo root in Phase 1)
version: "3.8"
services:
  keycloak-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: ${KC_DB_PASSWORD:-keycloak-dev}
    volumes:
      - keycloak-db-data:/var/lib/postgresql/data
    ports: ["5433:5432"]

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD:-StrongAdminPassword}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: ${KC_DB_PASSWORD:-keycloak-dev}
      KC_HTTP_ENABLED: "true"
      KC_HOSTNAME_STRICT: "false"
    command: ["start-dev", "--import-realm"]
    volumes:
      - ./docs/keycloak:/opt/keycloak/data/import
    ports: ["8080:8080"]
    depends_on: [keycloak-db]

volumes:
  keycloak-db-data:
```

### 5.2 Staging environment

Same compose layout but with:
- `KC_HOSTNAME=keycloak-staging.aiappinvent.com`
- `KC_PROXY=edge` (behind a Traefik / Nginx terminating TLS)
- A real Postgres instance (Neon free tier is fine — separate database from SolarPro).
- LE certificate for `keycloak-staging.aiappinvent.com`.
- Master-realm admin credentials moved out of compose env into a Docker secret.

### 5.3 Production environment — Render free path (ACTUAL, beta tier)

This is what landed 2026-06-20. The K8s spec in §5.4 stays as the
end-state target once paying users arrive. Until then, beta runs on
Render free to honour `[[feedback-zero-cost-apis]]`.

| Concern | Choice (beta) | End-state (post-revenue) |
|---|---|---|
| Container image | `quay.io/keycloak/keycloak:26.0` (pinned, quarkus-native `kc.sh build` at image-build time) | same |
| Hosting | Render free Web Service (Docker), region oregon | Render Starter $7/mo OR K8s (§5.4) |
| Database | **Schema cohabit** on `solarpro-postgres`: `keycloak` schema + dedicated `keycloak_app` role + `REVOKE ALL ON SCHEMA keycloak FROM PUBLIC` (migration 006) | Dedicated Postgres (Render Basic-256MB $6/mo OR Neon) |
| TLS | Render auto-issued Let's Encrypt at the LB | same |
| Hostname | `auth.aiappinvent.com` (Namecheap CNAME → `solarpro-keycloak.onrender.com`) | same |
| Sleep mitigation | `.github/workflows/keycloak-keepalive.yml` cron every 10 min | not needed on paid plans |
| Backup | `.github/workflows/keycloak-backup.yml` daily `pg_dump --schema=keycloak` to GH artifact, 30-day retention | + S3 / R2 offsite |
| Admin access | Restricted by per-role TOTP at KC level (no network-level isolation on Render free) | + Cloudflare Zero Trust on `auth.aiappinvent.com/admin` |
| Monitoring | KC `/metrics` on management port 9000 (internal-only); not yet scraped | Prometheus + Loki per K8s spec |
| Secrets | `KC_BOOTSTRAP_ADMIN_PASSWORD` + `KC_DB_PASSWORD` as Render env vars (set via `.github/workflows/deploy-keycloak.yml`); `KC_DB_PASSWORD` rotated per deploy run | Vault per `[[project-solar-pv-secrets-engine-proposal-v3]]` |
| HA | Single Render free instance (no replicas) | 2-replica K8s + JGroups |

**Render configuration quirks worth remembering:**

1. **Bind main listener to `$PORT`.** KC 26 splits HTTP into a main port
   (admin + realms) and a management port (health + metrics, default 9000).
   Render only routes external traffic to `$PORT` (10000 by default), so
   the Dockerfile MUST pass `--http-port=$PORT` to kc.sh start, otherwise
   Render auto-routes to whichever port replies and you end up serving
   `/metrics` externally and 404 on `/realms/*`. The shell-form CMD in
   `keycloak/render/Dockerfile` handles this.

2. **`healthCheckPath` must be a main-port endpoint.** `/health/ready` is
   on the management port and is unreachable through Render. The deploy
   workflow uses `/realms/master/.well-known/openid-configuration`
   (created by KC on first boot) so Render's verifier hits a real
   main-port endpoint.

3. **`KC_HOSTNAME` accepts a full URL in KC 26.** Set to
   `https://auth.aiappinvent.com` so the discovery doc returns HTTPS
   issuer URLs even though the container itself speaks HTTP (Render's
   LB terminates TLS). Use `KC_PROXY_HEADERS=xforwarded` (not the
   legacy `KC_PROXY=edge`) to trust Render's `X-Forwarded-Proto`.

4. **Render-managed Postgres rejects `ALTER DEFAULT PRIVILEGES FOR
   ROLE`** for any role other than the connected one or a superuser.
   Migration 006 sidesteps this — the `keycloak_app` role owns
   everything it creates via Liquibase on first boot, so creator-owns
   semantics make explicit default-priv grants redundant.

5. **psql `:'var'` substitution does NOT work inside dollar-quoted
   PL/pgSQL blocks.** Migration 006 uses a `__KC_DB_PASSWORD__`
   placeholder and the deploy workflow's "Apply migration 006" step
   preprocesses it via Python before piping to psql.

6. **Render API: `PUT /env-vars` race with `POST /deploys`.** Render
   may queue an env-triggered deploy before the explicit one lands,
   leaving an `update_failed` entry adjacent to the new build. Symptom:
   the "live" deploy ran with old env vars. Fix: re-trigger the
   workflow; eventually a clean deploy wins.

**Files involved in the Render-free deployment:**

```
keycloak/render/
  Dockerfile               # KC 26 quarkus-native, $PORT-aware shell CMD
  build_realm_prod.py      # strips test users from realm-export.json
  realm-prod.json          # generated artefact, committed
  render.yaml              # Blueprint reference; deploy uses API directly
  deploy_render.py         # Render API create-or-update + PATCH service config

migrations/
  006_keycloak_schema.sql  # keycloak schema + keycloak_app role + REVOKE PUBLIC

.github/workflows/
  deploy-keycloak.yml          # orchestration; --field kc_hostname_url for custom domain
  attach-kc-custom-domain.yml  # adds auth.aiappinvent.com to Render service
  verify-kc-custom-domain.yml  # nudges Render to verify DNS + provision TLS
  keycloak-keepalive.yml       # 10-min cron to defeat Render free 15-min idle sleep
  keycloak-backup.yml          # daily pg_dump --schema=keycloak artifact
  cutover-to-keycloak.yml      # flips KEYCLOAK_ENABLED=true on solar app Render env
  rollback-from-keycloak.yml   # the reverse: KEYCLOAK_ENABLED unset
```

**Upgrade trigger (out of beta):** when paying users arrive OR
> 100 active users, split to dedicated Render Postgres + Render
Starter ($13/mo total) before traffic exposes blast-radius or
RAM-ceiling risk. K8s manifests in §5.4 are the longer-term target.

### 5.3 Legacy K8s production target (deferred until revenue)

Below: the original production target before the Render-free beta
deployment took precedence. K8s deploy is parked until traffic warrants
the operational investment.

| Concern | Choice |
|---|---|
| Container image | `quay.io/keycloak/keycloak:26.0` (pinned tag, not `latest`) |
| Database | Dedicated Postgres (Neon paid tier OR Render Postgres OR self-hosted) — **NOT shared with SolarPro app DB** |
| TLS | Let's Encrypt cert at the reverse proxy (Traefik or Nginx) |
| Hostname | `auth.aiappinvent.com` (single SSO host for all apps) |
| Admin access | Restricted by IP (Cloudflare Zero Trust or Render private network) |
| Backup | Daily Postgres dump + realm export to S3 / R2 |
| Monitoring | Prometheus metrics endpoint enabled (`KC_METRICS_ENABLED=true`); Loki for logs |
| Secrets | Realm export does NOT contain client secrets — those are injected via env at boot, sourced from Vault (per `docs/SECRETS_ENGINE_PROPOSAL_v3.md`) |
| HA | Single instance initially; add second instance when traffic > 100 RPS |

### 5.4 Kubernetes deployment (per recommended expansion topic)

Production target. Stanza outline:

```yaml
# k8s/keycloak/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: keycloak, namespace: identity }
spec:
  replicas: 2
  selector: { matchLabels: { app: keycloak } }
  template:
    metadata: { labels: { app: keycloak } }
    spec:
      containers:
      - name: keycloak
        image: quay.io/keycloak/keycloak:26.0
        args: ["start", "--optimized"]
        env:
        - name: KC_DB
          value: postgres
        - name: KC_DB_URL
          valueFrom: { secretKeyRef: { name: keycloak-db, key: url } }
        - name: KC_DB_USERNAME
          valueFrom: { secretKeyRef: { name: keycloak-db, key: username } }
        - name: KC_DB_PASSWORD
          valueFrom: { secretKeyRef: { name: keycloak-db, key: password } }
        - name: KC_HOSTNAME
          value: auth.aiappinvent.com
        - name: KC_PROXY
          value: edge
        - name: KC_METRICS_ENABLED
          value: "true"
        ports:
        - { name: http,    containerPort: 8080 }
        - { name: metrics, containerPort: 9000 }
        livenessProbe:
          httpGet: { path: /health/live,  port: 8080 }
        readinessProbe:
          httpGet: { path: /health/ready, port: 8080 }
        resources:
          requests: { cpu: 500m, memory: 1Gi }
          limits:   { cpu: 2,    memory: 2Gi }
---
apiVersion: v1
kind: Service
metadata: { name: keycloak, namespace: identity }
spec:
  selector: { app: keycloak }
  ports:
  - { name: http,    port: 80,   targetPort: 8080 }
  - { name: metrics, port: 9000, targetPort: 9000 }
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: keycloak
  namespace: identity
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-buffer-size: "32k"
spec:
  ingressClassName: nginx
  tls:
  - hosts: [auth.aiappinvent.com]
    secretName: auth-aiappinvent-tls
  rules:
  - host: auth.aiappinvent.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend: { service: { name: keycloak, port: { number: 80 } } }
```

Two-replica deployment is the minimum for production; Keycloak supports clustering via JGroups out of the box. The Postgres backend handles state coordination.

### 5.5 Backup and disaster recovery (per recommended expansion topic)

| Asset | Backup strategy | Restore RTO |
|---|---|---|
| Keycloak Postgres database | `pg_dump` nightly to S3-compatible storage; PITR via WAL archive | 1 hour |
| Realm export (clients, roles, groups) | Versioned `docs/keycloak/realm-export.json` in repo; weekly automated export to S3 | 15 min |
| Encryption keys (realm signing keys) | Backed up with the Postgres dump (Keycloak stores them in the DB) | included above |
| Master admin credentials | In Vault (`secret/keycloak/master-admin`); fallback in operator's password manager | manual |
| Service account client secrets | In Vault (`secret/keycloak/clients/<client_id>/secret`); rotated quarterly | manual |

**DR drill cadence:** quarterly. Restore Keycloak + realm into a sandbox namespace, verify all 5 service-account clients can fetch tokens, verify realm role list matches §7.2.

### 5.6 Implementation note

Phases 1–6 run against the Docker Compose stack. Phase 7 cuts production over to the Kubernetes deployment. The owner has to provision the `auth.aiappinvent.com` DNS + Render/K8s service before Phase 7 day 1.

---

## 6. SolarPro Realm design (per brief §3)

### 6.1 Realm: `solarpro`

| Setting | Value | Why |
|---|---|---|
| Realm name | `solarpro` | Brief §3. |
| Display name | `SolarPro Global` | shown on login page |
| Enabled | `true` | |
| User-managed access | `false` | we don't expose admin REST to end users |
| Login theme | `solarpro` (custom; clone of `keycloak.v2`) | brand consistency |
| Email theme | `solarpro` | brand consistency |
| Default locale | `en` | most users; `fr` and `pt` planned |
| Internationalisation | enabled | supports `en, fr, pt` |
| SSL required | `external` | TLS enforced for non-localhost traffic |
| Login with email | `true` | username field accepts email or username |
| Duplicate emails | `false` | one email = one user |
| Verify email | `true` | aligns with brief §12 password policy |
| Reset password | `true` | enabled out of the box |
| Remember me | `true` | tied to refresh token |
| Brute-force detection | `true` | replaces SolarPro's home-grown lockout |
| Max login failures | `5` | matches current SolarPro behaviour |
| Quick login check seconds | `1` | guard against credential-stuffing |
| Wait increment seconds | `60` | linear backoff up to max |
| Max wait seconds | `900` | matches 15-minute cooldown |

### 6.2 Clients (per brief §3 + §4)

Five clients in the realm, exactly as enumerated in the brief:

| Client ID | Access type | Standard flow | Service accounts | PKCE | Valid redirect URIs | Audience |
|---|---|---|---|---|---|---|
| `solarpro-web` | public | yes | no | required (S256) | `https://solarpro.aiappinvent.com/auth/callback`, `https://staging.solarpro.aiappinvent.com/auth/callback`, `http://localhost:5000/auth/callback` | `solarpro-api` |
| `solarpro-mobile` | public | yes | no | required (S256) | `solarpro://auth/callback` (deep link) | `solarpro-api` |
| `solarpro-api` | bearer-only | no | no | n/a | n/a | self |
| `solarpro-agent-service` | confidential | no | yes (client credentials) | n/a | n/a | `solarpro-api` |
| `solarpro-admin-console` | confidential | yes | no | required | `https://auth.aiappinvent.com/admin/*` | self |

**Per-client notes:**

- `solarpro-web` is the Flask Jinja frontend. Public client because the browser can't keep a secret; PKCE compensates.
- `solarpro-mobile` is the future React Native app. Same model as web.
- `solarpro-api` is the Flask backend's audience. It doesn't issue tokens — it accepts them. `bearer-only` access type is appropriate.
- `solarpro-agent-service` is the umbrella client for any backend job or AI agent that doesn't represent a human. Service-account-enabled, client credentials grant. **Per-agent fine-grained scopes** are layered via additional client roles assigned to the service account user (§12).
- `solarpro-admin-console` is the Keycloak admin console itself; only the platform team logs in here.

### 6.3 Realm-level settings (consolidated)

| Setting | Value |
|---|---|
| Access token lifespan | 10 min (brief §7 specifies 5–15; we pick the middle) |
| Access token lifespan for implicit flow | n/a (we don't use it) |
| Refresh token lifespan | 60 min (brief §7 specifies 30–120; centred) |
| SSO session idle | 30 min |
| SSO session max | 10 hours |
| Offline session idle | 30 days (for backend agents only — see §12) |
| Offline session max | 60 days |
| Login timeout | 30 min |
| Login action timeout | 5 min |
| OTP type | `totp` (default), `hotp` configurable |
| OTP algorithm | `HmacSHA1` (RFC 6238 standard) |
| OTP digits | 6 |
| OTP look-around window | 1 |
| OTP period | 30 sec |
| Password policy | `length(12)`, `digits(1)`, `upperCase(1)`, `lowerCase(1)`, `specialChars(1)`, `notUsername`, `notEmail`, `hashIterations(210000)`, `passwordHistory(5)`, `forceExpiredPasswordChange(90)` |

### 6.4 Implementation note

The full realm spec lands in `docs/keycloak/realm-export.json` during Phase 1. The file is treated as code — version-controlled, reviewed, re-imported via `kc.sh import` on each deploy.

---

## 7. RBAC design

### 7.1 Five main user groups (per brief supplement §1)

The brief is explicit: SolarPro supports five major user groups. They are the top-level mental model for everything in §7 and §13.

1. **Engineers** — design PV systems, prepare reports.
2. **Electricians / Installers** — execute installation work, upload site photos, update progress.
3. **Suppliers** — list products, manage prices and stock, respond to RFQs.
4. **Procurement Specialists** — request quotations, compare prices, prepare purchase recommendations.
5. **Marketplace Admin** — approve suppliers and products, manage catalogue quality.

The other users (Customer, Finance Officer, Catalogue Manager, Senior Engineer, Tenant Admin, Platform Super Admin, Support Agent) are real but smaller in volume; they are first-class Keycloak roles but do not warrant a separate "user group" header.

### 7.2 13 Keycloak realm roles (per brief supplement §10)

| Role | Main function | Typical headcount per tenant |
|---|---|---|
| `platform_super_admin` | Full platform access — only the platform team. | 2–3 globally |
| `marketplace_admin` | Approve suppliers, approve products, monitor marketplace quality. | 2–3 globally |
| `tenant_admin` | Manage one company / tenant — owners and CXOs of customer tenants. | 1–3 per tenant |
| `solar_engineer` | Designs solar systems, reviews technical outputs, prepares BOQ/BOM. | 1–10 per tenant |
| `senior_engineer` | Approves designs, validates calculations, reviews reports. | 1–2 per tenant |
| `electrician_installer` | Executes installation work, uploads site photos, updates progress. | 2–20 per tenant |
| `supplier_admin` | Manages supplier profile, products, prices, stock, warranty. | 1–3 per supplier |
| `supplier_user` | Updates assigned product and price records. | 1–5 per supplier |
| `procurement_specialist` | Requests quotations, compares prices, prepares recommendations. | 1–3 per tenant |
| `catalogue_manager` | Manages product catalogue and supplier catalogue. | 1–2 globally |
| `finance_officer` | Views pricing, invoices, payments, subscriptions. | 1 per tenant |
| `support_agent` | Helpdesk; read-only on most modules. | 2–5 globally |
| `customer` | View own designs, proposals, payments. | the bulk of users |

### 7.3 Role → SolarPro permission map (per brief §5)

| Role | SolarPro permission |
|---|---|
| `platform_super_admin` | Full platform access. |
| `tenant_admin` | Manage one company / tenant. |
| `supplier_admin` | Manage supplier company, products, prices. |
| `solar_engineer` | Design PV systems, prepare reports. |
| `estimator` *(alias of solar_engineer for BOQ-only)* | Prepare BOQ/BOM/pricing. |
| `electrician_installer` | View installation tasks and materials. |
| `product_catalogue_manager` *(alias of catalogue_manager)* | Update Product Catalogue. |
| `supplier_catalogue_manager` *(alias of catalogue_manager)* | Update Supplier Catalogue. |
| `sales_agent` | Manage leads and trials. |
| `finance_officer` | View invoices and payments. |
| `customer` | View own designs, proposals, payments. |

Implementation note: the brief mentions two roles (`estimator`, `product_catalogue_manager`, `supplier_catalogue_manager`, `sales_agent`) that overlap heavily with the 13-role list. Phase 0 of the ADR decides whether they become separate Keycloak roles or scoped aliases. The current recommendation is to keep them as **composite roles** in Keycloak — for example `estimator = solar_engineer + (boq:view, boq:create, boq:update)` — so the realm role count stays at 13 + a handful of composites.

### 7.4 Permission scopes (per brief supplement §8)

Backend authorization is keyed on these 27 scopes. Each Keycloak role exposes a set of scopes; the middleware checks `@require_scope("verb:resource")` per route.

| Resource | Scopes |
|---|---|
| **project** | `project:view`, `project:create`, `project:update`, `project:approve` |
| **design** | `design:view`, `design:create`, `design:update`, `design:approve` |
| **boq** | `boq:view`, `boq:create`, `boq:update`, `boq:approve` |
| **supplier** | `supplier:view`, `supplier:create`, `supplier:update`, `supplier:approve`, `supplier:suspend` |
| **product** | `product:view`, `product:create`, `product:update`, `product:approve`, `product:merge` |
| **price** | `price:view`, `price:update`, `price:approve` |
| **rfq** | `rfq:create`, `rfq:view`, `rfq:respond`, `rfq:compare` |
| **purchase** | `purchase:view`, `purchase:create`, `purchase:approve` |
| **installation** | `installation:view`, `installation:update`, `installation:commission` |
| **audit** | `audit:view` |
| **admin** | `admin:manage` |

Per-role scope assignment:

| Role | Scopes |
|---|---|
| `platform_super_admin` | every scope above + `admin:manage` |
| `marketplace_admin` | `supplier:view`, `supplier:approve`, `supplier:suspend`, `product:view`, `product:approve`, `product:merge`, `price:view`, `audit:view` |
| `tenant_admin` | every scope inside the tenant + `admin:manage` |
| `solar_engineer` | `project:view`, `project:create`, `project:update`, `design:view`, `design:create`, `design:update`, `boq:view`, `boq:create`, `boq:update`, `supplier:view`, `product:view`, `price:view`, `installation:commission` |
| `senior_engineer` | every `solar_engineer` scope + `design:approve`, `boq:approve` |
| `electrician_installer` | `project:view` (assigned only), `design:view`, `boq:view`, `product:view`, `installation:view`, `installation:update`, `installation:commission` |
| `supplier_admin` | `supplier:view` (own), `supplier:update` (own), `product:view`, `product:create`, `product:update` (own), `price:view`, `price:update` (own), `rfq:view`, `rfq:respond` |
| `supplier_user` | `supplier:view` (own), `product:view`, `product:update` (assigned), `price:update` (assigned), `rfq:view`, `rfq:respond` |
| `procurement_specialist` | `project:view`, `boq:view`, `supplier:view`, `product:view`, `price:view`, `rfq:create`, `rfq:view`, `rfq:compare`, `purchase:view`, `purchase:create` |
| `catalogue_manager` | `product:view`, `product:create`, `product:update`, `product:approve`, `product:merge`, `supplier:view`, `supplier:update`, `price:view`, `price:approve` |
| `finance_officer` | `price:view`, `purchase:view`, `purchase:approve`, `audit:view` (financial events only) |
| `support_agent` | `*:view` (read-only across all tenants the support agent is assigned to) |
| `customer` | `project:view` (own), `design:view` (own), `boq:view` (own), `purchase:view` (own) |

### 7.5 RBAC matrix (per brief supplement §9)

The brief gives a per-module matrix. Reproduced here verbatim, with the post-Keycloak permission key in parentheses:

| Module / Action | Engineer | Electrician | Supplier | Procurement | Marketplace Admin |
|---|:---:|:---:|:---:|:---:|:---:|
| View Product Catalogue (`product:view`) | Yes | Yes | Yes | Yes | Yes |
| Add Product (`product:create`) | No | No | Yes | No | Yes |
| Approve Product (`product:approve`) | No | No | No | No | Yes |
| Update Supplier Price (`price:update`) | No | No | Own Only | No | Yes |
| Create Solar Design (`design:create`) | Yes | No | No | No | No |
| Approve Solar Design (`design:approve`) | Senior Only | No | No | No | No |
| Generate BOQ/BOM (`boq:create`) | Yes | No | No | View Only | No |
| View Approved BOQ (`boq:view`) | Yes | Yes | No | Yes | Yes |
| Send RFQ (`rfq:create`) | No | No | No | Yes | Yes |
| Respond to RFQ (`rfq:respond`) | No | No | Yes | No | No |
| Update Installation Progress (`installation:update`) | No | Yes | No | No | No |
| Submit Commissioning Report (`installation:commission`) | Yes | Yes | No | No | No |
| Approve Supplier (`supplier:approve`) | No | No | No | No | Yes |
| Suspend Supplier (`supplier:suspend`) | No | No | No | No | Yes |
| View Audit Logs (`audit:view`) | Limited | No | Own Only | Limited | Yes |

"Limited" = scope restricted to events on resources the user owns or co-edits. "Own Only" = scope restricted to records where `tenant_id = current_tenant_id()` AND `supplier_id = jwt.supplier_id`.

### 7.6 Implementation note

The matrix above is the canonical source. Phase 2's middleware turns each row into a `@require_role + @require_scope + @require_tenant_match` triple. The realm export at `docs/keycloak/realm-export.json` enumerates the roles + composite scopes; the matrix is the verification artifact.

---

## 8. Group structure + tenant isolation

### 8.1 Group hierarchy (per brief supplement §10)

Keycloak groups give us a tree under which users sit. The brief specifies:

```
solarpro/
├── Platform Admins                          (members get platform_super_admin)
├── Marketplace Admins                       (members get marketplace_admin)
├── Engineering Firms/                       (parent group per tenant)
│   ├── <Firm A>/
│   │   ├── Engineers                        (solar_engineer)
│   │   ├── Senior Engineers                 (senior_engineer)
│   │   └── Electricians                     (electrician_installer)
│   ├── <Firm B>/
│   │   └── ...
├── Suppliers/                               (parent per supplier company)
│   ├── <Supplier X>/
│   │   ├── Supplier Admins                  (supplier_admin)
│   │   └── Supplier Users                   (supplier_user)
│   ├── <Supplier Y>/
│   │   └── ...
├── Procurement Teams/                       (parent per buyer tenant)
│   ├── <Buyer P>/
│   │   └── Procurement Specialists          (procurement_specialist)
├── Customers/                               (end-user customers)
└── AI Agents                                (service-account users)
```

Groups have **default roles** attached so adding a user to a group grants the right role automatically. Tenant attributes on the user (see §8.2) cascade from the parent group.

### 8.2 Required user attributes (per brief §6 + supplement §10)

Every user record carries:

| Attribute | Type | Purpose |
|---|---|---|
| `tenant_id` | string | UUID of the owning tenant; the **JWT carries this claim** and the backend filters by it. |
| `tenant_name` | string | Display only. |
| `user_type` | enum | `engineer`, `electrician`, `supplier`, `procurement`, `marketplace_admin`, `customer`, `platform_admin`. |
| `country` | string | ISO-3166-1 alpha-2 — used by regional pricing and reports. |
| `region` | string | Free text (Ghana → "Greater Accra"); per the `mounting_type` and Ghana region docs. |
| `subscription_plan` | enum | `free`, `pro`, `enterprise`. |
| `supplier_id` | string (UUID) | Set for `supplier_admin` / `supplier_user`; used by tenant-match middleware. |
| `engineering_company_id` | string (UUID) | Set for `solar_engineer` / `senior_engineer` / `electrician_installer`. |
| `marketplace_scope` | string | For marketplace_admin: comma-separated category codes the admin can approve (e.g. `transformers,hv_cables`). |

The attributes flow into the JWT as **token claims** via Keycloak protocol mappers — one mapper per attribute, claim type `String` for plain attributes, `JSON` for arrays.

### 8.3 Backend tenant enforcement (per brief §6 + 8)

The brief is explicit: "SolarPro backend must enforce: User can only read/write records where `token.tenant_id = database.tenant_id`."

The post-Keycloak enforcement runs at three layers:

1. **JWT middleware** — reads `tenant_id` claim into the request context. No claim → 401.
2. **Application query layer** — every `SELECT/UPDATE/DELETE` includes `WHERE tenant_id = :ctx_tenant`. The `current_tenant_id()` helper returns the value the middleware stashed.
3. **PostgreSQL RLS** — every row in tenant-owned tables has `tenant_id` checked against `current_setting('app.current_tenant')::uuid`. Before each request the middleware calls `SET app.current_tenant = :tid; SET app.current_user = :uid;`.

Defence in depth: even if a developer forgets the `WHERE` clause, the database refuses to return cross-tenant rows. Even if the Postgres GUC is missed, the application code refuses too.

### 8.4 Implementation note

The cross-tenant test in `tests/security/test_tenant_isolation.py` must include:
- Direct API call with `tenant_id=A`'s JWT trying to read a `tenant_id=B` row → 404 (RLS hides the row; we return 404 not 403 to avoid leaking existence).
- Same row referenced via foreign key (e.g. `/projects/<id>/reports/<report_id>`) where the project belongs to tenant A and the report to tenant B → 404.
- Service account JWT without a `tenant_id` claim trying to read any tenant-owned table → 403 with `MISSING_TENANT_CONTEXT`.
- Logged-in user trying to update their own `tenant_id` attribute → 403 with `IMMUTABLE_ATTRIBUTE` (only `platform_super_admin` can move a user across tenants, and only through a dedicated admin endpoint).

---

## 9. Token management (per brief §7)

### 9.1 Token types

| Token | Lifespan | Storage | Purpose |
|---|---|---|---|
| Access token | 10 min | Memory (browser tab) | Authorise API calls. Short to limit blast radius of a steal. |
| Refresh token | 60 min | HttpOnly secure cookie | Mint a fresh access token; the only token that crosses TLS termination via Set-Cookie. |
| Offline token | 30 days (idle), 60 days (max) | Encrypted DB column for **service accounts only** | Backend jobs that need long-running auth (e.g. nightly catalogue scan). |
| ID token | tied to session | Memory | Display name + email + role list for the UI; never sent to backend. |
| Service account token | client credentials grant, 10 min | Memory (agent process) | AI agent authn; refreshed before every backend call. |

### 9.2 JWT lifecycle

```
Login
  → POST /realms/solarpro/protocol/openid-connect/token
    grant_type=authorization_code, code=<code>, code_verifier=<pkce>
  ← {access_token, refresh_token, id_token, expires_in, refresh_expires_in}

10 min later (or pre-emptively at 8 min)
  → POST /realms/solarpro/protocol/openid-connect/token
    grant_type=refresh_token, refresh_token=<rt>
  ← fresh tokens (refresh token rotated; old one invalidated)

60 min later
  → user is prompted to re-authenticate (refresh token expired)

Logout
  → POST /realms/solarpro/protocol/openid-connect/logout
    refresh_token=<rt>
  ← server-side session invalidated; all tokens for the session are dead
```

### 9.3 Refresh strategy

- **Sliding refresh.** Every successful API call returns a `X-Token-Expires-In` header. Frontend refreshes when the value drops below 90 seconds.
- **Rotation.** Each refresh issues a new refresh token AND invalidates the old one. Token theft is limited to the time between issue and the next refresh.
- **Reuse detection.** Keycloak's "Refresh Token Family" mechanism: if a stolen refresh token is used after the legitimate user has rotated, Keycloak kills the entire family + flags the user.

### 9.4 Logout

Per brief §9 (existing SolarPro Q-gate 2.1 / 2.2: "stateless 30-day tokens; no revocation") this is the gap Keycloak closes.

A real logout requires:

1. Frontend calls `POST /api/auth/logout` → SolarPro deletes refresh-token cookie.
2. SolarPro calls Keycloak `/realms/solarpro/protocol/openid-connect/logout` with the refresh token → Keycloak invalidates the session, increments the user's `session_version`, kills the refresh-token family.
3. SolarPro middleware on the next access-token use sees the access token's `session_state` no longer matches the user's `session_version` and returns 401.
4. Audit row written: `action='LOGOUT'`, `user_id`, `session_id`.

Test: login → access dashboard → logout → old access token → API returns 401 → browser back does not reveal private data → revoked refresh token cannot mint a new access token. Matches the Project Directive §9 "Logout Must Really Work Rule" verbatim.

### 9.5 Implementation note

Backend never validates tokens by introspection (network round trip); it validates JWT signatures locally against Keycloak's JWKS endpoint, cached and refreshed on `kid` rotation. Introspection is reserved for opaque tokens, which SolarPro does not use.

---

## 10. Backend API security (per brief §8)

### 10.1 7-step middleware (verbatim from brief)

```
Request comes in
  → Read Authorization Bearer token
  → 1. Validate JWT signature with Keycloak public key (JWKS cache)
  → 2. Validate expiry (exp) and not-before (nbf)
  → 3. Validate issuer (iss == https://auth.aiappinvent.com/realms/solarpro)
  → 4. Validate audience (aud contains "solarpro-api")
  → 5. Extract user_id, tenant_id, roles, scopes
  → 6. Check route permission (role + scope intersection)
  → 7. Check tenant isolation (route's path param tenant matches token claim)
  → Allow or deny request
```

### 10.2 Flask middleware skeleton (delivered in Phase 2)

`app/security/keycloak_middleware.py`:

```python
# Skeleton — full implementation lands in Phase 2.
import os, time, requests
from functools import wraps, lru_cache
from flask import request, jsonify, g
from jose import jwt, JWTError  # python-jose, FOSS-friendly

KEYCLOAK_ISSUER = os.environ["KEYCLOAK_ISSUER"]                # e.g. https://auth.aiappinvent.com/realms/solarpro
KEYCLOAK_AUDIENCE = os.environ.get("KEYCLOAK_AUDIENCE", "solarpro-api")
JWKS_TTL_SECONDS = 300


@lru_cache(maxsize=1)
def _jwks_cache():
    return {"fetched_at": 0, "keys": None}


def _jwks():
    cache = _jwks_cache()
    if time.time() - cache["fetched_at"] > JWKS_TTL_SECONDS or cache["keys"] is None:
        url = f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs"
        cache["keys"] = requests.get(url, timeout=5).json()["keys"]
        cache["fetched_at"] = time.time()
    return cache["keys"]


def verify_jwt(token: str) -> dict:
    """Returns the validated claims dict or raises JWTError."""
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header["kid"]
    key = next((k for k in _jwks() if k["kid"] == kid), None)
    if not key:
        # Cache miss -- force refresh once then retry.
        _jwks_cache()["fetched_at"] = 0
        key = next((k for k in _jwks() if k["kid"] == kid), None)
        if not key:
            raise JWTError(f"unknown kid: {kid}")
    return jwt.decode(
        token, key,
        algorithms=[key["alg"]],
        audience=KEYCLOAK_AUDIENCE,
        issuer=KEYCLOAK_ISSUER,
        options={"verify_at_hash": False},  # we don't ship the nonce flow
    )


def require_jwt(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify(error="MISSING_BEARER"), 401
        try:
            claims = verify_jwt(auth.split(" ", 1)[1])
        except JWTError as e:
            return jsonify(error="INVALID_JWT", reason=str(e)), 401
        g.claims = claims
        g.user_id = claims["sub"]
        g.tenant_id = claims.get("tenant_id")
        g.roles = claims.get("realm_access", {}).get("roles", [])
        g.scopes = claims.get("scope", "").split()
        return view(*args, **kwargs)
    return wrapper


def require_role(role_name: str):
    def decorator(view):
        @wraps(view)
        @require_jwt
        def wrapper(*args, **kwargs):
            if role_name not in g.roles:
                _audit_denial(role_name)
                return jsonify(error="FORBIDDEN_ROLE", required=role_name), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def require_scope(scope_name: str):
    def decorator(view):
        @wraps(view)
        @require_jwt
        def wrapper(*args, **kwargs):
            if scope_name not in g.scopes:
                _audit_denial(scope_name)
                return jsonify(error="FORBIDDEN_SCOPE", required=scope_name), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def require_tenant_match(path_param: str):
    """For routes like /tenants/<tenant_id>/projects -- verifies the URL
    tenant matches the JWT tenant. CRITICAL for multi-tenant safety."""
    def decorator(view):
        @wraps(view)
        @require_jwt
        def wrapper(*args, **kwargs):
            url_tenant = kwargs.get(path_param)
            if g.tenant_id != url_tenant:
                _audit_denial(f"tenant_mismatch:{path_param}")
                return jsonify(error="TENANT_MISMATCH"), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator


def _audit_denial(reason: str):
    # Writes to audit_log via the structured logger (see §15).
    from logging_config.structured_logger import audit
    audit("PERMISSION_DENIED", user_id=g.get("user_id"),
          tenant_id=g.get("tenant_id"), ip=request.remote_addr,
          path=request.path, method=request.method, reason=reason)
```

### 10.3 Module → role map (per brief §9)

| Module | Required role(s) |
|---|---|
| Product Catalogue | `product_catalogue_manager` (alias `catalogue_manager`), `tenant_admin` |
| Supplier Catalogue | `supplier_catalogue_manager` (alias `catalogue_manager`), `tenant_admin` |
| BOQ/BOM Generator | `solar_engineer`, `senior_engineer`, `tenant_admin` (composite: `estimator` accepted as alias) |
| Solar Calculator | `customer`, `solar_engineer`, `senior_engineer` |
| Procurement Module | `procurement_specialist`, `tenant_admin` |
| Sales CRM | `sales_agent`, `sales_manager` (composite of `procurement_specialist` + `tenant_admin`) |
| Tender Hunter | `sales_manager`, `tenant_admin` |
| AI Agents (admin surface) | `api_service_account`, `tenant_admin` |
| Admin Dashboard | `platform_super_admin`, `tenant_admin` |
| Payment/Billing | `finance_officer`, `tenant_admin` |
| Marketplace Admin | `marketplace_admin`, `platform_super_admin` |

Per route this translates into `@require_role` / `@require_any_role([])` / `@require_scope` triplets. Phase 2 generates a table from `docs/auth_inventory.csv` (built in Phase 0) and applies them in order of blast radius (admin first, then marketplace, then engineering, then customer).

### 10.4 Authorization Services (ABAC, per brief §10)

For rules that role + scope can't express alone — ownership, time windows, IP restriction, marketplace category scope — we use Keycloak Authorization Services. Examples from the brief:

- Only `supplier_admin` can edit products belonging to their own supplier tenant. → Policy: `tenant.id == resource.supplier.tenant_id && user.has_role("supplier_admin")`.
- Only `product_catalogue_manager` can approve catalogue imports. → Policy: `user.has_role("catalogue_manager") && resource.action == "import:approve"`.
- Only `finance_officer` can view payment reports. → Policy: `user.has_role("finance_officer") && resource.kind == "payment_report"`.
- Only `platform_super_admin` can suspend tenants. → Policy: `user.has_role("platform_super_admin") && resource.action == "tenant:suspend"`.

Authorization Services tokens (`urn:ietf:params:oauth:token-type:rpt`) are fetched per-resource on demand. Cached for the token lifetime to avoid round-trip-per-call.

### 10.5 Implementation note

Phase 2 ships only `require_jwt`, `require_role`, `require_scope`, `require_tenant_match`. Authorization Services (Phase 6) adds `require_policy("policy_name")`. Old `@admin_required` etc. is wrapped — both paths approve so we have parallel-run safety, with metrics counting how often each path approves.

---

## 11. Frontend integration

### 11.1 Flask Jinja (current)

Today's flow: form post to `/login`, `web_app.py` checks bcrypt, sets `session["user_id"]`. Replaced in Phase 5 with:

1. `GET /login` → render a "Sign in with Keycloak" button (and the marc667us emergency form behind `?legacy=1`).
2. Button → `GET /auth/login` → redirect to `https://auth.aiappinvent.com/realms/solarpro/protocol/openid-connect/auth?response_type=code&client_id=solarpro-web&redirect_uri=...&code_challenge=...&code_challenge_method=S256&scope=openid profile email`.
3. Keycloak login + MFA + return to `https://solarpro.aiappinvent.com/auth/callback?code=<code>&state=<state>`.
4. SolarPro `/auth/callback`:
   - validates `state` (CSRF).
   - exchanges code for tokens via PKCE.
   - sets `session["access_token"]` (short-lived), refresh token in HttpOnly secure cookie `solarpro_rt`.
   - reads ID token claims into `session["user"] = {sub, preferred_username, email, name, tenant_id, roles}`.
   - redirects to original target (`?next=` param) or `/dashboard`.
5. Logout: `POST /auth/logout` → call Keycloak end-session → clear cookies → redirect home.

### 11.2 Next.js (planned)

Same OIDC flow via `next-auth` with the Keycloak provider:

```ts
// pages/api/auth/[...nextauth].ts
import NextAuth from "next-auth"
import KeycloakProvider from "next-auth/providers/keycloak"

export default NextAuth({
  providers: [
    KeycloakProvider({
      clientId: process.env.KEYCLOAK_CLIENT_ID!,        // solarpro-web
      clientSecret: "",                                  // public client; PKCE
      issuer: process.env.KEYCLOAK_ISSUER!,             // https://auth.aiappinvent.com/realms/solarpro
    }),
  ],
  callbacks: {
    async jwt({ token, account }) {
      if (account) {
        token.access_token = account.access_token
        token.refresh_token = account.refresh_token
        token.expires_at = account.expires_at
      }
      // pre-emptive refresh
      if (Date.now() / 1000 > (token.expires_at as number) - 90) {
        token = await refreshAccessToken(token)
      }
      return token
    },
    async session({ session, token }) {
      session.access_token = token.access_token
      session.user.tenant_id = (token.tenant_id as string)
      return session
    },
  },
})
```

### 11.3 Token storage rules

| Token | Browser storage | Why |
|---|---|---|
| Access token | Memory (React state / Flask `session`) | XSS-resistant; short-lived limits damage if leaked |
| Refresh token | HttpOnly + Secure + SameSite=Lax cookie | Inaccessible to JavaScript; CSRF-protected by SameSite |
| ID token | Memory | Display only; rotated each refresh |

Never put any token in `localStorage` or `sessionStorage` — both are XSS-accessible.

### 11.4 Implementation note

Phase 5 ships the Flask flow. The Next.js flow is documented now so the eventual port doesn't re-litigate the OIDC choice.

---

## 12. AI agent + service account security (per brief §14)

### 12.1 Five service accounts (verbatim from brief)

| Service account | Purpose | Allowed scopes | Forbidden actions |
|---|---|---|---|
| `solarpro-catalogue-agent` | Reads supplier catalogues, suggests product updates | `read_supplier_catalogue`, `write_extraction_queue`, `suggest_product_update` | `cannot_approve_final_update` |
| `solarpro-tender-agent` | Hunts tender opportunities, drafts RFQ replies | `read_tender_feed`, `write_tender_draft`, `notify_sales_manager` | `cannot_publish_tender_reply` |
| `solarpro-report-agent` | Generates PV / shading / proposal reports | `read_project`, `read_design`, `write_report_artifact` | `cannot_modify_design` |
| `solarpro-email-agent` | Sends transactional emails | `read_user_email`, `send_transactional_email` | `cannot_send_to_unverified_email`, `cannot_attach_user_pii` |
| `solarpro-payment-agent` | Reconciles Paystack / Stripe webhooks | `read_payment_event`, `write_invoice_status` | `cannot_issue_refund_directly`, `cannot_modify_payment_history` |

### 12.2 Human-in-the-loop checkpoints

The Project Directive §14 and the brief §14 both require human approval for:

- Sending emails to external recipients (overrides `solarpro-email-agent` for any non-transactional flow).
- Deleting data.
- Awarding bids.
- Changing subscriptions.
- Exporting confidential reports.
- Updating supplier prices.
- Modifying financial data.
- Admin operations.

The decorator `@require_human_approval("action_name")` redirects the agent's action into the `agent_pending_actions` queue. A `tenant_admin` (or `platform_super_admin` for cross-tenant actions) approves or rejects via the admin dashboard. Approved actions resume via the agent's service account token.

### 12.3 Service account token flow

```
AI Agent (running in SolarPro pod)
  → POST /realms/solarpro/protocol/openid-connect/token
    grant_type=client_credentials
    client_id=solarpro-catalogue-agent
    client_secret=<vault-fetched>
  ← {access_token, expires_in: 600, scope: "..."}

Agent
  → GET /api/marketplace/products?status=pending
    Authorization: Bearer <jwt>
  → middleware: validates JWT, sees jwt.azp == solarpro-catalogue-agent
  → middleware: looks up scope, confirms read_supplier_catalogue
  → middleware: writes audit log (agent_id, action, target_id)
  ← 200
```

### 12.4 Implementation note

Each agent's client secret rotates on a 90-day Vault lease. Rotation hooks update the realm via `kc.sh client credentials regenerate` and the new secret writes into Vault before the lease expires. Phase 3 of the migration delivers the agent loader rewrite and the Vault integration.

---

## 13. Five user flows (per brief supplement §3–§7)

Each flow is reproduced from the brief verbatim, with the post-Keycloak realisation called out. Each flow corresponds to one of the five main user groups (§7.1).

### 13.1 Engineer flow (per brief supplement §3)

**Login flow**

```
Engineer opens SolarPro
  → Redirected to Keycloak login page (solarpro-web client)
  → Enters username/password
  → MFA verification (TOTP)
  → Keycloak issues JWT with realm role solar_engineer + tenant_id + engineering_company_id
  → SolarPro reads role; engineer dashboard opens
```

**Dashboard surfaces**

- New design requests · Assigned projects · Load assessment forms · Solar sizing calculator · PV design workspace · BOQ/BOM generator · Product catalogue · Supplier pricing · Technical report generator · Design approval status.

**Scenario — commercial building solar design**

1. Engineer opens client assessment.
2. Reviews load schedule.
3. Confirms voltage level and backup requirement.
4. Runs PV sizing.
5. Selects panels, inverter, batteries, cables, isolators, DBs, breakers.
6. Generates BOM.
7. Generates BOQ.
8. Checks supplier price options.
9. Prepares technical report.
10. Sends design for senior engineer approval.

**Permissions matrix (verbatim from brief; mapped to Keycloak scopes)**

| Function | Today | Post-Keycloak scope |
|---|---|---|
| View projects | Allow | `project:view` |
| Create solar design | Allow | `design:create` |
| Edit own design | Allow | `design:update` (+ ownership policy via Authorization Services) |
| View product catalogue | Allow | `product:view` |
| View supplier catalogue | Allow | `supplier:view` |
| Generate BOQ/BOM | Allow | `boq:create`, `boq:update` |
| Approve own design | Deny | n/a — needs `design:approve` (senior_engineer only) |
| Approve final technical report | Deny unless senior engineer | `senior_engineer` role required |
| Edit supplier prices | Deny | scope `price:update` not in role |
| Delete products | Deny | scope `product:delete` does not exist |

### 13.2 Electrician / Installer flow (per brief supplement §4)

**Login flow**

```
Electrician logs in
  → Keycloak verifies identity (MFA optional but recommended)
  → SolarPro reads role electrician_installer + assigned_project_ids attribute
  → Installation dashboard opens
```

**Dashboard surfaces**

- Assigned installation jobs · Site address · Approved design drawings · Installation checklist · Materials list · Work method statement · Safety checklist · Photo upload · Progress update · Testing and commissioning forms.

**Scenario — approved project installation**

1. Electrician opens assigned job.
2. Reviews approved BOM and drawings.
3. Confirms materials received.
4. Completes site safety checklist.
5. Installs panels, inverter, batteries, cables, earthing, protection devices.
6. Uploads installation photos.
7. Records test results.
8. Marks work stages complete.
9. Submits commissioning report.
10. Engineer reviews and closes installation.

**Permissions matrix**

| Function | Today | Post-Keycloak |
|---|---|---|
| View assigned jobs | Allow | `installation:view` (+ assigned_project_ids policy) |
| View approved design | Allow | `design:view` (+ approved-only policy) |
| View BOM | Allow | `boq:view` |
| Upload photos | Allow | `installation:update` |
| Update installation progress | Allow | `installation:update` |
| Submit test results | Allow | `installation:commission` |
| Change design | Deny | scope `design:update` not in role |
| Change product prices | Deny | `price:update` not in role |
| Approve supplier | Deny | `supplier:approve` not in role |
| Delete project | Deny | no such scope |

### 13.3 Supplier flow (per brief supplement §5)

**Login flow**

```
Supplier logs in
  → Keycloak verifies supplier role (supplier_admin or supplier_user)
  → SolarPro reads tenant_id + supplier_id from JWT claims
  → Supplier dashboard opens
```

**Dashboard surfaces**

- Supplier company profile · Product catalogue · Price list · Stock status · Quotations · Purchase enquiries · Warranty records · Delivery terms · Product approval status.

**Scenario — adding solar products**

1. Supplier logs in.
2. Opens supplier profile.
3. Uploads receipt, price list, or spreadsheet.
4. AI extracts products and prices.
5. Supplier reviews extracted records.
6. Supplier submits products for marketplace approval.
7. Marketplace Admin reviews products.
8. Approved products appear in Product Catalogue.

**Permissions matrix**

| Function | Today | Post-Keycloak |
|---|---|---|
| Edit own supplier profile | Allow | `supplier:update` (+ supplier_id ownership policy) |
| Add products | Allow | `product:create` |
| Upload price list | Allow | `price:update` (+ supplier_id policy) |
| Update own prices | Allow | `price:update` (own only via policy) |
| View own quotation requests | Allow | `rfq:view` (own only) |
| Respond to RFQ | Allow | `rfq:respond` |
| View other supplier prices | Limited / Deny | scope `price:view` restricted by marketplace_scope |
| Approve own marketplace listing | Deny | scope `product:approve` is `marketplace_admin` only |
| Edit other supplier products | Deny | ownership policy denies |
| Delete approved catalogue item | Deny without approval | scope `product:approve` required |

### 13.4 Procurement Specialist flow (per brief supplement §6)

**Login flow**

```
Procurement officer logs in
  → Keycloak authenticates (MFA recommended for finance-adjacent)
  → SolarPro reads procurement_specialist role + tenant_id
  → Procurement dashboard opens
```

**Dashboard surfaces**

- Approved BOQs · Material requests · Supplier comparison · RFQ generator · Price comparison · Purchase recommendation · Delivery tracking · Procurement approvals.

**Scenario — solar project procurement**

1. Opens approved BOQ.
2. System identifies required products.
3. System matches products against supplier catalogue.
4. Sends RFQs to selected suppliers.
5. Suppliers submit quotations.
6. System compares prices, warranty, stock, delivery time.
7. Prepares recommendation.
8. Finance/Admin approves purchase.
9. Purchase order is issued.

**Permissions matrix**

| Function | Today | Post-Keycloak |
|---|---|---|
| View approved BOQ | Allow | `boq:view` (approved status only via policy) |
| View supplier catalogue | Allow | `supplier:view` |
| Send RFQ | Allow | `rfq:create` |
| Compare prices | Allow | `rfq:compare` |
| Generate procurement report | Allow | `purchase:view` |
| Recommend supplier | Allow | `purchase:create` |
| Approve final purchase | Depends on policy | `purchase:approve` granted to `finance_officer` / `tenant_admin` only |
| Edit supplier product data | Deny | `product:update` not in role |
| Approve marketplace product | Deny | `product:approve` is `marketplace_admin` only |
| Change engineering design | Deny | `design:update` not in role |

### 13.5 Marketplace Admin flow (per brief supplement §7)

**Login flow**

```
Marketplace Admin logs in
  → Keycloak validates marketplace_admin role + MFA required
  → SolarPro opens marketplace control centre
```

**Dashboard surfaces**

- Pending supplier approvals · Pending product approvals · Product quality issues · Duplicate product records · Price anomaly alerts · Supplier verification status · Marketplace performance · Catalogue audit logs.

**Scenario — new inverter products from supplier**

1. Opens pending approval queue.
2. Reviews supplier business details.
3. Reviews product specifications.
4. Checks duplicate product records.
5. Checks price reasonableness.
6. Approves, rejects, or requests correction.
7. Approved item becomes visible in marketplace.
8. Audit log records admin action.

**Permissions matrix**

| Function | Today | Post-Keycloak |
|---|---|---|
| Approve suppliers | Allow | `supplier:approve` |
| Suspend suppliers | Allow | `supplier:suspend` |
| Approve products | Allow | `product:approve` |
| Merge duplicate products | Allow | `product:merge` |
| Review price anomalies | Allow | `price:view` (cross-tenant for marketplace admin only) |
| Manage catalogue quality | Allow | `product:update` (+ category-scope policy) |
| View audit logs | Allow | `audit:view` |
| View platform marketplace reports | Allow | composite scope |
| Edit user passwords directly | Deny | NO ONE can do this; only Keycloak knows passwords |
| Access private tenant financial data | Restricted | `finance_officer` role required |
| Delete audit logs | Deny | append-only; admin events log doubles up |

### 13.6 Implementation note

The five flows are the acceptance criteria for Phase 5 + 7. The smoke test extends `tmp/live_smoke_test_2026-06-19.py` with one section per flow.

---

## 14. MFA + password policy (per brief §12)

### 14.1 Required configuration

| Setting | Value | Notes |
|---|---|---|
| Email verification | required for every new user | Keycloak required action `VERIFY_EMAIL`. |
| Password reset flow | enabled | Forgot-password link on the login page. |
| Password policy | length(12), digits(1), upper(1), lower(1), special(1), notUsername, notEmail, hashIterations(210000), history(5), forceExpiredChange(90) | Argon2id is Keycloak 26 default; iteration count for legacy PBKDF2 hashed users only. |
| OTP / TOTP | required for: `platform_super_admin`, `tenant_admin`, `marketplace_admin`, `finance_officer`. Optional but encouraged for `senior_engineer`, `procurement_specialist`, `catalogue_manager`. | Configured via authentication-flow conditional require. |
| WebAuthn / Passkey | enabled, optional for everyone, recommended for `platform_super_admin` and `marketplace_admin`. | Keycloak built-in WebAuthn flow. |
| Brute-force protection | enabled, 5 failures → 60s wait, doubling up to 15 min. | Replaces SolarPro's in-app lockout. |
| Session timeout | SSO idle 30 min; max 10 h. | Per brief §7. |
| Account lockout | enabled after 30 failed attempts in 24 h; admin override available. | |
| Admin event logging | enabled, retained 90 days in Keycloak; mirrored to SolarPro `audit_log`. | |

### 14.2 Per-role MFA matrix

| Role | TOTP | WebAuthn | Recovery |
|---|---|---|---|
| `platform_super_admin` | required | recommended | recovery codes + admin escalation via separate channel |
| `marketplace_admin` | required | recommended | recovery codes |
| `tenant_admin` | required | optional | recovery codes |
| `finance_officer` | required | optional | recovery codes |
| `senior_engineer` | optional | optional | email |
| `solar_engineer` | optional | optional | email |
| `procurement_specialist` | optional | optional | email |
| `catalogue_manager` | optional | optional | email |
| `supplier_admin` | optional | optional | email |
| `supplier_user` | optional | optional | email |
| `electrician_installer` | optional | optional | email + admin reset |
| `customer` | optional | optional | email |
| `support_agent` | required | optional | recovery codes |

### 14.3 Implementation note

Required-action enforcement is configured per realm-role via Keycloak's "Conditional - User Role" sub-flow in the authentication flow. First-login of an `marketplace_admin` user lands on the OTP-setup screen before reaching `/dashboard`.

---

## 15. Audit logging (per brief §15)

### 15.1 Events to log

| Event | Source | Sink |
|---|---|---|
| Login success | Keycloak | admin events + SolarPro `audit_log` |
| Login failure | Keycloak | admin events + SolarPro `audit_log` |
| Password reset | Keycloak | admin events + SolarPro `audit_log` |
| Role change | Keycloak (admin) | admin events + SolarPro `audit_log` |
| Token refresh | Keycloak | sampled (one per session) + SolarPro `audit_log` |
| Catalogue update | SolarPro | `audit_log` |
| Supplier update | SolarPro | `audit_log` |
| Price change | SolarPro | `audit_log` |
| Permission denial | SolarPro middleware | `audit_log` (and metric counter for alerting) |
| Admin action (any) | SolarPro | `audit_log` + `security.log` (Loki) |
| Tenant change (rare) | SolarPro | `audit_log` + email to owner |

### 15.2 Sinks

| Sink | Retention | Purpose |
|---|---|---|
| SolarPro `audit_log` table (Postgres, RLS append-only) | 1 year hot; archive thereafter | source of truth, admin queries |
| Keycloak admin events | 90 days | identity-side events |
| `logs/audit/audit.log` (JSON, structured logger) | 30 days on disk, shipped to Loki | search + alerting |
| OpenSearch / ELK (optional) | per project | aggregated cross-app search |

### 15.3 Audit row shape

```sql
CREATE TABLE audit_log (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     UUID,
  user_id       UUID,
  action        VARCHAR(120) NOT NULL,         -- e.g. LOGIN_SUCCESS, PERMISSION_DENIED, PRICE_UPDATED
  resource_type VARCHAR(60),                   -- product, supplier, design, etc.
  resource_id   VARCHAR(120),
  ip_address    INET,
  user_agent    VARCHAR(500),
  request_id    UUID,                          -- correlates with Loki
  status        VARCHAR(20),                   -- SUCCESS / FAILURE
  details       JSONB DEFAULT '{}',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_tenant_time ON audit_log(tenant_id, created_at DESC);
CREATE INDEX idx_audit_user_time   ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_action_time ON audit_log(action, created_at DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;

CREATE POLICY audit_log_tenant ON audit_log FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant')::uuid
         OR current_setting('app.current_role') = 'platform_super_admin');
CREATE POLICY audit_log_insert ON audit_log FOR INSERT
  WITH CHECK (true);  -- writes are unconditional; reads are gated
-- No UPDATE / DELETE policies → append-only.
```

### 15.4 Implementation note

The Keycloak event listener that mirrors events to SolarPro is a small JAR — or we use the built-in `jboss-logging` listener and shape SolarPro to subscribe to Loki. Phase 6 picks one; the JAR is preferred because it lets SolarPro write directly to `audit_log` with the right tenant context.

---

## 16. User migration (per brief §13)

### 16.1 Inventory

Before Phase 7 runs, we need:

```sql
SELECT
  u.id, u.username, u.email, u.is_admin, u.role,
  u.country, u.region, u.subscription_plan,
  s.id AS supplier_id, ec.tenant_id
FROM users u
LEFT JOIN suppliers s ON s.user_id = u.id
LEFT JOIN engineering_companies ec ON ec.owner_user_id = u.id
ORDER BY u.created_at;
```

Save the export to `migrations/users_export_<date>.csv`.

### 16.2 Mapping

For each user, decide:

1. **Realm role.** `is_admin=true` → `platform_super_admin` (only the platform team) or `tenant_admin` (customer-side admins). `users.role = 'supplier_admin'` → keep. `users.role = 'procurement_specialist'` → keep. Default → `customer`.
2. **Tenant.** From `engineering_companies.tenant_id` or `suppliers.tenant_id` or new tenant created during migration for legacy single-user accounts.
3. **Attributes.** `country`, `region`, `subscription_plan`, `supplier_id`, `engineering_company_id`.
4. **Required actions.** `["UPDATE_PASSWORD", "VERIFY_EMAIL"]` on first login.
5. **Email status.** Force re-verification — old verifications don't transfer.

### 16.3 Import

Build `migrations/keycloak_partial_import.json`:

```json
{
  "users": [
    {
      "username": "marc667us",
      "email": "marc@aiappinvent.com",
      "enabled": true,
      "emailVerified": false,
      "firstName": "Marc",
      "lastName": "—",
      "attributes": {
        "tenant_id": ["<uuid>"],
        "tenant_name": ["AI App Invent"],
        "user_type": ["platform_admin"],
        "country": ["GH"],
        "subscription_plan": ["enterprise"]
      },
      "requiredActions": ["UPDATE_PASSWORD", "VERIFY_EMAIL"],
      "realmRoles": ["platform_super_admin"]
    }
    // ...
  ]
}
```

POST to `/admin/realms/solarpro/partialImport`:

```bash
TOKEN=$(curl -s -X POST \
  -d "client_id=admin-cli&grant_type=password&username=admin&password=$KC_BOOTSTRAP_ADMIN_PASSWORD" \
  https://auth.aiappinvent.com/realms/master/protocol/openid-connect/token \
  | jq -r .access_token)

curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @migrations/keycloak_partial_import.json \
  https://auth.aiappinvent.com/admin/realms/solarpro/partialImport
```

### 16.4 Cutover

1. Email broadcast 7 days before cutover: "We're moving to a new login system. Please use the password-reset link the day of cutover. MFA-required roles, please be ready to set up an authenticator app."
2. Day of cutover (off-peak):
   - Apply `migrations/keycloak_partial_import.json`.
   - Set production `KEYCLOAK_ISSUER` env to `https://auth.aiappinvent.com/realms/solarpro`.
   - Deploy the Keycloak-only `web_app.py` (legacy form removed).
   - Run `tmp/live_smoke_test_keycloak.py` (extension of the 2026-06-19 smoke test).
3. Day +1 to day +7: rollback window. Legacy form behind `?legacy=1` still available. Owner-controlled fallback for marc667us.
4. Day +14: drop `users.password_hash` column. Remove legacy form. Remove `_seed_pwd` and `SOLARPRO_*_PASSWORD` envs.

### 16.5 What NOT to migrate

- Plain passwords — Keycloak refuses; the brief is explicit.
- Bcrypt hashes — Keycloak 26 can import them as `bcrypt` credential type but the user is still forced through password reset on first login per our policy.
- Sessions — every existing Flask session is invalidated. Users must log in again. (Acceptable; we tell them in the broadcast.)
- API keys — replaced by Keycloak service-account tokens (Phase 3).

### 16.6 Implementation note

Phase 7 starts only after Phases 1–6 have all passed acceptance. Migration day is announced 14 days in advance and the rollback window stays open for 7 days. No exceptions.

---

## 17. Security hardening checklist

This is the consolidated checklist drawn from brief §8, §10, §12, §17, the existing `SECURITY_ARCHITECTURE.md` Q-gate log, and the recommended expansion topic "Security hardening checklist".

### 17.1 Keycloak hardening

- [ ] Master realm admin only reachable from VPN / Cloudflare Zero Trust.
- [ ] Master admin password rotated 90 days, stored in Vault.
- [ ] Realm sign-on key rotated 90 days (Keycloak supports key sets; old keys retained for verification of issued tokens).
- [ ] `SSL required = all` in production (we use `external` because the LB terminates TLS, but the Keycloak pod runs HTTP behind it).
- [ ] Brute force detection enabled (§14).
- [ ] Password policy enforced (§14).
- [ ] OTP / WebAuthn enforced per the role matrix (§14.2).
- [ ] Email verification required (§14).
- [ ] User self-registration disabled in production realm (sign-ups happen via the SolarPro app, which uses the admin REST API).
- [ ] Account recovery via email AND admin override.
- [ ] Keycloak Postgres on private network, not publicly reachable.
- [ ] Daily Postgres backup + weekly realm export.

### 17.2 Backend hardening (SolarPro)

- [ ] JWT signature verified locally via JWKS (no per-request introspection round-trip).
- [ ] JWKS cache TTL 5 min; rotation handled by `kid` mismatch + refetch.
- [ ] `iss`, `aud`, `exp`, `nbf` all validated.
- [ ] `tenant_id` claim required for every protected route except a small whitelist (status, health, `auth/callback`).
- [ ] Permission scope checked on every protected route.
- [ ] Cross-tenant access denied at app layer.
- [ ] Cross-tenant access denied at DB layer (RLS FORCED).
- [ ] No business logic in route handlers — Service → Repository → DB pipeline (Project Directive §4).
- [ ] Audit denial events written on every 401/403.
- [ ] Rate limit on login + token endpoints (in front of Keycloak via Traefik).
- [ ] CSRF: SameSite cookies; double-submit token on form posts. (CSRF largely solved by Bearer-only API model post-migration.)
- [ ] CORS: only `solarpro.aiappinvent.com` and explicit dev hosts.

### 17.3 Frontend hardening

- [ ] No token in `localStorage` or `sessionStorage`.
- [ ] Refresh token in HttpOnly + Secure + SameSite=Lax cookie.
- [ ] PKCE on the auth code exchange.
- [ ] State parameter on every auth redirect (CSRF).
- [ ] Logout invalidates server-side session, not just the cookie.
- [ ] No reflected XSS — Jinja autoescape on every template; React JSX renders escape by default.
- [ ] CSP header restricts script sources to `self` + Keycloak + analytics CDN if any.
- [ ] HSTS header.

### 17.4 Implementation note

This checklist is the acceptance criteria for Phase 7's go-live review. The owner signs off on each line.

---

## 18. Testing + validation (per brief §17)

### 18.1 Mandatory tests (verbatim)

- Login.
- Logout.
- Token refresh.
- Expired token rejection.
- Invalid token rejection.
- Role-based screen access.
- API permission denial.
- Tenant isolation.
- MFA.
- Password reset.
- Service account token.
- Catalogue manager permissions.
- Supplier user restrictions.
- Admin-only actions.

### 18.2 Test layout

Mirroring the Project Directive §19 categories:

```
tests/
├── security/
│   ├── test_keycloak_jwt.py            # signature, expiry, issuer, audience
│   ├── test_login_logout.py            # Phase 5 flow end-to-end
│   ├── test_token_refresh.py           # rotation + family invalidation
│   ├── test_role_screen_access.py      # 13 roles × ~50 routes = ~650 assertions
│   ├── test_api_permission_denial.py   # 27 scopes × routes
│   ├── test_tenant_isolation.py        # cross-tenant + RLS forced
│   ├── test_mfa.py                     # required-action enforcement
│   ├── test_password_reset.py          # forgot password flow
│   ├── test_service_account.py         # 5 service accounts, scope boundaries
│   ├── test_catalogue_manager.py       # marketplace_admin permissions
│   ├── test_supplier_user.py           # supplier_user vs supplier_admin
│   ├── test_admin_only_actions.py      # platform_super_admin scopes
│   └── test_audit_log.py               # every event from §15.1 lands in the table
├── integration/
│   ├── test_engineer_flow.py           # §13.1 end-to-end
│   ├── test_electrician_flow.py        # §13.2
│   ├── test_supplier_flow.py           # §13.3
│   ├── test_procurement_flow.py        # §13.4
│   └── test_marketplace_admin_flow.py  # §13.5
└── load/
    └── locust_keycloak_login.py        # 1000 concurrent logins SLA
```

### 18.3 Live smoke test extension

`tmp/live_smoke_test_keycloak.py` extends the existing 2026-06-19 smoke test with:

- Token fetch from Keycloak for each of the 5 user flows.
- Per-flow happy path against live.
- Per-flow denial test (e.g. electrician trying to approve a design).
- Service-account token fetch for `solarpro-catalogue-agent` and read of pending products.

Acceptance: 100% pass before Phase 7 day-of-cutover starts.

### 18.4 Implementation note

Phase 2 adds the JWT verification tests. Phase 4 adds tenant isolation. Phase 5 adds login/logout. Phase 6 adds MFA + audit. Phase 7 adds the migration test + the live smoke test. Run all tests before each phase ships.

---

## 19. Claude Code implementation tasks (per recommended expansion)

This section is the actionable to-do list. Each task references the phase it belongs to.

### Phase 0 — Inventory + ADR

1. Run `grep -nE "@(login|admin|supplier|procurement_role)_required|session\[\"user_id\"\]|current_user\(\)|is_admin|users\.role|_seed_pwd|SOLARPRO_(ADMIN|OWNER)_PASSWORD" web_app.py > docs/auth_inventory.csv`. Open the CSV; for each row write the target Keycloak replacement (role / scope / tenant-match).
2. Draft `docs/ARCHITECTURE_DECISIONS.md` ADR-0007: "Adopt Keycloak as identity provider". Context, decision, alternatives (Auth0 paid, Auth.js self-hosted, Logto, Ory). Reason for decision. Consequences.
3. Owner sign-off → log in `docs/IMPLEMENTATION_LOG.md`.

### Phase 1 — Local Keycloak

4. Write `docker-compose.keycloak.yml` (skeleton in §5.1).
5. Write `docs/keycloak/realm-export.json` — 5 clients + 13 roles + group hierarchy + password policy + OTP policy + brute-force config.
6. Write `scripts/keycloak/bootstrap.sh` and `scripts/keycloak/teardown.sh`.
7. Verify locally: `curl -d "client_id=solarpro-web&grant_type=password&username=engineer_test&password=Test1234!" http://localhost:8080/realms/solarpro/protocol/openid-connect/token` returns a JWT.

### Phase 2 — Backend JWT middleware

8. Add `python-jose` + `requests` to `requirements.txt` (FOSS-compatible per Project Directive §FOSS).
9. Implement `app/security/keycloak_middleware.py` (skeleton in §10.2).
10. Implement `app/security/decorators.py` exporting `require_jwt`, `require_role`, `require_any_role`, `require_scope`, `require_tenant_match`.
11. Migrate `GET /admin/marketplace` as the pilot — apply `@require_role("marketplace_admin")` first, leave `@admin_required` underneath. Both paths approve in parallel-run.
12. Tests in `tests/security/test_keycloak_jwt.py` + `tests/security/test_role_screen_access.py`.
13. Append entry to `IMPLEMENTATION_LOG.md`.

### Phase 3 — Service accounts

14. Create 5 service account clients in `docs/keycloak/realm-export.json`.
15. Implement `app/security/service_account_client.py` (token fetch + cache).
16. Rewrite each agent loader in `engine/agents/marketplace/_llm.py`, etc. to use service-account tokens.
17. Remove the shared OpenRouter / SMTP API-key path from agent code.
18. Tests in `tests/security/test_service_account.py`.

### Phase 4 — Tenant filter + RLS

19. Implement `app/security/tenant_context.py` — extracts `tenant_id` from JWT, sets Postgres GUC.
20. Rewrite every `web_app.py` query that touches a tenant-owned table to use `current_tenant_id()`.
21. Apply migration `migrations/003_rls_tenant.sql` to live Postgres (with parallel-run safety: app layer still filters AND RLS is forced).
22. Tests in `tests/security/test_tenant_isolation.py`.
23. Q-gate close: update `SECURITY_ARCHITECTURE.md` table to mark 1.1, 1.2, 3.2 closed.

### Phase 5 — Frontend OIDC

24. Implement `app/auth/oidc_routes.py` — `/auth/login`, `/auth/callback`, `/auth/logout`.
25. Update `templates/base.html` and `templates/login.html` per §11.1.
26. Add `?legacy=1` emergency form behind a feature flag.
27. Tests in `tests/security/test_login_logout.py`.

### Phase 6 — MFA + audit unification

28. Enable OTP required-action on the four roles (§14.2).
29. Build / install Keycloak event listener JAR. Configure it to POST to `/api/keycloak/events` on SolarPro.
30. Implement `/api/keycloak/events` handler that writes to `audit_log`.
31. Wire `_audit_denial` into the middleware (skeleton above).
32. Tests in `tests/security/test_mfa.py`, `tests/security/test_audit_log.py`.

### Phase 7 — User migration + cutover

33. Implement `scripts/migrate_users_to_keycloak.py`.
34. Email broadcast 14 days before cutover (Brevo).
35. Cutover day: apply partial import; flip `KEYCLOAK_ISSUER` env; deploy; smoke test.
36. 7-day rollback window. Day +14: drop `users.password_hash`, remove legacy form, deploy.
37. Update `CLAUDE.md` to reflect the new authn/authz surface.
38. Update `context.MD` with the migration summary.

### 19.1 Implementation note

Each task is 0.5–2 days of work. Owner availability for sign-off windows on the end of phase 0, 4, 7 is the bottleneck, not the engineering itself.

---

## 20. Development schedule + milestones

| Week | Phase | Owner sign-off | Deploy |
|---|---|---|---|
| 1 (Mon–Tue) | Phase 0: Inventory + ADR | end of Tue | none |
| 1 (Wed–Fri) | Phase 1: Local Keycloak | self-merge | local only |
| 2 (Mon–Tue) | Phase 2: Backend JWT middleware (pilot route) | self-merge | staging |
| 2 (Wed) | Phase 3: Service accounts | self-merge | staging |
| 2 (Thu–Fri) | Phase 4: Tenant filter + RLS | end of Fri | staging + Postgres prod (migration applied) |
| 3 (Mon–Tue) | Phase 5: Frontend OIDC | self-merge | staging |
| 3 (Wed) | Phase 6: MFA + audit unification | self-merge | staging |
| 3 (Thu) | Phase 7 prep: announce cutover, broadcast email | owner approval to send | n/a |
| 3 (Fri) | Phase 7 day-of: cutover | day-of approval | **production** |
| 4 (Mon–Fri) | Phase 7 rollback window | n/a | hotfix only |
| 5 (Mon) | Phase 7 cleanup: drop password_hash, remove legacy form | self-merge | **production** |

Total elapsed time: **5 weeks** from kickoff to clean cutover, assuming owner sign-off windows are honoured.

---

## 21. Final deliverable + acceptance criteria (per brief §18)

At the end of the migration SolarPro must have:

| Capability | Verification |
|---|---|
| Keycloak-powered login | `solarpro.aiappinvent.com/login` redirects to `auth.aiappinvent.com` |
| Central user management | All users provisioned and managed in Keycloak admin console |
| Secure JWT token authentication | Smoke test passes; introspection of any token returns expected claims |
| Role-based authorization | RBAC matrix (§7.5) verified; every cell tested |
| Tenant-based access control | Cross-tenant access denied at app + DB layer |
| MFA-ready login | OTP enforced for the four required roles; recovery codes documented |
| Service account security for AI agents | Each of the 5 agents has its own client credentials and minimum scopes |
| Protected APIs | Every protected route returns 401 without JWT, 403 without role, 200 with both |
| Protected frontend routes | UI hides menus the user can't reach; backend denies anyway |
| Full audit logging | Every event in §15.1 lands in `audit_log` |
| Zero licensing cost | Keycloak Apache 2.0; no paid plan |
| Open-source identity platform | All components FOSS per `CLAUDE.md` FOSS rule |

The brief closes with: "Best recommendation: implement Keycloak first, then gradually remove the old SolarPro authentication code after all frontend routes, backend APIs, and tenant permissions are fully tested." This plan honours that rule verbatim — phase 1 stands up Keycloak, phase 2 begins the parallel run, phase 7 removes the old code only after the migration test has passed.

---

## 22. Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cutover-day auth outage | Low | Catastrophic | Rollback window 7 days; legacy `?legacy=1` form retained; owner-controlled fallback for marc667us |
| Token-storage bug leaks JWT via `localStorage` | Medium | High | Frontend code review per §17.3; CSP header denies inline scripts |
| Tenant-mismatch policy gap (URL says tenant A, JWT says A but resource belongs to B) | Medium | Catastrophic | Authorization Services policy per §10.4; tests in `test_tenant_isolation.py` exercise the cross-FK case |
| AI agent over-scoped (e.g. catalogue-agent gets `product:approve`) | Medium | High | Per-agent scope review at Phase 3 sign-off; audit_log monitors agent actions |
| Keycloak Postgres outage breaks every login | Low | High | Two-replica Keycloak; Postgres PITR; documented DR runbook (§5.5) |
| MFA recovery flow abuse | Medium | Medium | Admin-controlled override; recovery codes rate-limited |
| User migration email rejected as spam | Medium | Low | Use Brevo with SPF + DKIM aligned; alternate communication channel (in-app banner) for 14 days before cutover |
| RLS policy mistake breaks legitimate read | High | Medium | Phase 4 ships behind a feature flag; per-table observability counts the deny rate |
| Loss of marc667us session during cutover | High | Medium | `?legacy=1` form retained; pre-issued admin recovery code stored in operator's password manager |
| Service-account secret leak | Low | High | Vault rotation 90 days; admin event listener flags any token request from outside the K8s pod CIDR |

---

## 23. References

### 23.1 Source documents

- `C:\Users\USER\Documents\pvsolar1\kubernates\secmigrate.txt` — the brief that drove this plan (18 sections + supplement + recommended expansion).
- `C:\Users\USER\Documents\pvsolar1\kubernates\securityMD (1).txt` — related security spec.
- `C:\Users\USER\Documents\pvsolar1\kubernates\Add to security MD.txt` — additional security notes.
- `C:\Users\USER\Documents\pvsolar1\improvements\dontforget1.txt` — Project Execution Directive (mandates audit log, tenant isolation, RLS, etc.).
- `docs/SECURITY_ARCHITECTURE.md` — current authn/authz state + Q-gate gap log.
- `docs/SECRETS_ENGINE_PROPOSAL_v3.md` — Vault-based credential broker (carries Keycloak's admin password and service-account secrets).
- `docs/DATABASE_DESIGN.md` — tenant column model + RLS policies.
- `CLAUDE.md` Marketplace section — the surface this migration replaces.

### 23.2 External

- Keycloak documentation — https://www.keycloak.org/documentation
- OpenID Connect Core 1.0 — https://openid.net/specs/openid-connect-core-1_0.html
- RFC 6749 (OAuth 2.0) — https://datatracker.ietf.org/doc/html/rfc6749
- RFC 7636 (PKCE) — https://datatracker.ietf.org/doc/html/rfc7636
- RFC 6238 (TOTP) — https://datatracker.ietf.org/doc/html/rfc6238
- WebAuthn — https://www.w3.org/TR/webauthn-2/
- Argon2id RFC 9106 — https://datatracker.ietf.org/doc/rfc9106/

### 23.3 Implementation-time hand-offs

When Phase 1 begins, the next session should:

1. Re-read this document end-to-end.
2. Check `docs/ARCHITECTURE_DECISIONS.md` for ADR-0007 (must exist before any code lands).
3. Run `docker compose -f docker-compose.keycloak.yml up -d`.
4. Import `docs/keycloak/realm-export.json`.
5. Follow §19's task list, ticking items in `docs/IMPLEMENTATION_LOG.md` after each.

If this document drifts from `secmigrate.txt`, re-read the brief and reconcile — `secmigrate.txt` is the source of truth.

---

**End of plan.**
