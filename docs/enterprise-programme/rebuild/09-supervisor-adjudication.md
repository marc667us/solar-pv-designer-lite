# Supervisor Adjudication — Enterprise Programme Rebuild Plan

**Adjudicator:** Supervisor (Claude Code, App Factory gate 2)
**Subject:** Codex planning artefacts 01–08 in `docs/enterprise-programme/rebuild/`
**Date:** 2026-07-12
**Sources of truth:** `docs/enterprise-programme/source/{00-vision,01-master-prompt,02-lifecycle-workflows}.txt`

---

## VERDICT: **APPROVE WITH TWO REQUIRED CORRECTIONS + ONE OWNER DECISION**

The plan is repository-specific, evidence-based, and rejects the generic-architecture failure mode the
master prompt (§6.4) explicitly forbids. It may proceed to implementation **after** corrections R1 and
R2 below are folded in, and **after** the owner rules on decision D1.

---

## 1. Independent verification of Codex's load-bearing claims

The Supervisor does not accept Codex's citations on trust. Each was re-checked against the working tree.

| Claim | Codex citation | Supervisor result |
|---|---|---|
| Registration seam exists; `web_app.py` need not be edited | `wsgi.py:29,32` | **CONFIRMED** — `from enterprise_programme_routes import register_enterprise_programme` + `import web_app as _wa` |
| Standard projects are user-owned | `web_app.py:1043` | **CONFIRMED** — `SELECT * FROM projects WHERE id=? AND user_id=?` |
| Generation-station projects are user-owned | `new_capital_investment_routes.py:6325` | **CONFIRMED** |
| `tenant_id` is a pure function of `user_id` | `migrations/003_rls_tenant.sql:136` | **CONFIRMED** — `md5('solarpro-tenant-v1:'||uid)` |
| No organisations table | `migrations/001_mirror_sqlite.sql:44` | **CONFIRMED** — explicitly DROPped |
| Auth decorators exist to layer RBAC on | `app/security/decorators.py` | **CONFIRMED** — 7 decorators (`require_jwt`, `require_role`, `require_any_role`, `require_all_roles`, `require_scope`, `require_tenant_match`, `require_service_account`) |
| BOQ service registry usable as dropdown source | `new_boq_services_engine.py:28` | **CONFIRMED** — `_BOQ_SERVICES` |
| Flag + rollback workflow exists | `set-enterprise-programme-flag.yml` | **CONFIRMED** — workflow name `Set Enterprise Programme Flag` |
| Deploy workflow exists | `render-deploy-now.yml` | **CONFIRMED** — workflow name `Force Render Deploy` |
| Audit chain, quality gate, Ghana regions exist | various | **CONFIRMED** — all four files present |
| No dispatched background worker | `tasks/celery_app.py` + Render start cmd | **CONFIRMED** |

**No fabricated citations found.** This is a materially better evidence standard than the previous
enterprise plan, which the owner had to correct.

## 2. REQUIRED CORRECTION R1 — the background worker is not deployable as planned (HIGH)

`07-implementation-plan.md:241` instructs: *"add a Render worker service or cron that runs
`python -m app.enterprise_programme.worker --loop`"*.

**This is not achievable on the current hosting.** SolarPro runs on the **Render free tier, which caps
the account at one running instance** — a second Render service (a worker) was already attempted and
**BLOCKED** during the 2026-07-10 recovery. A Render cron job is likewise a paid-tier primitive.

Left uncorrected, slices 5 and 7 (beneficiary import, project generation) would ship a queue that
**enqueues but never drains** — precisely the failure the old `enterprise_programme_jobs.tick()` already
exhibits (`enterprise_programme_jobs.py:185` fails claimed jobs by design). The master prompt (§17)
forbids synchronous mass generation in a web request, so removing the queue is not an option either.

**Mandated design:** drive the durable Postgres queue from a **GitHub Actions scheduled workflow** that
calls an authenticated, admin-scoped drain endpoint, processing a bounded chunk per invocation. This is
already the proven pattern in this repo — `keep-warm.yml`, `backup-postgres.yml`, `fx-rates-refresh.yml`,
`kc-weekly-restart.yml` and others are all GH-cron-driven against the live service. Requirements:

- Chunked and idempotent: each invocation claims N jobs, commits per job, and is safely re-runnable.
- The drain endpoint re-runs **every guard** (already required at `05:443`) — the worker path is a
  security boundary, not a convenience.
- The UI must state plainly when generation is queued and the drainer has not yet run. GitHub free-tier
  cron is **best-effort and silently drops fires under load** — a caveat this repo already documents in
  `keep-warm.yml`. Do not present queue latency as real-time.
