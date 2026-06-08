# SolarPro custom domain fix — resume point

Pick this up on your next session. `solarpro.aiappinvent.com` is dark
because Namecheap's CNAME still points at the dead Railway target
(`ihmu7mu2.up.railway.app`). The Render side has been attached + verified
since 2026-06-02 — the moment DNS resolves correctly, Let's Encrypt
issues automatically within minutes.

This document closes the loop **without you touching DNS records by
hand again**. Migrating to Cloudflare gives the DNS-edit skill (built
this session) full control over future records via API. The one-time
bootstrap is a Cloudflare token; everything else runs from a command.

---

## What you do (≤ 5 minutes, one time)

### 1. Generate a Cloudflare API token

Open **https://dash.cloudflare.com/profile/api-tokens** → **Create Token**
→ pick the **"Edit zone DNS"** template → add **Zone : SSL and
Certificates : Edit** before saving. Token scopes you should see in the
review screen:

- Zone — Zone — Read
- Zone — DNS — Edit
- Zone — SSL and Certificates — Edit

Set **Zone Resources** = *Include — All zones* (this is the bootstrap
token; it must be allowed to register the new zone too).

Copy the token. You only see it once.

### 2. Paste the token into `.env` at the project root

```
CLOUDFLARE_API_TOKEN=<the-token-you-just-copied>
```

(`.env` is already gitignored.)

### 3. Run one command

```bash
./scripts/dns-edit.sh request "Add aiappinvent.com to Cloudflare and create a CNAME 'solarpro' pointing at solarpro-global.onrender.com with TTL 300 — closes the broken custom domain that has been HTTP 000 since 2026-05; Render side is already attached and verified-ready."
```

The skill will (Codex plans → Supervisor approves → script applies):

- POST `aiappinvent.com` to Cloudflare → Cloudflare returns 2 nameservers (let's call them `nsA.cloudflare.com` and `nsB.cloudflare.com`).
- Create the CNAME `solarpro -> solarpro-global.onrender.com` in the new Cloudflare zone.

### 4. Switch nameservers at Namecheap (one-time, unavoidable)

This is the ONE step that can't be automated — your Namecheap plan
doesn't expose a DNS API, and Cloudflare can't reach into a registrar
they don't run. Log in to Namecheap, find the `aiappinvent.com`
**Nameservers** field, switch from "Namecheap BasicDNS" (or whatever
it shows) to **Custom DNS**, and paste the two `*.ns.cloudflare.com`
hostnames the previous step printed.

Propagation: Namecheap usually applies in seconds; ICANN reflects in
5-30 minutes.

### 5. Verify

```bash
dig +short solarpro.aiappinvent.com @1.1.1.1
# expect: solarpro-global.onrender.com.   <Render's edge IPs>

curl -sS -o /dev/null -w '%{http_code}\n' https://solarpro.aiappinvent.com/api/ping
# expect: 200 (may show 526 for 1-5 min while Render issues the LE cert)
```

When `/api/ping` returns 200 on `solarpro.aiappinvent.com`, the cert is
live and the migration is done.

---

## After this is closed

The DNS-edit skill keeps working for every future record on
`aiappinvent.com` (any subdomain, MX changes, TXT for SPF/DKIM, etc.).
No more dashboards. You can hand off any DNS intent like:

```bash
./scripts/dns-edit.sh request "Create TXT _dmarc.aiappinvent.com 'v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com'"
./scripts/dns-edit.sh request "Add CNAME beta.aiappinvent.com pointing at solarpro-global.onrender.com"
```

The supervisor still gates every change — the team contract from
`ai-coworkers/dns-edit-role.md` stays in force.

---

## Why we can't skip step 4

| Tried | Result |
|---|---|
| Namecheap API on current plan | No API tier — confirmed during this session |
| Render auto-issuing on existing CNAME | Already done; still waiting on the CNAME to actually point at Render |
| Railway as the target | Decommissioned — see `[[feedback_render_ephemeral_db]]` is unrelated; Railway state in `project_solar_pv` memory |
| Fly.io migration | Rejected — required a credit card even for free tier; violates zero-cost policy |
| pyautogui driving the browser | Available as a contingency but skipped in favor of one-time Cloudflare bootstrap (gives long-term API leverage) |

---

## Pre-built plan preview

`reviews/dns/_planned_cf_solarpro_cname.preview.json` contains the exact
plan.json the skill will produce for the CNAME record once the token is
present. The plan has no checksum/approval/applied artifacts because the
provider call is blocked on the token — it's there so the Supervisor can
pre-review the shape before you authorize.
