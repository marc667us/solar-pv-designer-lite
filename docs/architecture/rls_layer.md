# RLS Data Layer

Last revised: 2026-06-25 (M1.6 BOQ-hierarchy batch applied)

How a tenant claim on the JWT becomes a Postgres `WHERE tenant_id = …` predicate.

```mermaid
flowchart LR
  subgraph REQ["One HTTP request"]
    JWT[Bearer JWT<br/>claim tenant_id = uuid]
    Mid["app/security/keycloak_middleware<br/>verify_jwt + extract_request_context"]
    G["g.kc_ctx<br/>RequestContext(tenant_id, user_id, roles, ...)"]
    Hook["@app.before_request M1.7<br/>g.tenant_scoped, g.tenant_ctx_present"]
  end

  subgraph DBCALL["First get_db() call inside the route"]
    GD["get_db() context manager"]
    Apply["apply_tenant_guc(conn)<br/>SELECT set_config('app.current_tenant', tid, true)"]
    Query["any SELECT / UPDATE / DELETE"]
  end

  subgraph PG["Postgres"]
    direction TB
    GUC["GUC app.current_tenant = uuid<br/>(tx-local: is_local=true)"]
    Fn["current_tenant_id() returns app.current_tenant::uuid"]
    Policy["RLS policy &lt;table&gt;_tenant_isolation<br/>USING ( GUC IS NULL OR row.tenant_id IS NULL OR row.tenant_id = GUC )"]
    Row[(actual rows)]
  end

  JWT --> Mid --> G --> Hook
  Hook --> GD --> Apply --> GUC
  GUC --> Fn --> Policy
  Apply --> Query --> Policy --> Row
```

## Defence in depth

```mermaid
flowchart TD
  L1["1. JWT middleware<br/>refuses unsigned / expired / bad-aud tokens"]
  L2["2. Decorator<br/>@require_role / @admin_required gates the route"]
  L3["3. App-level WHERE<br/>handlers should still filter by tenant_id where they can"]
  L4["4. RLS policy<br/>even if 3 is missing, the row is invisible"]
  L5["5. M1.7 audit signal<br/>warns when a tenant-scoped path ran without g.kc_ctx"]
  L1 --> L2 --> L3 --> L4 --> L5
```

## Parallel-run NULL escapes (current state)

The RLS policies created in migrations 003 + 007 carry two NULL escapes:

```sql
USING (
  current_tenant_id() IS NULL    -- GUC unset (no JWT context) -> visible
  OR tenant_id IS NULL            -- legacy row (pre-backfill) -> visible
  OR tenant_id = current_tenant_id()
)
```

Both escapes are intentional during the parallel-run phase. **Phase 7 cutover migration** (scheduled separately, post Phase B) tightens to `FORCE ROW LEVEL SECURITY` + drops both NULL escapes — at which point any request without `g.kc_ctx` will see zero rows on any tenant table.

## Tables under RLS today

| Migration | Tables |
|---|---|
| 003 (Phase 4) | projects, tickets, ticket_replies, email_logs, password_reset_tokens, payments, suppliers, equipment_catalog, rfqs, rfq_items, marketplace_boms, marketplace_bom_items, marketplace_boqs, marketplace_boq_items, price_sheets, price_sheet_items, marketplace_audit |
| 004 (audit log) | audit_logs |
| 007 (M1.6 BOQ batch) | boq_projects, boq_buildings, boq_floors, boq_floor_items, boq_floor_rate_buildup, boq_audit_log |
