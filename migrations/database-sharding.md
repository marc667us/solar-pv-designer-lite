# SolarPro Global — Database Sharding Architecture

## Sharding Strategy: Tenant-Based Geographic Sharding

Data is partitioned by `organization_id` using consistent hashing, with geographic co-location:
tenants are routed to the shard closest to their primary business location.

---

## Phase 1: Single Database (Current — SQLite → Neon PostgreSQL)

```
All tenants → solar-production (Neon, eu-west-2)
```

Migrate from SQLite to Neon when approaching 100 active users:
```bash
# Export SQLite
sqlite3 solar.db .dump > solar_dump.sql

# Import to Neon (adapt DDL for PostgreSQL syntax)
psql $DATABASE_URL < migrations/001_postgresql_schema.sql
psql $DATABASE_URL < migrations/002_rls_policies.sql
# Run data migration script
python migrations/migrate_sqlite_to_postgresql.py
```

---

## Phase 2: Read Replicas (100–500 tenants)

```
Primary (eu-west-2)    ← all writes
Read replica (af-south-1)  ← reads for Africa region tenants
Read replica (us-east-2)   ← reads for Americas tenants
```

**Backend routing:**
```python
def get_db_connection(operation='read', tenant_country=None):
    """Route DB connections by operation type and tenant geography."""
    if operation == 'write':
        return connect(DATABASE_URL_PRIMARY)   # always write to primary
    
    # Route reads to nearest replica
    COUNTRY_TO_REGION = {
        # Africa West
        'GH': 'af', 'NG': 'af', 'SN': 'af', 'CI': 'af', 'CM': 'af',
        'KE': 'af', 'TZ': 'af', 'ZA': 'af', 'UG': 'af', 'ET': 'af',
        # Middle East
        'AE': 'me', 'SA': 'me', 'QA': 'me', 'KW': 'me', 'BH': 'me',
        # Americas
        'US': 'us', 'CA': 'us', 'MX': 'us', 'BR': 'us', 'AR': 'us',
    }
    region = COUNTRY_TO_REGION.get(tenant_country, 'eu')
    
    read_urls = {
        'af': DATABASE_URL_AF_REPLICA,
        'me': DATABASE_URL_ME_REPLICA,
        'us': DATABASE_URL_US_REPLICA,
        'eu': DATABASE_URL_PRIMARY,
    }
    return connect(read_urls.get(region, DATABASE_URL_PRIMARY))
```

---

## Phase 3: Horizontal Sharding (500+ tenants)

### Shard Key

**Primary shard key:** `organization_id` (UUID)

Using consistent hashing with virtual nodes:
```python
import hashlib

SHARDS = {
    'shard-af': {'url': DATABASE_URL_SHARD_AF, 'regions': ['GH', 'NG', 'SN', 'KE', 'ZA']},
    'shard-eu': {'url': DATABASE_URL_SHARD_EU, 'regions': ['GB', 'DE', 'FR', 'ES', 'IT']},
    'shard-us': {'url': DATABASE_URL_SHARD_US, 'regions': ['US', 'CA', 'MX', 'BR']},
    'shard-me': {'url': DATABASE_URL_SHARD_ME, 'regions': ['AE', 'SA', 'QA', 'KW']},
}

SHARD_ROUTING_TABLE = {}  # organization_id → shard name, stored in Redis

def get_shard_for_tenant(organization_id: str) -> str:
    """Lookup shard for tenant. Check cache first, then routing table."""
    # Check Redis routing cache
    cached = redis_client.get(f'shard:{organization_id}')
    if cached:
        return cached.decode()
    
    # Consistent hash: UUID → shard
    hash_val = int(hashlib.md5(organization_id.encode()).hexdigest(), 16)
    shard_index = hash_val % len(SHARDS)
    shard_name = list(SHARDS.keys())[shard_index]
    
    # Cache for 1 hour
    redis_client.setex(f'shard:{organization_id}', 3600, shard_name)
    return shard_name

def get_db_for_tenant(organization_id: str):
    """Get database connection for a specific tenant."""
    shard = get_shard_for_tenant(organization_id)
    return connect(SHARDS[shard]['url'])
```

---

## Shard Tables

Each shard is an independent Neon PostgreSQL database with the same schema.
Cross-shard queries are avoided by design (all tenant data in one shard).

**Global tables** (NOT sharded — exist in all shards):
- `equipment_catalog` — replicated read-only
- `newsletter_subscribers` — replicated to all shards

**Tenant tables** (sharded by organization_id):
- `organizations`, `users`, `projects`, `leads`, `assessment_requests`
- `crm_opportunities`, `proposals`, `procurement_packages`, `bidder_submissions`
- `subscriptions`, `payments`, `tickets`, `ticket_replies`, `uploaded_files`
- `audit_log`, `email_logs`

---

## Shard Migration Strategy

When a tenant needs to move shard (e.g., company expands from Africa to global):

```python
def migrate_tenant_to_shard(organization_id: str, target_shard: str):
    """Zero-downtime tenant shard migration."""
    # 1. Start dual-write (write to both old and new shard)
    # 2. Backfill new shard from old shard
    # 3. Verify data consistency
    # 4. Switch reads to new shard
    # 5. Stop writes to old shard
    # 6. Update routing table
    # 7. Delete old shard data after verification period
    pass
```

---

## Cross-Shard Reporting (Admin/Platform Analytics)

Platform-level analytics (not tenant-scoped) query all shards:

```python
def platform_aggregate_stats():
    """Aggregate stats across all shards for admin dashboard."""
    totals = {'users': 0, 'projects': 0, 'revenue': 0}
    for shard_name, shard_config in SHARDS.items():
        conn = connect(shard_config['url'])
        totals['users']    += conn.execute("SELECT COUNT(*) FROM users").scalar()
        totals['projects'] += conn.execute("SELECT COUNT(*) FROM projects").scalar()
        totals['revenue']  += conn.execute("SELECT SUM(amount_usd) FROM payments WHERE status='success'").scalar() or 0
    return totals
```

---

## Neon-Specific Sharding (Using Neon Branches)

Neon provides database branching which maps perfectly to multi-region sharding:

```
Neon Project: solarpro-global
  ├── main (production primary — eu-west-2)
  ├── shard-af (Africa tenants — af-south-1 region)
  ├── shard-us (Americas tenants — us-east-2 region)
  ├── shard-me (Middle East — me-central-1 region)
  ├── staging (staging environment)
  └── dev (development environment)
```

Each branch has:
- Independent connection string
- Independent compute (auto-suspend when idle = zero cost when no queries)
- Full schema replication from main at branch creation

**Cost estimate with Neon:** ~$0 idle + $0.25/compute-hour active.
For a platform with 1000 tenants, ~$20-100/month total across all shards.

---

## Implementation Timeline

| When | Action |
|------|--------|
| Now | SQLite → Neon PostgreSQL single instance (migration 001 + 002) |
| 100 users | Add Neon read replica in Africa region |
| 500 users | Enable geographic sharding (shard-af, shard-eu, shard-us, shard-me) |
| 2000 users | Add dedicated shard per major market (shard-ng, shard-gh, shard-uk, etc.) |
