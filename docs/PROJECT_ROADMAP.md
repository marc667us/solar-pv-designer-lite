# Project Roadmap — SolarPro Global

**Current stage:** Selling-ready Flask SaaS on Render free tier. SQLite runtime. SolarPro frontend + admin + 22 reports + helpline AI + Paystack + Brevo email + referral program shipped. Quality-gate verdict (2026-06-06): FAIL on 8 of 10 gates — see `SolarPro_QualityGate_WorkSchedule_2026-06-06.md` on Desktop.

---

## Now (in progress this week)

- **Q-gate Phase 1 / 3 / 5 / 6 close** (this session, 2026-06-07) — RLS hardening migrations, Playwright Test rewrite, CI hard-fail on `tests/`, doc backfill.
- **Campaign portal teardown commit** — locally deleted, awaiting commit + push to remove from live Render.
- **Railway cert revival** to `solarpro.aiappinvent.com` per `Documents\pvsolar1\improvements\railwaycertissue.txt`.

## Next (planned, blocked on inputs)

- **PostgreSQL migration (Q-gate items 1.1, 1.2)** — blocked on a free-tier Postgres URL (Neon). Apply migrations 001–004 against it. Wire `DATABASE_URL` + per-tx tenant context middleware.
- **Real session revocation (Q-gate 2.1, 2.2, 2.3)** — requires `web_app.py` edits the user has not yet authorized. Will add `user_sessions` table + `session_version` flow.
- **Live admin password rotation + git history purge (Q-gate 0.1)** — user-deferred from 2026-06-07 session.

## Soon

- Q-gate Phase 4: real Celery worker + queue PDF/DOCX/AI work (4.1–4.7). Needs Redis URL.
- Q-gate 3.3–3.7: 5-case auth matrix across ~100 routes, RLS tests, logout tests, k6 load, security micro-tests. Multi-session.
- 14-day free-trial model on `develop` (commit `163a936`) — deploy to a Render preview.
- Custom domain (`solarpro.aiappinvent.com`) cert finally valid.

## Later / parked

- Public 50k+ electrical product catalog
- 20k+ IT product catalog
- Day 7/10/13/15 trial reminder scheduler
- AI Product Intelligence Agent
- CRM tables: public_visitors, product_views, supplier_views, trial_users, subscription_events
- Public landing-page sections from `basicprice.txt` spec

## Done (selected milestones, see commit log + IMPLEMENTATION_LOG)

- Phase 1–18: Auth, projects, sizing, reports, BOQ, economics, subscriptions, payments, AI agent, helpline, repricing, custom domain
- Phase 19 (2026-05-30): Multi-AI stack + Resend email + SMTP fallback
- Phase 20 (2026-06-01): Ground mount diagrams, AI agent fixes, globe widget complete
- Phase 21 (2026-06-02): K8s infra, security architecture spec, monitoring stack, admin ops center (26/29 live tests passing)
- 2026-06-03..05: Referral program + Brevo + Render primary
