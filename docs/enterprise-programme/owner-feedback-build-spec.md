# Enterprise Programme Module — Owner Feedback Build Spec

Source: live-site walkthrough feedback from the owner, 2026-07-11 → 07-12.
This is the authoritative build list for the next work session. Every item here
came directly from the owner testing the live module. Build in the order below.

Module code already live (dark flag): `enterprise_programme_*.py`,
`templates/enterprise_programme/*`, migration 024. Foundation = organisations,
memberships, programmes, phases, beneficiaries, project links, jobs, audit.

---

## Status of the two DEFECT fixes (DONE — commit 592d7e4, NOT yet deployed)

1. **Contrast** — grey text on white unreadable. Fixed: `.ent-page` scoped CSS in
   `templates/base.html` (`color:#1f2430`, `.text-muted → #4a5160`, stronger card
   borders/headers) + `ent-page` class on all 7 enterprise templates.
2. **Linked-project drill-down opened a "hiccup" page** — `href="/project/<id>"`
   is not a real route. Fixed to `url_for('project_results', pid=...)` in
   `project_links.html` and `programme_detail.html`; generation-station links use
   `/large-scale-solar/<id>` (already correct).

**FIRST ACTION next session:** deploy 592d7e4 to live (`gh workflow run
"Force Render Deploy"`) so the owner sees these two fixes, OR fold them into the
bigger deploy below. Needs explicit owner "deploy" per harness guard.

---

## ITEM A — Link is a LINK; you must also be able to start from scratch

Owner: *"when you create a project and you select the design approach it opens
all the steps and tools for design and all reports — it must just link, you must
be able to start from scratch."*

Meaning:
- **Linking stays a pure reference** (already the behaviour — do not regress it).
  The programme NEVER owns the project; `WHERE id=? AND user_id=?` preserved.
- **Add a "Start a new design from scratch" path** on the project-links page (and
  optionally programme detail). Two buttons:
  - *Start new standard design* → the EXISTING new-project wizard.
  - *Start new Generation Station design* → the EXISTING large-scale wizard.
- After the new project is created it should **auto-link back** to the programme.
  Implementation: pass a `?link_programme=<id>` (and `link_beneficiary`) query
  param into the existing create route; on successful project creation, if that
  param is present and the caller owns both, call `repo.link_project(...)`.
  - MUST find the existing new-project + new-generation-station route names in
    `web_app.py` (grep `@app.route` for `/project/new`, `/large-scale-solar/new`
    or similar). web_app.py is NEVER edited directly — the auto-link back has to
    live in the enterprise module: after redirecting into the wizard, capture the
    new project id on the enterprise side, OR add a tiny enterprise route
    `/enterprise/programmes/<id>/start/<kind>` that creates the project via the
    same helper the wizard uses and then links it. Prefer the enterprise-side
    route so web_app.py stays untouched.
- The `design_strategy` radio on the programme form should keep its honest copy
  ("you link projects you have already designed") — it does NOT auto-open a
  wizard. Selecting it records the strategy only.

---

## ITEM B — Delivery models + lifecycle phases + selectable activities + GENERATE

Owner: *"how does it work the steps and phase for standard epc. turnkey — all
types must be listed and the activities in each phase selectable and the system
generates"* + *"phases may include initiation, planning, execution, monitoring
and closure, so all the activities under each phase."*

### B.1 Delivery models (DONE — constant added, not yet wired)
`enterprise_programme_services.DELIVERY_MODELS` already added:
EPC, EPCM, Design-Build, Turnkey, Framework, Multiple Lots, Regional Packages,
District Packages, Technology Packages, Equipment-Only, Installation-Only, O&M,
Other. Column `delivery_model` already exists on `enterprise_programmes` and is
already read by `_programme_form()`. **To wire:** add a `<select
name="delivery_model">` to `programme_form.html` and pass `delivery_models=
svc.DELIVERY_MODELS` into the 4 `render_template("...programme_form.html")` calls
in `enterprise_programme_routes.py` (new GET, new POST-error, edit GET, edit
POST-error).

### B.2 Lifecycle phases (PMBOK, owner-specified 5)
Initiation → Planning → Execution → Monitoring & Control → Closure.
These become `enterprise_programme_phases` rows tagged with a new
`lifecycle_stage` column. Sequence 1..5.

### B.3 Activity catalog (baseline — real solar/PM practice, no fabrication)
Add `LIFECYCLE = [{stage, label, activities:[...]}, ...]` to services. Baseline:

- **Initiation**: Programme charter/mandate · Stakeholder identification &
  register · Needs assessment / beneficiary demand survey · Site identification &
  preliminary screening · Preliminary budget & funding strategy · Delivery-model
  & contracting strategy selection · Feasibility go/no-go decision.
