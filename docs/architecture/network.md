# Network Trust Boundaries

Last revised: 2026-06-25

```mermaid
flowchart TB
  subgraph PUBLIC["Public internet — UNTRUSTED"]
    direction LR
    B[Browser]
    Bot[Crawlers + agents]
  end

  subgraph TLS["TLS perimeter — TRUST = TLS only"]
    direction LR
    CF[Cloudflare edge]
  end

  subgraph APP["App perimeter — TRUST = OIDC JWT"]
    direction LR
    APPNGINX[Render proxy + Flask]
    KC[Keycloak]
  end

  subgraph DATA["Data perimeter — TRUST = Postgres role + RLS GUC"]
    direction LR
    PG[(solarpro-postgres)]
    KCDB[(KC postgres)]
  end

  subgraph SECRETS["Secrets perimeter — TRUST = Render env + GH Secrets"]
    direction LR
    Render[Render env-vars]
    GHSec[GitHub Secrets]
  end

  B --> CF
  Bot --> CF
  CF -- HTTPS only --> APPNGINX
  CF -- HTTPS only --> KC
  APPNGINX -- Bearer JWT --> KC
  APPNGINX -- SET app.current_tenant + RLS --> PG
  KC -- direct conn --> KCDB
  Render -- env injection --> APPNGINX
  Render -- env injection --> KC
  GHSec -- env injection (gated workflows) --> Render

  classDef untrusted fill:#fee,stroke:#c33;
  classDef tls fill:#eef,stroke:#33c;
  classDef app fill:#efe,stroke:#3c3;
  classDef data fill:#ffe,stroke:#cc3;
  classDef secret fill:#fef,stroke:#c3c;
  class B,Bot untrusted;
  class CF tls;
  class APPNGINX,KC app;
  class PG,KCDB data;
  class Render,GHSec secret;
```

## Trust boundary rules

| Boundary | What crosses | How it's enforced |
|---|---|---|
| Public → TLS | HTTP request | TLS termination at Cloudflare |
| TLS → App | HTTPS request | TLS-only ingress, no plain HTTP |
| App → IDP | OIDC flow + Bearer JWT validation | PKCE S256 + JWKS signature check (`app/security/keycloak_middleware.py`) |
| App → Data | DB query | `set_config('app.current_tenant', …)` + RLS policies on every tenant-owned table |
| Secrets → App | env-var injection only | Render env-vars API (gated workflows); no plaintext in repo |
| GH Secrets → Render | one-shot push via workflow | `apply-*-migrations.yml` + `Force Render Deploy` (uses `?limit=100` since 2026-06-22 incident) |

## Known footguns

- `Render Force Render Deploy` does a `PUT /env-vars` over the full list — `?limit=100` is **required** or KC vars get truncated (root cause of 2026-06-22 KC outage).
- Cloudflare free tunnel caps a single request at 100s — long admin actions return 524 even when the backend succeeds.
- Render free tier sleeps after 15min of inactivity → first request after sleep adds ~30s cold start.
