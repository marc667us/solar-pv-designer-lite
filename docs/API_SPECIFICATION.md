# API Specification — SolarPro Global

All routes are served by `web_app.py` unless noted. Auth = Flask session cookie (`@login_required`). Admin = `@admin_required` (admin flag in users table). CSRF = `_csrf` form field on POST; `X-CSRF-Token` header for JSON.

Schema/response details live alongside the route handler in `web_app.py`. This document is the index + auth/authorization summary.

---

## Public

| Method | Path | Purpose | Auth |
|---|---|---|---|
| GET | `/` | Landing | — |
| GET | `/register`, POST | Self-service signup; reads `ref_code` cookie for referrals | — |
| GET | `/login`, POST | Login. Field: `username`. Lockout after 5 failed attempts (15 min) | — |
| GET | `/logout` | Clear Flask session cookie. **Note (Q-gate 2.1):** does NOT revoke refresh tokens — fix pending. | session |
| GET | `/forgot-password`, POST | Password reset link via Brevo | — |
| GET | `/reset-password/<token>`, POST | Set new password | reset token |
| GET | `/assess`, POST | Public solar assessment form → AI score | — |
| GET | `/r/<code>` | Referral redirect; sets `ref_code` cookie | — |
| GET | `/robots.txt`, `/healthz` | Boilerplate | — |

## Liveness + Metrics

| Path | Returns |
|---|---|
| `GET /api/ping` | `{ "pong": true }` |
| `GET /api/health` | Overall health summary |
| `GET /api/health/{database,redis,queue,storage,ai}` | Per-component health |
| `GET /metrics` | Prometheus text format |

## Authenticated (user)

| Path | Purpose |
|---|---|
| `/dashboard`, `/account`, `/settings` | User home + settings |
| `/project/new` | Project wizard entry |
| `/project/<pid>/{location,loads,results}` | Wizard steps |
| `/project/<pid>/report/{pv,boq,cable,economic,installation,installation/drawings,proposal,energy,inspection}` | Engineering reports |
| `/project/<pid>/report/<kind>/pdf` | PDF export |
| `/project/<pid>/export/{excel,csv,docx}` | Other exports |
| `/procurement`, `/procurement/{plan,catalog,suppliers,pdf}` | Procurement views |
| `/upgrade`, `/upgrade/checkout`, `/upgrade/success` | Subscription upgrade |
| `/paystack/verify` (POST), `/paystack/webhook` (POST) | Paystack payment confirmation |
| `/stripe/checkout`, `/stripe/webhook` (POST) | Stripe (alternative) |
| `/tickets`, `/ticket/<tid>` | Support tickets |
| `/feedback` (POST) | In-app feedback |
| `/referrals` | User dashboard with referral code + stats |
| `/api/assistant/chat` (POST, CSRF via `X-CSRF-Token`) | Helpline AI |

## Admin (`@admin_required`)

All admin routes require login + admin flag. Hidden ≠ secured (`CLAUDE.md` §8). Backend rejects unauthenticated even if URL is guessed.

- `/admin` — dashboard
- `/admin/{users,tickets,appliances,helpline-kb,leads,assessments,installers,pipeline,sales,news,newsletter,codes,platform,agent,api-status,beta,feedback}` — module pages
- `/admin/operations` — NOC/SOC ops center
- `/admin/logs` — structured JSON log viewer
- `/admin/ops/ping/{frontend,backend,redis,database}` — ping endpoints
- `/admin/ops/db/{rls-check,vacuum}` — DB ops
- `/admin/ops/security/{audit,tenant-isolation,sessions,revoke-all-sessions}` — security tools
  - **Q-gate 2.2 caveat:** `revoke-all-sessions` currently only clears the requesting cookie, not all sessions. Fix pending.
- `/admin/ops/system/{pip-audit,load-test}` — system tools
- `/admin/ops/{cache/clear,queue/restart}` — cache/queue
- `/admin/ops/email/{status,test,env-keys}` — email diagnostics
- `/admin/ops/backup/{run,download}` — backup
- `/admin/ops/logs/{view,audit,export}` — log access

## Campaign portal (`/api/campaign/*`)

Defined in `campaign_api.py` as a Flask blueprint. **Status (2026-06-07): file deleted in working tree, awaiting commit.** Once committed + pushed, these routes disappear from the live deploy. Until then they remain live on Render.

If retained: see `reviews/codex-security-review.md` for the Q-gate findings to fix first (unauth `/entities` + `/state`, 30-day non-revocable tokens, plaintext default secret).

---

## Authorization matrix (target — Q-gate 3.3)

Every protected resource needs the 5-case test matrix:
- authorized correct-role
- authorized wrong-role
- authorized wrong-tenant
- logged-out
- expired session

Status: 0 of ~100 routes currently satisfy all 5. See `docs/TEST_PLAN.md`.