- **Planning**: Detailed site surveys & energy audits · Solar resource & load
  assessment · System sizing & preliminary design · BOQ & cost estimation ·
  Procurement plan & tender packaging · Financial model / tariff / affordability ·
  Risk assessment & mitigation · Implementation schedule & milestones · Permits,
  approvals & regulatory compliance · Quality & HSE plan.
- **Execution**: Detailed engineering design · Procurement & supplier contracting
  · Equipment delivery & logistics · Civil & mounting works · Electrical
  installation & wiring · Battery / storage installation · Grid / inverter
  integration · Testing & commissioning · Beneficiary connection & handover ·
  Training & capacity building.
- **Monitoring & Control**: Performance monitoring (generation vs target) ·
  Quality inspections & audits · Budget & cost control · Schedule tracking &
  progress reporting · Fault & incident management · Stakeholder reporting ·
  Change control.
- **Closure**: Final inspection & acceptance · As-built docs & O&M manuals ·
  Warranty & O&M handover · Financial closeout & final accounts · Lessons learned
  / post-implementation review · Beneficiary satisfaction survey · Programme
  closure report.

Delivery model MAY filter/annotate the activity set (e.g. Equipment-Only trims
civil/installation execution activities; O&M emphasises Monitoring). Keep a base
set for all; add a small per-model include/exclude map. Do NOT invent activities
beyond standard practice.

### B.4 Data model — migration 025 (gated workflow, RLS ENABLE like 024)
- `ALTER TABLE enterprise_programme_phases ADD COLUMN lifecycle_stage TEXT` (idempotent).
- New table `enterprise_phase_activities`:
  `id, organisation_id, programme_id, phase_id, name, sequence_no, selected(bool
  default true), status TEXT default 'planned', planned_start, planned_finish,
  notes, created_by, created_at, updated_at`. FK phase_id → phases. RLS keyed on
  `organisation_id = ANY(current_enterprise_org_ids())` (reuse the 024 helper).
  Index on (organisation_id, programme_id, phase_id).
- Repo methods: `generate_lifecycle(org,uid,pid,delivery_model,selected_map)`,
  `list_activities(...)`, `set_activity_status(...)`, `activity_belongs_to(...)`
  IDOR guard mirroring `phase_belongs_to`.

