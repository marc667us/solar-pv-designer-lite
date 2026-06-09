# Dynamic Secrets Engine — Proposal v2

**Author:** Claude Code (Principal Solution Architect / Principal Security Engineer)
**Date:** 2026-06-09
**Supersedes:** `SECRETS_ENGINE_PROPOSAL_v1.md` (verdict: REVISE — 5 criticals, 5 highs)
**Scope:** SolarPro Global. Template for IPPSP, IPPTH, MEP, Claude App Factory after solar validates.
**Owner requirements (verbatim):** secret engine · credentials on demand · dynamic secret management · no permanent secret credential · scope credentials by time · audit trail

---

## Changelog — v1 → v2

Each critical and high finding from the v1 review, and what changed:

| ID | Finding (short) | Resolution in v2 |
|---|---|---|
| **R1** | "No permanent credential" claim broken from day one | §1 honest reframing + §2.3 explicit bootstrap-credential model with separate threat tier |
| **R2** | Vault availability = SPOF for the running app | §2.6 tiered fallback policy (critical hard-fail / non-critical cached-degrade) |
| **R3** | `SecretView` TTL is audit, not security | §2.5 relabels it as **access-audit wrapper**, not a containment primitive |
| **R4** | Sync DB write per secret read hammers SQLite | §2.5 batched ring-buffer + 1s flush worker; high-volume reads sampled |
| **R5** | No `FakeVault` design — tests would break | §2.7 explicit `VAULT_ADDR=test://memory` short-circuit, in-process dict, contract documented |
| **R6** | Audit log not linked to `g.request_id` | §2.5 audit row carries `app_request_id` joined at write-time |
| **R7** | `users.resend_api_key` column not in any phase | §3 Phase 2 explicitly migrates it to `kv/data/solarpro/users/<id>/resend` |
| **R8** | Hot-cutover risk: running tunnel stays on old code | §3 every phase has an explicit "restart `start.py`" step + smoke checklist |
| **R9** | KV secrets still rotate manually | §1.3 honest about which requirements are met when; only DB engine is true dynamic |
| **R10** | `OLLAMA_URL` is itself a rotating tunnel URL | §2.4 deliberately excluded from Vault; tracked separately via Cloudflare Named Tunnel |
| R11 | CI can't reach a laptop-hosted Vault | §3 Phase 1.5 — deploy decouples via GitHub Secrets bridge; only the *app at runtime* uses Vault, not CI |
| R12 | Render-free Vault unworkable (cold-start reseal) | §2.2 production Vault deployment moved entirely off Render |
| R13 | Brevo 300/day cap | acknowledged out of scope (§7) |
| R14 | No kill-switch | §3.4 explicit rollback procedure documented |
| R15 | Non-goals not explicit | §7 expanded |

---

## 1. Problem statement (honest reframing)

The current secrets surface is **static, broad, and unaudited**:

- `.env` files on disk — long-lived plaintext API keys.
- GitHub Secrets — same keys, until manual rotation, no per-step scoping.
- Render env vars — mirrored in prod, lifetime forever.
- `users.resend_api_key` column — plaintext at rest in app DB, undetectable theft.
- **Zero central audit log of secret reads.**

### 1.1 What this proposal actually delivers vs. the owner's six requirements

Honest mapping — corrects the v1 over-promise:

| Owner requirement | Phase 0 | Phase 1 (Vault KV) | Phase 2 (broker complete) | Phase 3 (DB dynamic) |
|---|---|---|---|---|
| Secret engine | shim (broker module) | ✓ Vault KV v2 | ✓ | ✓ |
| Credentials on demand | ✓ (each `get()` is a call) | ✓ | ✓ | ✓ |
| Dynamic secret management | ✗ (still static) | partial (KV rotation cadence only) | partial | **✓ DB creds truly dynamic** |
| **No permanent secret credential** | ✗ | ✗ (bootstrap still in `.env`) | partial (only app keys gone from `.env`) | **only for DB creds** — KV bootstrap still exists |
| Scope credentials by time | audit-only (R3) | KV: lease TTL on issued tokens; KV values themselves still static | same | DB creds: hard 1h TTL, Vault revokes |
| Audit trail | ✓ batched broker writes | ✓ + Vault audit device | ✓ end-to-end | ✓ end-to-end |

