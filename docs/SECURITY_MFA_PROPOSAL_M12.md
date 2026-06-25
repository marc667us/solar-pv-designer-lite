# SOC 2 M1.2 — MFA Enforcement Proposal

Owner: Eng
Status: **Proposed — not yet applied to live**
Drafted: 2026-06-25

## Why this is staged, not auto-applied

MFA enforcement is the **one M1 item I can't safely apply without owner present**. If the seed admin's authenticator isn't set up before the realm flips, they're locked out of the live KC admin console with no fallback (M1.1 retired the bcrypt bypass). Rolling back requires a Render env edit + redeploy, which is a 5-10 min recovery window.

So this doc captures everything the owner needs to do it manually, plus the realm-export delta that can be applied via a future workflow once a staged rollout is agreed.

## Target state

| Role | Current | Target |
|---|---|---|
| `platform_super_admin` | password only | password + TOTP **required** |
| `tenant_admin` | password only | password + TOTP **required** |
| `finance_officer` | password only | password + TOTP **required** |
| `read_only` (auditor) | password only | password + TOTP **required** |
| `marketplace_admin` | password only | password + TOTP **strongly recommended** (optional) |
| All other roles | password only | password only (unchanged) |
| `api_service_account`, `ai_agent`, `background_worker` | client_credentials only | unchanged (no human, no MFA) |

Implementation pattern: **Keycloak Conditional OTP** execution in the `browser` flow, with role-based condition.

## What Keycloak needs

Keycloak ships a "Conditional OTP" execution out of the box. The browser flow becomes:

```
Browser flow
├── Cookie
├── Identity Provider Redirector (passthrough for SSO)
└── browser-forms
    ├── Username Password Form
    └── browser-conditional-otp                          ← NEW
        ├── Condition - User Role  [REQUIRED]
        │   - role:  platform_super_admin
        │   - role:  tenant_admin
        │   - role:  finance_officer
        │   - role:  read_only
        │   - negate: false
        └── OTP Form  [REQUIRED]
```

When the user has any of those 4 roles, KC forces TOTP. Users without those roles skip the OTP step entirely.

## Three application paths

Pick one per environment.

### Path A — Admin console (recommended for first rollout)

For the live realm:

1. `auth.aiappinvent.com/admin` → log in.
2. Authentication → Flows → click "Copy" on the default `browser` flow → name it `browser-mfa-conditional`.
3. In the new flow, open the `forms` subflow.
4. Add execution: **Conditional OTP Form** (set to `Conditional`).
5. Under the Conditional OTP Form → Actions → Config:
   - Add a sub-execution: **Condition - User Role** (set to `Required`).
   - Role: `platform_super_admin` AND/OR add separate conditions for `tenant_admin`, `finance_officer`, `read_only`.
6. Authentication → Bindings → set Browser Flow → `browser-mfa-conditional`.
7. Realm Settings → User Profile → tick `OTP` under Required actions, set `Default Action = OFF` (don't force every user; only the conditional flow does).

### Path B — Admin REST API (scriptable)

The realm-export schema lets us define an `authenticationFlows` block. The payload to POST against `auth.aiappinvent.com/admin/realms/solarpro/authentication/flows` (after copying the default browser flow) lives at `keycloak/render/mfa_conditional_otp.json` in this repo (next commit).

### Path C — Workflow

Once Path A or B has been validated against a staging realm, encode the change as a gated GitHub Action `apply-kc-mfa-conditional.yml` that hits the KC admin REST API. Skipped for now — the realm config is a one-shot, not something to re-apply on every deploy.

## Rollout plan

| Day | Action | Risk |
|---|---|---|
| -7 | Send Brevo broadcast to the 4 elevated-role users with TOTP setup link + screenshots. Owner enrolls their own authenticator app first as a smoke test. | Low |
| -1 | Smoke test on the staging realm (when one exists) OR on a freshly created admin user. | Low |
| 0 | Apply via Path A on live realm. Owner login first. | **Medium — owner must have authenticator app installed and verified** |
| +1 | Each elevated-role user logs in: KC presents "Set up Authenticator" screen → user scans QR → enters OTP → done. Subsequent logins always prompt. | Low |
| +7 | If no help-desk tickets, mark M1.2 complete in the SOC 2 audit. | — |

## Recovery if something goes wrong

If the seed admin gets locked out:

1. Render → solarpro-keycloak service → Environment.
2. Remove the `BROWSER_FLOW_OVERRIDE` env (if applied via Path C) OR open the KC database directly and `UPDATE realm SET browser_flow = '<old_flow_id>'`.
3. Redeploy KC.
4. Owner logs in via the default browser flow (no MFA), fixes the conditional config.

The recovery path itself requires Render access — owner should keep `RENDER_API_KEY` available offline.

## Acceptance criteria for marking M1.2 done

- [ ] Conditional OTP execution present in active browser flow (verify via admin REST: `GET /admin/realms/solarpro/authentication/flows`).
- [ ] Every user with `platform_super_admin`, `tenant_admin`, `finance_officer`, or `read_only` carries `CONFIGURE_TOTP` in their required-actions OR has at least one `otp` credential on file.
- [ ] Live smoke: a fresh user with `tenant_admin` role attempts login → is presented with TOTP setup screen → completes setup → second login prompts for OTP code.
- [ ] SOC 2 audit dashboard's "M1.2 MFA enforcement" check flips to PASS (helper TBD — would query KC admin REST and count `otp` credentials per role).

## What this commit ships

- This proposal doc.
- A SOC 2 audit check `M1.2 MFA enforcement (proposed)` that reads as a documented WARN until the actual realm change lands.
- No live realm modification.
