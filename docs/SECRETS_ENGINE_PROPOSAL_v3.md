# Dynamic Secrets Engine — Proposal v3

**Author:** Claude Code (Principal Solution Architect / Principal Security Engineer)
**Date:** 2026-06-09
**Supersedes:** `SECRETS_ENGINE_PROPOSAL_v2.md` (supervisor verdict: REVISE — 5 blockers)
**Scope:** SolarPro Global. Template for IPPSP, IPPTH, MEP, Claude App Factory after solar validates.
**Owner requirements (verbatim):** secret engine · credentials on demand · dynamic secret management · no permanent secret credential · scope credentials by time · audit trail

---

## Changelog — v2 → v3

Surgical revisions only. Sections unchanged from v2 are referenced by §; sections that changed are reproduced in full.

| ID | Class | Section changed | Resolution |
|---|---|---|---|
| **N1** | BLOCKER | §2.6 | DEGRADED tier now warms cache from `.env` at boot ONLY, refuses env reads after first Vault success; explicit cold-start behaviour table |
| **N2** | BLOCKER | §3 Phase 1 + new §2.8 | `_EmailClient` refactored to lazy-property fetch; code skeleton specified; explicit "first-read after init" contract |
| **N3** | BLOCKER | §3 Phase 3 split | Phase 3.0 = Postgres migration (separate workstream, references prior 46-item schedule items 1.1/1.2/3.4); Phase 3.1 = Vault `database` engine (only after 3.0) |
| **N4** | BLOCKER | §2.2 + §2.5 | Two audit devices (file + syslog); log-rotation policy; disk-fill alarm; documented Vault "block-on-all-audit-failure" safety behaviour |
| **N5** | BLOCKER | §2.6 | `SOLARPRO_*_PASSWORD` re-tiered as CRITICAL; hard-fail at boot if Vault unreachable; rationale documented |
| N6 | FIX | §2.5 | `_request_id` slot renamed `_vault_req_id`; capture point documented |
| N7 | FIX | §2.5 | `deque(maxlen=10000)` replaces `queue.Queue`; explicit drop counter exported as broker metric |
| N8 | FIX | §2.6 | Production detection: `RENDER=true OR FLASK_ENV=production` — documented at top of `secrets_broker.py` |
| N9 | FIX | §2.7 | `VAULT_ADDR` re-checked per call (negligible perf), not cached |
| N10 | FIX | §3 Phase 2.5 | Baseline = option (c) defer; (a)(b) downgraded to "owner-elected overrides" with required CC-acceptance note |
| N11 | FIX | §2.3 | `.env` rotation uses `os.replace` of `.env.new`; dotenv re-read deferred to next AppRole expiry; mid-request reads use cached value |
| N12 | FIX | §8 DoD | Substitute `./scripts/codex-security-review.sh` for `/security-review` skill (git ref unavailable) |
| N13 | FIX | §2.5 | `threading.Lock` around `hvac.Client` init + mutations; gunicorn fork-safety documented |
| N14 | DOC | §2.5 | Sampling policy fully defined: writes/failures always logged; first-read-per-path-per-minute always logged; remainder sampled 1-in-10 |
| N15 | DOC | §3.4 | Ops manual line: "rollback uses current bootstrap, not backed-up .env" |
| N16 | DOC | §7 | OpenBao rationale honest (community size + track record, not client maturity) |
| N17 | DOC | §5 | "accepted" → "documented non-compliance with literal owner spec; bootstrap is a separate threat tier" |
| N18 | DOC | §2.5 + §7 | Anomaly detection out of Phase 1–3 scope; moved to Phase 4 as explicit deliverable, no longer claimed as Phase 1 |

All §1, §4, §6 content unchanged from v2 unless noted.

---

## 1. Problem statement (unchanged from v2 §1.1–1.2)

See v2 §1. The two-credential-layer model (bootstrap vs. application) and the requirement-vs-phase matrix carry over verbatim.

**One reinforcement:** the literal owner requirement "no permanent secret credential" is achievable for *application* secrets only at Phase 3.1 (DB creds), and is documented non-compliance for *bootstrap* credentials. v3 does not handwave this.

