# CI/CD Pipeline

Last revised: 2026-06-25

```mermaid
flowchart LR
  Dev[Developer commit]
  Repo[(GitHub repo<br/>marc667us/solar-pv-designer-lite)]
  CI{CI workflow<br/>.github/workflows/ci.yml}
  Tests["pytest tests/security/<br/>177-179 unit tests"]
  Push[git push origin master]

  subgraph Deploy["Deploy lane"]
    direction LR
    FDeploy["Force Render Deploy<br/>(workflow_dispatch)"]
    EnvSync["GET-merge-PUT env vars<br/>?limit=100 mandatory"]
    Trigger["POST /deploys"]
    Render["Render builds<br/>Docker + waitress"]
    Live["solarpro.aiappinvent.com<br/>LIVE"]
  end

  subgraph Migrations["Migrations lane (gated)"]
    direction LR
    MigDispatch[gh workflow run<br/>Apply Migration 00X]
    DryRun{confirm=token?}
    Apply["psql -f migrations/00X.sql"]
    Verify[Post-apply checks]
  end

  subgraph Cron["Cron lane"]
    direction LR
    FXCron["FX Rates Refresh<br/>cron 06:00 UTC"]
    FXFetch[open.er-api.com]
    FXGuard{guards pass?<br/>15% max move, 36h freshness}
    FXPush[PUT FX_*_PER_USD]
  end

  Dev --> Repo --> CI --> Tests
  Tests -->|all pass| Push
  Push --> FDeploy --> EnvSync --> Trigger --> Render --> Live

  MigDispatch --> DryRun
  DryRun -->|DRYRUN| Verify
  DryRun -->|APPLY token| Apply --> Verify

  FXCron --> FXFetch --> FXGuard
  FXGuard -->|pass| FXPush --> Render
  FXGuard -->|fail| FXFail[no-op, log only]

  Live --> Smoke["tmp/live_smoke_*.py"]
  Smoke --> Live
```

## Workflow gating policy (per `feedback_workflow_dry_run_gate.md`)

Every UPDATE / DELETE / DDL workflow MUST:

1. Default to dry-run on `workflow_dispatch`.
2. Take a `confirm` input that must equal a specific token to commit.
3. Print a clear "would have done X" preview when in dry-run.
4. Print verification queries post-apply when in apply mode.

Workflows that follow this pattern today: `apply-keycloak-migrations`, `apply-migration-005-phase-b`, `apply-migration-007-boq-rls`, `paystack-rotate-to-live`, `cutover-to-keycloak`, `rollback-from-keycloak`, `fx-rates-refresh`.

## Test suites

| Suite | Where | When | What |
|---|---|---|---|
| Unit | `tests/security/` | every commit (local) | 179 tests, decorators + tenant ctx + OIDC routes + audit |
| Live smoke | `tmp/live_smoke_*.py` | after every deploy | M1.1 + SOC 2 routes + FX stamp + logout |
| Phase B smoke | `tmp/smoke_keycloak_pilot.py` | quarterly | full KC token-exchange path |
