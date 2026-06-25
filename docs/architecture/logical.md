# Logical Architecture

Last revised: 2026-06-25

```mermaid
flowchart LR
  subgraph Browser
    User[Buyer / Engineer / Admin]
  end

  subgraph Edge["Edge & DNS"]
    CF[Cloudflare DNS + Tunnel]
    LE[Let's Encrypt TLS]
  end

  subgraph App["App layer (Render Web Service)"]
    Flask[Flask + Waitress<br/>web_app.py 1.4MB monolith]
    OIDC[app/auth/oidc_routes<br/>PKCE S256]
    Sec[app/security/<br/>decorators + tenant_context + audit]
    Storage["Static + Local FS<br/>marketplace assets"]
  end

  subgraph IDP["Identity Provider (Render Web Service)"]
    KC[Keycloak<br/>auth.aiappinvent.com]
    KCDB[(KC Postgres<br/>users, sessions, MFA)]
  end

  subgraph Data["Data layer (Render Postgres)"]
    PG[(solarpro-postgres<br/>20+ tables RLS-enforced)]
    Audit[(audit_logs)]
    Errors[(error_logs)]
    FX[(FX_*_PER_USD env vars)]
  end

  subgraph Pay["Payments"]
    Paystack[Paystack API]
  end

  subgraph Mail["Email"]
    Brevo[Brevo SMTP]
    Resend[Resend API]
  end

  subgraph Ops["Ops"]
    GH[GitHub Actions<br/>CI + cron + gated migrations]
    ER[open.er-api.com<br/>FX daily refresh]
  end

  User --> CF --> Flask
  CF --> KC
  Flask --> OIDC --> KC
  KC --> KCDB
  Flask --> Sec
  Flask --> PG
  Flask --> Paystack
  Flask --> Brevo
  Flask --> Resend
  Sec --> Audit
  Sec --> Errors
  GH --> Flask
  GH --> KC
  GH --> PG
  GH --> ER
  GH --> FX
```

## Component ownership

| Component | Owner | Backed by |
|---|---|---|
| Flask app | Eng | Render Web Service (free tier) |
| Keycloak | Eng | Render Web Service + KC Postgres |
| solarpro-postgres | Eng | Render Postgres |
| Paystack / Brevo / Resend | Vendor | 3rd party |
| Cloudflare DNS | Ops | Cloudflare account |
| GitHub Actions | Eng | Repo CI runner |