---

## 2. Architecture (revised sections)

### 2.1 Why Vault OSS

Unchanged from v2.

### 2.2 Deployment topology (N4 — two audit devices, log rotation)

```
┌─────────────────────────────────────────────────────────────┐
│  Owner laptop / development                                 │
│   - Docker Desktop                                          │
│   - vault:latest container, port 8200                       │
│   - storage backend: file (encrypted volume on host)        │
│   - audit device 1: file → ./vault-audit/audit.log          │
│       (logrotate.d: 100 MB cap, 7-day retention)            │
│   - audit device 2: socket → ./vault-audit/audit.sock       │
│       (drained by audit_log_drainer.py → secret_audit DB)   │
│   - disk-fill alarm: cron checks df > 90% on the audit vol  │
│     and emits an app warning + tries to rotate early        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ (Vault HTTP API + AppRole)
┌─────────────────────────────────────────────────────────────┐
│  SolarPro Flask app                                         │
│   (see §2.5 for broker / §2.6 for tiering)                  │
└─────────────────────────────────────────────────────────────┘
```

**Why two devices:** Vault's safety mechanism blocks ALL requests if every configured audit device fails to write. A single-device deployment is a hidden single point of failure. With two devices, a write to either one keeps the gate open.

**Log rotation:** `logrotate.d` configuration shipped at `vault-config/logrotate.conf` rotates `audit.log` at 100 MB or daily, retains 7 days, gzip-compresses old files. Vault's audit hash is preserved across rotation by use of the standard `compress` + `copytruncate` flags.

**Disk-fill alarm:** a 5-minute cron checks `df --output=pcent /vault-audit` and:
- ≥85% → WARN row in `secret_audit` (logged to itself, recursively safe via socket device).
- ≥95% → triggers `logrotate --force /etc/logrotate.d/vault-audit.conf` to free space.
- 100% → both audit devices fail-write → Vault blocks all requests. Hard outage; explicit playbook in `docs/SECRETS_ENGINE_OPERATIONS.md`.

**Production Vault host:** see §3 Phase 2.5 (revised — baseline is defer).

### 2.3 Bootstrap credential model (N11 — atomic `.env` rotation)

Bootstrap tier carried over from v2 §2.3. Rotation mechanism now explicit:

