#!/usr/bin/env bash
# One-off review: ask Codex CLI for the fastest legitimate path
# to post the beta launch to Facebook + Instagram + LinkedIn TODAY.
# Output to reviews/codex-social-posting-path.md.
set -e
cd "$(dirname "${BASH_SOURCE[0]}")/.."
source ./scripts/_codex-runner.sh

CONTEXT="$(gather_context)"

PROMPT="You are Codex acting as Independent Pair Programmer for the solar-pv-designer-lite repository.

DECISION TO REVIEW: how to actually post the SolarPro beta launch announcement to Facebook + Instagram + LinkedIn TODAY (within hours, not days).

OWNER CONTEXT:
- v0.9.0-beta.1 is live at solarpro.aiappinvent.com. 35 invitees emailed yesterday.
- Owner wants to broaden the funnel: post landing-page + flyer to FB / IG / LinkedIn now.
- Owner explicit: 'you have to find a way to post, work with reviewer and supervisor to find a way.'
- Owner is NOT willing to have me hand off and say 'go upload it manually.' Wants automated posting if at all possible today.

CONSTRAINTS (from memory + CLAUDE.md):
- ZERO COST policy: only free-tier services. No paid Hootsuite / Buffer / Publer / Zapier paid plans.
- NO DASHBOARD ASK rule: owner refuses recurring 'click through provider dashboards' steps. **One-time OAuth setup is acceptable** because it bootstraps recurring API access — but any approach that requires manual posting via web UI for every post is rejected.
- NO PROVIDER THRASH: don't propose switching social platforms; the four named (FB/IG/LI/YT) stand.
- TOS-COMPLIANT ONLY: no headless browser automation against FB/IG/LI login. That risks account ban.
- The brand domain aiappinvent.com is on Brevo + Namecheap. Google Workspace for marc@.
- Existing brand/business assets: unknown — owner may or may not have a Facebook Page, Instagram Business Account, LinkedIn Company Page. Need to flag this as a gating question.

SCOPE — answer these:
  1. **Fastest legitimate API path for FB Page + IG Business + LinkedIn:**
     - For Meta (FB+IG): exact steps to get from 'no app, no token' to 'curl POSTs a photo+caption to the Page feed and the IG Business account'. Include developer.facebook.com app creation + token-generation flow. Quote scope names (pages_manage_posts, instagram_basic, instagram_content_publish). State realistic minute-by-minute time estimate.
     - For LinkedIn: same — app at linkedin.com/developers/, OAuth scope (w_member_social for personal, w_organization_social for company page), token generation.
     - Total realistic time for a first-time-setup human: 30 min? 2 hours? Be honest.

  2. **Pre-requisites the owner must verify FIRST** (otherwise the API path doesn't work):
     - FB Page exists for SolarPro Global brand
     - IG account is set to 'Business' or 'Creator' AND linked to that FB Page
     - LinkedIn personal profile (for personal-post route) OR LinkedIn Company Page (for organization-post route)
     - If any of these don't exist, what's the workaround?

  3. **Alternative: free tools that require LESS setup**
     - Buffer free tier (3 channels, 10 posts queued) — does it have an API for the free plan, or only via web UI?
     - Postiz / Mixpost self-hosted — can it be spun up on a free Render web service in <1 hour?
     - IFTTT free (2 applets) — could RSS-or-trigger → FB/IG/LI work?
     - For each: net time to first post, and whether it lets us script future posts vs. forcing manual.

  4. **Risk-rank ALL paths** by:
     - Account-safety risk (ToS / temp ban / shadow-ban)
     - Time cost (first post + each subsequent post)
     - Dollar cost (must be \$0)
     - Maintenance cost (token refresh, app review)

  5. **Pick the single path you'd recommend** for the next hour, and the single biggest risk in it.

  6. **YouTube is skipped this round** — owner already decided. Don't propose it.

  7. Bonus: if you spot a path I haven't listed that's faster and safer, surface it.

Be decisive. Do not enumerate every option then refuse to recommend. Pick a path and own it.

${CONTEXT}"

codex_run "codex-social-posting-path" "$PROMPT"
