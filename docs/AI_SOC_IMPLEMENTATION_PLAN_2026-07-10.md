# AI Support & Security Operations Centre (AI-SOC) — Implementation Plan

**Date:** 2026-07-10
**Source spec:** `C:\Users\USER\Documents\pvsolar1\agentic support.txt` (2,044 lines, read in full)
**Target:** embedded inside the existing SolarPro Global app. **No separate application.**
**Status:** PLAN — not yet approved, not yet started.

---

## 0. How this plan was derived

The source file contains **three overlapping master prompts**, written at different times, describing
the same capability at three different scales. They are not consistent with one another:

| Pass | Lines | Agents proposed | Scope |
|---|---|---|---|
| A — "Embedded Technical Support and Security Operations Plan" | 1–798 | 7 | Embedded, orchestrator + 3 tiers + security + knowledge + notifications |
| B — "AI Support Operations Center (AI-SOC)" | 808–1368 | ~40 (14 Tier-1 monitors, 13 Tier-2 specialists, 7 Tier-3 principals, 16 security agents) | Full NOC + SOC + DevOps centre |
| C — "Integrated Tier 1/2/3 … Operations Agents" | 1373–2044 | 10 | Embedded, adds Documentation / Notification / Remediation / Approval agents |

Where they conflict, this plan follows **A and C** (7–10 agents, embedded) and treats **B's ~40 agents
as a taxonomy of *signals to monitor*, not as forty processes to run.** Pass B itself concedes the
governing principle: *"Claude Code should never monitor the application directly"* (line 810).

All three passes agree on the one rule that matters, and this plan treats it as inviolable:

> Agents may **diagnose** automatically and execute only **safe, reversible** fixes automatically.
> Code changes, database changes, security-policy changes and production deployments pass through
> testing and a human approval gate. (lines 798, 1368, 2044)

---

## 1. What already exists — reuse map

The spec says *"Reuse existing entities where available"* (line 754) and *"Do not create a separate
application"* (line 771). Verified against the live codebase on 2026-07-10:

| Spec requirement | Already exists | Evidence |
|---|---|---|
| Admin Notification Inbox | **YES** | `admin_notifications` table; `POST /admin/indicators/clear`; navbar bell badge |
| Immutable audit trail | **YES** | `audit_logs` + SHA-256 hash chain (SOC 2 sprint, mig 016) |
| Structured logs, redacted | **YES** | `logging_config/structured_logger.py` → `log_app / log_error / log_audit / log_security / log_ai / log_queue` |
| Incident register (user-facing) | **PARTIAL** | `tickets` + `ticket_replies` (+ `/api/assistant/escalate` opens a P-high ticket) |
| Knowledge base | **PARTIAL** | `helpline_learned_kb` — a helpline answer store, **not** an incident-article store |
| Operations Centre UI | **YES** | `/admin/operations`, `/admin/logs`, `/admin/ops/*` (34 endpoints) |
| Remediation primitives | **YES** | `/admin/ops/cache/clear`, `/queue/restart`, `/db/vacuum`, `/backup/run`, `/security/revoke-all-sessions`, `/system/pip-audit`, `/system/load-test` |
| Health / liveness | **YES** | `/api/health*`, `/api/health/boot` (added 2026-07-10), `/metrics` (Prometheus) |
| Monitoring definitions | **YES (not running)** | `monitoring/prometheus/alerts.yml` — HighErrorRate, SlowResponseTime, BruteForce, TenantIsolationViolation |
| Failed-login / brute-force signal | **YES** | `login_failures` table + 5-fail/15-min lockout |
| Tenant isolation + RLS | **YES** | 47/48 tables FORCE RLS, 45 policies |
| CI/CD + gated deploy | **YES** | GitHub Actions; `Force Render Deploy`; `scripts/quality-gate.sh`; Codex reviewer |
| Agent-run logging pattern | **PARTIAL** | `capital_investment_agent_runs` (project-scoped; not a general shape) |
| Error store | **YES** | `error_logs`, `email_logs`, `marketplace_audit_log`, `boq_audit_log` |
| Background monitor loop | **YES (misfit)** | `web_app.py:11322` `_monitor_thread` — a *sales prospecting* scanner, not health monitoring. Do not overload it. |

