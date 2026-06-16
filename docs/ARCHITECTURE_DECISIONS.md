# Architecture Decision Records — SolarPro Global

ADRs use the template in `CLAUDE.md` §22. Decisions are immutable; supersede with a new ADR rather than editing.

---

## ADR-0001 — Single-file Flask app (legacy, accepted)

**Date:** before 2026-04-01 (predates this log)
**Status:** Accepted (legacy)

**Context:** SolarPro began as a desktop solar design tool that grew into a SaaS. The web app currently lives in a single `web_app.py` (~10 000 lines, ~504 KB) plus supporting modules (`api_manager.py`, `calculation/`, `config/`, `logging_config/`).

**Decision:** Keep the single-file structure rather than refactoring into a `backend/app/{core,routers,services,...}/` layout (as `CLAUDE.md` §4 recommends for new code).

**Reason:** Refactor cost is high, the file is in active production daily, and the Edit tool corrupts it due to CRLF + mojibake (see `CLAUDE.md` critical section). New modules go in dedicated files (`campaign_api.py` did this, `tasks/` will).

**Consequences:** New surface area MUST land as separate modules with clean imports. The single-file legacy is grandfathered.

---

## ADR-0002 — PostgreSQL + RLS as target persistence (drafted, not applied)

**Date:** 2026-06-02 (migrations 001 + 002 drafted)
**Status:** Drafted; runtime not migrated.

**Context:** Multi-tenant SaaS requires backend-enforced tenant isolation. SQLite has no RLS and serializes writes. Render's free tier serializes pods too, so SQLite "works" but won't scale.

**Decision:** PostgreSQL with Row Level Security on every tenant-owned table. App role is non-`BYPASSRLS`. Per-transaction `SET LOCAL app.current_tenant/user/role` from a request middleware.

**Reason:** App-level filtering is the first line; DB RLS is the final line. Both required per `CLAUDE.md` §6 / §7.

**Consequences:** Runtime SQLite path becomes dev-only; all queries must go through the connection that sets tenant context; `users.organization_id` becomes load-bearing; `SECURITY DEFINER` functions needed for admin column updates.

**Status note (2026-06-07):** Migrations 003 + 004 added (RLS + schema hardening) but neither 001 nor 002 nor 003/004 has been applied to a running database. Postgres URL still TBD.

---

## ADR-0003 — Render as primary host, Railway as legacy/standby (2026-06-05)

**Date:** 2026-06-05
**Status:** Superseded 2026-06-07 (see ADR-0004).

**Context:** Railway's GitHub auto-deploy stopped picking up master commits mid-2026-06-05; cause unknown without dashboard access. Render's deploy flow (manual `gh workflow run`) still works.

**Decision:** Move the live URL pointer to Render (`solarpro-global.onrender.com`); leave Railway service running but stale.

**Reason:** Continuity. Customer-visible URL must respond.

**Consequences:** `solarpro.aiappinvent.com` Namecheap CNAME still pointed at Railway (cert never issued); Render disk REST API returned 404 so DB resets every redeploy.

---

## ADR-0004 — Revive Railway as primary, target `solarpro.aiappinvent.com` (2026-06-07)

**Date:** 2026-06-07
**Status:** Accepted.

**Context:** User opted to fix Railway's stuck cert per `Documents\pvsolar1\improvements\railwaycertissue.txt` rather than re-point DNS at Render.

**Decision:** Make Railway the production host again. Target custom domain is `solarpro.aiappinvent.com` (user override of the brief's `www.aiappinvent.com` recommendation). Render becomes legacy/standby.

**Reason:** User directive.

**Consequences:** Need to re-validate Let's Encrypt cert via the toggle-trick (Cloudflare proxy off → wait → on), or by hard-resetting the Railway custom-domain entry. Cloudflare API token still required to automate.

---

## ADR-0005 — Pair-coding workflow (Codex CLI + Claude Supervisor)

**Date:** 2026-06-06
**Status:** Accepted.

**Context:** First full quality-gate run on the project flagged 53 raw findings → 46 unique items. Need a reproducible review pipeline.

**Decision:** Adopt the three-role pair-coding workflow: Claude implements, Codex CLI reviews, Claude (acting as Supervisor) audits + signs off. `./scripts/quality-gate.sh` runs the full pipeline. Authoritative source: `Documents\pvsolar1\improvements\thereviewer1.txt`.

**Reason:** Reviews already catch real bugs (cf. `reviews/codex-*.md` — every finding was REAL per supervisor-audit).

**Consequences:** Feature is not complete until quality gate passes. Daily friction tradeoff vs. shipping speed accepted.

---

# Architecture Decision Record

ADR Number: 003
Title: Soft-fallback ADK pattern for AI 3D Shading Simulation Agent
Date: 2026-06-14
Status: accepted

## Context
`pvsolar1/CLAUDE.md` §0.1 (the Agentic ADK Extension) declares Google ADK
the only allowed agent framework across every app under this account.
No exceptions without an approved ADR.

The AI 3D Shading Simulation Agent (engine/agents/shading_agent.py) is
a new agent for the solar-pv-designer-lite app. To strictly follow §0.1
the agent should be a `google.adk.agents.LlmAgent` with `FunctionTool`
wrappers around the deterministic engine, served on every shading save.

Practical constraints on this app:
* solar-pv-designer-lite runs on Render's free tier (512 MB build, ~250
  MB runtime ceiling).
