# Enterprise Programme — Revision 4 Implementation Plan

**Author:** Claude Code (Software Engineering Agent)
**Date:** 2026-07-15
**Source of truth:** `C:\Users\USER\Documents\pvsolar1\enterprise revision 4.txt` (owner's revised spec, 45 sections)
**Reviewed against:** current `app/enterprise_programme/` package (19 modules), root `enterprise_programme_*.py`, migrations 024–031, `templates/enterprise_programme/` (31 templates).
**Status:** REVISION 2 — Codex-reviewed 2026-07-15, findings folded in. Pending owner sign-off. **No code written yet.**

**Codex verdict (2026-07-15):** *PLAN NEEDS REVISION* — but the **root-cause diagnosis, the KEEP-vs-rebuild split, and the 16→6 collapse were all CONFIRMED.** The revisions below are sharpening, not rejection. Codex's three headline asks — (1) reframe KEEP as *reusable components, not finished workflows*; (2) specify the 16→6 migration/backfill + beneficiary-org privacy model; (3) make the document-agent fix concrete (schemas, specialist contracts, dedupe in the *document* path, acceptance tests) — are all now incorporated (§1, §3.A, §3.F, §7).

---

## 0. Why the last implementation was rejected (root cause)

The current module is well-engineered but was **built to a different, heavier spec** (`02-lifecycle-workflows.txt`: 16 phases / 14 gates / 38 roles / 144 deliverables). The owner's Revision 4 is a deliberate **simplification and re-framing** around one idea: *"simple, guided and largely automated… long text entry must be avoided wherever possible."* The mismatch is structural, not cosmetic:

| # | Owner's Revision 4 requirement | Current build | Verdict |
|---|---|---|---|
| A | **6 lifecycle phases** (Initiation / Planning / Execution / Monitoring / **Value Realisation & Transition** / Closure) | 16 phases grouped into 5 stages (no Value-Realisation phase) | **Interface "made too large"** — owner's own words. Primary rejection. |
| B | **Guided low-typing creation wizard** (10 steps, all dropdowns/multiselect/radio) | Plain 6-field form | Missing. Dropdown data half-plumbed, wizard UI absent. |
| C | **Programme-developer organisation registration + approval** (Draft→Submitted→Under Review→Approved→Rejected→Suspended) with document extraction | Org auto-created *active*; no approval, no extraction | Missing. |
| D | **Home = summary-card dashboard** (16 KPI cards + rich per-programme history) | Plain 5-column table | Missing. |
| E | **Deliverable buttons per phase → consistent Deliverable Workspace** (§15 fields) | 144 deliverables, one shared page, ~20 wired | Partial / wrong shape. |
| F | **Real per-deliverable agent content** (§16–18 agent architecture) | Grounded generator that produced the *"same statement for every question"* bug (patched 07-14) | The bug is a **symptom**: a topic-keyed template filler dressed as an agent. Owner rejected the *output quality*. |
| G | **Beneficiary onboarding chain** (§22): Prog-Admin registers org → invites Benef-Admin → admin completes profile → approval → admin invites users | Beneficiaries are records (create/import); no invitation; no distinct Benef-Admin / Benef-User roles | Missing. |
| H | **Bill upload + Check-My-Bill** (§24–31): users upload 3–6 months of bills → auto-extract → confirm → Check My Bill → Bill Analysis Report → design route | Uses monthly-kWh figures; no bill-image upload/OCR; bill-check runs on applications only | Partial. |
| I | **Role-based taskboards** (§36): 5 distinct boards | None (gate board + application inbox only) | Missing. |
| J | **6 role archetypes** (§20): Developer / Sponsor / Prog-Admin / Benef-Org-Admin / Benef-User | 38 granular roles | Over-built; needs collapse to the owner's 6. |

**One-line diagnosis:** the engine layer is right; the *interface model, the guided wizard, the agent output, and the beneficiary→bill→design chain* are not what the owner asked for. **We do not hide the complexity behind a simpler skin — that is exactly what "made too large" rejects.** We rebuild the model to the owner's 6-phase, low-typing, guided shape and **reuse the engines underneath**.

---

## 1. What we KEEP — **reusable components, not finished workflows** (Codex-corrected)

⚠️ **Codex correction:** the last draft overstated this list as "works and maps." These are **reusable building blocks** — engines, adapters, primitives. **None of them is the owner's finished Revision-4 workflow.** Reuse the component; build the workflow around it.

1. **Tenancy + RLS** — migration 025, `app.current_user_id` GUC, `require_tenant_scope` (C13), 404-on-cross-tenant. **⚠️ GAP: current RLS is TENANT-level, not beneficiary-org-scoped.** Rev 4 §45 (`owner-spec:1912`) requires beneficiary orgs not to see *each other* within a programme. That is a **new** policy layer to design in §3.G — do not assume existing RLS covers it. (`tenancy.py:73`, `gates.py`)
2. **Feature flag** — `enterprise_rebuild_enabled`, fail-closed dark. (`flags.py:27`) ✅ fully reusable.
3. **Design engines (adapters, not guided workflows)** — the crown jewels, but they are *engine calls*, not the owner's §34 guided design workflow:
   - Standard Design via `web_app._run_project_design` (`engines.py:169`)
   - Generation Station via `size_utility_pv` (`engines.py:278`)
   - **One reference design → cloned/scaled to N sites**, durable 25-site/pass drain (`rollout.py:83`). Maps to §32/§34 *sizing*; the guided selection UI + per-beneficiary routing is still to build.
4. **Check-My-Bill = calculation SEED ONLY** (Codex REFUTED "works and maps"). Current code synthesises loads from a *monthly-kWh figure* (`engines.py:109`; applications use `monthly_bill/monthly_kwh` at `applications.py:240`). Rev 4 §24–31 needs **3–6 uploaded bill images → extraction → confirm → validate → report → route**. The engine is reusable; the *entire bill pipeline* is new (§3.H).
5. **Bulk import (partial)** — CSV/XLSX parse → auto-map → stage → commit, zip-bomb guarded (`imports.py:68`). But it commits **in-request under a cap**; owner §37 bulk actions are broader and must run through the **durable job queue** (item 8).
6. **Applications chain ≠ the §22 onboarding chain** (Codex PARTLY REFUTED). Submit + inbox + 3-level decide exist (`applications.py`), and are useful — but Rev 4 §22 is a *different* flow: Prog-Admin **registers** a beneficiary org → **invites** a Benef-Admin → profile completed → **approved** → users invited (`owner-spec:1147`,`:1780`). Treat the applications code as a **reference**, not the required chain (§3.G). **Risk:** the two models can conflict — reconcile, don't bolt together.
7. **Template version engine** — draft→submit→approve→publish (`templates.py`). Reusable infra; not central to §45 acceptance.
8. **Durable job queue** — `/enterprise/jobs/drain` + GitHub-Actions cron (no Celery on Render free). This is where §37 bulk actions and large generation belong.
9. **Document honesty principle** — the 07-14 fix: *state a fact once, admit the rest; boilerplate is worse than a blank* (`documents.py:621,752`). ✅ Keep the principle. **But note (§3.F): the 07-14 dedupe only touched `draft_answers`; the generated-DOCUMENT path (`build_markdown` → `_write_from_facts` per activity, `documents.py:1309`) can still repeat.** The real fix is deeper than the last patch.

---

## 2. Governance decision to confirm (agents / ADK)

Owner §18 names a **Programme Orchestrator Agent** coordinating specialist agents (Initiation, Beneficiary, Bill Analysis, Technical Planning, Site Qualification, Standard Design, Generation Station, Funding, Procurement, Schedule, Risk, Monitoring, Document).

Root `CLAUDE.md §0.1` says **Google ADK is the only agent framework**. But:
- The user's instruction this session: **do not open Google ADK.**
- The module's own history: last plan recorded *"do not use Google ADK for this module. Gemini key is exhausted."*
- The **zero-cost APIs** rule (free-tier only pre-launch).

**Decision (owner-confirmed 2026-07-15): NO Google ADK.** Owner: *"dont use google adk it will make you too fail."* Implement the spec's agents as **logical agents** — a deterministic orchestrator function that fans work to specialist functions, each using the existing grounded free-tier LLM gateway (`api_manager.api.ai.chat`) + real engine calls. This is consistent with the module's own history (*"do not use Google ADK for this module. Gemini key is exhausted"*) and the zero-cost-APIs rule. It is a documented `§0.1` deviation from root `CLAUDE.md`; per the precedence rule this only requires an **ADR + note in `docs/IMPLEMENTATION_LOG.md`** — it is settled, not reopened.

---

## 3. The rebuild — by area

### A. Lifecycle model: 16 phases → owner's 6 (canonical, not cosmetic)
- New canonical phases: **Initiation · Planning · Execution · Monitoring · Value Realisation & Transition · Closure** (spec §6, `owner-spec:434-440,613`). Note current code has 5 grouped stages and **no Value-Realisation stage** (`constants.py:1507`) — that phase is genuinely new.
- **Author the six-phase deliverable lists directly from Rev 4 §9–§14** (`owner-spec` those sections) — **do NOT rebucket the old 144** (Codex F). The owner's lists are the contract.
- Retire the 14-gate lattice to **5 phase-gates** at the 6 boundaries with the owner's §38 conditions. Keep gates **advisory-by-default** (`enterprise_governance_advisory`).
- **Migration 032 — with explicit backfill + rollback + read-only archive (Codex C, G-1):** live rows carry `current_phase_code`, seeded `enterprise_programme_phase_states`, `enterprise_stage_gates`, and document `doc_type`s all tied to old phase/gate codes (`workflows.py:493`). The migration must: (a) map every old phase→new phase and old gate→new gate via an explicit lookup table; (b) **preserve old evidence read-only** (archive, never orphan) so prior approvals/docs remain auditable; (c) ship **migration + backfill + rollback acceptance tests** before it touches live. This is the single highest-risk step.
- State machine (`workflows.TRANSITIONS`) rewritten to 6 nodes.

### B. Programme-developer organisation registration + approval (spec §3)
- New `enterprise_organisation_registration` state on the org tenant: `Draft → Submitted → Under Review → Approved → Rejected → Suspended`.
- Registration form = dropdowns + required uploads (cert, tax doc, logo, authorisation letter, profile, licence). **Document extraction**: reuse the app's existing extraction path used for bills/applications; user only *confirms/corrects extracted values*.
- **Gate:** only `Approved` orgs can create programmes (`enterprise_programme_new` guard). Platform-admin approves.
- Migration 033.

### C. Guided low-typing creation wizard (spec §5)
- Replace `programme_new.html` with a **10-step wizard** (category → scale → beneficiary types → design strategy → objectives → funding → delivery → geography → size → governance roles → **auto-generate**).
- All inputs = dropdown / multiselect / radio / cascading country→region→district / numeric selectors. Dropdown data already exists (`dropdowns.py`, `constants.py`); wire it into the wizard.
- Step 11 = **Programme Initiation Agent** generates name/code/description/problem-statement/objectives/scope/schedule/risk-register/concept-note → user Accept / Regenerate / Edit-section / Save-Draft / Submit. Programme is born `Initiation – Draft`.

### D. Enterprise Programme Home = summary-card dashboard (spec §4)
- Add the 16 KPI summary cards (totals by phase, beneficiary orgs/sites, planned/installed solar & battery capacity, estimated value).
- Rich per-programme history rows with the owner's §4 fields + **Next required action** + filters (§4 filter dropdowns) + row actions (Open / Continue / Dashboard / Tasks / Beneficiaries / Designs / Reports / Approvals / Duplicate / Archive).

### E. Deliverable buttons → consistent Deliverable Workspace (spec §15–17)
- Each phase page shows deliverable **buttons** (§9–14). Clicking opens the **one consistent Deliverable Workspace** with the §15 field set: title / phase / purpose / required inputs / existing data / **missing information** / responsible+supporting roles / approver / due date / dependencies / **agent actions** / **human actions** / generated draft / files / comments / version history / approval + audit trail.
- Low-typing inputs per deliverable = predefined selectors (§17 concept-note example). **Never a blank report page.**

### F. Fix the agent output at the root (spec §16–18) — kills the "same statement" bug for good
**Codex D: the diagnosis is right but the last draft was under-specified. The 07-14 patch only deduped `draft_answers` (`documents.py:1535`); the generated-DOCUMENT path still calls `_write_from_facts` per activity and appends prose whenever present (`build_markdown`, `documents.py:1309`), keyed on a coarse `_topic_of(activity_text)` bucket (`_facts_for_topic`, `documents.py:621,784,1520`). So a real document can still repeat a paragraph.** The concrete fix:
1. **Per-deliverable INPUT SCHEMAS.** Each Rev 4 deliverable declares the exact fields/selectors it needs (§17). Generation reads *those fields*, not a shared topic bucket.
2. **Specialist agents with hard CONTRACTS (Codex G-4 — stop them degrading into renamed helpers).** Each §18 specialist declares: `inputs`, `outputs`, `owner` (which deliverables it writes), `audit` (logged run record), `missing_info` (what it emits when a field is absent). A specialist writes ONLY from its own inputs + engine outputs → two deliverables cannot collide on one paragraph.
3. **Dedupe in the DOCUMENT path, not just the answer path.** `build_markdown`/`generate_document` must track a seen-set of emitted fact paragraphs across the whole document (and vs stored prior versions) — the same discipline the 07-14 fix applied to `draft_answers`, now applied where documents are actually assembled.
4. **Honesty contract preserved:** a fact stated once; anything underivable shown as **Required user action / Open issue / Assumption / Missing evidence** (§18 Document Agent rule) — never boilerplate.
5. **Acceptance test that encodes the owner's complaint at the document level:** *no two activities in a generated deliverable share the same fact paragraph* — extend `test_no_two_activities_get_the_SAME_STATEMENT` from the answer path to the built document.

### G. Beneficiary onboarding chain (spec §20.4–§22)
- Add **Beneficiary-Org-Admin** and **Beneficiary-User** as first-class roles (collapse the 38-role table to the owner's 6 archetypes; keep granular perms internally but expose only the 6).
- Flow: Prog-Admin **registers beneficiary org** → **invites** Benef-Admin (email token) → Benef-Admin completes **guided org profile** (§23 dropdowns + uploads) → Prog-Admin **approves** → Benef-Admin **invites users** → users act. Enforce the §21 registration hierarchy; Benef-Admin cannot see other beneficiary orgs (RLS + app-layer).
- Migration 034 (org profile, sites, buildings, meter/provider, invitation tokens).

### H. Bill upload + Check-My-Bill + Bill Analysis Report (spec §24–§32)
- **Bill upload UI** (§25): select site → provider (ECG/NEDCo/…) → meter type → billing month → upload image/PDF → repeat 3–6× → submit. Statuses per §25.
- **Auto-extraction** (§26): reuse existing extraction; Benef-Admin confirms/corrects; validation checks (§27: <3 bills, duplicates, meter mismatch, abnormal consumption…).
- **Run Check My Bill** (§28) → existing engine → **Bill Analysis Report** (§29/§31) stored in document register → **route recommendation** (§30: Standard / Standard+Adjust / Survey / Generation-Station / Insufficient…).

### I. Standard Design & Generation Station routes (spec §32–§34)
- Standard route: match beneficiary → package (§32 dropdown) → populate preliminary SolarPro project from bill analysis → existing engine → preliminary BOQ/cost/savings → Standard Design Report → publish to taskboards. **Reuse `engines.build_standard_design` + `rollout` scaling.**
- Generation Station route (§33): structured config page → `engines.build_generation_station_design` → preliminary concept/BOQ/cost/schedule/risk → review → approve → publish.

### J. Role-based taskboards (spec §36)
- Build the 5 boards (Developer / Prog-Admin / Sponsor / Benef-Admin / Benef-User) each showing only that role's slice, sourced from lifecycle + deliverable + bill + design + approval state. Owner §19 task fields.

### K. Interface reduction (owner: "reduce the enterprise interface / made too large")
- 6 phases, 6 visible roles, 5 gates, low-typing everywhere, advanced calcs in expandable sections (§44), no complex controls exposed to beneficiary users. This is an explicit acceptance dimension, not polish.

---

## 4. Build order (follow the owner's own §40–§43 — vertical slices)

Ship **one fully-working vertical before expanding** (owner's explicit instruction). Each slice = full stack + Codex + Supervisor gate + live smoke test.

- **Slice 0 — MINIMAL enabling migration only (Codex E).** Migration 032 (16→6 with backfill/rollback/read-only archive per §3.A) + the six phase buttons + relabel the two UI strings that still say "16 phases" (`programme_new.html:8`, `home.html:89`). **No broad refactor here** — just the phase model + visible owner confirmation. This unblocks everything and is the visible fix for "made too large."
- **Slice 1 — First vertical (§40), in the owner's §43 order:** Org registration → **platform approval** (§B) → Home + programme history (§D) → creation wizard (§C) → Workspace → Initiation → **Programme Charter** deliverable (§E/§F) → agent actions + agent charter → developer review → sponsor approval → Planning unlock. **Role-based taskboard shell lands HERE** — owner §43 places the programme + role taskboards *before* beneficiary registration (`owner-spec:1810`), so build the board in Slice 1 and populate per role as later slices add data (§J).
- **Slice 2 — Second vertical (§41):** Benef-org registration → invite admin → profile → approve → invite user → **upload 3–6 bills → extract → confirm → validate → submit → Check My Bill → Bill Analysis Report** → Standard Design route → preliminary design → publish to taskboards. (§G, §H, §I-standard) — bill OCR confidence + correction UI + exception path designed **up front** (Codex G-3).
- **Slice 3 — Third vertical (§42):** Generation site → land/grid → GS strategy → capacity → agent station design → BOQ → cost/schedule → review → approve → publish. (§I-genstation)
- **Slice 4 — Planning reports + §37 bulk actions + notifications** (§35–§37) and remaining deliverables filled to the §45 bar. *(Audit is NOT deferred here — see below.)*

**Every slice** carries, non-negotiably: tenant_id + **beneficiary-org-scoped** RLS (not just tenant-level — Codex G-2), role/permission checks, **audit log (every slice, not Slice 4 — Codex E)**, error handling, tests (unit + tenant-isolation + RLS + **beneficiary-org-isolation** + route), tutorial scenarios (ratchet is RED on 5 pages — pay down as we touch each page), and the four-gate quality bar (Codex → Supervisor → Work Reviewer → Work Scheduler). **Tests are mapped item-by-item to the §45 acceptance list (Codex F).**

---

## 5. Acceptance criteria

Bind delivery to the owner's **§45 (30 items)** — a programme-developer can register+get-approved → open Enterprise → see history → create via wizard → 6 phases at top → phase pages with deliverable buttons → deliverable generates agent+human actions → agents draft docs → review/approve/return → sponsor unlocks next phase → Prog-Admin registers beneficiary orgs → Benef-Admin completes invited registration → invites users → user uploads ≥3 bills (supports ≥6) → auto-extract → confirm/correct → run Check My Bill → consumption calculated → prelim PV/battery/inverter estimated → Bill Analysis Report → route recommended → Standard + Generation-Station outputs generate → planning reports auto-generate → outputs on correct role taskboards → tenant-scoped → beneficiary orgs isolated → all auditable → tested creation-through-planning → integrated in existing SolarPro (no separate app).

---

## 6a. Owner decisions (locked 2026-07-15)

- **Q1 — Migrate live 16→6: APPROVED in principle.** Collapse to the six-phase model. **Verify the live programme count BEFORE any apply**; migration 032 stays **dry-run gated** — nothing touches live until the owner sees the dry-run and explicitly confirms "apply." Old phase/gate/doc evidence preserved read-only, never orphaned.
- **Q3 — Sponsor model: registry-as-catalogue + invited sponsor USER.** Keep `financial_institutions` (status='approved') as the catalogue of *potential* sponsors, but a programme's sponsor becomes an **invited user** who accepts the invitation and gains gate-approval rights (satisfies §20.2 accept-invitation / approve-gate). Not a pure registry pick.
- Q2 (reject-vs-return) and Q4 (extraction autofill-vs-confirm) — deferred; decided before Slice 1.

## 6. Risks / open questions for the owner

1. **Phase-model migration** (16→6) touches every existing programme. Recommend collapse (not skin) — confirm the owner accepts a data migration on live.
2. **ADK deviation** (§2 above) — need explicit approval to implement §18 agents as logical (non-ADK) agents, logged as an ADR.
3. **Bill OCR quality** on Ghanaian ECG/NEDCo bills — extraction confidence + the §27 validation guardrails; confirm the "confirm/correct" UX is acceptable as the safety net.
4. **Reject vs Return** at application level 1 — owner question from 07-14 still open (both currently built).
5. **Sponsor dropdown source** — sponsors = existing `financial_institutions` with `status='approved'`; empty until rows exist. Confirm this is still the intended source under Revision 4 (§20.2 implies a sponsor *invitation*, which is subtly different).
6. **Scope of "document extraction"** at org registration (§3) — how much to auto-fill vs confirm.

**Execution risks Codex added (§G) — carried into the build:**
- **G-1 Migration orphaning:** old phase/gate/doc evidence must be mapped/archived/read-only, never orphaned (handled in §3.A migration 032).
- **G-2 False-safe RLS:** tenant-level RLS can pass tests while beneficiary-org privacy still fails — test beneficiary-org isolation explicitly (every slice).
- **G-3 Bill OCR blocking:** extraction confidence + manual-correction + validation-exception paths designed *before* Slice 2, not after.
- **G-4 Fake agents:** "logical agents" degrade into renamed helpers unless each has explicit inputs/outputs/ownership/audit/missing-info contracts (handled in §3.F).
- **G-5 Applications conflict:** the existing applications chain may fight the required §22 invitation hierarchy — reconcile deliberately (§3.G), don't bolt together.

---

## 7. Requirements Codex flagged as missed / under-specified — now in scope

Each becomes an explicit work item in its slice:

1. **Platform/admin org-approval UI** + the developer-org status lifecycle (Draft→…→Suspended). (Slice 1)
2. **Document-extraction specifics** for org-registration uploads — fields, confidence, confirm-vs-autofill. (Slice 1)
3. **Exact six-phase deliverable lists authored from Rev 4 §9–§14** — not rebucketed from the old 144. (Slice 0/1)
4. **Phase-page fields** (§8): overview, status, risks, required approvals, generated docs, completion criteria, phase-gate approval. (Slice 1)
5. **Deliverable-Workspace persistence** (§15): version history, approval history, comments, **locked approved version**. (Slice 1)
6. **Agent + human action task generation with dependency tracking** (§16/§18/§19). (Slice 1→2)
7. **Monitoring runs continuously** across planning/execution/operations (§12) — not only a late phase. (Slice 2→4)
8. **Voice notes** as a low-typing input where text would otherwise be needed (§44). (Slice 2)
9. **Bill pipeline completeness** (§24–31): OCR confidence, correction UI, 6-plus uploads, validation-exception approval. (Slice 2)
10. **Full route-recommendation enum** (§30) + preliminary-output disclaimers on every estimate. (Slice 2)
11. **Role-based taskboard visibility matrix** (§36) — the exact per-role slice each of the 5 boards shows. (Slice 1 shell → filled later)
12. **Migration strategy for existing documents / gates / transitions** (folded into §3.A). (Slice 0)
13. **Tests mapped item-by-item to the §45 acceptance list** (30 items). (Every slice)