**Genuinely missing** (these are the build): `support_incidents`, `support_events`, `support_actions`,
`support_approvals`, `support_agent_runs`, `support_runbooks`, `security_incidents`,
`security_evidence`, `knowledge_articles`, `deployment_changes`, and — critically — **a kill switch**.

> The spec requires *"Kill switch for all automated remediation"* and *"Admin ability to pause any
> agent"* (lines 1997–1999). **No feature-flag or kill-switch mechanism exists in the app today.**
> That is Slice 0. Nothing automated ships before the off-switch does.

---

## 2. Constraints that change the design

These are not preferences; they are facts about the running system, and the spec was written without
them. Each one invalidates part of the source text.

1. **One instance, 512 MiB, free tier.** Render's free instance type cannot scale beyond one
   (confirmed 2026-07-10; the owner declined the upgrade). Pass B's *"Monitor application every few
   seconds"* (line 871) with 14 concurrent monitor agents is not affordable and would itself become
   the outage. **Detection must be event-driven** (hook the existing error/audit/security loggers)
   **plus a cron sweep**, not a polling fleet.

2. **No Redis, no Celery, no queue.** `/api/health/redis` and `/api/health/queue` return WARN on this
   tier by design. Pass B's Event Bus does not exist. Use the database as the event log
   (`support_events`) and GitHub Actions cron as the scheduler.

3. **Ephemeral filesystem.** Evidence preservation (`security_evidence`) must write to Postgres or an
   Actions artifact, never to local disk — it is wiped on every deploy.

4. **The LLM chain is degraded.** Outstanding blocker #1: the live helpline is falling through to the
   rule-based fallback. An AI-SOC whose classification depends on an LLM will silently degrade to
   keyword matching. **Therefore classification must be deterministic-first** (rules over severity,
   module, source) with the LLM as an *enrichment* step that is allowed to be absent.

5. **`web_app.py` cannot be edited directly** (CRLF + mojibake; repo rule). New routes go in
   `new_*.py` modules spliced by byte-level `patch_*.py`, per the established pattern.

6. **Claude Code is not a service.** The spec repeatedly says an agent will "execute repair using
   Claude Code" (line 928). Claude Code is an interactive/headless CLI, not a daemon the app can
   call. The honest mapping: the Tier-3 agent **produces a structured repair package and opens a
   GitHub issue + branch**; a human (or a scheduled cloud agent) runs Claude Code against it. This
   satisfies the spec's own hard rule: *"Do not allow Claude Code to commit directly to the
   production branch"* (line 574).

---

## 3. Conflicts with existing governance — resolve before coding

| # | Conflict | Resolution required |
|---|---|---|
| G1 | Root `CLAUDE.md` §0.1: **Google ADK is the only agent framework.** But ADK's only LLM key is exhausted (HTTP 429, quota 0 — outstanding blocker #5), and SolarPro is a single-file Flask app with no `app/agents/` tree. | **Owner decision + ADR.** Either (a) provision a paid Gemini key / Vertex service account and build the agents as real ADK `LlmAgent`s, or (b) log an approved ADR exempting SolarPro, and implement the agents as deterministic Python services with an optional LLM enrichment call. This plan is written so **(b) works today and (a) is a drop-in later** — the agent boundary is a function signature, not a framework. |
| G2 | Root `CLAUDE.md` §0.2: every request enters via a **Root Orchestrator**. The spec agrees ("Claude Code is invoked only through the Support Orchestrator", line 1363). | Honour it: one `SupportOrchestrator` entry point. No route calls a tier agent directly. |
| G3 | Spec wants agents that can `revoke session`, `block IP`, `disable API key` **automatically** (lines 1656–1664). | Allowed only from the `support_runbooks` catalogue with `enabled=true` **and** the global kill switch off. Every auto-action writes `support_actions` + `audit_logs`. Blocking an IP has no implementation on Render free (no WAF) — record it as *proposed*, do not pretend to enforce it. |
| G4 | Spec wants automatic `secret rotation`, `firewall change`, `tenant suspension`. | Mode C (human-led) only. Never automated. Matches spec lines 1669–1676. |

