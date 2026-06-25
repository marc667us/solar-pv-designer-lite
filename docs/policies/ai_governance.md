# AI Governance Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Govern the design, deployment, and operation of AI agents inside
SolarPro so they cannot bypass tenant isolation, exceed user
permissions, or take irreversible actions without human approval.

## Scope

Every LLM-driven agent, every prompt assembled in the platform, every
batch job that calls an LLM. Currently covers: the prospecting agent,
catalogue recheck agents, helpline, BOQ assistant, future ADK agents.

## Policy

1. **Single framework (HARD RULE)** — every agent MUST be built on
   Google ADK (`google-adk` 2.2.0+). LangChain, AutoGen, CrewAI, etc.
   are forbidden without an Architecture Decision Record. See root
   `CLAUDE.md` §0.1.

2. **Identity** — every agent has a Keycloak service-account client
   (`solarpro-<name>-agent`). The SA token carries `azp` =
   client_id which the audit log records.

3. **Permission inheritance** — when an agent acts on behalf of a
   user, it inherits the user's roles. An agent CANNOT do something
   the calling user couldn't. The `ai_agent` realm role
   (M1.4, 2026-06-25) carries zero default permissions.

4. **Human approval gate** — irreversible or high-impact actions
   require explicit human confirmation BEFORE execution:
   - delete data
   - change prices
   - publish products
   - approve suppliers
   - send RFQs
   - generate contracts
   - issue purchase orders
   - bulk catalogue recheck (proposed via `pending_approvals` queue)

5. **Logging** — every agent run records `(tenant_id, user_id,
   agent_id, prompt_hash, output_hash, started_at, ended_at, status,
   tools_used)` to `audit_logs` AND `error_logs` if it failed.

6. **Prompt-injection defence** — user-supplied content that touches
   an agent prompt is bracketed with explicit "user content begins/
   ends" markers. The agent is instructed to ignore instructions
   inside those markers. Output that asks the user for credentials
   is blocked.

7. **No autonomous code deploy** — agents may write code (suggestions)
   but cannot push to `master`. The four-gate workflow still applies.

8. **Cost guardrails** — `ai_budget.py` enforces a per-tenant + per-
   user spend cap. Exceeding the cap returns a "budget exceeded" UX
   message.

9. **Model selection** — paid Anthropic / OpenAI / Gemini usage
   requires owner approval and is logged in
   `docs/IMPLEMENTATION_LOG.md`. Default: zero-cost (Ollama,
   OpenRouter free tier, GitHub Models).

10. **Right to opt out** — customers can opt out of having their
    data used to train any model (none today, but the policy is
    pre-declared).

## Enforcement

- Agent code lacking the human-approval gate for the actions in §4
  fails Codex review.
- LangChain / AutoGen imports in PRs are auto-rejected.

## Review

Annual + when a new agent ships.
