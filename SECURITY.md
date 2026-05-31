# SECURITY.md — SolarPro Global

Security register and implementation status for the Intelligent Global PV Solar System Design Platform (`web_app.py`). Updated 2026-05-31.

---

## Current Security Architecture

```
Internet
   ↓
Cloudflare (DNS / CDN / DDoS / SSL)
   ↓
Render (Flask/Gunicorn — 2 workers)
   ↓
web_app.py  →  api_manager.py  →  External APIs
                                   (Claude / OpenRouter / Paystack / Stripe / Resend / SMTP)
```

All external API calls go through `api_manager.py` — the backend never exposes secret keys to the frontend.

---

## Implementation Status

### ✅ Implemented

| Control | Detail |
|---|---|
| Password hashing | `werkzeug.security.generate_password_hash` / `check_password_hash` |
| CSRF protection | Custom token in session; checked on every POST via `csrf_protect()` |
| Rate limiting | `Flask-Limiter`: register 10/hr, login 20/hr, forgot-password 5/hr, assess 20/hr, AI chat 30/hr |
| Login brute-force lockout | 10 failures per IP/username in 15 min → lockout; tracked in `login_failures` table |
| Login audit log | Every success and failure written to `audit_logs` table with IP |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Cache-Control` |
| Content-Security-Policy | `default-src 'self'`; allows CDN (jsdelivr, Stripe JS), blocks objects |
| Session security | `SESSION_COOKIE_HTTPONLY=True`, `SameSite=Lax`, 8h lifetime |
| Proxy trust | `ProxyFix` — reads real IP from `X-Forwarded-For` behind Render/Cloudflare |
| All secrets in `.env` | Stripe, Paystack, Anthropic, SMTP, Resend — never in source code |
| `.gitignore` | `.env` excluded; no secrets committed to GitHub |
| Stripe webhook | Signature verified via `stripe.Webhook.construct_event` (HMAC-SHA256) |
| Paystack push webhook | `POST /paystack/webhook` — HMAC-SHA512 verified; duplicate reference rejected |
| Paystack inline verify | `POST /paystack/verify` — server-side re-verification before plan activation |
| Payment amount match | Subscription activates only after backend verification of amount + plan + reference |
| Duplicate payment guard | Reference checked in `payments` table before activating subscription |
| `login_required` decorator | All authenticated routes protected |
| `admin_required` decorator | All `/admin/*` routes protected |
| API key masking | Keys shown masked in admin dashboard |
| Email anti-enumeration | Forgot-password shows same message whether email exists or not |
| robots.txt | `/admin/`, `/project/`, `/api/`, `/dashboard`, payment routes all disallowed |
| AI fallback chain | Claude → OpenRouter → Ollama → GitHub Models → rule-based (no single point of failure) |

---

### 🟡 Partially Implemented

| Control | Gap | Priority |
|---|---|---|
| `SESSION_COOKIE_SECURE` | Set to `False` to support http tunnels locally. Must be `True` on Render (HTTPS only). | High — flip to `True` on Render via env var |
| Admin 2FA | No 2FA on admin login. Admin account secured by strong password + rate limiting only. | High |
| AI usage limits per plan | Free plan has no per-month AI call cap. Rate limiter (30/hr) is the only guard. | Medium |
| Paystack DMARC | SPF + DKIM added; DMARC TXT record not yet added to DNS. | Medium |

---

### ❌ Not Yet Implemented

| Control | Action Required | Priority |
|---|---|---|
| Admin 2FA | Add TOTP (e.g. `pyotp`) to admin login flow | High |
| DMARC DNS record | Add `_dmarc.aiappinvent.com TXT "v=DMARC1; p=none; rua=mailto:marc667us@yahoo.com"` to Namecheap | Medium |
| Daily database backup | Schedule `sqlite3 solar_web.db .dump > backup.sql` via Render cron or GitHub Actions | High |
| Per-plan AI credit limits | Track AI call count per user per month; block on free plan after limit | Medium |
| Bot protection on public forms | Add Cloudflare Turnstile to `/assess` and `/register` (free, no JS dependency) | Medium |
| Logout-all-devices | Single logout only. No "sign out all sessions" feature. | Low |
| Security dashboard (admin) | Surfacing audit_logs, login_failures, and active sessions in admin UI | Low |

---

## API Key Protection Rules

1. Secret keys only in backend `.env` — never in frontend JavaScript
2. `.env` in `.gitignore` — never committed
3. `api_manager.py` is the single proxy for all external calls
4. Keys logged masked (`sk-...xxxx`) in `api_logs` table, never in full
5. Separate test and live keys (Stripe test mode for local dev)
6. Rotate keys immediately if `git log` or browser DevTools ever shows a real key

## Payment Security Rules

1. Frontend starts payment only (Paystack public key, Stripe publishable key)
2. Backend verifies every payment before plan activation
3. Stripe webhook: `construct_event` with `STRIPE_WEBHOOK_SECRET`
4. Paystack push webhook: HMAC-SHA512 with `PAYSTACK_SECRET_KEY`
5. Duplicate reference check prevents payment replay
6. Amount verified server-side — frontend amount cannot activate subscription

## Login / Session Security

- Passwords: `werkzeug` PBKDF2-HMAC-SHA256 (work factor ~260k iterations)
- Rate limit: 20 attempts per hour per IP
- Lockout: 10 failures in 15 minutes → account locked until window expires
- Session: Flask signed cookie, HTTPOnly, SameSite=Lax, 8h lifetime
- Password reset: cryptographically random token, 1h expiry, single-use

## AI / API Cost Protection

| Task | Provider |
|---|---|
| Customer helpline, proposals | Claude (primary) → OpenRouter Llama (fallback) |
| Lead scoring, classification | Ollama (local, free) |
| All responses | Cached in `api_cache` table (TTL per call) |
| No-API fallback | Rule-based answers always available |

## Disaster Recovery (Minimum)

| Item | Status |
|---|---|
| Code backup | GitHub `master` branch |
| Database | SQLite on Render persistent disk (`/opt/render/project/src/solar_web.db`) |
| Automated backup | ❌ Not yet configured |
| Emergency admin access | Admin credentials in `start.py` output on cold start |
| Domain registrar | Namecheap — secured with 2FA |

**Target**: add daily `pg_dump` / SQLite dump to GitHub Actions or Render cron.

---

## Security Architecture Diagram (Target)

```
Frontend (Jinja2 + Bootstrap)
   │  Public key only (Paystack/Stripe)
   │  CSRF token on every POST
   ↓
Flask Backend (web_app.py)
   │  Session auth (login_required)
   │  Rate limiting (Flask-Limiter)
   │  CSRF validation
   │  Input validation
   ↓
api_manager.py (single API proxy)
   │  All secrets from .env
   │  Fallback chain per provider
   │  Caching layer
   ↓
External APIs
   Anthropic / OpenRouter / Ollama / Stripe / Paystack / Resend / SMTP
```

---

## Immediate Next Actions

1. **Add DMARC DNS record** in Namecheap (5 min)
2. **Enable `SESSION_COOKIE_SECURE=True`** on Render via env var `FORCE_HTTPS=true`
3. **Set up daily database backup** — GitHub Actions cron or Render cron job
4. **Add per-plan AI usage limits** — monthly counter in `users` table
5. **Add admin 2FA** — `pyotp` TOTP, QR code setup in admin settings

---

*This file is tracked in git. Do not include real API keys, passwords, or secrets anywhere in this file.*
