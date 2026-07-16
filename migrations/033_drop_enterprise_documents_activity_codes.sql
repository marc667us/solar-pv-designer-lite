-- 033 -- DROP enterprise_documents.activity_codes (the last column of the old 453-activity map).
--
-- WHY. The owner is re-implementing the Enterprise Programme module from their spec
-- `enterprise revision 4.txt`, and their rule is verbatim: "the app you are building now can
-- not be touched, but the exist[ing] remnant of the old map must be removed and deleted."
--
-- THE OLD MAP was constants.py: 16 phases, 14 gates, 453 lifecycle ACTIVITIES and 144
-- deliverables. Revision 4 replaces it with 6 phases, 5 gates and 112 deliverables, and it
-- has NO activities at all -- a report IS one deliverable (owner-spec sections 9-14).
--
-- This column recorded which of the 453 activities a generated document "answered". With the
-- activities deleted, it can only ever be an empty JSON array. Worse, it was a SECOND copy of
-- a fact the row already carries: a Rev 4 report's provenance is its deliverable, which is
-- stamped into `doc_type` (rev4_phases.deliverable_doc_type) and recorded in the
-- ENTERPRISE_DOCUMENT_GENERATED audit event. Two copies of one fact is a place for them to
-- disagree, and this one would have disagreed permanently -- always empty, next to a doc_type
-- that names the real answer.
--
-- WHAT READS IT: nothing, as of this commit. `documents.generate_document` no longer writes
-- it, `list_documents` and `get_document` no longer select it, and it is out of
-- `documents._NEW_COLUMNS` so a fresh SQLite database never grows it.
--
-- SAFETY PROFILE:
--   * DESTRUCTIVE and IRREVERSIBLE for the column's contents.
--   * Narrow blast radius: ONE nullable column on ONE table (added by migration 028). It is
--     not indexed, carries no constraint, and no FK or view references it -- verified before
--     writing this migration.
--   * The live enterprise data was wiped to a clean slate on 2026-07-16 (workflow
--     `Clear Enterprise Rebuild Data`, run 29507134756: the only programme and its single
--     document were deleted), so enterprise_documents is expected to be EMPTY. The workflow
--     prints the row count and the count of rows carrying a non-empty activity_codes value
--     BEFORE dropping, either way -- do not trust this paragraph over that output.
--     (2026-07-16 lesson: run the dry-run before you describe the blast radius, not after.
--      The last drop was authorised on my claim a table was "likely near-empty"; it held 33
--      rows.)
--   * IF EXISTS: idempotent, and a no-op if a previous run already dropped it.
--   * NOT applied automatically. The workflow defaults to DRY-RUN and commits only on
--     -f confirm=DROP_ACTIVITY_CODES_APPLY.
--
-- DO NOT RE-RUN MIGRATION 028 AFTER THIS ONE. 028 line 65 is
-- `ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS activity_codes text;`, so
-- re-running it would silently RESURRECT the column this migration drops -- and
-- `apply-migration-028-lifecycle-documents.yml` also verifies that column is present, so its
-- check would fail here and rightly so. 028 is applied history and its workflow is a one-shot;
-- migrations are append-only, so 028 is deliberately left untouched and THIS migration is the
-- one that has the last word. If the enterprise schema is ever rebuilt from zero, 028 then 033
-- in order produces the correct end state.

BEGIN;

ALTER TABLE enterprise_documents DROP COLUMN IF EXISTS activity_codes;

COMMIT;
