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
