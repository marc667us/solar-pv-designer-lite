# Enterprise Programme Module — Implementation Plan (Tranche 0 + Tranche 1)

Session-close plan, 2026-07-12. The "how" for `outstanding-jobs-schedule.md`.
Controlling spec: pvsolar1 `solar programm initiation.txt` + `…prompt.txt`.
Non-negotiables carried from source + house rules:
- web_app.py is NEVER edited directly (CRLF+mojibake). New code = injected modules
  registered from wsgi.py via the DI pattern `register_*(app, *, get_db,
  login_required, csrf_protect, current_user)`.
- Programmes LINK projects, never own them (`WHERE id=? AND user_id=?` preserved).
- No LLM / no Google ADK in the module (ADR-018). Deterministic Python only.
- Reuse, don't duplicate: read existing engine outputs; never build a 2nd BOQ /
  marketplace / financial / reporting / auth engine (source §5.2).
- Every route: login_required → _require_module() (flag) → _require_membership()
  (org from membership, never URL) → csrf_protect on POST → repo re-scopes by org_id.
- IDOR: an id in a URL is untrusted; add a `*_belongs_to` guard for every new child.
- Migrations: gated workflow, dry-run default, RLS ENABLE (matching 024). SQL
  function bodies referencing a table must be defined AFTER that table (024 lesson).
- Tests + Codex + Supervisor + LIVE module test per item before "done".

---

## Item 0 — Deploy the committed defect fixes (`592d7e4`)
- `gh workflow run "Force Render Deploy"` (Render does NOT auto-deploy on push).
- Verify live: enterprise pages readable (contrast), linked-project links resolve to
  `project_results` / `/large-scale-solar/<id>` (no "hiccup" page).
- Needs owner "deploy" OK (harness guard).

---

## Item B — Delivery models + lifecycle phases + selectable activities + generate

### B1 Delivery-model select (no migration)
- `templates/enterprise_programme/programme_form.html`: add a `<select
  name="delivery_model">` (Identity or a new "Delivery & procurement" card) iterating
  `delivery_models` with `selected` on `form.delivery_model`. Add procurement_strategy
  input while here.
- `enterprise_programme_routes.py`: pass `delivery_models=svc.DELIVERY_MODELS` into all
  4 `render_template(".../programme_form.html", …)` calls (new-GET, new-POST-error,
  edit-GET, edit-POST-error). `_programme_form()` already reads `delivery_model`.
- `DELIVERY_MODELS` constant already added to services.py.
- Test: create/edit programme with each model persists + re-renders selected.

### B3 Migration 025 (also carries E + activities)
File `migrations/025_enterprise_lifecycle_stakeholders.sql`, BEGIN/COMMIT +
`\set ON_ERROR_STOP`:
- `ALTER TABLE enterprise_programme_phases ADD COLUMN IF NOT EXISTS lifecycle_stage TEXT;`
- `CREATE TABLE enterprise_phase_activities (id, organisation_id, programme_id,
  phase_id, name, sequence_no, selected BOOL DEFAULT true, status TEXT DEFAULT
  'planned', planned_start, planned_finish, notes, created_by, created_at,
  updated_at)`; FK phase_id→phases; index (organisation_id, programme_id, phase_id).
- `CREATE TABLE enterprise_stakeholders (…)` — see Item E schema.
- RLS ENABLE on both; policies key on `organisation_id = ANY(current_enterprise_org_ids())`
  (reuse the 024 helper — do NOT redefine it before tables).
