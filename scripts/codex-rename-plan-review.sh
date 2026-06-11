#!/usr/bin/env bash
# One-off review: ask Codex CLI to scrutinize the rename plan
# ("Solar PV" -> "PV Solar") at reviews/rename-plan.md.
# Output to reviews/codex-rename-plan-review.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: a plan to rename user-visible 'Solar PV' -> 'PV Solar' across the codebase. Full plan at reviews/rename-plan.md. Read it before answering.

OWNER CONTEXT:
- Owner asked: 'go through each page where you see solar pv change to pv solar ... do all'.
- 'Do all' confirmed as scope: everything except historical data (data/beta_outreach/*.json, data/news_cache.json) and generated outputs (output/*).
- Industry-standard term is 'Solar PV' (NREL/IEC/IEEE all use 'Solar Photovoltaic'). Owner is aware and elected to proceed. Out of scope to re-litigate the rename.
- The app brand is 'SolarPro Global' (web_app.py:2158).

PROPOSED PLAN (Claude's categorization of 142 hits across 43 files):
  A. RENAME — user-facing display text in templates, marketing HTML, generated reports, user-facing docs (~60 hits).
  B. SKIP — identifiers: GitHub repo slug 'marc667us/solar-pv-designer-lite', file paths, dir 'solar_pv_designer/', filename 'solar_pv_store.html', email 'admin@solarpv.gh', class 'SolarPVApp', UA 'SolarPVDesignerLite/1.0'.
  C. SKIP — FUNCTIONAL code: web_app.py lines 8856, 8860, 9278, 9461, 9509 (Google search queries and keyword filters); test_agent.py:16 (search query); web_app.py:8979 (AI analyst system prompt).
  D. SKIP — official third-party name: 'Ghana Energy Commission - Solar PV Code of Practice (2019)' at docs/src/technical_guide.md:31.
  E. SKIP — legacy tkinter desktop app (auth/*.py, ui.py, main.py) per CLAUDE.md 'ignore them'.
  F. SKIP — historical/generated/log files (output/*, data/beta_outreach/*.json, data/news_cache.json, *.log, *.zip).
  G. SKIP — memory file name references (project_solar_pv.md, etc.).

CASING RULE (preserve per match):
  'Solar PV' -> 'PV Solar'
  'solar PV' -> 'PV solar'  (acronym stays uppercase, noun goes lowercase to keep sentence flow)
  'SOLAR PV' -> 'PV SOLAR'
  'solar pv' -> 'pv solar'

WEB_APP.PY EDITING PROTOCOL: per CLAUDE.md, NEVER use Edit tool on web_app.py. Use byte-replace Python script at scripts/patch_solar_to_pv_rename.py with assertions that each replace is non-identity.

POLICIES that apply (from CLAUDE.md):
- feedback_solar_app_works_dont_break: 'during sweeping fixes default to additive; never modify web_app.py silently - surface and ask.'
- feedback_solar_globe_off_limits: 'never touch templates/location.html, the D3 globe, static/land-110m.json, or the project site locator dot.'
- feedback_verify_before_acting: 'read the actual logs/error message before proposing any fix.'
- 'A feature is NOT complete until Codex has reviewed it AND the supervisor has signed off.'

YOUR JOB - give a decisive review of this plan:
  1. Open reviews/rename-plan.md and read it.
  2. For category C (functional): grep web_app.py for the cited lines and read 5 lines of context around each. Confirm or refute that renaming would break a search query, keyword filter, or LLM context. Find any other lines that should be in C but Claude marked A.
  3. For category A (rename): spot-check 3 of the templates/web_app.py hits. Are there any lines Claude has marked A that are actually identifiers or code?
  4. Order of byte-replacement: confirm that replacing 'Solar PV Designer Lite' BEFORE 'Solar PV' is mandatory (otherwise 'PV Solar Designer Lite' becomes 'PV Solar Designer Lite' after the second replace - or does it?). Walk through the sequence and identify any other longer-then-shorter dependencies.
  5. Brand coherence: 'professional PV Solar design platform' alongside 'SolarPro Global' - flag if any rendered page becomes incoherent.
  6. Anything Claude's grep missed: <title> tags, OG meta, alt text, aria-label, JSON schema descriptions, PDF metadata, JS string constants.
  7. Pick: APPROVE the plan as written, APPROVE WITH CHANGES (list them), or REJECT (explain blockers).
  8. State confidence (high/medium/low) and single biggest risk.

Be decisive. Do not enumerate every consideration - pick a path and own it.

${CONTEXT}"

codex_run "codex-rename-plan-review" "$PROMPT"
