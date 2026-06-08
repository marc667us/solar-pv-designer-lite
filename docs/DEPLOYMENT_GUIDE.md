# Deployment Guide — SolarPro Global

---

## Current hosting (2026-06-07)

| Tier | URL | Status |
|---|---|---|
| **Primary (per user 2026-06-07)** | Railway custom domain `solarpro.aiappinvent.com` | Cert stuck — see Railway cert revival below |
| Live now | https://solarpro-global.onrender.com | Render free tier — auto-deploys on push to `master` |
| Stale | https://web-production-744af.up.railway.app | Railway auto-deploy broken; redeploy via `gh workflow run "Railway Sync and Deploy"` |

## Render deploy

```powershell
# Trigger a deploy from the GitHub Actions workflow
gh workflow run "Force Render Deploy"
```

Render service ID + API key live in GitHub Secrets. Render mounts disk at `/app/data` if attached (NOT yet — disk REST API returned 404; investigate or move to Turso/SQLite Cloud for persistence).

## Railway deploy (when reconnected)

Auto-deploy on push to `master` once the GitHub integration is repaired in the Railway dashboard. Manual redeploy:

```powershell
gh workflow run "Railway Sync and Deploy"
```

Project ID `310ad3cf-...`, service ID `b9889adc-...`. Environments: `production` (token in secrets), `staging`, `development` (no tokens — need per-env Railway dashboard tokens).

## Railway cert revival (in progress)

Target subdomain: **`solarpro.aiappinvent.com`** (per user 2026-06-07, NOT `www.aiappinvent.com` from the original brief).

Full procedure: `Documents\pvsolar1\improvements\railwaycertissue.txt`.

Summary:
1. Read current Railway custom-domain CNAME + TXT values via Railway CLI / API.
2. Verify Namecheap is authoritative for `aiappinvent.com` (not Cloudflare).
3. Add the Railway-provided CNAME for `solarpro` host to Namecheap Advanced DNS.
4. If Cloudflare is in front: temporarily disable proxy (grey cloud) for the CNAME, wait for Let's Encrypt validation, re-enable.
5. If still stuck after 30 min: hard reset — delete + re-add the custom domain in Railway, re-paste DNS, wait.

**Never delete Namecheap MX / SPF / DKIM / DMARC records** — they keep `sales@`, `support@`, `billing@aiappinvent.com` email working through Brevo.

## Environment variables (Render + Railway)

| Variable | Source / value |
|---|---|
| `SECRET_KEY` | GitHub Secret |
| `DATABASE_URL` | Currently unset → falls back to SQLite. Set when Postgres is provisioned (Q-gate 1.1). |
| `OPENROUTER_API_KEY` | GitHub Secret. Free Llama/Gemma. |
| `ANTHROPIC_API_KEY` | **Empty by design** — zero-cost policy keeps Claude out of the runtime chain. |
| `BREVO_API_KEY` | GitHub Secret. Primary email. |
| `RESEND_API_KEY` | GitHub Secret (placeholder; domain unverified). |
| `SMTP_*` | Namecheap Private Email; Render blocks outbound SMTP so this is fallback-only. |
| `OLLAMA_URL`, `OLLAMA_MODEL` | GitHub Secrets. Last-resort AI. |
| `PAYSTACK_SECRET_KEY` | GitHub Secret. |
| `CAMPAIGN_*` | (For campaign portal — file slated for removal). |
| `CAMPAIGN_TEST_EMAIL`, `CAMPAIGN_TEST_PASSWORD` | New 2026-06-07. Required by Playwright workflow. |

## Local dev

```powershell
cd "C:\Users\USER\Desktop\solar-pv-designer-lite"
python start.py     # Waitress on :5000 + cloudflared tunnel; prints public URL
# OR
python web_app.py   # Flask dev server, hot reload, no tunnel
```

## Docker

`docker-compose up` runs `backend + redis + celery-worker + celery-beat`. **Q-gate 4.1 caveat:** `web_app.celery_app` does not currently exist; the compose file references a stub. Fix is in the Phase 4 work-schedule.

## CI/CD

- `.github/workflows/ci.yml` — lint + security scan + tests + Docker image build/push to GHCR.
  - Q-gate 3.1 + 3.2 (2026-06-07): `pytest tests/` now hard-fails. Legacy root smoke tests are explicitly non-blocking.
- `.github/workflows/test-browser-flow.yml` — Playwright Test against the live campaign portal.
- `.github/workflows/deploy-production.yml` — semver tag → manual approval → K8s deploy (no cluster yet).
- `.github/workflows/deploy-dev.yml` — push to `dev` → kustomize apply (no cluster yet).

## Rollback

- Render: revert via Render dashboard or push a fix to master (auto-redeploy).
- Railway (when working): revert + redeploy from `master`.
- DB: restore from `backups/solar_<ts>.db` via `/admin/ops/backup/run` artifacts.
