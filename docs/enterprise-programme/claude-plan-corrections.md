# Claude Code — Corrections to the Codex Plan (adjudicated)

Per master prompt §8, Claude Code must validate the Codex plan against the repository and
document every correction: what changed, why, and the repository evidence that justified it.
Every correction below was put BACK to Codex for adjudication before being accepted.

Status: Codex verdict recorded for each. Phase 1 is **SAFE TO BUILD AS AMENDED**.

---

## Correction 1 — RLS policy design (Codex verdict: CONFIRMED; Claude's fix improved by Codex)

**Codex originally proposed** a policy on `enterprise_organisations` containing
`EXISTS (SELECT 1 FROM enterprise_memberships m WHERE ... m.user_id::text = current_user_sub())`.

**Why that is wrong (evidence):**

1. **Identity mismatch.** `app/security/tenant_context.py:191` sets `user_value = user_sub or ""` —
   the `app.current_user` GUC carries the **Keycloak sub**, never the integer `users.id`, and is the
   empty string when there is no Keycloak RequestContext. So `m.user_id::text = current_user_sub()`
   can never be true, and users on the legacy Flask-session path collapse the predicate to false.
2. **Cross-table RLS recursion / silent-empty.** The policy subqueries `enterprise_memberships`,
   which is itself RLS-protected, so Postgres applies that table's policy *inside* the subquery.
   No precedent exists in this repo for a policy referencing another RLS table.
3. **FORCE makes it fatal, not loud.** `migrations/018_force_rls_globals.sql:8-10` states the app
   connects as table owner and owner-bypass is closed only by FORCE (applied at `018:114`,
   `019:143`, `020:118`). A wrong policy therefore returns **zero rows silently** — an empty,
   un-debuggable dashboard in production.

**Codex's correction to Claude's fix:** `SECURITY DEFINER` alone does **not** escape FORCE — a
function owned by the same table owner is still subject to RLS. Do not rely on it.

**Adopted design:**

- Publish the canonical identity: the enterprise module sets `app.current_user_id` (integer
  `users.id`) itself, on the connection it already holds. Feasible without touching `web_app.py`
  (`get_db()` at `web_app.py:383-399` applies only the Keycloak GUCs; `db_adapter.py:228-256`
  supports `?` placeholders on Postgres).
- `enterprise_memberships` is the **base policy** and queries no other enterprise table — this
  kills the recursion at the root.
- All child tables key off `organisation_id = ANY(current_enterprise_org_ids())`.
- Phase 1: `ENABLE ROW LEVEL SECURITY` **without FORCE**. Primary enforcement is **app-layer
  membership checks keyed on `session["user_id"]`**, with cross-org denial proven by tests.
  This is a parallel-run safety net, **not** DB-enforced isolation — and must not be described as
  such. FORCE is a later cutover, after the GUC identity path is proven live.

---

## Correction 2 — the Procfile is not the production start command (Codex verdict: CONFIRMED)

Codex originally cited `Procfile:1` (`--workers 1 --timeout 300`) as production.

**Evidence:** `.github/workflows/update-render-start-command.yml:3-6` states explicitly that Render
ignores the Procfile once an explicit `startCommand` exists, and PATCHes it via the Render API
(`:37-48`). `.github/workflows/render-apply-best-practices.yml:53` shows the real command:
`--worker-class gthread --workers 1 --threads 4 --timeout 300 --graceful-timeout 25`.

**Consequence:** no worker/timeout assumption may cite the Procfile. Job chunks are sized to
complete in **60–90s** and must be **idempotent and resumable**, rather than designed against a
file Render does not read.

---

## Correction 3 — admin_settings RLS (Codex verdict: **REFUTED — Claude was wrong**)

Claude claimed `admin_settings` has no RLS policy, having grepped only `migrations/022_soc_rls.sql`.

**Codex refuted this with evidence Claude missed:**
- `migrations/012_rls_batch5.sql:83,172-184` — RLS enabled + parallel-run policy.
- `migrations/015_global_table_policies.sql:214-233` — admin-only policy
  (`FOR ALL USING (current_user_is_admin())`).
- `migrations/018_force_rls_globals.sql:66,104` — **FORCE applied**.
- `migrations/018_force_rls_globals.sql:143-147` — an explicit check that `admin_settings` is
  invisible without `app.current_role='admin'`.

**Impact had this not been caught:** the feature-flag seed in migration 024 would have been
**silently rolled back**, shipping the module with no flags. This is the exact failure mode recorded
in the standing `feedback_solar_rls_seed_admin_role` note.

**Adopted fix — the seed must set the admin role GUC inside the transaction:**

```sql
BEGIN;
SELECT set_config('app.current_role', 'admin', true);
INSERT INTO admin_settings (key, value, updated_at)
VALUES ('enterprise_programme_enabled', '0', CURRENT_TIMESTAMP), ...
ON CONFLICT (key) DO NOTHING;
COMMIT;
```

(`ON CONFLICT (key)` itself is valid — `key` is the PRIMARY KEY in both DDL branches,
`new_marketplace_pagination.py:9-18`. That half of the correction was confirmed.)

---

## Codex's final safety call

> Phase 1 is **safe to build as amended** only if the handoff changes in three places:
> - Use legacy `users.id` as canonical enterprise identity and publish `app.current_user_id`.
> - Make app-layer membership checks the primary Phase 1 enforcement, with every enterprise query
>   scoped by `organisation_id`.
> - Do not claim DB-enforced enterprise isolation until FORCE is applied and tested with the real
>   GUC path.
>
> "Claude is right on the important RLS objection. The original policy design should not ship as written."

These three amendments are binding on the Phase 1 build.
