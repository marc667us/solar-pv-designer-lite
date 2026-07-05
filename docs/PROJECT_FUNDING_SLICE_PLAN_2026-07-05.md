# Project Funding ("Sponsor") Module — Slice Plan (2026-07-05)

Source spec: `pvsolar1/sponsors page1.txt` (Final Combined SolarPro Project Funding
Plan + Claude Code Master Prompt). Status at start: **greenfield** — no funding
routes/tables/templates exist. `funding_mode` in web_app.py is the existing loan-vs-
self economics, unrelated.

Hard rules from the spec + house rules: ONE project/customer/CRM/pipeline/BOQ/BOM/
finance/report/doc/email system — **Project Funding reuses them, never duplicates**.
Additive only; never Edit web_app.py directly; PG+SQLite parity; tenant/RLS + audit.

## Integration target
Start on the **generation-station (Capital Investment) project** — it is the natural
home for large funding (SPV, sponsor, PPA, financial close) and reuses the finance
engine (`finance_config.computed`), `_ci_bankability` (= funding readiness score),
`_ci_cashflow_plan`, BOQ actuals, CRM/pipeline (steps 11/12). Regular `/project/<pid>`
funding is a later slice.

## Slices
1. **Foundation (THIS SLICE)** — `capital_investment_funding` table (one funding
   application per project, tenant-scoped) + `GET/POST /large-scale-solar/<pid>/funding`
   Overview page auto-populated from existing project + finance data + the bankability
   "funding readiness score" + a "Request Project Funding" action + a hub button.
2. **Financial Institution registration + admin approval** — `financial_institutions`
   registry, `Register as Financial Institution` path, Platform-Admin approve/suspend
   (Pending/Approved/Rejected/Suspended), institution RBAC roles.
3. **Customer submission flow** — generate funding package, select ≥1 institution,
   explicit consent, submit-to-selected only (`funding_institution_selections`).
4. **Institution Workspace** — assigned-applications list + dashboard metrics; strict
   isolation (an institution sees only applications submitted to it).
5. **Application Review page** — full application + reuse report engine; decision panel
   + status transitions (under review → conditional → approved/rejected).
6. **Communication + document tracking** — email applicant / request docs / secure
   messages (reuse `_send_email`), hard-copy courier tracking (no custody).
7. **Success Fee + Revenue** — 2% (configurable per institution) triggered by
   Approved + Executed + First-Disbursement; `funding_revenue` record + invoice + Admin
   Revenue Dashboard.
8. **AI Funding Assessment (ADK)** — funding-qualification/technical/financial/risk/
   bankability/matching agents under the existing orchestrator; funding score + matches.
9. **CRM + Sales Pipeline + Marketplace handoff** — new funding fields + pipeline stages;
   approved → existing procurement.
10. **Tests + security isolation + audit + extend to regular /project projects.**

Each slice: additive · POST+CSRF on state changes · tenant-scoped · audit · Codex +
Supervisor gates before ship.