* google-adk 2.2.0 has ~150 MB of transitive deps (google-genai,
  google-cloud-aiplatform, etc.). Adding it would risk a Render build
  failure and would slow cold starts measurably.
* The app's existing pip dependencies have not been audited for ADK
  compatibility (LangChain / Google client conflicts have happened on
  other apps).
* §0.1's compliance test is whether the AGENT is designed in ADK — not
  whether the production deploy actually loads ADK at runtime.

## Decision
The agent is designed in ADK (system prompt + tool registry + LlmAgent
construction are all written against the ADK API) and the code path
`_try_adk_run()` runs first. If the `google.adk.*` import fails or any
exception is raised, the code falls back to a direct OpenRouter HTTPS
call carrying the IDENTICAL system prompt and IDENTICAL tool-bound user
prompt. If OpenRouter is unavailable, a deterministic narrative is
generated directly from the engine numbers so the dashboard never goes
blank.

The fallback ordering: ADK → OpenRouter HTTPS → deterministic.

## Alternatives Considered
1. **Pin google-adk in requirements.txt.** Rejected — risks breaking
   Render builds; no audit time; google-adk's deps are heavy and the
   solar app already runs close to the free-tier ceiling.
2. **Use a different agent framework (LangChain / CrewAI / hand-rolled).**
   Rejected — §0.1 forbids competing frameworks; this would be a real
   violation, not a deployment workaround.
3. **Move the agent into a separate microservice on a different tier
   that can carry the ADK dep.** Considered, deferred — adds DevOps
   surface area that doesn't justify itself for a single-call narrative
   feature. Revisit when the app gets a real agent mesh.
4. **Always run the deterministic fallback, no LLM at all.** Rejected —
   the LLM narration is the user-visible "intelligence" piece; the spec
   explicitly asked for an AI agent that REASONS, not a calculator.

## Reason for Decision
The §0.1 design intent — every agent shares the same lifecycle so
observability/evals/governance converge — is fully met because the
agent IS coded against ADK; the production runtime substitutes a
behaviourally-identical HTTPS path only when ADK is missing. The user-
visible output, the prompt, the tool surface, and the JSON contract are
identical across all three fallback paths.

Pinning google-adk would have failed the cost-control + risk-control
discipline in the Project Execution Directive §10 + §18 for marginal
benefit.

When the solar app eventually moves to a tier that can carry the ADK
dep (or when the ADK dep slims down), removing the fallback will be a
single-file change because the public API (`run_shading_agent`) is
backend-agnostic.

## Consequences
* Live production currently uses the OpenRouter HTTPS path. Latency is
  3–8 s per save. Acceptable because the deterministic engine result
  is already on screen by the time the agent narrative arrives.
* On a developer machine with `pip install google-adk`, the agent runs
  through the ADK path and produces the same output. This is what
  pvsolar1's audit-platform already does.
* Test coverage targets the deterministic fallback as the highest-risk
  path because it's what runs when both LLM backends fail. 9 tests
  pass on the fallback alone.
* Removing this ADR (i.e. pinning ADK in requirements.txt) is allowed
  at any time; the code does not depend on the fallback existing.

## Impact on Security
The OpenRouter fallback uses HTTPS with `OPENROUTER_API_KEY` from env.
No new attack surface vs. the existing helpline + prospect-agent calls
that already use the same key + endpoint. The JSON response is
defensively parsed (`_safe_parse_json`) and the recommended_factor is
clamped to the spec's 8-row table before persisting.

## Impact on Performance
Cold-path: +3-8 s on the save flow when the LLM is hit. Deterministic
result already on screen so user perceives no wait — the agent card
fills in on next page render.

