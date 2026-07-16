-- 032 -- DROP enterprise_activity_answers (the Rev 4 Q&A engine's store).
--
-- WHY. The owner is re-implementing the Enterprise Programme module from their spec
-- `enterprise revision 4.txt`: the OLD version is removed and a NEW six-phase model is built.
-- The per-activity Question & Answer engine is old-version machinery and was deleted in
-- `afe7d08` ("we not need the Q and A engine -- rip it off"). This table is the last thing
-- left of it.
--
-- Owner's rule, verbatim: "item marked to be removed must be removed and delected."
-- Owner's decision on this table, 2026-07-16: drop it now, NO backup.
--
-- WHAT READS IT: nothing. `documents.ensure_schema` no longer creates it, and every function
-- that touched it (get_answers, outstanding_questions, save_answers, _raise_question) is
-- deleted, as are the three /answers routes and the template. Independently confirmed by the
-- Codex gate on that commit ("not a correctness defect ... assuming no code reads/writes it").
--
-- SAFETY PROFILE:
--   * DESTRUCTIVE and IRREVERSIBLE. This is the only statement here that matters.
--   * Narrow blast radius: one table, created by migration 028. Nothing references it -- it
--     is the CHILD of enterprise_programme_registry, never a parent, so no other table has an
--     FK pointing AT it and no CASCADE can reach beyond it.
--   * The live enterprise data was already wiped to a clean slate on 2026-07-15 (workflow
--     `Clear Enterprise Rebuild Data`, run 29459626937), so this table is expected to be
--     empty or near-empty. The workflow prints its row count before dropping either way.
--   * IF EXISTS: idempotent, and a no-op if a previous run already dropped it.
--   * NOT applied automatically. The workflow defaults to DRY-RUN and commits only on
--     -f confirm=DROP_ANSWERS_APPLY.

BEGIN;

-- The unique index goes with the table; naming it here only documents what 028 created.
--   ux_ent_activity_answer ON enterprise_activity_answers (tenant_id, programme_id, activity_code)
DROP TABLE IF EXISTS enterprise_activity_answers;

COMMIT;
