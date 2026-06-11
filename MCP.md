<!-- BEGIN: AGENTIC MCP REGISTRY (canonical seed — do not edit Sections 0–4 in place; re-sync from C:\Users\USER\_agentic_adk_mcp.md. Per-app entries go in Sections 5–8.) -->

# MCP.md — Model Context Protocol Registry & Agent Connection Map

This file is the per-app registry of MCP servers, agent connection points, and the bridge between **Claude Code (Software Engineering Agent)** and **Google ADK (Agent Operating System)**. Read this before launching any agent runtime, wiring a new tool, or onboarding a new MCP server.

> **Read alongside:** `CLAUDE.md` (Project Execution Directive + Agentic ADK Extension) and `context.MD` (orientation summary). If those three files disagree, the Directive wins, then the Extension, then this file.

## 0. What MCP is, in one paragraph

The **Model Context Protocol** is a standardised way for an LLM-driven agent (Claude Code, an ADK agent, a Codex pair-coder) to discover and call **tools, resources, and prompts** hosted by an external server. Each MCP server exposes a typed surface; each agent declares which servers it consumes. This file is the source of truth for "which MCP servers does THIS app expose and consume."

## 1. The Two Roles This App Plays

Every app under this account simultaneously:

- **Consumes MCP servers** (filesystem, git, GitHub, Postgres, Qdrant, Brevo, etc.) so its agents can act.
- **May expose MCP servers** of its own (e.g. a project's domain tools — solar-pv sizing, BOQ generation, tender extraction — wrapped as MCP so other apps' agents can call them).

Both directions are tracked in Section 5 below.

## 2. The Agent ↔ MCP Connection Map

```
┌─────────────────────────────────────────────────────────────────┐
│                       GOOGLE ADK RUNTIME                        │
│  (Agent Operating System — orchestrates business agents)        │
│                                                                 │
│   Executive Dept   Technology Dept   Engineering Dept   ...     │
│        │                  │                  │                  │
│        └──────────┬───────┴──────────┬───────┘                  │
│                   │                  │                          │
│                   ▼                  ▼                          │
│          Work Reviewer       Development Supervisor             │
│          Work Scheduler         (Governance Lane)               │
└──────────┬──────────────────────────┬───────────────────────────┘
           │                          │
           │  MCP                     │  MCP
           ▼                          ▼
   ┌───────────────┐         ┌───────────────────┐
   │ Claude Code   │◀──────▶ │ Codex CLI         │
   │ (SE Agent)    │  diff   │ (Review Agent)    │
   └──────┬────────┘         └───────────────────┘
          │
          │  MCP servers consumed:
          ▼
   filesystem · git · github · postgres · qdrant ·
   brevo · cloudflared · domain-specific (see §5)
```

## 3. The Four Gates as MCP Surfaces

Each governance gate is exposed as an MCP tool so any agent (including Claude Code) can call it programmatically:

| Gate | MCP tool name | Owned by | Returns |
|---|---|---|---|
| 1. Code review | `quality_gate.run` | Codex CLI runner | pass / fail + report path |
| 2. Supervisor sign-off | `supervisor.review` | Supervisor (Claude Code skills) | pass / fail + findings |
| 3. Work Reviewer | `governance.review_work` | ADK Work Reviewer Agent | `WorkReview` schema (see CLAUDE.md §2.1) |
| 4. Work Scheduler | `governance.update_task_status` | ADK Work Scheduler Agent | `WorkSchedule` schema (see CLAUDE.md §2.3) |

Until ADK is wired in this app, gates 3 and 4 are stubbed and call no-op MCP endpoints. Stubs are still mandatory — they keep the contract visible.

## 4. Universal MCP Server Registry (seed list)

These MCP servers SHOULD be configured in every app's runtime. Mark each row's status in Section 5 as `active`, `stubbed`, `unavailable`, or `not-applicable` for this specific app.

| Server | Purpose | Used by |
|---|---|---|
| `filesystem` | Read/write project files | Claude Code, ADK tools |
| `git` | Local git operations | Claude Code, Development Supervisor |
| `github` | PRs, issues, Actions | Claude Code, Codex, Development Supervisor |
| `postgres` | Structured data | All ADK agents that read/write project state |
| `qdrant` (or `chromadb`) | Vector memory | Memory layer, Document Intelligence |
| `redis` | Sessions, cache, queues | All agents |
| `brevo` (or chosen SMTP) | Transactional email | Sales, Support, Customer Success agents |
| `cloudflared` | Public tunnels | Demo + smoke-test against tunnel URLs (per `feedback_no_localhost`) |
| `document-intelligence` | PDF/Word/Excel/CAD/BIM readers | Engineering, Construction, Tender, Procurement agents |
| `vertex-ai` | Hosted ADK runtime | Production deployments only |