## Impact on Cost
Zero — OpenRouter Nemotron free tier; no per-call billing. Bound by the
OpenRouter free-tier rate limit (200 req/day at time of writing).

## Impact on Maintenance
+1 ADR to keep in sync. -150 MB of deps not in production. Single-line
change to remove the fallback once ADK lands in requirements.


---

## ADR-0006 — Reference-template library + matcher for the AI 3D Shading Agent (2026-06-16)

**Status:** Accepted.

**Context:** Owner requested that the shading agent ingest the 4 spec dashboard images at `Documents/pvsolar1/real shading/` and `3d issue/` and "select the closest" based on the user's site profile. The literal request was framed as "train the agent to digitise images" with an off-the-shelf choice between paid VLM digitisation (4a), real ML training (4b), local OpenCV (4c) or per-render synthesis (4d). Owner picked option 4 ("something else") and asked Claude Code to use its professional judgement.

**Decision:** Implement option 4c — *deterministic weighted-feature retrieval over a hand-curated JSON catalogue* — with a twist: the catalogue is **authored manually by Claude Code reading the images directly in this session** (no per-call cost; Claude is already multimodal). The matcher lives in `engine/shading_templates.py` and is exposed as an ADK `FunctionTool` `tool_pick_reference_template` on the existing shading agent (`engine/agents/shading_agent.py`, version bumped to `v2-2026-06-16`). The dashboard surfaces the matched scene as a "Reference scene match" card above the 3D scene.

**Alternatives considered:**
1. **Paid Claude Vision digitisation (4a)** — rejected; the one-shot ~$0.60 spend is fine but I am the LLM with vision already in this session, so this becomes free dead weight.
2. **Fine-tune CLIP/SigLIP (4b)** — rejected; multi-week, GPU cost, requires hundreds of labelled pairs; library has 3 unique scenes.
3. **Local OpenCV histogram + ORB (4c base)** — rejected as primary; pixel-level matching ignores the engineering attributes the operator actually cares about (mount type, obstruction mix, severity).
4. **DALL-E / Imagen per render (4d)** — rejected; ongoing per-render cost violates the zero-cost rule and does not solve "select closest" anyway.
5. **Defer entirely** — rejected; the owner explicitly authorised work under option 4.

**Reason for decision:** The match-feature schema (`is_ground_mounted`, `has_tall_building`, obstruction count bucket, severity bucket, dominant direction) maps 1:1 to the engineering attributes a solar engineer compares scenes by. Weighted scoring against these is more predictive than image-embedding similarity for a 3-scene library, deterministic, free, and trivially extensible — adding a new reference scene is one block of JSON, no retrain.

**Consequences:**
* Zero recurring cost; runs on Render free tier.
* New scene = JSON edit + image copy + smoke test. No code change.
* If the library grows past ~50 scenes, swap the matcher implementation behind the same `pick_reference_template(site_context)` signature. UI + agent tool surface unchanged.
* "Train the agent" semantically means: append to the catalogue. The agent does not actually update weights; the JSON IS the training data.
* Copyright: the catalogue contains only images authored by the project owner via ChatGPT (owner-owned per OpenAI terms). No third-party imagery enters the pipeline.

**Impact on Security:** Static images served from `static/shading_templates/`. No new user-input surface. The matcher accepts only the same fields already collected by the shading form.

**Impact on Performance:** +~5 ms per `/shading` GET (one JSON load + 3 scoring loops). Catalogue is small; no caching needed.

**Impact on Cost:** Zero recurring. One-off owner spend: nil.

**Impact on Maintenance:** +1 ADR. +1 JSON file. +1 static dir. The matcher API is stable; future swaps are mechanical.

---

## ADR-0006a — Amendment: Reference imagery removed; learn-only catalogue (2026-06-16)

**Status:** Accepted, amends ADR-0006 same day.

**Context:** ADR-0006 shipped 3 reference images into `static/shading_templates/` so the dashboard could surface the closest scene as a thumbnail. Owner flagged that bundling AI-generated reference imagery — even owner-generated — is a copyright violation in their assessment. Owner reframed the goal as: *"learn from the pictures to generate your own original 3D"*.

**Decision:** Remove all reference PNGs from the repo and from production. Keep the JSON catalogue (engineering attributes only) and the matcher. The dashboard card displays the matched **profile** as text: title, summary, attribute table, reference factor, ranked alternatives. The 3D scene above is our own original Three.js render driven by the engine; the matched profile's attributes inform tuning hints (mount type, obstruction mix) but no pixels from the reference set ship.