- Mirror both tables in `_SQLITE_DDL` / `ensure_enterprise_schema()` in the repo.
- Gated workflow `.github/workflows/apply-migration-025-*.yml` (copy 024's), dry-run
  default, `-f confirm=APPLY`. Owner-authorised apply.

### B4 Lifecycle catalog (services)
- Add `LIFECYCLE = [{stage,label,activities:[…]}]` for the 5 PMBOK stages
  (Initiation, Planning, Execution, Monitoring & Control, Closure) — activity lists
  per `owner-feedback-build-spec.md` §B.3 (real solar/PM practice, no fabrication).
- Add `def lifecycle_for(delivery_model)` returning the stages with a small per-model
  include/exclude (e.g. Equipment-Only trims civil/install execution; O&M weights
  Monitoring). Base set applies to all.

### B5 Generate-phases route + UI
- Repo: `generate_lifecycle(get_db, org, uid, pid, delivery_model, selected_map)` —
  inserts the 5 phases (with `lifecycle_stage`, sequence 1..5) + the checked
  activities; warn (flash) if phases already exist, offer append/regenerate; org-scoped
  + `programme` ownership re-check. `list_activities(...)`, `set_activity_status(...)`,
  `activity_belongs_to(...)` (IDOR guard mirroring `phase_belongs_to`).
- Route `POST /enterprise/programmes/<id>/generate-phases` + a GET form template
  listing all stages, each activity a pre-checked checkbox, filtered by the
  programme's delivery model. Standard guards + csrf.
- B6: render generated phases + activities read-only on `programme_detail.html` with
  per-activity status badges (reuse `ent-page` styling).
- Tests: generate inserts correct rows; regenerate warns; activity status update
  IDOR-guarded across programmes/orgs.

---

## Item E — Stakeholder registry
- Table `enterprise_stakeholders (id, organisation_id, programme_id,
  stakeholder_type, name, role, organisation_name, contact_name, contact_email,
  contact_phone, address, funding_record_id NULL, notes, created_by, created_at,
  updated_at)` (in migration 025). Seed types: employer/client, funding_sponsor,
  user_institution, epc_contractor, consultant, regulator, om_provider, community.
- Services: `STAKEHOLDER_TYPES`, `validate_stakeholder(data)` (name+type required;
  reuse email-safe check if present).
- Repo: `add_stakeholder / list_stakeholders / update_stakeholder / remove_stakeholder
  / stakeholder_belongs_to` — all org-scoped + IDOR guard.
- Routes: `/enterprise/programmes/<id>/stakeholders` (list+add), `.../<sid>/edit`,
  `.../<sid>/delete` — standard guards + csrf.
- UI: stakeholders section/tab on `programme_detail.html`, grouped by type; sponsor
  rows offer a link to a Funding-module record (E2 — reference id only, do NOT
  duplicate funding logic).
- Tests: CRUD + cross-org IDOR rejection; sponsor link resolves.

---

## Item C — Final Programme Proposal PDF (reads existing outputs ONLY)
- Route `GET /enterprise/programmes/<id>/proposal.pdf` (login + module + membership +
  org scope). Build markdown → `markdown-pdf` (MarkdownPdf + Section) → stream bytes
  as attachment. Template pattern: `Desktop\_build_tutorial_pdf.py` + existing report
  routes.
- Sections: cover/identity · exec summary (real portfolio KPIs from
  `svc.org_dashboard` / `programme_dashboard`) · delivery model & contracting ·
  lifecycle phases + selected activities · beneficiary summary · linked projects (for
  each, read its `projects.data_json['results']` — size, BOQ total, economics; DO NOT
  recompute) · stakeholders (from E) · budget/funding · assumptions/limitations.
- Codex caveat (accepted): this must READ existing engine outputs and link out to each
  project's own full report set — it must NOT become a parallel reporting engine.
  Where a figure is unavailable, OMIT it (no invented values — source §28).
- C2: "Download final proposal" button on detail page.
- Tests: renders for a programme with 0 links, with standard links, with gen-station
  links; no recompute; org-scoped.

---

## Item A — Start a new design from scratch (+ keep pure link)
- Keep existing "link an existing project" flow byte-for-byte (backward compatible).
- Find the existing new-project + new-generation-station entry points in web_app.py
  (grep `@app.route` for the create routes) — do NOT edit web_app.py.
- Add enterprise-side route `POST /enterprise/programmes/<id>/start/<kind>` that:
  creates a fresh project via the SAME helper the wizard uses (import the function, or
  call the internal create path), then `repo.link_project(...)` it back to the
  programme, then redirect INTO the existing wizard for that project id. `kind ∈
  {standard, generation_station}`; verify caller owns the new project (they will —
  they create it). Optional `beneficiary_id` link-through.
- UI: two buttons on `project_links.html` — "Start new standard design" / "Start new
  Generation Station" — beside the existing link form.
- The `design_strategy` radio keeps its honest copy; selecting it does NOT auto-open a
  wizard.
- Tests: start creates+links+redirects; pure link path unchanged; ownership enforced.

---

## Item D — Tutorials on enterprise pages
- Confirm the tutorial engine's mount script is emitted by base.html for these pages
  (they extend base.html) and confirm the scenario-file lookup convention by reading
  an existing `/static/tutorial/scenarios/*.json` (endpoint name vs path).
- Add scenario JSONs for: enterprise_home, enterprise_programmes,
  enterprise_programme_new, enterprise_programme_detail, enterprise_project_links,
  enterprise_beneficiaries.
- Add `data-a="…"` anchors on the matching elements in the 7 enterprise templates.
- Test: each page mounts its tutorial; anchors resolve.

---

## Tranche 1 — foundation (after Tranche 0; surface to owner, don't skip)

### T1 Programme Template version engine (§13) — BIGGEST MISSING PIECE
- Migration 026: `enterprise_programme_templates` (id, organisation_id, name, category,
  version, status[draft/review/approved/published/superseded/archived], created_by,
  timestamps) + `enterprise_programme_template_versions` (template_id, version_no,
  payload_json[standard capacities, battery options, standard equipment/BOQ refs,
  drawings refs, reports, funding model, O&M model, required beneficiary/survey
  fields, protection/testing/commissioning, KPI/schedule/risk templates], published_at).
  RLS ENABLE, org-scoped.
- Services: template CRUD + version lifecycle transitions (validate legal transitions).
- Repo + routes + UI (list/create/version/publish). Projects generated from a template
  MUST store the template_version_id used (feeds T4).
- Key rule (source §13): later template edits must NOT overwrite completed/approved
  project designs — version pinning.

### T2 Richer programme registration (§12)
- Migration 027 (or fold into 025 if not yet applied): add columns sponsor,
  managing_institution, owner, start_date, target_completion_date, duration,
  objectives, target_energy_generation, target_grid_offset, target_carbon_reduction,
  contract_framework, technical_standards, kpi_framework, reporting_requirements,
  risk_classification, esg_requirements, local_content_target, job_creation_target,
  archive_status. Surface in `programme_form.html` (progressive-disclosure cards).
  Programme cloning route where permitted.

### T3 Bulk beneficiary import (§15)
- Enqueue a durable job (existing `enterprise_programme_jobs` queue). Upload CSV/Excel
  → stage rows → validate per-row → preview with row-level errors → dedup detection →
  operator corrects → approve → commit. Idempotent, resumable, chunked (no thousands
  in one request — source §36). Export register. Sensitive-field minimisation (§15).

### T4 Automated project generation (§17)
- Durable job: approved beneficiary + approved template version → create/link a
  SolarPro project via the existing design service, copy template defaults, link
  programme/phase/beneficiary, generate initial inputs/BOQ where supported, record the
  generation event, return partial-failure results. Single / batch / whole-phase.
  Background, progress, retry, cancel-where-safe, idempotent (source §17).

### T5 Granular RBAC (§11)
- Activate `enterprise_memberships.permissions_json`. Define role→permission matrix
  (~38 roles / ~22 permissions from §11). Enforce in `_require_membership` /
  per-route permission checks. Automated authorization tests proving role + region +
  cross-programme isolation (§39.3). Consider RLS FORCE once role model lands.

---

## Definition of done (per item, from source §45 + house four-gate)
Code + tests written → targeted tests pass → Codex review clean (all HIGH/CRITICAL
fixed) → Supervisor `/code-review` + `/security-review` → migration applied via gated
workflow (owner-authorised) → deployed via Force Render Deploy (owner "deploy") → LIVE
module smoke test passes (owner directive: "run full test suite on the live site") →
docs/IMPLEMENTATION_LOG.md updated. Module stays DARK until owner flips the flag and
walks the acceptance test.
</content>
