# Phase B Runbook — Drop the legacy bcrypt path

**Run on or after**: **2026-06-30** (= cutover date + 14 days; today is 2026-06-24).

**Pre-requisite**: the 7-day Keycloak rollback window has closed clean (no `rollback-from-keycloak` triggered, no surprise legacy-login spikes in `audit_logs`).

## What Phase B does

Applies `migrations/005_phase7_drop_password_hash.sql`:

1. Renames `users.password_hash` → `users.legacy_password_hash`
2. Renames `users.is_admin` → `users.legacy_is_admin`
3. Deletes `login_failures` rows older than 90 days

After this, the `POST /login?legacy=1` escape hatch can no longer bcrypt-authenticate anyone — the legacy form returns "Invalid username or password" because the column it reads no longer exists. The `?legacy=1` GET path still renders the form (cosmetic), but it's dead.

Phase A (`6dbd4f3`, shipped 2026-06-24) already 302s the non-legacy POST `/login`, `/register`, `/forgot-password`, `/reset-password` to Keycloak. Phase B closes the legacy-only carve-out.

## Step-by-step

### 1. Dry-run preview (zero risk)

```bash
gh workflow run "Apply Migration 005 (Phase B)"
```

This runs `confirm=` empty, which triggers dry-run mode. The workflow:

- Verifies `KEYCLOAK_ENABLED=true` on Render.
- Verifies migrations 003 + 004 already applied.
- Prints current `users` table columns (you should see `password_hash` + `is_admin` present, `legacy_*` absent).
- Prints the full migration SQL.
- Reports recent legacy login count (last 7 days).
- **Does NOT apply.**

Watch the run log. If pre-flight fails (e.g. KC not enabled), STOP — something's misaligned with the cutover state.

### 2. Commit

After the dry-run reads clean:

```bash
gh workflow run "Apply Migration 005 (Phase B)" -f confirm=PHASE_B
```

This applies the migration and verifies post-state:

- Confirms `legacy_password_hash` + `legacy_is_admin` columns now exist.
- Confirms `password_hash` + `is_admin` columns are GONE.
- Prints PASS summary.

Total runtime: ~1 minute.

### 3. Live smoke (manual, ~30 seconds)

```bash
# Should redirect to KC (Phase A behaviour, unchanged)
curl -i -X POST -d "username=anyone&password=x" https://solarpro.aiappinvent.com/login
# Expect: HTTP 302 -> /auth/login

# Should reach the legacy form (cosmetic; bcrypt auth dead post-migration 005)
curl -i https://solarpro.aiappinvent.com/login?legacy=1
# Expect: HTTP 200 with the legacy <form>

# Try to authenticate via the legacy path (must FAIL after migration 005)
curl -i -X POST -d "username=admin&password=any-old-bcrypt-pw" \
     -b /tmp/cookie -c /tmp/cookie \
     https://solarpro.aiappinvent.com/login?legacy=1
# Expect: HTTP 200, flash="Invalid username or password" (NOT a 302 to /dashboard)
```

If the third probe returns a 302 to /dashboard, the migration didn't take — re-run the workflow with `confirm=PHASE_B`.

## Rollback (if needed within 48h)

The migration only renames columns; nothing is destroyed. To undo:

```sql
BEGIN;
ALTER TABLE users RENAME COLUMN legacy_password_hash TO password_hash;
ALTER TABLE users RENAME COLUMN legacy_is_admin TO is_admin;
COMMIT;
```

Run via psql against the same connection the workflow uses (resolve via `gh workflow run "Audit BOM Formula V1 vs V2"` first — it prints the Postgres URL into the log, masked).

After 30 days a follow-up migration (006) drops the renamed columns entirely; from that point rollback requires restoring from backup.

## What stays on the carry-over list

- Code-side removal of the `?legacy=1` GET render path in `web_app.py` (the form still draws cosmetically; cleanup commit).
- Drop the `?legacy=1` escape hatch from Phase A's KC guards on `/login`, `/register`, `/forgot-password`, `/reset-password` (web_app.py lines around 1756, 1882, 1961, 2010).

These are tracked in `[[project-solar-pv-keycloak-migration-plan]]` as the post-Phase-B cleanup.

## Cross-references

- Migration file: `migrations/005_phase7_drop_password_hash.sql`
- Apply workflow: `.github/workflows/apply-migration-005-phase-b.yml`
- Cutover workflow (already run): `.github/workflows/cutover-to-keycloak.yml`
- Rollback workflow: `.github/workflows/rollback-from-keycloak.yml`
- Phase A patch: `patch_phase_a_close_legacy_post_bypass.py` (commit `6dbd4f3`)
- Migration plan: `docs/SECURITY_MIGRATION_KEYCLOAK.md`
