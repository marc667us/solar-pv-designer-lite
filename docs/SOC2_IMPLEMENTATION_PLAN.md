# SOC 2 Type II — Implementation Plan for `solar-pv-designer-lite`

> Source directive: `C:\Users\USER\Documents\pvsolar1\soc 2 implement.txt` (20-phase greenfield prompt).
> Adapted to this app's reality: 10K-line Flask monolith, Render hosting, Postgres in prod, Keycloak OIDC live, baseline `app/security/` package already in place.
> Precedence: this plan is scoped to **`solar-pv-designer-lite`** only. The pvsolar1 greenfield directive does **not** override this app's own `CLAUDE.md`.

---

## 0. Framing

The directive is a from-scratch checklist. This app is not from-scratch. So this plan is reorganised into **4 milestones × ~1.5 weeks each**, ordered by risk-reduction per engineer-day, every line item tagged ✅ done / 🟡 partial / 🔴 missing against today's repo.

Estimates assume Claude + Codex working the standing four-gate workflow, parallelising independent tasks (per the App Factory speed rule). They do **not** assume a solo engineer typing every line.

**Total to SOC 2 Type I readiness: ~6 weeks (28 engineer-days).** Type II observation window adds 3 months calendar-time after Type I close.

---

## 1. Current Baseline (already meets or partially meets SOC 2)

| Control | Status | Where it lives |
|---|---|---|
| Centralised IdP (Keycloak OIDC PKCE) | ✅ | `auth.aiappinvent.com`, `app/auth/oidc_routes.py` |
| MFA at IdP | 🟡 capable, not enforced | KC realm policy length(8); MFA flow not required |
| RBAC decorator | ✅ | `app/security/decorators.py` (`@require_role`) |
| Tenant context middleware | ✅ | `app/security/tenant_context.py` |
| Audit log writer | ✅ | `app/security/audit.py` |
| Keycloak event sink | ✅ | `app/security/keycloak_events.py` |
| Service-account / internal-call discipline | ✅ | `app/auth/internal_calls.py`, `app/security/service_account_client.py` |
| Postgres production DB | ✅ | Render Postgres (cutover 2026-06-13) |
| Row-Level Security DDL | 🟡 partial | `migrations/003_rls_tenant.sql` (subset of tables) |
| Marketplace perf indexes | ✅ | 15 indexes added 2026-06-23 |
| Workflow dry-run gate | ✅ | 3 workflows gated; pattern documented |
| Security test suite | 🟡 10 files exist | `tests/security/` |
| CI pipeline | 🟡 basic | `.github/workflows/ci.yml` (lint + tests only) |
| HTTPS + custom domain | ✅ | Let's Encrypt at `solarpro.aiappinvent.com` |
| Secrets in env, not git | ✅ | Render env + GitHub Secrets |
| Architecture docs scaffolded | ✅ | `docs/SECURITY_ARCHITECTURE.md`, `SECURITY_MIGRATION_KEYCLOAK.md`, `ADR-0007` |
| Phase B Postgres migration runbook | ✅ | `docs/PHASE_B_RUNBOOK.md` |

**Honest gaps to close before milestones begin:**
- `KEYCLOAK_ENABLED=false` is still the safe default on some routes → SOC 2 auditor will see "auth can be bypassed by config" → must flip default and remove the flag.
- Many DB calls bypass the `tenant_context.set(...)` set/reset pair → coverage measurement needed before promising RLS.
- No backups tested for restore; no DR plan written.
- No malware scanning on uploads (only file-type / size).
- No observability stack (no Prometheus / no error tracker).
- No formal policies (Information Security Policy, AUP, Vendor Mgmt, etc.).

---

## 2. Milestones

### **M1 — Close the IAM + Multi-Tenant Gap (1 week, ~5 engineer-days)**

Maps to Directive Phases 1, 2, 3 + the open Phase A/B Keycloak items.