---

## 4. Target architecture (fitted to this app)

```
   existing signal sources                    (NO new daemons)
   ─────────────────────────────────────────────────────────
   log_error() ─┐
   log_security()├─► SupportSignal hook ──► support_events   (append-only)
   log_audit() ─┘                                │
   /api/health/* + /metrics ──► cron sweep ──────┤
   tickets + /api/assistant/escalate ────────────┤
   login_failures / RLS violations ──────────────┘
                                                 │
                                    ┌────────────▼────────────┐
                                    │  Support Orchestrator   │  deterministic classify:
                                    │  (single entry point)   │  severity P1..P4, module, tier
                                    └────────────┬────────────┘
                        ┌──────────────┬─────────┴────┬──────────────┐
                        ▼              ▼              ▼              ▼
                    Tier 1         Tier 2         Tier 3        Security
                 (runbooks)     (diagnostics)  (repair pkg)   (containment)
                        │              │              │              │
                        └──────────────┴──────┬───────┴──────────────┘
                                              ▼
                        support_actions ─► KILL SWITCH + approval gate
                                              ▼
                         admin_notifications (existing inbox)
                                              ▼
                    knowledge_articles  ◄── on incident close
```

**Agents (7, per Pass A — Pass C's extra three are *roles*, not processes):**

1. `SupportOrchestrator` — classify, dedupe, assign, own the incident lifecycle.
2. `Tier1Agent` — execute enabled low-risk runbooks only.
3. `Tier2Agent` — correlate logs, run read-only diagnostics, produce a root-cause hypothesis.
4. `Tier3Agent` — produce a repair package (issue + branch + failing test). Never deploys.
5. `SecurityAgent` — detect, preserve evidence, execute pre-authorised containment.
6. `KnowledgeAgent` — write the article on close.
7. `NotificationAgent` — the existing inbox; thin adapter, not a new system.

A **Support Supervisor** (spec line 1368) is deliberately deferred to Slice 8: it prevents duplicate
incidents and reports SLAs, which is meaningless until incidents actually exist.

---

## 5. Data model

New tables, all carrying the platform's standard columns (`tenant_id` where applicable,
`created_at`, `updated_at`, `created_by`, `assigned_agent`, `audit_reference`) plus RLS + the
`current_tenant_id() IS NULL` escape, and the indexes required by `CLAUDE.md` §11.

| Table | Purpose | Notes |
|---|---|---|
| `support_incidents` | one row per incident | statuses per spec §15 (Detected → … → Closed → Reopened) |
| `support_events` | append-only signal log | the "event bus" substitute |
| `support_actions` | every action an agent took | auto or approved; links to `audit_logs` |
| `support_approvals` | approval requests + verdicts | who, when, what was approved |
| `support_agent_runs` | per-agent run record | `agent, input_hash, output_hash, status, started_at, finished_at` (§8 of the ADK extension) |
| `support_runbooks` | the auto-remediation catalogue | exactly the `RemediationRunbook` shape from spec line 644 |
| `security_incidents` | security-classified incidents | severity, containment applied |
| `security_evidence` | preserved evidence | Postgres, never local disk (constraint 3) |
| `knowledge_articles` | one per resolved incident | redaction enforced (spec lines 1887–1895) |
| `deployment_changes` | links an incident to a deploy | commit sha, workflow run id, rollback status |

**Reused, not recreated:** `admin_notifications`, `audit_logs`, `tickets`, `login_failures`,
`error_logs`, `helpline_learned_kb`.

