# Operations Manual — SolarPro Global

For day-to-day operating procedures. SOC/NOC dashboard at `/admin/operations` is the primary console.

---

## Health checks

```powershell
Invoke-RestMethod https://solarpro-global.onrender.com/api/health
Invoke-RestMethod https://solarpro-global.onrender.com/api/ping
Invoke-RestMethod https://solarpro-global.onrender.com/api/health/database
```

Or in the admin UI: `/admin/operations` → "Pings" panel runs all four.

## Deploys

| Action | Command |
|---|---|
| Push code | `git push origin master` (Render auto-deploy; Railway is stale) |
| Force a Render redeploy | `gh workflow run "Force Render Deploy"` |
| Force a Railway redeploy | `gh workflow run "Railway Sync and Deploy"` |
| View Render logs | `gh workflow run "Get Render Logs"` (writes logs to artifact) |

## Database

| Action | Command |
|---|---|
| Backup | Admin UI → `/admin/operations` → "Run Backup" (writes `backups/solar_<ts>.db`) |
| Download latest backup | Admin UI → "Backup Download" |
| Local VACUUM | Admin UI → "DB Vacuum" (or `sqlite3 solar.db "VACUUM"` locally) |
| RLS check (Postgres future) | `/admin/ops/db/rls-check` |

⚠ Render free tier has no persistent disk attached, so `solar.db` resets on every redeploy. Track the open Render disk issue or migrate to Turso / SQLite Cloud / Postgres before storing anything important.

## Email

- **Provider chain:** Brevo (primary, HTTPS) → Axigen (scaffolded) → Resend (key invalid) → SMTP (blocked by Render).
- Test from `/admin/operations` → "Email Test".
- Brevo domain `aiappinvent.com` is authenticated → can send from any `@aiappinvent.com` sender.
- Verified senders: `sales@`, `support@`, `billing@`, plus auto-verified `marc667us@yahoo.com`.

## Logs

- `/admin/logs` — JSON log viewer (app, error, audit, security, ai, queue).
- `/admin/ops/logs/export` — download as ZIP.
- Files on disk: `logs/{app,error,audit,security,ai,queue}.log` (RotatingFileHandler).

## Security ops

- "Revoke All Sessions" button at `/admin/operations` — **NOTE (Q-gate 2.2):** currently lies; only clears the requesting browser's cookie. Real revocation pending.
- pip-audit: `/admin/ops/system/pip-audit` (also runs in CI).
- Active sessions: `/admin/ops/security/sessions`.

## Incident response

1. Identify the affected component via `/admin/operations` pings.
2. Check `/admin/logs` for the error stream + audit trail.
3. Rollback via `git revert` + push (Render auto-redeploys) or via the Render dashboard.
4. If a DB corruption: restore from latest `backups/solar_*.db`.
5. If a credential leak: rotate the relevant Secret (`gh secret set`) + redeploy + audit-log review.

## Monitoring (configured but not running)

- Prometheus + Grafana + Loki + Promtail + Uptime Kuma + Flower — `docker-compose.monitoring.yml`.
- Alert rules: `monitoring/prometheus/alerts.yml` (HighErrorRate >5 %, SlowResponseTime p95>3s, BruteForce >20/5min, TenantIsolationViolation, CeleryQueueBacklog >100).
- No cluster is up yet, so alerts only fire if someone runs the compose locally.

## Recurring tasks

- Daily 07:00 UTC: `test-browser-flow.yml` runs the Playwright smoke (since 2026-06-07).
- On every push to master/dev/staging: `ci.yml` runs lint + security scan + tests.
- On every PR: `ci.yml` runs the same.