| # | Task | File / target | Effort |
|---|---|---|---|
| 1.1 | Flip `KEYCLOAK_ENABLED` default to `true`; delete bypass branch + `legacy=1` cookie path. | `web_app.py`, `app/security/decorators.py` | 0.5 d |
| 1.2 | Enforce MFA (TOTP) on KC realm flow for `Platform Admin`, `Tenant Admin`, `Finance Officer`, `Auditor`. | KC realm export + `apply-keycloak-migrations` workflow | 0.5 d |
| 1.3 | Run Phase B migration 005 (already gated workflow, date ≥ 2026-06-30). | `gh workflow run "Apply Migration 005 (Phase B)" -f confirm=PHASE_B` | 0.25 d |
| 1.4 | Add missing roles: `Supplier Staff`, `Electrical Estimator`, `Electrician`, `Read Only`, `API Client`, `AI Agent`, `Background Worker`. Map to KC client roles. | `app/security/decorators.py`, KC realm | 0.5 d |
| 1.5 | Refresh tenant inventory (`docs/auth_inventory.csv` already exists with 517 callsites); identify untenanted callsites. | `scripts/tenant_inventory.py` | 0.5 d |
| 1.6 | Extend `migrations/003_rls_tenant.sql` to **every** tenant-owned table; apply via gated workflow. | `migrations/006_rls_full.sql` | 1 d |
| 1.7 | Enforce `tenant_context.set()` set/reset on every request via WSGI `before_request` hook. | `app/security/tenant_context.py` + `web_app.py` | 0.5 d |
| 1.8 | Logout regression test: token revoked, `session_version` bumped, browser-back leaks nothing. | `tests/security/test_oidc_routes.py` | 0.25 d |
| 1.9 | Architecture diagrams: logical, network, trust boundaries, auth flow, RLS layer. Mermaid in markdown. | `docs/architecture/*.md` | 0.5 d |

**Exit:** every endpoint requires KC token; every tenant table has RLS + `tenant_id`; MFA enforced for elevated roles; `tests/security/` pass on Postgres. No `KEYCLOAK_ENABLED` env var anywhere.

---

### **M2 — Data, File, API, Agent Hardening (2 weeks, ~10 engineer-days)**

Maps to Directive Phases 4, 5, 6, 7.

| # | Task | File / target | Effort |
|---|---|---|---|
| 2.1 | App-level field encryption (AES-256-GCM via `cryptography`) for: bank details, supplier API keys, AI conversation contents, financial models. Verify Render Postgres at-rest encryption is on. | `app/security/field_crypto.py` + migration | 1 d |
| 2.2 | Object storage → Cloudflare R2 (or S3-compatible). Encrypted at rest. Tenant-prefixed key path. | `app/storage/object_store.py` | 1 d |
| 2.3 | Upload pipeline: `python-magic` sniff, size cap, **ClamAV** scan, SHA-256 dedup. | `app/storage/upload_guard.py` | 1 d |
| 2.4 | Rate limiting (`flask-limiter` + Redis). Per-IP and per-user buckets. | `app/security/rate_limit.py` | 0.25 d |
| 2.5 | Output filtering: strip PII/financial fields per caller role. | `app/security/output_filter.py` | 1 d |
| 2.6 | pydantic schemas on every `POST/PUT/PATCH` (`extra="forbid"` for mass-assignment defence). ~60 endpoints. | `app/schemas/*.py` | 2 d |
| 2.7 | CSRF audit + close gaps (partial via `test_csrf.py`). | `web_app.py` | 0.5 d |
| 2.8 | SSRF defence on lit/datasheet proxy + URL fetchers. Allowlist + IP-pinning. | `web_app.py` | 0.25 d |
| 2.9 | AI agent permission inheritance + human approval gate on: price changes, supplier approval, RFQ send, contract gen, PO issue, data deletion, bulk catalogue recheck. | `app/agents/governance/approval_gate.py` | 1.5 d |
| 2.10 | OWASP ZAP baseline scan → fix Highs. | one-off | 1 d |

**Exit:** no plaintext sensitive fields in DB; every upload scanned; every API endpoint has schema + rate-limit + RBAC + tenant filter + audit log; ZAP baseline returns zero High.

---

### **M3 — Audit, Monitoring, DevSecOps (1.5 weeks, ~8 engineer-days)**

Maps to Directive Phases 8, 9, 10, 11, 12.

| # | Task | File / target | Effort |
|---|---|---|---|
| 3.1 | Audit completeness pass: every Directive Phase 8 event emits a row. Single helper enforces fields. | `app/security/audit.py` | 1.5 d |
| 3.2 | Immutable audit table: revoke UPDATE/DELETE from app role; add `prev_hash` chain. | `migrations/007_audit_immutable.sql` | 0.5 d |
| 3.3 | Structured JSON logging with `request_id` correlation. | `logging_config/structured_logger.py` | 0.5 d |
| 3.4 | Observability — Grafana Cloud Free + Loki + Prometheus. | `monitoring/` + workflow | 1 d |
| 3.5 | Error tracker — Sentry SaaS free (5K events) or GlitchTip self-hosted. | `app/observability/errors.py` | 0.25 d |
| 3.6 | Alerts (Slack + email): 5xx spike, auth failures, queue depth, disk, cert expiry, backup failure. | Alertmanager rules | 0.5 d |
| 3.7 | CI security pipeline: `semgrep`, `pip-audit`, `bandit`, `trivy fs`, `gitleaks`. Fail on High. | `.github/workflows/security.yml` | 1 d |
| 3.8 | Pre-commit hooks: `gitleaks`, `ruff`, `black`, `bandit`. | `.pre-commit-config.yaml` | 0.25 d |
| 3.9 | Container scan: `trivy image` against prod image. | `.github/workflows/security.yml` | 0.25 d |
| 3.10 | Test coverage to 70% on critical paths (marketplace, supplier portal, exports, uploads, rate-buildup, project library). | `tests/` | 2.25 d |

