# Test Plan — SolarPro Global

---

## Layers

| Layer | Location | Status |
|---|---|---|
| Unit + integration | `tests/test_app.py` | Minimal — only `/dashboard` logged-out check at the moment. Hard-failed in CI (Q-gate 3.1 + 3.2, 2026-06-07). |
| Live smoke (HTTP against deployed site) | `test_render.py`, `test_admin_ops2.py`, `test_referrals_live.py`, `test_sales_readiness.py`, `test_session_audit.py`, `test_agent.py`, `test_email_debug.py`, `test_panel_wp.py`, `test_exports.py`, `test_procurement.py`, `test_reports.py`, `test_admin_ops.py` | Run locally / on demand. CI runs them as non-blocking advisory. |
| Browser smoke | `tests/browser/portal.spec.js` (new 2026-06-07) | Playwright Test. Three scenarios. Run via `gh workflow run test-browser-flow.yml` or daily 07:00 UTC. |
| Security scan | `ci.yml` security-scan job: pip-audit, Semgrep, Trivy filesystem + image. | Non-blocking advisory. |

## Required matrix per protected resource (Q-gate 3.3 — NOT met today)

For every authenticated route in `docs/API_SPECIFICATION.md`, the test must cover:

1. Authorized session of correct role → 200 + expected payload.
2. Authorized session of wrong role → 403 or login redirect; no payload leak.
3. Authorized session of a different tenant → 404 / 403; no cross-tenant data.
4. Logged-out client → 401 / login redirect.
5. Session older than the access-token TTL → 401.

For mutations, also assert no side effects when denied.

**Current coverage: 0 of ~100 protected routes satisfy all 5.** This is the largest single gap in the quality-gate.

## RLS tests (Q-gate 3.4 — blocked on Postgres)

For every RLS-protected table:
- Same-tenant SELECT/INSERT/UPDATE/DELETE succeed.
- Cross-tenant denied.
- Unset-context denied.
- Super-admin allowed.

Requires the CI job to start `postgres:16` as a service, apply migrations 001–004, connect as `solarpro_app` (no BYPASSRLS), and `SET LOCAL app.current_*` per case.

## Logout + revocation (Q-gate 3.5 — blocked on `web_app.py` auth rewrite)

Currently only `/dashboard` is checked post-logout. Target:
- Logout → old cookie → 401.
- Password reset → old cookie → 401.
- Account suspend → old cookie → 401.
- Admin demotion → old admin cookie → 403 on admin routes.
- Concurrent sessions: revoking one does not kill the others (unless "revoke all").
- "Revoke all sessions" actually revokes all sessions (Q-gate 2.2 — currently lies).

## Load test (Q-gate 3.6 — not implemented)

Target k6 / Locust scenarios:
- 1000 concurrent logins.
- 1000 concurrent dashboard fetches.
- 500 concurrent project create + report generate.
- 200 concurrent PDF/DOCX/Excel exports.
- 100 concurrent AI assistant calls.

Mix tenants per scenario. Thresholds: p95 < 800 ms, error rate < 0.5 %, DB pool < 80 % saturation, no observed cross-tenant data in sampled responses.

## Security micro-tests (Q-gate 3.7)

- Token tampering (payload, signature, expiry boundaries).
- CSRF omission on every POST.
- SQL injection payloads on every form input + URL param.
- XSS payloads on every renderable field.
- Paystack webhook forgery + replay.
- IDOR variants (URL ID swap).
- File download content-disposition.
- Enumeration on `/api/regions/*`.

## How to run locally

```powershell
cd "C:\Users\USER\Desktop\solar-pv-designer-lite"
pytest tests/ -v                          # unit + integration
pytest test_panel_wp.py -v                # one legacy unit test
python test_render.py                     # live smoke against Render URL (slow)
cd tests/browser && npm ci && npx playwright test
```
