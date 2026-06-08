# DNS Edit Skill — Team Contract

Claude, Codex (planner/reviewer), and the Supervisor are coworkers on this
project. Each has their own role and skills; together with the human owner we
form the team that builds and ships changes. This skill extends our team's
reach into DNS — adding domains and subdomains, creating/editing/deleting DNS
records — using the same three-role rhythm we use for code: Codex plans, the
Supervisor approves, the script applies. The human is on the team too, with a
focused role: **login** — generate one API token per provider, paste into env.
After that, the team handles the DNS work end-to-end.

## Who does what

| Role | What they do | What they cannot do |
|---|---|---|
| **Owner / Claude (requester)** | States the intent in plain English: "Point solarpro.aiappinvent.com to solarpro-global.onrender.com". Triggers `./scripts/dns-edit.sh "<intent>"`. | Cannot bypass the supervisor. Cannot call provider APIs directly from scripts in this skill. |
| **Codex (planner)** | Reads the intent + repo context + current zone state (via provider API list calls) and writes a single `reviews/dns/<id>.plan.json` that fully specifies the change (provider, zone, operation, record, rationale, rollback, verification). | Cannot apply. Cannot mark its own plan approved. |
| **Supervisor (approver)** | Reads `plan.json`, runs the DNS safety checks (see `supervisor-checks` below), writes `reviews/dns/<id>.verdict.md` ending in `SUPERVISOR VERDICT: PASS` or `SUPERVISOR VERDICT: FAIL`. On PASS, drops the sentinel `reviews/dns/<id>.approved`. | Cannot edit the plan — only PASS or FAIL it. If a finding needs a different plan, FAIL with reasons; the requester restarts. |
| **Apply step (executor)** | Reads `plan.json`, verifies `<id>.approved` exists, dispatches to `scripts/dns-providers/<provider>.sh`, writes `<id>.applied.json` (success) or `<id>.failed.json` (HTTP error). | Refuses to run if the approval sentinel is missing or the plan was modified after approval (checksum guard). |
| **Human** | Generates the provider API token once at the dashboard. Pastes it into env or `.env`. Never clicks DNS records manually. | Should not approve plans — that's the supervisor's job. May veto by deleting the `.approved` sentinel before apply runs. |

## Supervisor checks (the DNS safety list)

The supervisor FAILs unless every check passes. These are encoded in
`scripts/dns-supervise.sh` and re-stated to the reviewer as the prompt.

1. **Zone authority** — the zone in the plan matches a zone the configured
   provider actually controls (lookup via provider API). Refuse if missing.
2. **Target reachability** — for CNAME/A records, the target name resolves OR
   the destination service responds on the expected port. Refuse pointing a
   live host at a dead origin (this is the bug that kept the solar app's
   custom domain dark for a month).
3. **Blast radius** — if the operation overwrites an existing record with a
   different value, the plan must include the prior value in `rollback`.
4. **TTL sanity** — TTL between 60 and 86400 seconds (or provider "auto").
5. **No wildcard footguns** — `*.<zone>` records require an explicit
   `risk: "high"` in the plan and a stated business reason.
6. **Production domain protection** — if the zone is on the project's
   `production_domains` allowlist (see `dns-edit.config`), the plan must
   include an explicit `production: true` flag confirming the change is
   intended for the live customer-facing surface.
7. **Cert path coherence** — if attaching a custom domain to a hosting
   provider (Render/Railway/Fly), the corresponding hosting-side attachment
   step is either already done OR is in the plan as a prior operation.

## File layout

```
scripts/
  dns-edit.sh              # entry point: dispatches sub-commands
  dns-plan.sh              # produces reviews/dns/<id>.plan.json via Codex
  dns-supervise.sh         # produces reviews/dns/<id>.verdict.md + .approved
  dns-apply.sh             # reads plan + sentinel, calls provider
  dns-providers/
    _lib.sh                # JSON-via-python helpers, env loading, logging
    cloudflare.sh          # Cloudflare API v4 (zones + DNS records)
    render.sh              # Render API (custom domain attach/list/verify)
    namecheap.sh           # Namecheap API (IP whitelist required; not all plans)

reviews/dns/               # all plan/verdict/apply artifacts (gitignored)
  <id>.plan.json
  <id>.verdict.md
  <id>.approved            # zero-byte sentinel; presence = supervisor PASS
  <id>.applied.json        # API response on success
  <id>.failed.json         # error body on failure
```

## Credentials (the "login" step)

Each provider needs ONE env var (or set, for Namecheap). Generate once, store
in `.env` at project root or export in the shell that runs `dns-edit.sh`. The
script reads `.env` automatically if present.

| Provider | Env var(s) | Where to generate |
|---|---|---|
| Cloudflare | `CLOUDFLARE_API_TOKEN` | https://dash.cloudflare.com/profile/api-tokens → "Edit zone DNS" template + add SSL:Edit permission |
| Render | `RENDER_API_KEY` | https://dashboard.render.com/account/api-keys |
| Namecheap | `NAMECHEAP_API_USER`, `NAMECHEAP_API_KEY`, `NAMECHEAP_USERNAME`, `NAMECHEAP_CLIENT_IP` | https://ap.www.namecheap.com/settings/tools/apiaccess/ — must also whitelist your client IP. Plan tier matters: free/basic accounts don't get API access. |

> Railway is disabled in this project (dead infra, decommissioned 2026-06-08). The `railway.sh` provider file is kept in the tree for reference but `dns-apply.sh` and `dns-supervise.sh` will refuse plans naming it.

## Why this exists

The owner spent a month with `solarpro.aiappinvent.com` returning HTTP 000
because the only fix was a single CNAME edit at a dashboard and the owner
refused (rightly — it's not their job). This skill removes the dashboard
dependency: any DNS change the AI pair can plan + supervise, the AI pair can
also apply. Owner stays out of the loop except for the one-time token paste.