**Exit:** every audit event in the directive emits an immutable row; CI fails on any High security finding; dashboards show auth-failure rate, p95 latency, error rate, queue depth; coverage ≥ 70%.

---

### **M4 — Policies, Backup/DR, Evidence, Readiness (1.5 weeks, ~5 engineer-days + external)**

Maps to Directive Phases 13, 14, 15, 16, 17, 18, 19, 20.

| # | Task | Where | Effort |
|---|---|---|---|
| 4.1 | Backups: Render PG hourly snapshot + nightly logical dump → R2 immutable bucket, 30/90/365 retention. Checksum verify. | `.github/workflows/backup-postgres.yml` | 0.5 d |
| 4.2 | Tested restore workflow: restore latest dump into isolated DB; run schema + row-count assertions. Prove RPO < 1 h, RTO < 4 h. | `.github/workflows/backup-restore-test.yml` | 0.5 d |
| 4.3 | DR + BCP plan (from templates, tailored). | `docs/DR_PLAN.md`, `docs/BCP.md` | 0.5 d |
| 4.4 | DR tabletop drill + signed log. | `docs/dr_drills/2026-XX.md` | 0.25 d |
| 4.5 | 12 policy docs (Directive Phase 15) — adapt open-source templates (Vanta/JupiterOne style). | `docs/policies/*.md` | 1 d |
| 4.6 | Nightly evidence collector: audit-log sample, backup proof, CI security-scan reports, access-review CSV, vuln scan JSON → R2 with date prefix. | `.github/workflows/soc2-evidence.yml` | 0.5 d |
| 4.7 | `/admin/soc2` dashboard: % tables with RLS, % endpoints with `@require_role`, audit-row count, last backup verify, last DR drill, open Trivy/Semgrep Highs, policy status. | new admin route + template | 1.5 d |
| 4.8 | Blue/green deploy: Render preview env per PR + smoke gate + manual approval. | `.github/workflows/deploy-production.yml` | 0.25 d |
| 4.9 | Penetration test — external firm or HackerOne private. Fix Highs. | external | 1 wk wall-clock |
| 4.10 | Internal readiness assessment vs. 96 TSC criteria. | `docs/SOC2_READINESS_REPORT.md` | 1 d |
| 4.11 | Engage external auditor for **SOC 2 Type I** (point-in-time). Type II observation window starts after Type I close. | — | external |

**Exit:** all Directive Phase 20 acceptance items green; readiness report has zero High findings; auditor engaged for Type I.

---

## 3. Decisions the owner has to make before M2 starts

These cost money or change architecture — Claude shouldn't pick unilaterally:

1. **Object storage backend** — Cloudflare R2 (free 10 GB) vs. self-hosted MinIO on $5 VPS vs. S3.
2. **Observability stack** — Grafana Cloud Free vs. self-hosted on $10 VPS vs. Better Stack paid.
3. **Error tracker** — Sentry SaaS free (5K events) vs. self-hosted GlitchTip.
4. **MFA enforcement scope** — all users or only elevated roles? (M1.2 currently scopes to elevated.)
5. **Pen-test budget** — internal ZAP only (free) vs. external firm (~$5-15K) vs. HackerOne private (variable).
6. **Auditor timing** — Type I in Q3 2026 then Type II window starts, or skip Type I and go straight to Type II observation window?

---

## 4. Effort summary

| Milestone | Engineer-days | Wall-clock |
|---|---|---|
| M1 IAM + Tenant | ~5 | 1 week |
| M2 Data + File + API + Agent | ~10 | 2 weeks |
| M3 Audit + Observability + DevSecOps | ~8 | 1.5 weeks |
| M4 Backup + Policies + Evidence + Audit | ~5 + external | 1.5 weeks + auditor wall-clock |
| **Total to SOC 2 Type I readiness** | **~28 engineer-days** | **~6 weeks** |
| Type II observation window | — | + 3 months after Type I |

---

## 5. How this plan plugs into the existing four-gate workflow

Every milestone task ships through the standing pipeline: Claude implements → Codex reviews → Supervisor `/code-review` + `/security-review` + `/verify` → Work Reviewer agent → Work Scheduler marks `approved`. No bypass.

---

*Owner: SolarPro Global. Last revised: 2026-06-25.*