**Bottom line:** Phase 3 is the first point where "no permanent credential" is *literally true* — and only for DB creds. Static API keys (Paystack, Brevo, Resend, OpenRouter, SOLARPRO_*_PASSWORD) **remain rotation-only secrets** even at Phase 3 unless their issuer supports an OIDC/JWT exchange (which most of these don't). v2 is honest about this.

### 1.2 What "no permanent credential" realistically means in this stack

There are two credential layers:
- **Bootstrap** — what lets the app prove its identity to Vault. Cannot be eliminated; can only be rotated and scoped. Lives in `.env` (Phase 1) or platform-bound JWT (Phase 3+, requires non-free hosting).
- **Application secrets** — what the app uses to talk to Paystack, Brevo, the DB, etc. *These* can be made dynamic (DB) or short-lived (token leases). KV-stored values themselves stay until rotated.

v2 commits only to what the architecture can actually deliver against each layer.

---

## 2. Architecture

### 2.1 Why Vault OSS — unchanged from v1

HashiCorp Vault OSS (MPL 2.0, pre-BSL releases free for self-host), Python client `hvac`. Decision unchanged.

### 2.2 Deployment topology (revised for R12)

```
┌─────────────────────────────────────────────────────────────┐
│  Owner laptop / development                                 │
│   - Docker Desktop                                          │
│   - vault:latest container, port 8200                       │
│   - storage backend: file (encrypted volume on host)        │
│   - audit device: file -> ./vault-audit/audit.log           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ (Vault HTTP API + AppRole)
┌─────────────────────────────────────────────────────────────┐
│  SolarPro Flask app                                         │
│   - secrets_broker.py (NEW)                                 │
│   - On startup: AppRole login -> 1h token                   │
│   - On secret read: tier-based fetch (see §2.6)             │
│   - On dynamic creds (Phase 3): database/creds/solarpro-app │
└─────────────────────────────────────────────────────────────┘
                          ▲
                          │  (production path — see §3.2)
                          │
┌─────────────────────────────────────────────────────────────┐
│  Production Vault — NOT on Render free tier                 │
│   Options (owner choice, Phase 2.5):                        │
│   (a) self-host on $5 Hetzner CX11 (against zero-cost rule  │
│       — needs explicit owner approval)                      │
│   (b) Vault on a free Oracle Cloud Free Tier VM (ARM, $0)   │
│   (c) Defer prod Vault entirely; prod uses GitHub Secrets   │
│       bridged into Render env vars, only dev uses Vault     │
└─────────────────────────────────────────────────────────────┘
```

**R12 resolution:** Render-free Vault is dropped as an option. Cold-start reseal is unattended-impossible. Production Vault either lives on a paid-or-truly-free VM, or is deferred entirely (option c — preserves zero-cost, partially satisfies owner spec only in dev/CI).

### 2.3 Bootstrap credential model (R1 resolution)

The **bootstrap** is what proves the app to Vault. It cannot be eliminated; it must be acknowledged.

- **Phase 1:** `VAULT_ADDR`, `VAULT_ROLE_ID`, `VAULT_SECRET_ID` in `.env`. Documented as bootstrap-tier credentials, separate from application secrets. Their rotation cadence and threat model is logged at `docs/SECRETS_BOOTSTRAP.md` (new).
- **Phase 2:** add hourly rotation sidecar — `vault_secret_id_rotator.py` runs as a cron entry, fetches a fresh `secret_id` via the Vault `auth/approle/role/<role>/secret-id` admin endpoint, writes it to `.env` atomically, the app re-logs-in on next AppRole expiry.
- **Phase 3+:** swap to **platform-bound auth** *only if* a paid host (or Oracle Free Tier) provides an OIDC issuer. The Render-free OIDC path was a v1 misclaim — it does not exist. Owner decision required.

Honest answer to "no permanent credential": **the bootstrap is a permanent credential**, scoped narrowly to one capability (Vault login), rotated hourly. The owner requirement is met for *application* secrets, not bootstrap.

### 2.4 Secret-engine layout (R10 resolution)

```
kv/data/solarpro/payment/paystack       { secret, public }       — static KV
kv/data/solarpro/payment/stripe         { secret, webhook_secret } — static KV
kv/data/solarpro/email/brevo            { api_key }              — static KV
kv/data/solarpro/email/resend           { api_key }              — static KV
kv/data/solarpro/email/smtp             { host, port, user, pass, from, tls } — static KV
kv/data/solarpro/ai/openrouter          { api_key }              — static KV
kv/data/solarpro/seed/admin             { password }             — static KV (rotated via existing workflow)
kv/data/solarpro/seed/marc667us         { password }             — static KV
kv/data/solarpro/flask                  { secret_key }           — static KV
kv/data/solarpro/users/<user_id>/resend { api_key }              — per-user, R7 resolution
database/config/solarpro                { connection_url, allowed_roles } — Phase 3
database/roles/solarpro-app             { creation_statements, default_ttl: 1h, max_ttl: 24h } — Phase 3, truly dynamic
sys/audit/file                          { path: /vault/audit/audit.log }
```

**Explicitly NOT in Vault (R10):**
- `OLLAMA_URL` — itself a Cloudflare tunnel URL that rotates when the dev box restarts. Treated as runtime configuration, not a secret. Tracked at `docs/CONFIG_ROTATION.md` (new) with a Cloudflare Named Tunnel migration plan as a separate workstream.
- `RENDER_API_KEY`, `RENDER_SERVICE_ID` — deploy-time secrets used by GitHub Actions, NOT runtime. Stay in GitHub Secrets per R11.

### 2.5 `secrets_broker.py` — audit wrapper + batched write (R3, R4, R6)

**Honest naming.** v1 sold `SecretView` as time-scoping; v2 calls it `AccessLoggedSecret` — an **audit wrapper**, not a containment primitive. It cannot prevent in-process leakage. What it **does** is log every access with timestamp, caller, request_id, and TTL-expiry-warning.

```python
# secrets_broker.py — module-level contract
class AccessLoggedSecret:
    """Wraps a secret value with read-time audit logging.

    NOT a security primitive — in-process callers can bypass via __dict__.
    Sole purpose: every legitimate use of get_value() is recorded.

    TTL is advisory only — after expiry, get_value() raises SecretExpired
    so callers RE-FETCH from Vault (forcing a fresh audit trail), but the
    underlying string is unchanged.
    """
    __slots__ = ("_value", "_path", "_issued_at", "_ttl", "_request_id")

    def get_value(self) -> str:
        if time.time() > self._issued_at + self._ttl:
            raise SecretExpired(self._path)
        _audit_queue.put(_AuditRow(
            occurred_at=time.time(),
            request_id=self._request_id,
            app_request_id=getattr(g, "request_id", None),  # R6
            operation="read",
            path=self._path,
        ))
        return self._value
```

**Audit write path (R4):**
- Single `queue.Queue` ring buffer (max 10_000 entries; oldest dropped if full, with a warning logged).
- Background thread `_audit_flush_worker` woken every 1s, drains the buffer, executes one `INSERT ... VALUES (?), (?), ...` batch.
- High-volume callers (e.g. `_send_email` reading `BREVO_API_KEY` 100×/min) get **sampled** at 1-in-N (configurable, default 1-in-10) — full audit on reads that fail or precede a sensitive action.
- This decouples request latency from audit latency. SQLite writer lock is hit ≤1× per second instead of per-secret-read.

**Audit row schema (revised — R6):**

```sql
CREATE TABLE secret_audit (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at     TEXT NOT NULL,
    vault_req_id    TEXT,             -- Vault's request_id (joins to Vault audit log)
    app_req_id      TEXT,             -- Flask g.request_id (joins to app audit_log)
    auth_method     TEXT NOT NULL,
    accessor        TEXT NOT NULL,
    display_name    TEXT,
    operation       TEXT NOT NULL,
    path            TEXT NOT NULL,
    sampled         INTEGER DEFAULT 0,  -- 1 if this row is one-of-N sample
    error           TEXT
);
CREATE INDEX idx_secret_audit_path     ON secret_audit(path);
CREATE INDEX idx_secret_audit_occurred ON secret_audit(occurred_at DESC);
CREATE INDEX idx_secret_audit_app_req  ON secret_audit(app_req_id);  -- R6 cross-join
```

### 2.6 Tiered fallback policy (R2 resolution)

Per-secret tiering at `secrets_broker.py:_TIER`:

| Tier | Behaviour on Vault outage | Examples |
|---|---|---|
| **CRITICAL** | Hard-fail. App refuses to start; running requests 503. | Paystack secret · Stripe webhook secret · Flask SECRET_KEY · DB connection URL (Phase 3) |
| **DEGRADED** | Serve from in-memory last-known-good if <1h old; log WARNING per read. | Brevo · Resend · SMTP · OpenRouter |
| **DEV** | Fall through to `.env` value silently (dev only; refused in production). | `SOLARPRO_*_PASSWORD` (only used at startup seed; if Vault is down at boot in dev, fall to env) |

Tier is declared at the call site:
```python
PAYSTACK_KEY = secrets.get("payment/paystack", tier="CRITICAL")["secret"]
BREVO_KEY    = secrets.get("email/brevo",      tier="DEGRADED")["api_key"]
```

Production refuses to honor `tier="DEV"` (env-var fallthrough disabled when `FLASK_ENV=production`). Documented in the operations manual.

### 2.7 FakeVault contract for tests (R5 resolution)

`secrets_broker.py` short-circuits on a sentinel:

```python
if os.environ.get("VAULT_ADDR") == "test://memory":
    # Use process-local dict. Loaded by the test fixture.
    return _FakeVault()
```

`_FakeVault` reads from `secrets_broker._TEST_SEED` — a module-level dict pre-populated by the test fixture:

```python
# tests/test_app.py — added to app_client fixture
import secrets_broker as sb
sb._TEST_SEED.update({
    "kv/data/solarpro/seed/admin":     {"password": "test-admin-pass"},
    "kv/data/solarpro/seed/marc667us": {"password": "test-owner-pass"},
    "kv/data/solarpro/email/brevo":    {"api_key": "fake-brevo"},
    # ...
})
monkeypatch_session.setenv("VAULT_ADDR", "test://memory")
```

Tests never reach the network. Existing 31 passing tests are protected. A new `test_secrets_broker.py` proves:
1. `tier="CRITICAL"` raises on Vault unreachable.
2. `tier="DEGRADED"` returns cached value with WARNING after Vault is killed mid-test.
3. `tier="DEV"` falls through to env var in dev mode.
4. `tier="DEV"` raises in production mode.
5. `AccessLoggedSecret.get_value()` raises after TTL.
6. Audit queue drains within 2s of flush worker start.
7. Sampling: 100 reads of same secret produce ~10 audit rows (default sample 1-in-10) and 1 unsampled "summary" row.

This becomes the contract the rest of the system depends on.

---

## 3. Phased rollout (revised — R8 explicit restart steps)

Every phase ends with: (1) `pytest tests/` 31/0/141, (2) restart `start.py`, (3) tunnel smoke (login → project → email).

### Phase 0 (~45 min) — broker shim, no Vault yet
- New: `secrets_broker.py` with `_FakeVault` + `os.environ` fallback (no real Vault).
- New: `secret_audit` table in `init_db()`.
- New: `tests/test_secrets_broker.py` covering the 7 contracts above.
- **No callers changed yet.** Plumbing only. Hits 3/6 requirements (on-demand, audit, sample/scope-by-time as audit signal).
- Restart `start.py`. Smoke: still works.

### Phase 1 (~3h) — Vault stand-up, dev only
- `docker-compose.vault.yml`. `vault operator init` + unseal × 3. Owner safekeeps unseal keys.
- Bootstrap creds in `.env`: `VAULT_ADDR`, `VAULT_ROLE_ID`, `VAULT_SECRET_ID`. Documented at `docs/SECRETS_BOOTSTRAP.md`.
- Move into Vault KV: Paystack, Brevo, Resend, SMTP, OpenRouter, Flask SECRET_KEY, seed passwords.
- Update `api_manager.py` and `web_app.py:559` (seed) + `web_app.py:5876` (Paystack) callers. All other callers still use `.env`.
- Pytest 31/0/141. Restart. Smoke through tunnel.

### Phase 1.5 (~30 min) — CI bridge (R11)
- Deploy workflow continues to use **GitHub Secrets only**. CI does NOT auth to Vault.
- A new workflow `sync-vault-to-github.yml` runs manually: reads from Vault (using a dedicated bootstrap role), writes to GitHub Secrets via `gh secret set`. Owner triggers when rotating.
- Production env vars on Render still come from GitHub Secrets via existing sync workflow.

### Phase 2 (~2.5h) — finish solar app callers
- Migrate remaining static-key reads to broker. Includes the `users.resend_api_key` per-user override → `kv/data/solarpro/users/<id>/resend` (R7).
- Remove migrated keys from `.env`.
- Add `vault_secret_id_rotator.py` cron.
- Pytest 31/0/141. Restart. Smoke.

### Phase 2.5 (~1h, owner decision) — production Vault host
- Three options (§2.2): paid Hetzner ($5/mo, breaks zero-cost), Oracle Cloud Free Tier ($0, requires CC at signup which the owner may reject per past pattern), or defer prod Vault (option c — dev/CI only, prod stays on GitHub Secrets bridge).
- **Owner decides.** Until then, prod uses GitHub Secrets and Render env vars exactly as today.

### Phase 3 (~1d) — dynamic database creds
- Provision Postgres (Render free Postgres or local docker postgres).
- Wire Vault `database` engine + `solarpro-app` role with 1h TTL.
- Cut `web_app.py:get_db()` to fetch fresh creds per request.
- **This is the first point where "no permanent credential" is literally true** — for the DB only.

### Phase 4 (~1d) — template + roll to other apps
- `docs/SECRETS_ENGINE_INTEGRATION.md` step-by-step for IPPSP / IPPTH / MEP / Claude App Factory.
- `_ai-coworkers-template/` augmented with `secrets_broker.py` stub + test contract.

### 3.4 Kill-switch / rollback (R14 resolution)

Each phase has a *single* rollback file: the previous phase's `secrets_broker.py`. To revert:
1. `cp secrets_broker.py.bak_phase<N-1> secrets_broker.py`
2. Restore the `.env` keys that were removed (from `.env.bak_phase<N>`).
3. Restart `start.py`.
4. Pytest 31/0/141 confirms parity.

Total rollback time: <5 min per phase. Documented in the operations manual.

---

## 4. Cost analysis — unchanged

| Component | License | Cost |
|---|---|---|
| Vault OSS | MPL 2.0 (pre-BSL release) | $0 |
| Docker Desktop | personal use | $0 |
| `hvac` Python client | Apache 2.0 | $0 |
| Cloudflare Tunnel | free tier | $0 |
| Production host | deferred per §2.2(c) — $0 |
| **Total monthly** | | **$0** |

Phase 2.5 may incur $5/mo if owner picks Hetzner. Explicit owner sign-off required.

---

## 5. Risks + mitigations (revised)

| Risk | Probability | Mitigation |
|---|---|---|
| Vault unseal key loss | low, catastrophic | 3-of-5 Shamir split; owner stores in offline password manager + safe + USB |
| AppRole `secret_id` leak | medium | hourly rotation cron (Phase 2) + Vault audit-log alert on >5 read attempts/min |
| Vault unreachable mid-flight | medium | tiered fallback per §2.6 (CRITICAL hard-fails, DEGRADED serves last-known-good) |
| Render-free spin-down breaks Vault | n/a | resolved — production Vault NOT on Render (§2.2) |
| Test suite breaks on Vault dependency | resolved | `FakeVault` short-circuit (§2.7), 7 contract tests |
| Tunnel app on old code post-edit | high | every phase has explicit restart + smoke step (§3) |
| Sync DB write hammers SQLite | resolved | batched ring buffer + flush worker + sampling (§2.5) |
| Bootstrap creds in `.env` are still permanent | accepted | explicitly acknowledged (§1.1, §2.3); rotation cadence + narrow scope |
| `OLLAMA_URL` rotates and breaks app | medium | excluded from Vault (§2.4); tracked separately via Cloudflare Named Tunnel migration |

---

## 6. Open questions for next review

1. **Phase 2.5 production Vault host**: Hetzner ($5/mo, hard rule violation) vs Oracle Free (CC required) vs defer (option c, partial fulfillment). Owner decision required.
2. **Audit retention**: 90 days local file + permanent DB rows, OR rotate DB rows after 1 year? Compliance-driven.
3. **Per-user `users.resend_api_key`** move (R7) introduces N secrets per user. Acceptable explosion? Or move to per-user broker with single shared service account?
4. **Hourly `secret_id` rotation cron** — if the cron fails, AppRole token eventually expires and app stops booting. Add a passive alert? Phase 2 detail.

---

## 7. Non-goals (expanded — R15)

- HSM integration.
- Vault Enterprise features (namespaces, replication, performance standby).
- SAML / SSO for Vault UI (admin uses root token sparingly + AppRole for app).
- Kubernetes integration (k8s manifests reference Vault as out-of-cluster service only).
- Encrypting `.env` at rest with gpg as an interim.
- Rotating GitHub Secrets via Vault (one-way bridge only).
- Replacing `OLLAMA_URL` discovery (separate workstream, §2.4).
- Solving Brevo's 300/day cap (not a secrets problem).
- Migrating to OpenBao in v2 (deferred to v3+ once OpenBao Python client matures).

---

## 8. Definition of done — Phase 1 ("shippable" for dev)

- [ ] `docker-compose.vault.yml` boots sealed Vault on :8200.
- [ ] `vault operator unseal` clean with 3 of 5 keys; owner stores all 5 offline.
- [ ] `secrets_broker.py` resolves `kv/data/solarpro/payment/paystack` via Vault when `VAULT_ADDR` set, `.env` otherwise (DEV tier), `FakeVault` when `VAULT_ADDR=test://memory`.
- [ ] `secret_audit` table populated by `secrets_broker.py` with batched writes + sampling.
- [ ] `tests/test_secrets_broker.py` — 7 contract tests pass.
- [ ] `pytest tests/` still **31 passed, 141 skipped, 0 failed**.
- [ ] `start.py` restarted cleanly; tunnel smoke OK; `/api/ping` 200; login, project create, calc, PDF, email send all work.
- [ ] `docs/SECRETS_ENGINE_OPERATIONS.md` covers: unseal, rotate AppRole, query audit log, restore unseal shares.
- [ ] `docs/SECRETS_BOOTSTRAP.md` documents the bootstrap-credential threat tier.
- [ ] Codex CLI review passes (`./scripts/codex-security-review.sh`).
- [ ] No CRITICAL findings from `/security-review`.

---

**Status:** Draft v2 — addresses all 5 critical and 5 high findings from v1 review. Awaiting next review pass + owner sign-off on §6 questions before Phase 0 work begins.
