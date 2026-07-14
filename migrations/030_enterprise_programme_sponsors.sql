-- Migration 030 -- a programme's FIRST, SECOND and THIRD sponsor.
--
-- OWNER (2026-07-14):
--   "potential sponsors must be registered in the system and programme can select them from
--    a drop down list, there must be first sponsor, second sponsor and third, each case a
--    drop down list of potential sponsors must be selected from dropdown list"
--   ...and then, decisively:
--   "look, check and reuse the funding in the standard design and reuse"
--
-- SO THIS MIGRATION ADDS NO SPONSOR TABLE. It adds three columns.
-- ------------------------------------------------------------------------------------
-- The register the owner is asking for ALREADY EXISTS. `financial_institutions` (the Project
-- Funding module, shipped 2026-07-05) is a platform-wide registry of funders with a
-- `status='approved'` gate, and it already carries exactly what a programme needs to know:
-- loan_min, loan_max, tenor_months, interest_min/max, fee_pct, supported_project_types.
--
-- A second `enterprise_sponsors` table was written and then DELETED before it shipped. It
-- would have been a poorer copy of this one -- and worse, the two would have drifted: an
-- institution approved in one register and unknown in the other, and an operator with no way
-- to tell which list was the real one. Reusing the registry is not a shortcut here; it is the
-- only version that stays true.
--
-- It also makes the FEASIBILITY STUDY possible. "determines if the bill can fund the program
-- for a given beneficiary" is answerable precisely BECAUSE financial_institutions records
-- loan_min and loan_max. A hand-rolled sponsor table would have had to invent those fields,
-- and they would have been empty.
--
-- A SPONSOR IS AN INSTITUTION. IT IS NOT `sponsor_user_id`.
-- ------------------------------------------------------------------------------------
-- The registry already has `sponsor_user_id`: the PERSON who holds the `programme_sponsor`
-- post and signs Gate 1 (control C01, the named post holder). Untouched here. Conflating the
-- two would have the app asking a development bank to sign a stage gate.
--
-- WHY THREE COLUMNS AND NOT A JOIN TABLE
-- ------------------------------------------------------------------------------------
-- The owner asked for exactly three, and they are ORDERED: first, second, third. A join table
-- models an unordered set of N and needs a `rank` column plus a uniqueness constraint to say
-- the same thing -- more machinery for the same fact, and a rank you can violate. Three named
-- columns cannot express "two second sponsors".
--
-- TEXT, not bigint: financial_institutions.institution_id is a TEXT primary key.
--
-- Idempotent. Safe to re-run.

BEGIN;

ALTER TABLE enterprise_programme_registry
    ADD COLUMN IF NOT EXISTS sponsor_1_id text;
ALTER TABLE enterprise_programme_registry
    ADD COLUMN IF NOT EXISTS sponsor_2_id text;
ALTER TABLE enterprise_programme_registry
    ADD COLUMN IF NOT EXISTS sponsor_3_id text;

-- NO FOREIGN KEY to financial_institutions, deliberately. That table is created lazily by the
-- Project Funding module's `_ensure_fi_schema()` at first use, not by a migration -- so a
-- hard FK here would make this migration's success depend on whether some other module had
-- happened to run first. The application validates every id against the approved registry
-- before writing it (sponsors.set_programme_sponsors), which is where the check belongs when
-- the referenced table's lifecycle is not ours to guarantee.

CREATE INDEX IF NOT EXISTS idx_enterprise_registry_sponsor_1
    ON enterprise_programme_registry (tenant_id, sponsor_1_id);

COMMIT;