---

## 6. Delivery slices

Each slice is independently shippable, passes the four gates (Codex → Supervisor → Work Reviewer →
Work Scheduler), and leaves the app working. Ordering is by *risk retired per unit of work*.

### Slice 0 — Kill switch + read-only foundations `[no automation yet]`
- `support_settings` (or reuse `admin_settings`) keys: `soc_enabled`, `soc_automation_enabled`,
  `soc_agent_paused:<agent>`. Default: **all automation OFF.**
- `POST /admin/soc/kill-switch` (admin_required + CSRF + audit).
- Schema migration for the ten tables above, RLS + policies + indexes.
- **Acceptance:** with `soc_automation_enabled=false`, no agent may execute any action; a test asserts it.
- **Why first:** the spec mandates the off-switch; shipping detection before the brake is how an
  automation system causes its first outage.

### Slice 1 — Signal capture (detection only, zero actions)
- `SupportSignal` hook inside `log_error` / `log_security` / `log_audit` — never raises, never blocks
  the request (same discipline as `boot_state.py`).
- Cron sweep (GitHub Actions, 5-min) polls `/api/health*` + `/metrics` and posts signals.
- Rate-limit + dedupe by `(module, error_code, hour)` so one bad deploy does not write 10⁵ rows.
- **Acceptance:** a deliberate 500 produces exactly one `support_events` row; app latency unchanged.

### Slice 2 — Orchestrator + deterministic classification
- `SupportOrchestrator.classify()` → `{severity, module, tier, probable_cause?}` using a rule table.
  LLM enrichment optional and allowed to fail (constraint 4).
- Creates `support_incidents`; writes to the existing `admin_notifications` inbox.
- **Acceptance:** P1..P4 map per spec §6/§8; DB-unreachable ⇒ P1; cosmetic ⇒ P4; every incident
  appears in the inbox.

### Slice 3 — Admin UI inside the existing Operations Centre
- `SupportIncidentDashboard`, `IncidentDetailPanel`, `PendingApprovals`, `SecurityIncidentPanel`.
- Added to `/admin/operations`. **No new admin portal, no new login** (spec line 1386).
- **Acceptance:** every incident and status change is visible; buttons are `@admin_required` + CSRF.

### Slice 4 — Tier 1 + the runbook catalogue (first automation)
- Seed runbooks that map onto primitives that **already exist**: retry job, clear approved cache
  (`/admin/ops/cache/clear`), restart queue (`/admin/ops/queue/restart`), re-send notification.
- Each runbook declares `steps`, `verificationSteps`, `rollbackSteps`, `riskLevel`, `enabled`.
- **Acceptance:** a runbook runs only when `enabled` AND automation is on; every run writes
  `support_actions` + `audit_logs`; a failed verification triggers rollback.

### Slice 5 — Security agent + containment
- Detect: brute force (`login_failures`), repeated token failures, cross-tenant attempts
  (RLS violation signal), unusual admin actions.
- Pre-authorised containment: revoke session, force re-auth, quarantine upload, disable API key.
- **Not implemented, recorded as proposed:** IP blocking (no WAF on Render free) — say so in the UI
  rather than implying protection that does not exist.
- **Acceptance:** containment actions are reversible, audited, and gated by the kill switch.

### Slice 6 — Tier 2 diagnostics (read-only)
- Log correlation across `error_logs` / `audit_logs` / `support_events`; config + feature-flag
  inspection; root-cause hypothesis + evidence summary + proposed fix + rollback plan.
- **Acceptance:** Tier 2 mutates nothing. Enforced by a test, not by convention.

### Slice 7 — Tier 3 repair package + approval gate
- Emits the exact "issue package" of spec lines 1814–1830 (incident id, stack trace, module, logs,
  repro, expected/actual, severity, related files/endpoint/tables, tenant impact, proposed tests).
