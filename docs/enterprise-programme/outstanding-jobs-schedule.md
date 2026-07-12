# Enterprise Programme Module — Schedule of Outstanding Jobs

Prepared at session close 2026-07-12. Companion to `implementation-plan.md` (the
how) and `owner-feedback-build-spec.md` (the what + source coverage). Confirmed by
independent Codex gap analysis (`_codex_enterprise_gap_out.txt`).

Module state: Phase-1 foundation LIVE but DARK (feature flag off). Migration 024
applied live. 2 defect fixes committed (`592d7e4`) but NOT yet deployed.

Legend — Size: S ≤½ day · M ~1 day · L ~2–3 days. Status: TODO / PARTIAL / BLOCKED.

## Tranche 0 — answers the owner's live-site feedback (build first)

| # | Job | Spec | Size | Depends on | Migration | Status |
|---|-----|------|------|-----------|-----------|--------|
| 0 | Deploy defect fixes `592d7e4` (contrast + drill-down) to live | — | S | owner "deploy" OK | none | TODO |
| B1 | Wire delivery-model `<select>` into programme form + 4 render calls | §20 | S | — | none | TODO (constant already added) |
| B2 | Surface richer registration fields already in form-dict (procurement_strategy) + add dates/sponsor via ITEM E | §12 | S | E1 | none | TODO |
| B3 | Migration 025: `enterprise_phase_activities` + `lifecycle_stage` col + `enterprise_stakeholders` (one gated apply) | §13/§18 | M | — | **025** | TODO |
| B4 | Lifecycle catalog (5 PMBOK stages + activities) in services | §18 | S | — | none | TODO |
| B5 | Generate-phases route + checkbox UI (pre-checked, delivery-model filtered) | §18 | M | B3,B4 | none | TODO |
| B6 | Render generated phases + activities read-only on detail page | §18 | S | B5 | none | TODO |
| E1 | Stakeholder registry: repo + services + routes + UI (employer/sponsor/user-institution/...) | §12/§19 | M | B3 | (025) | TODO |
| E2 | Sponsor stakeholder ties to existing Funding module record | §19 | S | E1 | none | TODO |
| C1 | Final Programme Proposal PDF route (`markdown-pdf`, reads existing outputs only) | §32 | M | B6,E1 | none | TODO |
| C2 | "Download final proposal" button on detail page | §32 | S | C1 | none | TODO |
| A1 | "Start new design from scratch" enterprise-side route → creates project via existing wizard helper → auto-links | §17 | M | — | none | TODO |
| A2 | Keep pure-link path unchanged; buttons on project-links page | §17 | S | A1 | none | TODO |
| D1 | Tutorial scenario JSONs for 6 enterprise endpoints + `[data-a]` anchors | §35 | M | — | none | TODO |

Gate each item: Codex review → Supervisor → LIVE module test (owner directive).

## Tranche 1 — foundation required before "programme-ready" (Codex-ranked)

| # | Job | Spec | Size | Status |
|---|-----|------|------|--------|
| T1 | **Programme Template version engine** (tables, versioning, standard capacities/BOQ/drawings/reports, draft→published→archived, project retains template version) — BIGGEST MISSING PIECE | §13 | L | TODO |
| T2 | Richer programme registration (sponsor/managing-institution/dates/objectives/energy+carbon targets/KPI/contract framework/technical standards/cloning/archive) | §12 | M | TODO |
| T3 | Bulk beneficiary import (CSV/Excel, preview, dedup, row errors, staging, approve/reject, export) via durable job queue | §15 | L | TODO |
| T4 | Automated project generation from approved beneficiaries (template-driven, batch, background, idempotent, partial-failure) | §17 | L | TODO |
| T5 | Granular RBAC (~38 roles / ~22 permissions; activate `permissions_json`) | §11 | L | TODO |

## Tranche 2+ — later phases (not started)

Site qualification scoring (§16) · GIS portfolio (§27) · Funding allocation detail
(§19) · BOQ consolidation (§22) · EPC packaging + contractor assignment (§20) ·
FIDIC contract interface (§21) · Logistics/warehousing (§23) · Construction mgmt
(§24) · Inspection/commissioning (§25) · Operations centre (§26) · Scenario
modelling (§30) · Carbon/ESG (§31) · Programme AI agents (§29 — deterministic,
no ADK per ADR-018) · Full report catalogue (§32).

## Blockers / owner decisions outstanding

- **Deploy authorisation** — job 0 and every subsequent deploy needs explicit owner
  "deploy" (harness production guard). `gh workflow run "Force Render Deploy"`.
- **Migration 025 apply** — gated workflow, owner-authorised apply on live Postgres.
- **KC credential drift (BLOCKED)** — headless auth-gated live tests blocked; owner
  must run `Sync KC Seed Passwords` or approve. Public-surface tests pass.
- **Flag flip** — module stays DARK until owner flips
  `enterprise_programme_enabled='1'` and walks the acceptance test.
</content>