### B.5 UI + generate flow
- On programme detail (or a new "Phases & Activities" tab): a **"Generate
  standard phases"** button. Opens a form listing all 5 stages, each with its
  activities as **checkboxes (pre-checked)**, filtered by the programme's
  delivery model. Operator deselects any they don't want → submit →
  `POST /enterprise/programmes/<id>/generate-phases` inserts the 5 phases +
  selected activities. Warn (don't hard-fail) if phases already exist; offer
  regenerate/append.
- Render generated phases + their activities read-only on the detail page with
  per-activity status badges. Reuse existing `ent-page` contrast styling.

---

## ITEM C — All reports into one final PROPOSAL

Owner: *"all reports must come into a final proposal."*

Build a consolidated **Programme Proposal** PDF: one document per programme that
assembles everything the module and its linked projects already hold. Sections:
1. Cover + programme identity (name, code, type, delivery model, org, date).
2. Executive summary (portfolio KPIs — all real COUNT/SUM, no invented values).
3. Delivery model & contracting strategy.
4. Lifecycle phases + selected activities (from Item B).
5. Beneficiary register summary (counts by status/region; sample table).
6. Linked projects — for each, its key existing outputs (system size, BOQ total,
   economics) pulled from the project's `data_json['results']`. Do NOT recompute;
   read what the existing engines already produced. Link out to each project's
   own full report set.
7. Budget & funding summary.
8. Assumptions / limitations.

- Toolchain: `markdown-pdf` (MarkdownPdf + Section) — the ONLY installed PDF lib.
  Build markdown, render to PDF bytes, stream as attachment. Template pattern:
  `Desktop\_build_tutorial_pdf.py` and existing report PDF routes.
- Route: `GET /enterprise/programmes/<id>/proposal.pdf` (login + module +
  membership + org-scoped). Button on programme detail: "Download final proposal".
- Everything sourced from real rows; where a figure can't be computed, omit it
  rather than fake it (same discipline as `programme_dashboard`).

---

## ITEM D — Tutorials on every enterprise page

Owner: *"the tutorial don't show in the pages to direct the user."*

The app already has a tutorial engine that auto-mounts on any page with a
scenario JSON at `/static/tutorial/scenarios/<endpoint>.json` and reads
`[data-a]` attributes on the page. (See Tutorial Engine work 2026-07-09.)

- Add scenario JSONs for enterprise endpoints: `enterprise_home`,
  `enterprise_programmes`, `enterprise_programme_new`,
  `enterprise_programme_detail`, `enterprise_project_links`,
  `enterprise_beneficiaries` (endpoint = the Flask function name → file name).
- Add `data-a="..."` anchors on the corresponding elements in the 7 enterprise
  templates so the tutorial can point at them.
- Verify the engine's mount script is included by `base.html` for these pages
  (it should be, since they extend base.html). Confirm the scenario filename
  convention matches what the engine looks up (endpoint vs path — check an
  existing scenario file to copy the exact naming).

---

## ITEM E — Stakeholder registry (employer, sponsors, user institution)

Owner: *"bring in all stakeholders like employer, funding sponsors, user
institution."*

A programme has stakeholders beyond beneficiaries. Add a stakeholder registry so
the programme captures every party. Types (seed list, free-TEXT column so
operators can add more):
- **Employer / Client** (the entity commissioning the programme — e.g. a
  Ministry, utility, corporate owner).
- **Funding Sponsor / Financier** — grant body, DFI, bank, investor. **Tie this
  into the EXISTING Sponsor/Funding module** (`project_solar_pv_session_2026-07-05_funding_module.md`,
  the "Sponsor" module, slices 1-10 live) rather than duplicating funding logic —
  a stakeholder of type sponsor can reference a funding record.
- **User Institution / Off-taker** — the school, hospital, community, or
  institution that will use the energy (may overlap with beneficiaries, but at
  programme/organisation level, not per-site).
- **Implementing / EPC Contractor**, **Consultant / Engineer (Owner's Engineer)**,
  **Regulator / Authority**, **O&M Provider**, **Community / Local Government**.

### Data model — fold into migration 025
New table `enterprise_stakeholders`:
`id, organisation_id, programme_id, stakeholder_type, name, role, organisation_name,
contact_name, contact_email, contact_phone, address, funding_record_id (nullable
FK to the Sponsor/Funding module), notes, created_by, created_at, updated_at`.
RLS keyed on `organisation_id = ANY(current_enterprise_org_ids())`. Index
(organisation_id, programme_id). IDOR guard `stakeholder_belongs_to`.

### UI
- Stakeholders tab/section on programme detail: add/list/edit/remove, grouped by
  type. Sponsor rows can link to a funding record from the existing module.
- Include the stakeholder register as a section in the **final proposal** (Item C)
  — every programme proposal should list its employer, sponsors, and user
  institutions.

### Validation
`validate_stakeholder(data)` in services (name + type required; email format
check reusing existing email-safe helpers if applicable).

---

## Build order (recommended)

1. Deploy the 592d7e4 defect fixes (owner-visible quick win) — needs owner OK.
2. ITEM B (delivery models wire + migration 025 + lifecycle catalog + generate
   flow) — the largest and most-requested. Migration 025 also carries ITEM E's
   `enterprise_stakeholders` table (one gated apply for both).
3. ITEM E (stakeholder registry — employer/sponsors/user institution; sponsor ties
   to existing Funding module).
4. ITEM C (final proposal PDF) — depends on B (phases) + E (stakeholders).
5. ITEM A (start-from-scratch project creation + auto-link).
6. ITEM D (tutorials).

Each item: Codex review → Supervisor → live test on the module (owner directive:
"you must run full test suite on the live site on the module"). Migration 025 via
gated workflow, owner-authorised apply. Then flip nothing new — the module flag is
already the gate; these are additive within it.

## COVERAGE vs the two source files (pvsolar1: "solar programm initiation.txt" +
## "solar programm initiation prompt.txt") — re-read in full 2026-07-12

The prompt file defines a 5-phase release plan (§40) and 46 acceptance criteria
(§45). What is actually BUILT is roughly **Phase 1 (Foundation), partial**:

BUILT ✅ : enterprise org + membership (tenancy), programme registry CRUD, basic
phases, manual beneficiary add/list/status, programme↔project links, audit log,
durable job foundation, dark feature flag, real-COUNT dashboards.

The owner's five live-feedback items (A–E above) are the immediate visible layer.
But re-reading source shows these **larger Phase-1/Phase-2 items are still MISSING**
and should be scheduled — the owner's asks are the entry points to them:

- **Programme Templates (§13)** — version-controlled template engine (standard PV
  capacities, battery options, standard BOQ/drawings/reports, funding & O&M model,
  status draft→published→archived; projects retain template version). This is a
  Phase-1 foundation item and is entirely absent. "The system generates" (owner
  Item B) ultimately rests on this. **Biggest missing foundation piece.**
- **Programme registration fields (§12)** — current form has code/name/type/status/
  targets/budget/currency/countries/regions/design_strategy. MISSING: sponsor,
  managing institution, start & target dates, duration, objectives, target energy
  generation, target battery kWh, target carbon reduction, KPI framework, contract
  framework, technical standards, procurement strategy (in dict, not surfaced).
  → fold the important ones into the programme form alongside ITEM B's delivery
  model. ITEM E (stakeholders) covers sponsor/managing institution/owner.
- **Automated project generation (§17)** — approved beneficiary → generate a
  SolarPro project from a template. Owner ITEM A ("start from scratch") is the
  first step of this; full batch/background generation is the larger §17 feature.
- **Bulk beneficiary import (§15)** — CSV/Excel import with preview, duplicate
  detection, row-level errors, draft staging, approval. Only manual add exists.
- **Site qualification scoring (§16)** — technical/financial/priority scoring.
  Absent. Later phase.
- **GIS portfolio (§27), EPC/procurement consolidation (§20/§22), FIDIC (§21),
  logistics (§23), operations centre (§26), scenario modelling (§30),
  carbon/ESG (§31), programme AI agents (§29)** — all Phase 3–5, not started.
  (AI agents: note ADR-018 — module runs deterministic, no ADK, per owner.)
- **Granular RBAC (§11)** — source lists ~38 roles + ~22 granular permissions.
  Current model is a single membership role. Real RBAC is a later hardening item.

**Reuse discipline (source §5.2, §1) is being honoured**: no second auth, no
second BOQ/marketplace/financial/reporting engine — programmes LINK existing
projects and the proposal (ITEM C) READS existing project results rather than
recomputing. Keep it that way.

**Positioning for the owner:** items A–E make the module usable and demo-ready and
directly answer the live feedback. Templates (§13), full project generation (§17),
bulk import (§15), and richer programme registration (§12) are the next foundation
tranche after A–E — surface them so scope is explicit, don't silently skip (source
§47 change-control forbids silent omission).

## CODEX INDEPENDENT GAP VERDICT (gpt-5.5, read both source files + built module, 2026-07-12)
Full report: `_codex_enterprise_gap_out.txt`. Codex CONFIRMS the coverage above and
ranks the gaps:
1. **MISSING — Programme Template version engine (§13).** No template tables/UI/
   lifecycle; blocks automated generation + repeatable standards. **Biggest missing
   foundation piece** (Codex + Claude agree).
2. MISSING — Automated project generation from approved beneficiaries (§17). Only
   manual linking exists.
3. MISSING — Bulk beneficiary import (§15). Manual entry only.
4. PARTIAL — Programme registration fields (§12): sponsor/owner/managing institution/
   dates/objectives/energy+carbon targets/KPI/contract framework/technical standards/
   cloning absent; delivery_model & procurement_strategy stored but not surfaced.
5. PARTIAL — RBAC: single membership role, `permissions_json` unused; no granular
   §11 roles. Tenant scoping IS real at app layer (Codex verified the IDOR/isolation
   tests); RLS is ENABLE not FORCE (defence-in-depth only).
6. PARTIAL — Reuse: no duplicate engines (good) BUT reuse is mostly nav/linking, not
   orchestration of BOQ/marketplace/funding/reporting/design engines yet.
7. PARTIAL — Delivery models/EPC/lifecycle: constants exist, UI unwired; EPC packaging
   + lifecycle state machine + contractor/inspection/commissioning missing.
8. MISSING — funding alloc, BOQ consolidation, procurement, FIDIC, logistics, ops,
   GIS, ESG/carbon, AI, scenario, full reports (Phases 3–5).

**Codex CORRECTION to Claude's framing:** "A–E make the module usable and demo-ready"
is **too optimistic**. A–E improve the live walkthrough but the module is NOT genuinely
programme-ready without **template versioning + bulk import + automated generation +
richer registration + RBAC**. Accept this correction.

**Codex caveat on ITEM C:** the proposal PDF must READ existing report/export outputs
and must NOT become a parallel reporting engine (reuse discipline §5.2). Build it to
consume existing project `data_json['results']` only — already the plan, keep it strict.

### Revised recommended sequencing (post-Codex)
- **Tranche 0 (visible, bounded, answers live feedback):** deploy 592d7e4 defects →
  ITEM B delivery-model wire + lifecycle phases/activities → ITEM E stakeholders →
  ITEM C proposal (read-only) → ITEM A start-from-scratch → ITEM D tutorials.
- **Tranche 1 (foundation — required before calling it "programme-ready"):**
  Programme Template version engine (§13) → richer programme registration (§12) →
  Bulk beneficiary import (§15) → Automated project generation (§17) → granular
  RBAC (§11). Surface these to the owner as the real remaining foundation; do not
  imply Tranche 0 completes the module.

## Known blocker carried over
`.env` / Keycloak credential drift: the live auth flow blocks the headless test
login. Rotating/syncing KC seed passwords is blocked by the harness production-
secret guard — the owner must run `Sync KC Seed Passwords` (or approve the prompt)
themselves. Public-surface live tests pass; auth-gated live tests need this.
</content>
</invoke>