- Opens a GitHub issue + branch via the existing Actions credentials. **Never deploys.**
- `support_approvals` gate; production deploy remains the existing `Force Render Deploy` workflow,
  run by a human.
- **Acceptance:** no code path exists by which an agent can deploy to production. Proven by test.

### Slice 8 — Knowledge base, then Supervisor
- `KnowledgeAgent` writes `knowledge_articles` on close, with a redaction pass (no secrets, tokens,
  PII — spec lines 1887–1895). Searchable from the admin area and reusable by the helpline.
- Then the Support Supervisor: dedupe, merge related alerts, SLA reporting, daily/weekly digests.

---

## 7. Acceptance criteria traceability

The spec states 18 acceptance criteria (lines 2023–2042). Mapping, so none is quietly dropped:

| Spec criterion | Slice |
|---|---|
| Tier 1/2/3 agents exist | 4, 6, 7 |
| Cybersecurity agent exists | 5 |
| All agents operate through one orchestrator | 2 |
| Monitoring alerts create incidents automatically | 1, 2 |
| Incidents appear in the admin inbox | 2, 3 |
| Incidents assigned to correct tier | 2 |
| Safe low-risk fixes run automatically | 4 |
| Code fixes generated through Claude Code | 7 (as a repair *package*; see constraint 6) |
| Code changes require testing and approval | 7 |
| Production changes not deployed blindly | 7 |
| Security issues logged and escalated | 5 |
| Resolved incident ⇒ knowledge article | 8 |
| Agent actions fully audited | 0, and every slice |
| Admin can pause or disable automation | **0** |
| Existing app / admin / CRM / pipeline reused | all — see §1 |
| No separate application | all |
| Existing user and tenant permissions enforced | 0 (RLS) + 3 (RBAC on every route) |
| Covers frontend/backend/db/api/token/authn/authz/security incidents | 1, 5 |

---

## 8. Risk register

| Risk | Why it matters here | Mitigation |
|---|---|---|
| The AI-SOC becomes the outage | It hooks the logging path of a 512 MiB single-instance app | Hooks never raise, never block, and are bounded — the `boot_state.py` discipline. Kill switch first. |
| Alert storm writes millions of rows | 25 MB database on a paid-but-small plan | Dedupe by `(module, error_code, hour)`; cap per-hour inserts; retention job |
| Automation acts on a false positive | Auto-remediation on a misclassified incident | `enabled=false` by default for every runbook; verification + rollback steps mandatory |
| Silent LLM degradation | Blocker #1: chain already falls back to rules | Classification is deterministic; the LLM only enriches |
| Knowledge articles leak secrets | Articles are generated from logs and stack traces | Redaction pass + a test with a planted fake secret |
| Scope collapse into "build 40 agents" | Pass B reads like a mandate | This plan builds 7; Pass B's list is a monitoring taxonomy |

---

## 9. Decisions needed from the owner before Slice 0

1. **G1 — ADK.** Provision a paid Gemini key / Vertex service account, or approve an ADR exempting
   SolarPro from §0.1 for this subsystem? (Everything else is blocked on this only if you want real
   `LlmAgent`s; the deterministic path ships without it.)
2. **Scope.** Confirm 7 agents (Pass A/C), not ~40 (Pass B).
3. **Automation appetite.** Which Tier-1 runbooks may ever run unattended? Default in this plan:
   none, until you enable them individually.
4. **Retention.** How long do `support_events` and `security_evidence` live? (Storage is now billed.)

---

## 10. What this plan explicitly does NOT do

- It does not create a separate support application, database, login or admin portal.
- It does not let any agent deploy to production, rotate a secret, change RBAC, suspend a tenant, or
  delete data.
- It does not claim IP blocking, WAF rules, Kubernetes/Docker/CDN/SMS monitoring, or a DDoS agent —
  none of those surfaces exist on this deployment. Pass B lists them; this app does not have them.
- It does not add a polling monitor fleet. Detection rides the logging path that already runs.
