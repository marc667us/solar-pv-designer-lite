#!/usr/bin/env bash
# One-off review: ask Codex CLI to scrutinize the APPLIED rename diff
# ("Solar PV" -> "PV Solar"). Counterpart to codex-rename-plan-review.sh which
# reviewed the PLAN; this reviews EXECUTION against that plan.
# Output to reviews/codex-rename-apply-review.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export CONTEXT_DIFF_LINES=400
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: the APPLIED rename 'Solar PV' -> 'PV Solar' (and 'Solar PV Designer Lite' -> 'SolarPro Global — PV Solar Designer Lite' on tool-name lines).

PRIOR PLAN + PLAN-REVIEW (read these first):
- reviews/rename-plan.md (the plan)
- reviews/codex-rename-plan-review.md (your earlier APPROVE WITH CHANGES verdict + findings #1-#5)

WHAT WAS APPLIED THIS SESSION (uncommitted; tracked + untracked):
  Modified-tracked:
    web_app.py (already renamed in prior session via scripts/patch_solar_to_pv_rename.py)
    solar_pv_store.html
    templates/dashboard.html, landing.html, referrals.html, report_installation.html, report_proposal.html, settings.html, support_user_guide.html
    calculation/boq_generator.py
    calculation/specification_generator.py
    calculation/economic_impact_generator.py
    calculation/installation_method_generator.py
    scripts/patch_proposal_superset.py        # anchor updated line 27
    scripts/patch_pdf_diagrams_wiring.py      # anchor updated line 75
    .github/workflows/send-beta-invites.yml   # line 89 prose
    docs/src/user_guide.md                    # line 2 heading
    SPEC.md                                   # lines 22, 41
  Untracked (also part of this rename batch):
    scripts/patch_calc_solar_to_pv_rename.py  # new sister-patcher to patch_solar_to_pv_rename.py
    scripts/send_beta_invites.py              # lines 59, 127 prose (file already untracked from prior session)

HARD EXCLUDES (must NOT have been touched — verify):
  - web_app.py C-category functional code (search queries ~8856/8860/9461, keyword filters ~9278/9509, AI prompt ~8979, _GH_REPO ~10082)
  - Repo slug 'marc667us/solar-pv-designer-lite' anywhere
  - solar_pv_designer/ directory, solar_pv_store.html FILENAME, solar.db, admin@solarpv.gh, SolarPVApp, SolarPVDesignerLite/1.0
  - Legacy tkinter app (auth/*.py, ui.py, main.py)
  - Ghana EC Code references (docs/src/audio_tech_walkthrough.txt:5, docs/src/technical_guide.md:31)
  - Historical/generated: data/beta_outreach/*.json, output/* (other than fresh renders during verification), data/news_cache.json
  - URLs containing repo slug in workflow lines 115/116 and script lines 89/160/161

PATCHER-ANCHOR INVARIANT (Codex finding #3 — CRITICAL): The patcher anchors must match the post-rename web_app.py:5835 string ('PV Solar Proposal'), or future patcher re-runs silently no-op. Specifically:
  - scripts/patch_proposal_superset.py:27 END_ANCHOR
  - scripts/patch_pdf_diagrams_wiring.py:75 ROUTES entry for 'Proposal'

YOUR JOB — be decisive:
  1. Read reviews/rename-plan.md and reviews/codex-rename-plan-review.md. Note your earlier 5 findings and check that each was honored in this apply.
  2. Use git diff + direct file reads to inspect the actual changes. Spot-check 5 high-risk hits across at least 3 different files.
  3. Check the HARD EXCLUDES list: grep for each excluded pattern and confirm it is still present (not renamed).
  4. Casing-rule sanity (per plan):
       'Solar PV' -> 'PV Solar' (title case)
       'solar PV' -> 'pv solar' (lowercase prose)
       'SOLAR PV' -> 'PV SOLAR' (uppercase headers)
     Pick 2 hits of each and confirm casing was preserved correctly.
  5. Confirm the patcher-anchor invariant above by running:
       grep -n 'PV Solar Proposal' web_app.py scripts/patch_proposal_superset.py scripts/patch_pdf_diagrams_wiring.py
       grep -n 'Solar PV Proposal' web_app.py scripts/patch_proposal_superset.py scripts/patch_pdf_diagrams_wiring.py
  6. Look for missed callsites that the plan or apply might have overlooked: <title>, OG meta, alt text, aria-label, JSON schema descriptions, PDF metadata, JS string constants, comments that the user reads (e.g., view-source).
  7. Verify the new sister-patcher scripts/patch_calc_solar_to_pv_rename.py is idempotent (re-running on already-applied files should skip, not assert-fail).
  8. Verdict: APPROVE / APPROVE WITH CHANGES (list them) / REJECT (explain blockers).
  9. State confidence (high/medium/low) and single biggest residual risk.

Be decisive. One finding per defect; do not enumerate every consideration.

${CONTEXT}"

codex_run "codex-rename-apply-review" "$PROMPT"
