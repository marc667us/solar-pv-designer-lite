# SolarPro Global — Geo-Aware Edge Deployment Architecture

## Strategy: Deploy to the Nearest Edge

Users in Africa, Europe, Middle East, and the Americas are served by the **nearest regional cluster**, minimizing latency.

```
User in Ghana / Nigeria / West Africa
    ↓ DNS lookup: solarpro.aiappinvent.com
    ↓ Cloudflare GeoDNS → af-west endpoint (Lagos/Johannesburg cluster)
    ↓ Nearest Kubernetes cluster
    ↓ Neon PostgreSQL (Africa region: aws-af-south-1 or eu-west-1)
    ↓ Response time: < 80ms
```

---

## Regional Deployment Map

| Region | Cluster | Neon DB Branch | Solar Markets |
|--------|---------|----------------|---------------|
| **Africa West** | GKE `af-west-1` or Render West Africa | `solar-production-af` | Ghana, Nigeria, Senegal, Côte d'Ivoire |
| **Africa East/South** | Fallback to af-west | `solar-production-af` | Kenya, Tanzania, South Africa, Zimbabwe |
| **Europe** | GKE `eu-west-1` | `solar-production-eu` | UK, Germany, Spain, France |
| **Middle East** | GKE `me-central-1` | `solar-production-me` | UAE, Saudi Arabia, Qatar, Kuwait |
| **Americas** | GKE `us-east-1` | `solar-production-us` | USA, Brazil, Mexico |
| **Asia Pacific** | GKE `ap-southeast-1` | `solar-production-ap` | India, Indonesia, Philippines |

---

## Cloudflare GeoDNS Setup

### Step 1: Enable Cloudflare Load Balancing

In Cloudflare Dashboard → Traffic → Load Balancing:

```
Pool: solarpro-af-west
  → Origin: af-west.solarpro.aiappinvent.com  (weight: 1)
  → Health check: GET /api/ping (expect 200)

Pool: solarpro-eu-west
  → Origin: eu.solarpro.aiappinvent.com

Pool: solarpro-us-east
  → Origin: us.solarpro.aiappinvent.com

Pool: solarpro-me-central
  → Origin: me.solarpro.aiappinvent.com
```

### Step 2: Create Geo Steering Policy

```
Traffic Policy: Geo Steering
    Africa         → solarpro-af-west (primary) → solarpro-eu-west (fallback)
    Europe         → solarpro-eu-west (primary) → solarpro-us-east (fallback)
    Middle East    → solarpro-me-central (primary) → solarpro-eu-west (fallback)
    North America  → solarpro-us-east (primary)
    South America  → solarpro-us-east (primary)
    Asia Pacific   → solarpro-ap-southeast (primary) → solarpro-eu-west (fallback)
    Default        → solarpro-eu-west
```

### Step 3: Health Monitors

Each regional origin has Cloudflare health monitoring:
```
Type: HTTPS
Path: /api/ping
Expected: {"pong": true}
Interval: 60s
Timeout: 10s
Retries: 2
Alert: Email + Webhook on failure
```

---

## Kubernetes Manifests Per Region

Each region has an identical Kubernetes deployment, differentiated by:
- Namespace suffix: `solar-production-af`, `solar-production-eu`, etc.
- ConfigMap: `REGION=af-west`, `NEON_SHARD=af`
- Ingress hostname: `af.solarpro.aiappinvent.com`

---

## Neon PostgreSQL Multi-Region Strategy

Neon supports multiple regions. Strategy for SolarPro:

### Phase 1 (Current): Single Region + Read Replica
```
Primary: aws-eu-west-2 (EU)  ← all writes go here
Read replica: aws-af-south-1 ← African reads (faster for Ghana/Nigeria users)
```

### Phase 2 (100+ tenants): Regional Branches
```
solar-production-primary (eu-west-2)  ← global writes
solar-production-af   (af-south-1)    ← read replica for Africa
solar-production-me   (me-central-1)  ← read replica for Middle East
solar-production-us   (us-east-2)     ← read replica for Americas
```

### Phase 3 (Geographic sharding — see database-sharding.md):
```
Tenant routing:
  tenant.country IN (GH, NG, SN, CI, CM ...) → af-west shard
  tenant.country IN (GB, DE, FR, ES ...)      → eu-west shard
  tenant.country IN (US, CA, MX, BR ...)      → us-east shard
  tenant.country IN (AE, SA, QA ...)          → me-central shard
```

---

## Backend Connection Routing

The Flask backend detects which regional database to use:

```python
# web_app.py — region-aware DB connection
REGIONAL_DB_URLS = {
    'af-west':    os.environ.get('DATABASE_URL_AF', os.environ.get('DATABASE_URL')),
    'eu-west':    os.environ.get('DATABASE_URL_EU', os.environ.get('DATABASE_URL')),
    'us-east':    os.environ.get('DATABASE_URL_US', os.environ.get('DATABASE_URL')),
    'me-central': os.environ.get('DATABASE_URL_ME', os.environ.get('DATABASE_URL')),
}

def get_regional_db():
    region = os.environ.get('REGION', 'eu-west')
    url = REGIONAL_DB_URLS.get(region, os.environ.get('DATABASE_URL'))
    return url   # used by SQLAlchemy / psycopg2 connection pool
```

---

## Latency Targets

| User Location | Without Geo-Routing | With Geo-Routing |
|---------------|--------------------|--------------------|
| Ghana (Accra) | ~350ms (Render US) | ~60ms (af-west) |
| Nigeria (Lagos) | ~340ms | ~55ms |
| UK (London) | ~180ms | ~25ms |
| UAE (Dubai) | ~200ms | ~40ms |
| USA (New York) | ~80ms | ~20ms |

---

## Deployment Order

1. Set up Cloudflare Load Balancing (requires Cloudflare Pro plan, ~$20/month)
2. Deploy af-west cluster first (highest user density — Ghana/Nigeria)
3. Add eu-west cluster
4. Configure GeoDNS steering
5. Set up Neon regional read replicas
6. Enable geographic sharding when reaching 500+ tenants