## 5. This App's MCP Servers (FILL IN PER APP)

### 5.1 Consumed (this app's agents call these)

| Server | Status | Endpoint / config location | Notes |
|---|---|---|---|
| filesystem | | | |
| git | | | |
| github | | | |
| postgres | | | |
| qdrant / chromadb | | | |
| redis | | | |
| brevo | | | |
| cloudflared | | | |
| document-intelligence | | | |
| vertex-ai | | | |
| (app-specific) | | | |

### 5.2 Exposed (this app publishes these for other apps)

| Server name | Tools exposed | Auth | Endpoint | Notes |
|---|---|---|---|---|
| | | | | |

## 6. Agent → MCP Permissions Matrix (FILL IN PER APP)

Which agent is allowed to call which MCP tool. The default is **deny**; explicit allowlist below.

| Agent | filesystem | git | github | postgres | qdrant | brevo | cloudflared | doc-intel | vertex-ai | (app-specific) |
|---|---|---|---|---|---|---|---|---|---|---|
| Chief Executive Agent | ro | – | – | ro | ro | – | – | ro | – | |
| Chief Operating Agent | ro | – | – | rw | ro | – | – | ro | – | |
| Work Reviewer Agent | ro | – | – | rw | ro | – | – | ro | – | |
| Work Scheduler Agent | ro | – | – | rw | ro | – | – | – | – | |
| Development Supervisor Agent | ro | ro | ro | rw | – | – | – | – | – | |
| Claude Code Agent | rw | rw | rw | rw | rw | – | rw | rw | rw | |
| Codex Agent | rw | rw | rw | – | – | – | – | – | – | |
| Sales agents | ro | – | – | rw | ro | rw | – | – | – | |
| Support agents | ro | – | – | rw | ro | rw | – | – | – | |
| Engineering agents | ro | – | – | rw | rw | – | – | rw | rw | |

Legend: `ro` = read-only · `rw` = read-write · `–` = denied. Tighten per app.

## 7. Secrets & Environment Variables

All MCP server credentials live in environment variables. Document each in `.env.example`. Never commit real secrets. Standard names (extend per app):

```
# MCP — universal
POSTGRES_URL=
REDIS_URL=
QDRANT_URL=
QDRANT_API_KEY=
GITHUB_TOKEN=
BREVO_API_KEY=
CLOUDFLARED_TUNNEL_TOKEN=

# MCP — Google ADK / Vertex AI (production only)
GOOGLE_APPLICATION_CREDENTIALS=
VERTEX_AI_PROJECT=
VERTEX_AI_LOCATION=

# MCP — Claude Code / Anthropic (governance gate 2)
ANTHROPIC_API_KEY=        # only if not using Claude Code CLI auth
CLAUDE_MODEL=             # default: claude-opus-4-7

# MCP — Codex / OpenAI (governance gate 1)
# Codex CLI uses ChatGPT Plus auth at C:\Users\USER\.codex\auth.json — no key needed
```

## 8. How to Add a New MCP Server (per-app checklist)

1. Add a row to Section 5.1 (consumed) or 5.2 (exposed).
2. Add the credential to `.env.example` and document in Section 7.
3. Update the permissions matrix in Section 6 — explicit allowlist, default deny.
4. Add a stub test in `tests/test_mcp_connections.py` that asserts the server registers cleanly.
5. Run the four gates (Section 3). New MCP wiring is a code change; it goes through Codex → Supervisor → Work Reviewer → Work Scheduler.
6. Log the addition in `docs/IMPLEMENTATION_LOG.md` per the Project Execution Directive §21.

## 9. Cross-App MCP Mesh (account-wide note)

Eventually every app under this account should be reachable as an MCP server by every other app's ADK runtime — that is the long-term shape of the AppGrowth / AI App Invent factory. Until then, this file is the per-app contract. When apps start consuming each other, add the producing app's name + URL to Section 5.1.

<!-- END: AGENTIC MCP REGISTRY -->