- `vault_secret_id_rotator.py` (cron @ hourly):
  1. POST to Vault `auth/approle/role/solarpro-app/secret-id` using a separate **rotation token** (NOT the app's runtime token).
  2. Receive new `secret_id`.
  3. Write `.env.new` containing the same content as `.env` with the `VAULT_SECRET_ID` line replaced.
  4. `os.replace(".env.new", ".env")` — atomic at the OS level on POSIX and Windows (Python 3.3+).
  5. App's running process **does not re-read** `.env` until its current AppRole token expires (default 1h). At that point, on AppRole re-login, dotenv re-loads, picks up the new `secret_id`.
- **No mid-request reads of `.env`.** The app caches `VAULT_SECRET_ID` in-memory from boot. This eliminates the race.
- **Rollover gap:** if rotation succeeds but the running app's token expires *before* dotenv reload (i.e., misconfigured TTLs), the next AppRole login uses the OLD `secret_id` and fails — app then re-reads `.env`, retries with NEW `secret_id`, succeeds. Worst case: one failed request, retry succeeds.

### 2.4 Secret-engine layout (unchanged from v2)

See v2 §2.4. `OLLAMA_URL`/`RENDER_API_KEY` exclusions unchanged.

### 2.5 `secrets_broker.py` (N4, N6, N7, N13, N14, N18 — comprehensive revision)

**Module-level contract** (top of `secrets_broker.py`):

```python
"""
secrets_broker.py — audit-wrapping client to HashiCorp Vault.

Production-detection contract (N8):
    "production" = os.environ.get("RENDER") == "true"
                OR os.environ.get("FLASK_ENV") == "production"
    Tier="DEV" fallthrough is REFUSED in production.

Fork/thread safety (N13):
    The module-level Vault client is created lazily under a threading.Lock.
    Gunicorn workers fork — each worker initializes its own client on first
    use. No shared state between workers; no shared state between processes.

Test contract (N9):
    If VAULT_ADDR == "test://memory" (re-checked PER CALL, never cached),
    fall through to _FakeVault reading from _TEST_SEED dict.

Audit policy (N14):
    - writes / failures / first-read-per-path-per-minute: ALWAYS logged
    - other reads: sampled 1-in-10 (BROKER_AUDIT_SAMPLE_N, env override)
    - drop counter exported as broker.audit_drops metric for monitoring

Audit transport (N4, N7):
    - In-process: collections.deque(maxlen=10_000) — explicit oldest-drop
    - Background _audit_flush_worker: 1s tick, batched INSERT to secret_audit
    - Drop event itself logged as a single audit row per minute
"""
```

**`AccessLoggedSecret` (N3, N6 — renamed slot):**

```python
class AccessLoggedSecret:
    __slots__ = ("_value", "_path", "_issued_at", "_ttl",
                 "_vault_req_id")  # (N6: was _request_id; this is Vault's id)

    def get_value(self) -> str:
        if time.time() > self._issued_at + self._ttl:
            raise SecretExpired(self._path)
        _audit_enqueue(_AuditRow(
            occurred_at      = time.time(),
            vault_req_id     = self._vault_req_id,           # from Vault response
            app_req_id       = getattr(g, "request_id", None),  # Flask per-request
            operation        = "read",
            path             = self._path,
            sampled          = _should_sample(self._path),
        ))
        return self._value
```

`_vault_req_id` is captured at construction from the Vault HTTP response's `X-Vault-Request-ID` header; `app_req_id` is captured at access time from Flask's `g.request_id` — they're different IDs joining two different audit logs (Vault's file + the app's `secret_audit` table).

**Buffer + flush (N7):**

```python
_audit_buf: deque[_AuditRow] = deque(maxlen=10_000)
_audit_drops_total = 0
_audit_lock = threading.Lock()  # (N13)

def _audit_enqueue(row: _AuditRow) -> None:
    global _audit_drops_total
    with _audit_lock:
        if len(_audit_buf) == _audit_buf.maxlen:
            _audit_drops_total += 1
            # First drop in a minute is itself emitted as an audit row
        _audit_buf.append(row)

def _audit_flush_worker():
    while True:
        time.sleep(1)
        with _audit_lock:
            if not _audit_buf: continue
            batch = list(_audit_buf)
            _audit_buf.clear()
        _batched_insert(batch)
```

**Sampling policy (N14):**

```python
def _should_sample(path: str) -> bool:
    # Always log first-of-minute per path (kept in a small TTL dict)
    if _first_in_minute(path): return True
    # Always log writes/failures (caller passes operation="write" or "error")
    # That handled by the always-log path in get_value/set_value
    return random.randint(1, BROKER_AUDIT_SAMPLE_N) == 1
```

`writes` and `errors` bypass `_should_sample` and are always enqueued.

**Vault client init (N13 — thread-safe):**

```python
_client: hvac.Client | None = None
_client_lock = threading.Lock()

def _get_client() -> hvac.Client:
    global _client
    # Re-check VAULT_ADDR per call (N9) so tests can flip mode without restart
    if os.environ.get("VAULT_ADDR") == "test://memory":
        return _FakeVault()  # per-call, not cached
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None: return _client
        _client = hvac.Client(url=os.environ["VAULT_ADDR"])
        _approle_login(_client)
        return _client
```

**Anomaly detection (N18):** removed from Phase 1 deliverables. Re-scoped to Phase 4 as an explicit follow-on with a dedicated proposal. The current proposal claims **only**: every read is recorded; offline detection rules are out of scope.

### 2.6 Tiered fallback policy (N1, N5, N8 — comprehensive revision)

**Cold-start semantics (N1):** the broker honors a single `.env`-warm pass at boot per secret. Once Vault has successfully served a secret, the env fallthrough for that path is permanently refused for the process lifetime, even if Vault later goes down.

| Tier | At boot, Vault reachable | At boot, Vault DOWN | Mid-life, Vault DOWN |
|---|---|---|---|
| **CRITICAL** | fetch from Vault | **hard-fail, app refuses to start** | hard-fail; 503 to in-flight requests |
| **DEGRADED** | fetch from Vault, cache | **warm-from-`.env`** (one-shot), log WARN, mark for refresh | serve cached value, log WARN, mark for refresh |
| **DEV** | fetch from Vault | warm-from-`.env`, log INFO | serve cached, log INFO; **refused if RENDER=true OR FLASK_ENV=production** |

The "warm from `.env` at boot only" rule fixes v2's cold-start trap: DEGRADED secrets get a one-time bootstrap from `.env` if Vault is unreachable at startup, so the app comes UP. After Vault becomes available even once, env fallthrough is locked out — preventing silent stale-value usage.

**Tier table (N5 — `SOLARPRO_*_PASSWORD` re-tiered):**

```python
# secrets_broker.py
_TIER = {
    "payment/paystack":        "CRITICAL",
    "payment/stripe":          "CRITICAL",
    "flask/secret_key":        "CRITICAL",
    "database/connection_url": "CRITICAL",   # Phase 3.1+
    "seed/admin":              "CRITICAL",   # (N5) was DEV in v2 — rationale: seeded auth, mis-seed = wrong-password lockout
    "seed/marc667us":          "CRITICAL",   # (N5)
    "email/brevo":             "DEGRADED",
    "email/resend":            "DEGRADED",
    "email/smtp":              "DEGRADED",
    "ai/openrouter":           "DEGRADED",
    "users/<id>/resend":       "DEGRADED",
}
```

CRITICAL secrets at boot with Vault down: app refuses to start, exits non-zero, the supervisor (systemd/Render) emits an alarm. Better than booting with stale auth seeds.

**Production detection (N8):**

```python
def _is_production() -> bool:
    return (os.environ.get("RENDER") == "true"
            or os.environ.get("FLASK_ENV") == "production")
```

Used by tier=DEV path to refuse env fallthrough.

### 2.7 `FakeVault` contract (N9 — per-call check)

Per v2 §2.7, with one change: the `VAULT_ADDR=test://memory` check happens **per call** inside `_get_client()`, not once at module-init. This allows tests to monkeypatch the env var dynamically during a single test session without re-importing the broker module. Negligible perf cost — one `os.environ.get` per call.

### 2.8 `_EmailClient` refactor — Phase 1 contract (N2)

v2 hand-waved how api_manager picks up rotated values from Vault. v3 specifies:

```python
# api_manager.py (Phase 1 refactor)

class _EmailClient:
    def __init__(self, store: _Store):
        self._s = store
        # NO _load() here. All fields are lazy properties (below).

    @property
    def brevo_key(self) -> str:
        # broker handles Vault fetch + caching + tier=DEGRADED fallback
        return secrets.get("email/brevo", tier="DEGRADED")["api_key"]

    @property
    def smtp_host(self) -> str:
        return secrets.get("email/smtp", tier="DEGRADED")["host"]

    # ... same lazy pattern for smtp_port, smtp_user, smtp_pass, smtp_from,
    #     smtp_tls, resend_key, axigen_url, axigen_user, axigen_pass
```

**Effect:** every `_send_email()` call re-reads via the broker. Broker has its own short-TTL cache (default 60s; configurable per path), so we're not actually hammering Vault — but rotations propagate within the cache TTL window. No app restart needed for KV-level rotation.

The same lazy-property pattern applies to all other secret-consuming classes (`_PaymentClient`, etc.).

---

## 3. Phased rollout (N2, N3, N10 — revised)

Every phase ends with: (1) `pytest tests/` 31/0/141, (2) restart `start.py`, (3) tunnel smoke (login → project → email).

### Phase 0 (~45 min) — broker shim
Unchanged from v2 §3 Phase 0.

### Phase 1 (~3.5h — N2 surfaces) — Vault stand-up + api_manager refactor
- Docker compose Vault, init+unseal, owner stores keys offline.
- `docs/SECRETS_BOOTSTRAP.md` written.
- Move into Vault KV: Paystack, Brevo, Resend, SMTP, OpenRouter, Flask SECRET_KEY, seed passwords.
- **`api_manager.py` refactor per §2.8 (N2):** convert `_load()` to lazy properties; existing tests still pass because the broker's `FakeVault` short-circuit returns synthetic values for the test session.
- Update `web_app.py:559` seed callers + `web_app.py:5876` Paystack caller.
- Pytest 31/0/141. Restart. Smoke through tunnel.

### Phase 1.5 (~30 min) — CI bridge
Unchanged from v2 §3 Phase 1.5.

### Phase 2 (~2.5h) — finish solar app callers
Unchanged from v2 §3 Phase 2.

### Phase 2.5 (~1h — N10 revised) — production Vault host
**Baseline:** **option (c) defer.** Production stays on GitHub Secrets bridged to Render env vars exactly as today. The owner spec is satisfied for dev/CI only.

**Owner-elected overrides** (require explicit owner approval, both involve credit-card acceptance which the owner has rejected twice previously per `project_solar_pv` memory):
- (a) $5/mo Hetzner CX11 with Vault container.
- (b) Oracle Cloud Free Tier ARM VM (CC required at signup).

Neither (a) nor (b) is the baseline; both are explicit overrides only.

### Phase 3.0 (~3d — N3 separation) — Postgres migration prerequisite
This is **not** Vault work — it's the Postgres migration already on the prior 46-item quality-gate schedule (items 1.1, 1.2, 3.4 per `project_solar_pv` memory). Reproduced here only because Phase 3.1 depends on it.

- Provision Postgres (Render free Postgres or local docker postgres).
- Migrate solar's SQLite schema via existing `migrations/001_postgresql_schema.sql` + `migrations/002_rls_policies.sql`.
- `web_app.py:get_db()` cuts over to psycopg connection.
- All 31 tests retargeted at Postgres; some may need RLS context-setting fixture additions.
- Pytest 31/0/141 (or new equivalent baseline). Restart. Smoke.

### Phase 3.1 (~1d — was v2 Phase 3) — dynamic database creds
**Only after 3.0.** Wire Vault `database` engine + `solarpro-app` role with 1h TTL. Cut `get_db()` to fetch fresh creds per request from Vault. This is where "no permanent credential" becomes literally true for the DB layer.

### Phase 4 (~1d) — template + roll to other apps
Unchanged from v2 §3 Phase 4. **Plus (N18):** Phase 4 explicitly includes a follow-on proposal for anomaly-detection rules over `secret_audit` data — not part of Phase 1–3 deliverables.

### 3.4 Kill-switch / rollback (N15 documented)

Per v2 §3.4, with one clarification baked into ops manual: **rollback uses the *current* Vault bootstrap, not the `.env.bak` backup.** If Phase N rotated bootstrap after backup-taken, the backup is stale. Restore the *file* but leave the bootstrap line as current.

---

## 4. Cost analysis

Unchanged from v2.

---

## 5. Risks + mitigations (N17 reworded)

| Risk | Probability | Mitigation |
|---|---|---|
| Vault unseal key loss | low, catastrophic | 3-of-5 Shamir; offline storage (password manager + safe + USB) |
| AppRole `secret_id` leak | medium | hourly rotation (Phase 2) + Vault audit-log alert on >5 read attempts/min |
| Vault unreachable mid-flight | medium | tiered fallback per §2.6 |
| Vault unreachable at cold start | medium | DEGRADED/DEV `.env`-warm one-shot at boot (§2.6); CRITICAL refuses to start (correct posture) |
| Single audit device failure blocks all Vault requests | resolved | two devices (file + socket); disk-fill alarm; rotation policy (§2.2) |
| Render-free spin-down breaks Vault | n/a | prod Vault not on Render (§3 Phase 2.5) |
| Tests break on Vault dependency | resolved | `FakeVault` short-circuit per-call (§2.7) |
| Tunnel app on old code post-edit | high | per-phase explicit restart + smoke (§3) |
| Sync DB write hammers SQLite | resolved | batched deque + flush worker + sampling (§2.5) |
| Bootstrap creds in `.env` are permanent | **documented non-compliance with literal owner spec** | Bootstrap is a separate threat tier (§1.2, §2.3); rotated hourly; narrowly scoped to Vault login only. Not the same as application secrets. |
| `OLLAMA_URL` rotates and breaks app | medium | excluded from Vault (§2.4); separate Cloudflare Named Tunnel workstream |
| api_manager has captured stale values | resolved | lazy properties (§2.8); rotation propagates within broker cache TTL |
| Phase 3 prerequisite (Postgres) under-scoped | resolved | split: 3.0 = Postgres migration, 3.1 = Vault DB engine (§3) |

---

## 6. Open questions for owner

1. **Phase 2.5 baseline.** v3 commits to (c) defer as the baseline. If owner wants (a) Hetzner or (b) Oracle, explicit override needed.
2. **Audit retention:** 90 days local file + permanent DB rows, OR rotate DB rows after 1 year?
3. **Per-user `users/<id>/resend`** — acceptable explosion of N secrets per user?
4. **Hourly `secret_id` rotation alert** — if cron fails silently, AppRole token eventually expires. Add passive alert mechanism in Phase 2?
5. **Audit-log disk threshold** — proposal sets 85% WARN / 95% rotate-now. Reasonable, or tighter?

---

## 7. Non-goals (N16 reworded)

- HSM integration.
- Vault Enterprise features.
- SAML / SSO for Vault UI.
- Kubernetes Vault integration (out-of-cluster only).
- Encrypting `.env` at rest with gpg as interim.
- Rotating GitHub Secrets via Vault (one-way bridge only).
- Replacing `OLLAMA_URL` discovery (separate workstream).
- Solving Brevo's 300/day cap (not a secrets problem).
- Anomaly detection over `secret_audit` (Phase 4 deliverable; see §2.5).
- **Migrating to OpenBao in v3.** *Honest reason:* HashiCorp Vault has a larger community, longer production track record, and broader documentation. `hvac` works against OpenBao too, so migration is straightforward later. Picking Vault now is a community-size call, not a client-maturity call.

---

## 8. Definition of done — Phase 1 (N12 — substitute reviewer)

- [ ] `docker-compose.vault.yml` boots sealed Vault on :8200 with TWO audit devices.
- [ ] `vault operator unseal` clean with 3 of 5 keys; owner stores all 5 offline.
- [ ] `secrets_broker.py` resolves via Vault when `VAULT_ADDR` set, `FakeVault` when `VAULT_ADDR=test://memory`, `.env` warm-at-boot per §2.6 tiering.
- [ ] `secret_audit` table populated by batched writes + sampling.
- [ ] `tests/test_secrets_broker.py` — 7 contract tests pass.
- [ ] `pytest tests/` still **31 passed, 141 skipped, 0 failed**.
- [ ] `start.py` restarted cleanly; tunnel smoke OK; `/api/ping` 200; login, project create, calc, PDF, email send all work.
- [ ] `docs/SECRETS_ENGINE_OPERATIONS.md` covers: unseal, rotate AppRole, query audit log, restore unseal shares, log rotation, disk-fill playbook.
- [ ] `docs/SECRETS_BOOTSTRAP.md` documents bootstrap-credential threat tier.
- [ ] **`./scripts/codex-security-review.sh` passes** (substitutes for `/security-review` skill — git `origin/HEAD` ref unavailable in this repo per `git remote -v` check on 2026-06-09).
- [ ] No CRITICAL findings from `./scripts/codex-review.sh`.

---

**Status:** Draft v3 — addresses all 5 blockers, 8 fix-in-Phase-0 items, and 5 documented-acceptance items from v2 supervisor review. Ready to drive Phase 0 implementation pending owner sign-off on §6 questions.