- Keep `worker.py --once` runnable manually so the owner can force a drain.

## 3. REQUIRED CORRECTION R2 — Release 1 migration count is too high for a live free-tier Postgres (MEDIUM)

`07-implementation-plan.md:55-70` schedules **six migrations (025–030) inside Release 1 alone**, thirteen
overall. Each live migration against the free-tier Postgres is a discrete outage risk, and this database
has already had one destructive-migration near-miss (024's first apply failed on SQL-function parse order
and only survived because of the `BEGIN/COMMIT` + `ON_ERROR_STOP` wrapper).

**Mandated:** collapse R1 to **at most three migrations** — (a) tenancy + RBAC + taxonomy, (b) programme
core + lifecycle + gates + templates, (c) beneficiaries + qualification + project links + BOQ approval.
Every migration keeps the `BEGIN/COMMIT` + `ON_ERROR_STOP` wrapper, declares SQL functions **after** their
tables (C4), and wraps any `admin_settings` write in `set_config('app.current_role','admin',true)` (C5).
Ship each behind the dark flag and verify row-counts on live before the next.

## 4. OWNER DECISION D1 — teardown of the old module

The owner instructed: *"remove the old implementation existing in the app."*
Codex's architecture verdict (`01-current-state-and-teardown.md:41`) **objects** and recommends
**supersede-in-place**, deferring the physical `DROP` to a cleanup migration (037).

**The Supervisor sides with Codex, and records why.** Migration 024 is already applied to live Postgres.
Dropping those eight tables first would destroy any pilot programme rows, organisation bootstrap records,
project links and audit rows, while delivering **zero** lifecycle capability — it spends risk budget on
deleting dark scaffolding. The module is dark by default, so leaving it disabled carries almost no
operational risk.

Critically, **the owner's end state is still reached**: every line of the old implementation's internals,
templates, job helper and tests is replaced. Only the *seams* survive (the `/enterprise` URL, the dark
flag, the `register_enterprise_programme` entry point, the project-link semantics) — and those are the
things that make the replacement safe. The physical `DROP` is sequenced last, after a backup, an export
and a row-count inventory proving the tables are empty or migrated.

**This is the owner's call, and it is the only irreversible step in the plan.** Nothing is dropped from
the live database without explicit owner authorisation.

## 5. Findings raised and dispositioned

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | Worker requires a 2nd Render service / paid cron — not available on free tier | **R1** — GH Actions cron drain endpoint |
| 2 | MEDIUM | 6 live migrations in R1 on a fragile free-tier Postgres | **R2** — collapse to ≤3 |
| 3 | MEDIUM | Owner instruction (remove) vs architecture verdict (supersede) | **D1** — escalated to owner |
| 4 | LOW | `enterprise_memberships_v2` (04:migration path) vs "extend the 024 table" (04:domain model) — inconsistent naming | Fix at build: pick one, state it in migration 025 header |
| 5 | LOW | R1 spans 9 slices — large. Mitigated because each slice is independently shippable and flag-dark | Accept; re-assess after slice 3 |

## 6. Compliance check against the binding constraints

| Constraint | Status |
|---|---|
| C1 — no edits to `web_app.py` / `api_manager.py` / `start*.py` | **PASS** — plan imports from them via the `wsgi.py` seam; explicit "Do not modify" list at `07:51` |
| C2 — enterprise tenancy without breaking single-user ownership | **PASS** — overlay model; personal tenant id == existing deterministic hash; `projects.user_id` never written |
| C3 — no background worker | **FAIL → corrected by R1** |
| C4 — SQL functions after their tables | **PASS** — explicitly carried at `07:71` |
| C5 — admin GUC for `admin_settings` writes | **PASS** — explicitly carried at `07:71` |
| C6 — no ADK; LLM only via `_AIClient.chat()`; AI never approves | **PASS** — control 11 has a guard, a callsite and a test (`05:424`) |
| C7 — markdown-pdf only | **PASS** |
| O1 — reuse before rebuild | **PASS** — 35-row reuse matrix with real paths |
| O2 — integrate with existing workflows | **PASS** — names the real `.yml` files and in-app wizards |
| O3 — dropdowns, minimise typing | **PASS** — field-by-field spec; free text justified per field |
| O4 — bridge all gaps, nothing silently dropped | **PASS** — dual coverage tables; §47 change-control for every deferral |

## 7. Instruction to the implementer

Proceed to build **Release 1, slice by slice**, in the stated dependency order. Fold R1 and R2 into the
plan before writing slice 1. Do not execute any destructive live-database action until D1 is answered.
Each slice: implement → Codex review → Supervisor review → tests → only then the next slice.
