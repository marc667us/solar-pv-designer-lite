# Backup Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Define backup, retention, and recovery targets for SolarPro data.

## Scope

`solarpro-postgres` (application + audit + error data), Keycloak
Postgres (identity), Render-attached disk where present, repository
artifacts (workflow outputs).

## Policy

1. **Frequency**
   - **Application Postgres** — nightly logical pg_dump (custom binary
     format `-Fc`) via `.github/workflows/backup-postgres.yml` at 03:00 UTC.
   - **Render-managed snapshots** — daily, automatic, on Render's
     Postgres add-on (point-in-time recovery available).
   - **Keycloak Postgres** — covered by Render's automatic Postgres
     snapshots (same plan).

2. **Retention**
   - Workflow-artifact dumps: 30 days (rolling).
   - Render snapshots: 7 days (free tier).
   - Annual archive: a quarterly snapshot is downloaded + saved to a
     long-term store on owner's local + Cloudflare R2 (when wired).

3. **Recovery targets**
   - **RPO (data loss)** — under 24 hours (one nightly + Render
     point-in-time). Goal: under 1 hour as soon as PITR-to-the-minute
     is verified.
   - **RTO (time to recovery)** — under 4 hours.

4. **Verification**
   - Dump integrity verified via `pg_restore --list` immediately after
     dump (the same workflow).
   - **Quarterly restore drill** via `backup-restore-test.yml` (TODO):
     restore the latest dump into a throwaway Postgres, run schema +
     row-count assertions, log to `docs/dr_drills/`.

5. **Encryption** — dumps are stored as workflow artifacts inside
   GitHub's encrypted-at-rest storage. Annual archive copies are
   encrypted with `age` before leaving the platform.

## Enforcement

- Nightly cron is monitored — a failure paginates the owner via the
  workflow's email notification.
- SOC 2 evidence collector includes the latest backup run summary.

## Review

Annual + after every restore drill.
