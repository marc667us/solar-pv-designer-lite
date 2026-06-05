# SolarPro Global — Session Context

**Last updated:** 2026-06-05
**Purpose:** capture in-flight state so any session can resume mid-task without re-discovery.

---

## 1. Where the app is running RIGHT NOW

| Tier | URL | State | Branch | Railway env |
|------|-----|-------|--------|-------------|
| **Production** | https://web-production-744af.up.railway.app | ✅ Live, valid Railway SSL, sales-ready | `master` @ `16b7ba3` | production (`7ed9b8ad-…`) |
| Production custom domain | https://solarpro.aiappinvent.com | ❌ Cert not yet issued by Railway; browser refuses HTTPS | — | (same) |
| **Staging** | — | Created on Railway but **no token, no service deploy** | `staging` (planned) | staging (`f50c2e0e-…`) |
| **Development** | — | Created on Railway but **no token, no service deploy** | `develop` @ `163a936` | development (`2b52bbc8-…`) |

---

## 2. Active blockers (waiting on user)

1. **Cloudflare API token** — to put Cloudflare in front of Railway and bypass the stuck custom-domain cert.
   - Token created via https://dash.cloudflare.com/profile/api-tokens, "Edit zone DNS" template plus extra `Zone:Edit` and `Zone:SSL and Certificates:Edit` scopes.
   - Once received, I add `aiappinvent.com` as a CF zone, import DNS, set SSL/TLS mode = **Full** (not Strict), trigger Universal SSL.
   - User then pastes the 2 nameservers from Cloudflare into Namecheap (the only manual step that can't be automated).

2. **Railway env-scoped tokens** for staging + development environments — generated from Railway dashboard → project → Settings → Tokens. Without these the 3-tier deploy pipeline can't be wired.

3. **Paystack live keys** — user owns this; replacing `pk_test_…` / `sk_test_…` GitHub secrets with live values when ready.

---

## 3. Latest production commits (master)

| Commit | What |
|--------|------|
| `16b7ba3` | feat(referrals): add referral program with shareable per-user link |
| `9720710` | fix(security-audit): defensive wrapping + csrf_protect + brevo/axigen checks |
| `93c5423` | feat(email): wire Brevo as primary HTTPS provider |
| `cca3768` | fix(env): strip BOM from env vars (this was THE Render-deploy root-cause fix) |
| `27b2492` | feat(panel-select): 110/250/330/400/450/500/550 Wp options + dynamic install report |

## 4. Develop branch (not in production)

| Commit | What |
|--------|------|
| `163a936` | feat(trial): 14-day free trial model from `Documents\pvsolar1\kubernates\basicprice.txt` |

---

## 5. Email pipeline — current verified state

- **Provider:** Brevo (HTTPS API, free 300/day)
- **Authenticated domain:** `aiappinvent.com` (DKIM CNAMEs + brevo-code TXT + DMARC TXT all green)
- **Verified senders that the app actually uses:** `sales@aiappinvent.com`, `support@aiappinvent.com`, `billing@aiappinvent.com`, plus auto-verified `marc667us@yahoo.com`
- **Verified delivery test (2026-06-04 / 23:24 UTC):** request → delivered in 2 seconds. Sender shown to recipient = `sales@aiappinvent.com`. Stop using yahoo as visible sender.

---

## 6. Sales-readiness audit (latest run)

| Component | State |
|-----------|-------|
| Public landing | ✅ |
| Public assessment magnet (`/api/assess/design`) | ✅ — calc + lead-save + Brevo email all working |
| Register form + welcome email | ✅ |
| Free trial → upgrade via Paystack (test keys) | ✅ on test mode; live keys pending |
| Reports + exports (gated for paid plans) | ✅ 22/22 |
| Admin Ops Center | ✅ 26/29 (Redis/Queue WARN expected on free tier) |
| Referral link + dashboard | ✅ 10/10 |

---

## 7. Memory of session-level decisions (most important)

- **Zero-cost APIs only** until the app is generating revenue. No paid Claude / no paid Render Starter / no paid Brevo plan. Free-tier alternatives only (OpenRouter, GitHub Models, Ollama; Brevo / Mailgun / Resend free tiers).
- **Production untouched** unless explicitly directed. Trial-model + future basicprice features stay on `develop` until they're tested in dev/staging.
- **Code comments required** — every new code block must include: what it does, inputs, expected outputs, and any non-obvious syntax.
- **Verify before acting** — when something fails, read the actual log first. Don't delete/recreate state to "retrigger" provisioning unless the current state is definitively dead (this rule was learned the hard way during Railway cert debugging this session).

---

## 8. Out-of-scope work from `basicprice.txt` (queued for future sessions)

The spec also describes (but we have NOT built):
- Public 50,000+ electrical product catalog (RMUs, transformers, switchboards, MCCs, generators, cables, etc.) with search + technical specs + supplier directory
- Public 20,000+ IT product catalog (firewalls, switches, routers, PBX, CCTV, access control, etc.)
- AI Product Intelligence Agent (recommends products, brands, suppliers; benchmarks prices)
- CRM tracking tables: `public_visitors`, `lead_magnets`, `product_views`, `supplier_views`, `trial_users`, `upgrade_opportunities`, `subscription_events`, `marketing_campaigns`, `crm_leads`, `crm_opportunities`
- Automated trial-reminder emails on day 7, 10, 13, 15 (requires a scheduler — cron / Railway cron service / GitHub Actions cron)
- BOQ Generator, Invoice Generator, Procurement Module enhancements per the spec

When the user is ready for these, the trial-model commit (`163a936`) is the natural starting point because it already adds `trial_end_date` and the gating logic.
