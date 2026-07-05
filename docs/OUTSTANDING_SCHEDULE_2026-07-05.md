# Outstanding Requirements, Jobs & Corrections — Solar PV

**Prepared:** 2026-07-05 (session close) · **Live tip:** `9cc9694` on `solarpro.aiappinvent.com` (healthy: ping/marketplace 200, dashboard 302)

This is the consolidated backlog carried into the next session. Read alongside
`memory/outstanding_work_schedule.md` and the two 2026-07-05 resume-pointer memories.

---

## ✅ Closed today (for the record)
- **Project Funding ("Sponsor") module — 100% complete, Slices 1–10 (a+b+c), all live** (`d62e24d`). Institution registry, workspace, review, comms, hard-copy tracking, 2% success fee + revenue dashboard, deterministic AI assessment, CRM/pipeline handoff, 22-test suite, + extension to regular `/project/<pid>` via `PF_PID_OFFSET`.
- **UI de-clutter + reset-recent-history + CVD-safe cost-plan donut** (`cd49964`).
- **Check-My-Bill pitch "0% drop" bug fixed + yellow-band contrast + full calc audit** (`9cc9694`). Codex APPROVE, 31 tests pass.

---

## P0 — Corrections / confirmations to close first (next session)

| # | Item | Why | Action | Owner |
|---|---|---|---|---|
| C1 | **Dashboard "reset" scope confirmation** | Owner asked *"dashboards must have reset buttons to clear all values."* We shipped a **non-destructive filter/view reset** macro (`templates/_dashboard_reset.html`). "Clear all values" *could* mean destructive data-clear — a possible gap between ask and delivery. | Confirm intent: (a) filter/view reset only = **done**; or (b) also add a guarded "clear data" action per dashboard. Decide which dashboards. | Owner decision → Claude |
| C2 | **Verify reset buttons render on every intended dashboard** | Macro exists; coverage not audited page-by-page. | Walk each main dashboard, confirm the button is present + works. ~20 min. | Claude |

---

## P1 — Owner actions (dated migrations now OVERDUE + access blockers)

| # | Item | Status | How to clear |
|---|---|---|---|
| O1 | **Phase B migration 005** (drop NULL-escape; require tenant_id on INSERT) | **OVERDUE** (was due 2026-06-30) | `gh workflow run "Apply Migration 005 (Phase B)" -f confirm=PHASE_B` — runbook `docs/PHASE_B_RUNBOOK.md`. Pure DDL on live PG. Also resolves the KC-signup sentinel `password_hash` workaround. |
| O2 | **FK VALIDATE migration 021** | **OVERDUE** (was due 2026-07-03; 7-day clean window after mig 013 elapsed) | `gh workflow run "Apply Migration 021 (VALIDATE FOREIGN KEYs)" -f confirm=VALIDATE_FK_APPLY` |
| O3 | **LLM chain on live falls back to rule-based** | Blocker for D & F below | Rotate `OPENROUTER_API_KEY` GH Secret; refresh ephemeral Ollama tunnel (`OLLAMA_URL`); validate `GITHUB_TOKEN` for GH Models. Verify via `/admin/ops/ai/test`. |
| O4 | **Google ADK unusable — Gemini free key 429 (quota 0)** | App Factory §0.1 needs ADK for agent/plan work; currently falls back to Codex | Provision a paid Gemini key **or** a Vertex-AI service account (`GOOGLE_GENAI_USE_VERTEXAI=1` + ADC). |
| O5 | **Local `.env` SOLARPRO_*_PASSWORD drifted from GH Secrets** | Live-KC E2E tests fail "Invalid username or password" | Sync local `.env` to GH Secrets, or use `Sync KC Seed Passwords` workflow with a throwaway for E2E. Don't disclose passwords in chat. |
| O6 | **RLS owner-bypass close-out** (SOC 2 Phase 7) | 47/47 tables FORCE-enforced already; residual pieces open | `refresh_gauges`/`audit_logs` reads need admin-GUC fix when `/metrics` goes live; then Phase B cutover (O1). |
| O7 | **Observability VPS bring-up** | Prom/Loki/Grafana defined-as-code, not running | Set `METRICS_BEARER` on Render + `docker compose` the monitoring stack on a VPS; dashboards JSON already in repo. |
| O8 | **Brevo bulk Keycloak-migration email** | Pre-cutover comms | Run `scripts/broadcast_keycloak_migration_email.py` **14 days before** the chosen KC cutover day. |

---

## P2 — Engineering jobs (pick up with the relevant area)

| # | Item | Effort | Gated on |
|---|---|---|---|
| E1 | **AI Sales Agent handoff** — stub writes `growth_activities` but never calls an LLM; wire to `/api/assistant/chat` for real lead scoring | ~30 min | O3 (LLM chain) |
| E2 | **Opportunities deep-crawl LLM half** — persistence done; cron + LLM-classification crawler remains | ~1–2 h | O3 (LLM chain) |
| E3 | **Bulk back-fill structured `voltage_v` / `frequency_hz`** on 437+ marketplace products (one-shot GH Actions script parsing existing `spec` text) | ~1 h | — |
| E4 | **Catalog price sweep** — 605 Complete-BOQ items seeded with ballpark GHS; walk Fire Alarm / BMS / IP CCTV / Medical / LV switchboards to real supplier prices | 1–3 h owner-driven | before serious quoting |
| E5 | **Funding revenue — FX roll-up for mixed-currency** workspace totals (dashboard currently groups by currency; no cross-ccy sum) | ~1 h | — |
| E6 | **Per-project Share E2E** loops `/dashboard`↔`/admin` after PKCE callback (search backend independently proven) | ~30 min debug | not blocking |
| E7 | **Bankability optimizer before/after refinement** (optional) — compute the "before" economics via the optimizer's own model at original levers instead of the stored `eco0`; they're already consistent (same model), so belt-and-braces only | ~20 min | low priority |

---

## P3 — Housekeeping (dedicated cleanup session)

| Item | Note |
|---|---|
| Untracked `patch_*.py` + `*.bak-*` + `_pre_v2swap`/`_legacy` files in repo root | Harmless clutter; delete only in a focused cleanup pass. |
| `tmp/METRICS_BEARER_secret.txt` — uncommitted secret | **Never `git add .`** — stage files specifically. Recurring warning. |
| `web_app.py.before-*-bak` backups | Safe to delete; harmless. |

---

## Next-session sanity check

```bash
# Live tip
curl -sS "https://api.github.com/repos/marc667us/solar-pv-designer-lite/commits/master" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['sha'][:10], d['commit']['message'].split(chr(10))[0])"
# Health
for p in / /api/ping /marketplace; do curl -sS -o /dev/null -w "$p -> %{http_code}\n" "https://solarpro.aiappinvent.com$p"; done
# Tests
python -m pytest test_bill_check_pitch.py test_funding_module.py test_bankability_optimizer.py -q
```

**Recommended first move next session:** resolve **C1** (reset-button intent) so we either mark it done or correct it, then clear the two overdue owner migrations **O1/O2**.