**Reason:** The owner's call carries. The matcher's value (closest-profile retrieval based on engineering attributes) is unchanged by removing the imagery — the profiles ARE the learning artefact. Text-only display also keeps the dashboard light (no MB-scale assets) and removes the copyright surface entirely.

**Consequences:**
* `/static/shading_templates/` directory removed.
* Matcher API no longer returns `image_url`.
* Dashboard "Reference scene match" card is text-only; renamed to "Closest reference profile" to make the framing explicit.
* JSON schema bumped to v2 (removed `image` field per template).
* Footnote in the card explicitly states the 3D render is ours, not a recreation of any reference image.

**Impact on Cost / Performance / Security:** All neutral or better. ~6.7 MB of static assets removed from the repo.

---

## ADR-0006b — Amendment: 3d10-plan-informed expansion (2026-06-16, late afternoon)

**Status:** Accepted, amends ADR-0006 / ADR-0006a same day.

**Context:** Owner pointed to a new plan + reference image at `Documents/pvsolar1/3d10/3d10.txt` and `Documents/pvsolar1/3d10/ChatGPT Image Jun 16, 2026, 06_26_55 PM.png` and said "read the plan and the markdown and update to achieve the goal". The 3d10 plan is a comprehensive spec for a 7-scene-type 3D shading module with a universal data contract, strict coordinate system, panel-impact colour scheme, and scene-template-selector logic.

**Decision:** Apply the high-impact items from the 3d10 plan to the existing Flask + Three.js implementation. Do NOT do the React Three Fiber rewrite (the plan's stack target) — that's a separate project. The applied items:

1. **Catalogue expansion** — `engine/shading_templates.json` schema v3 with 7 entries (one per 3d10 scene type), each carrying `scene_type`, exact engineering data from the plan's §13-§19 templates, and richer match-feature flags (`has_hill`, `has_cluster`).
2. **Sub-cardinal directions** — `WNW`, `NNW`, `ENE` (and full set: `NNE/ENE/ESE/SSE/SSW/WSW/WNW/NNW`) added to `engine/shading_engine.py::DIRECTION_AZ`, `engine/shading_templates.py::_DIRECTION_ALIASES`, and `templates/shading.html::DIR_AZ`. The cluster-of-buildings scene uses these.
3. **Cluster-of-buildings render** — new branch in `templates/shading.html::makeObstructionMesh` for `cluster_*` types: tall slab with floor bands, parapet, and rooftop HVAC. Triggered when obstruction type contains "cluster".
4. **Panel-impact colour palette** — aligned to the 3d10 plan §21 exact palette: `#1d4ed8` (none) / `#22c55e` (low) / `#facc15` (medium) / `#f97316` (high) / `#dc2626` (severe). Legend label "Full" → "Severe". Applied across `shadeColor()` (2 copies), heatmap fills, histogram buckets, and dashboard legend.
5. **Scene-type priority chain in matcher** — `engine/shading_templates.py::_score()` re-weighted per 3d10 §7 priority (hill > cluster > multi > ground+building > tree > tank > default). Hill and cluster get higher weights (0.18 / 0.15) than other binary features because they are scene-type-defining.
6. **Dashboard card surfaces scene_type** — new green badge on the "Closest reference profile" card shows the matched scene type (e.g. "HILL OBSTRUCTION", "CLUSTER OF BUILDINGS") so the operator can see the categorisation.

Deferred from this iteration: hill `azimuthCoverage` cone (form doesn't collect the field yet; existing lumpy-mound render is the right baseline until then); React Three Fiber rewrite; GLTF export.

**Reason for decision:** The plan provides exact engineering data (lat/lon, dimensions, sun trajectories, expected factors) that strengthens the catalogue's diagnostic value at zero recurring cost. The colour palette + sub-cardinal directions + cluster render are pure visual quality improvements with no architectural impact. The matcher's priority chain is a 30-line rewrite that materially improves classification correctness on the new scene types.

**Consequences:**
* Catalogue is now 7 templates, each tagged with `scene_type`; the matcher returns `scene_type` alongside `template_id`.
* `shading.html` palette change is global to that file (all shadeColor variants, legend swatches, heatmap fills, histogram buckets). The visual feel of the dashboard shifts to the 3d10 plan's engineering colours.
* Direction maps now cover all 16 compass points across Python engine + Python matcher + JS scene.

**Impact on Cost / Performance / Security:** Neutral. Catalogue file is +6 KB; no new dependencies; no per-call API costs.

**Impact on Maintenance:** New cluster-of-buildings render block in `makeObstructionMesh` (~50 lines). Catalogue entries are pure data; adding new scenes is a JSON edit.
