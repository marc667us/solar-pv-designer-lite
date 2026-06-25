# OIDC Authorization Code + PKCE Flow

Last revised: 2026-06-25

Post SOC 2 M1.1 (KEYCLOAK_ENABLED retired), this is the **only** auth path.
The legacy `?legacy=1` bypass is closed; every /login, /register, /forgot-password,
/reset-password unconditionally bounces to `/auth/login`.

```mermaid
sequenceDiagram
  participant B as Browser
  participant A as solarpro.aiappinvent.com (Flask)
  participant K as auth.aiappinvent.com (Keycloak)
  participant DB as solarpro-postgres

  Note over B,K: 1. Login
  B->>A: GET /dashboard (anon)
  A->>B: 302 /auth/login
  B->>A: GET /auth/login
  A->>A: generate state + nonce + PKCE verifier (S256)
  A->>A: stash in Flask session
  A->>B: 302 KC /auth?code_challenge=...&state=...
  B->>K: GET /auth?...
  K->>B: render login form (KC theme = solarpro)
  B->>K: POST creds
  K->>B: 302 /auth/callback?code=...&state=...
  B->>A: GET /auth/callback?...
  A->>A: verify state == session._kc_state
  A->>K: POST /token (code + verifier)
  K->>A: { access_token, refresh_token, id_token }
  A->>A: verify_jwt(id_token) -> nonce match
  A->>A: session["user"] = sub + claims
  A->>B: 302 /dashboard, Set-Cookie solarpro_rt=<refresh>
  B->>A: GET /dashboard
  A->>A: g.kc_ctx = extract_request_context()
  A->>A: g.tenant_scoped=true, g.tenant_ctx_present=true (M1.7)
  A->>DB: SELECT set_config('app.current_tenant', <tid>, true)
  A->>DB: SELECT * FROM projects (RLS scopes to tid)
  A->>B: render dashboard

  Note over B,K: 2. Refresh (background)
  B->>A: POST /auth/refresh (X-Token-Expires-In dropped under 90s)
  A->>K: POST /token grant=refresh_token + refresh from cookie
  K->>A: { new access + new refresh }
  A->>B: 200 + Set-Cookie solarpro_rt=<new>

  Note over B,K: 3. Logout (M1.8: even legacy /logout funnels here)
  B->>A: GET /logout
  A->>A: purge draft projects, session.clear()
  A->>B: 302 /auth/logout
  B->>A: GET /auth/logout
  A->>K: POST /logout grant=refresh_token (revoke server-side)
  A->>B: 302 / + Set-Cookie solarpro_rt=; expires=0
```

## State + cookies

| Name | Where | Lifetime | Purpose |
|---|---|---|---|
| `solarpro_rt` | HttpOnly cookie | matches refresh_expires_in | hold refresh token between requests |
| `session["user"]` | Flask session (signed) | until logout | render user-specific UI |
| `g.kc_ctx` | request scope | one request | tenant_id, sub, roles, azp |
| `app.current_tenant` GUC | Postgres tx | one tx (`is_local=true`) | RLS policy lookup |

## What M1.1 closed

Before M1.1 every guard read `KEYCLOAK_ENABLED` and accepted `?legacy=1` as an escape — meaning the bcrypt-on-users.password_hash path remained reachable. Now the helper hard-codes `True`, the env var is ignored, and every login/register/reset URL unconditionally bounces to KC. The bcrypt column is scheduled for removal in Phase B (migration 005, owner-pending ≥ 2026-06-30).
