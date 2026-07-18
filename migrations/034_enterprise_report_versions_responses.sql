-- 034 -- report versions and per-recipient responses
--
-- Revision xx201 s42-s43. Two things the app could not express before:
--
--   1. A report has VERSIONS. A recipient asks for a change, the agent revises, and the
--      revision is a new version -- not an overwrite. Without this the app cannot show what
--      was sent, what changed, or which version someone actually accepted.
--
--   2. Each recipient answers SEPARATELY. xx201 s42 is explicit: "Do not use only one general
--      report response." A beneficiary may accept while a sponsor asks for changes, and the
--      report is accepted only when BOTH have accepted (s24, s29, s35). One blended status
--      cannot represent that, and a report that looks accepted when the sponsor has not
--      accepted it is the kind of error that ends a programme.
--
-- SUBORDINATE TO enterprise_documents, NOT A PARALLEL DOCUMENT TABLE. Codex (MEDIUM,
-- 2026-07-18): enterprise_documents already stores the generated markdown, the doc_type and
-- the tenant/programme scoping (026 + 028). A second table holding documents would be two
-- sources of truth for "what does this report say", and they would drift. The document row
-- stays the CURRENT report; versions are its history; responses hang off the document and
-- name the version they answered.
--
-- Tenant discipline per the Project Execution Directive s6/s7/s11: tenant_id on every row,
-- composite FKs that carry tenant_id so a child can never point at another tenant's parent,
-- RLS policies matching the 026 pattern, and indexes on the access paths actually used.

-- -----------------------------------------------------------------------------
-- PRE-REQUISITE -- the FK target these tables need
-- -----------------------------------------------------------------------------
-- Codex (CRITICAL, 2026-07-18): a composite FK needs a UNIQUE on exactly the referenced
-- columns. `enterprise_programme_registry` carries `uq_ent_programme_tenant_id UNIQUE
-- (tenant_id, id)` for precisely this reason (026), but `enterprise_documents` never got the
-- equivalent -- it has `id bigserial PRIMARY KEY` and nothing else. Without this, every FK
-- below is rejected by Postgres and the whole migration fails ON THE LIVE DATABASE.
--
-- It cannot fail on existing data: `id` is already the primary key and `tenant_id` is NOT
-- NULL, so `(tenant_id, id)` is trivially unique for every row that exists.
--
-- LOCK WINDOW, ACCEPTED EXPLICITLY rather than waved past (Codex, MEDIUM, 2026-07-18):
-- ADD CONSTRAINT ... UNIQUE takes an ACCESS EXCLUSIVE lock and builds an index. On this table
-- that is a fraction of a second -- enterprise_documents holds programme documents, tens of
-- rows per tenant, not millions -- and the app already tolerates a restart on every deploy.
-- The CREATE UNIQUE INDEX CONCURRENTLY dance is the right answer on a large hot table; here
-- it would trade a sub-second window for a migration that cannot run inside a transaction.
-- If this table ever grows into the millions, revisit before adding another constraint.
--
-- Guarded by a DO block because Postgres has no `ADD CONSTRAINT IF NOT EXISTS`, and this
-- migration must be rerunnable.
DO $$
BEGIN
    IF NOT EXISTS (
        -- SCOPED TO THE TABLE. Codex (MEDIUM): constraint names live in a schema-wide
        -- namespace, so an unqualified `conname` match could find this name on a DIFFERENT
        -- table, skip creating the constraint here, and leave the FKs below with nothing to
        -- reference -- the exact failure this block exists to prevent, silently.
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_ent_document_tenant_id'
          AND conrelid = 'enterprise_documents'::regclass
    ) THEN
        ALTER TABLE enterprise_documents
            ADD CONSTRAINT uq_ent_document_tenant_id UNIQUE (tenant_id, id);
    END IF;
END $$;

-- -----------------------------------------------------------------------------
-- report versions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enterprise_document_versions (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid   NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    document_id         bigint NOT NULL,
    version_number      integer NOT NULL,
    markdown            text   NOT NULL,
    -- Why this version exists. For a revision it summarises what changed and which
    -- modification notice drove it; for version 1 it is simply "first issue".
    change_summary      text   NOT NULL DEFAULT '',
    created_by_user_id  integer,
    created_at          timestamptz NOT NULL DEFAULT now(),

    -- The composite FK carries tenant_id, so a version physically cannot attach to another
    -- tenant's document even if application code passed the wrong id.
    CONSTRAINT fk_docver_document FOREIGN KEY (tenant_id, document_id)
        REFERENCES enterprise_documents (tenant_id, id) ON DELETE CASCADE,

    -- Version numbers are per document and dense. Two rows claiming to be "Version 2" would
    -- make "which version did the sponsor accept" unanswerable.
    CONSTRAINT uq_docver_number UNIQUE (tenant_id, document_id, version_number),
    CONSTRAINT ck_docver_number_positive CHECK (version_number >= 1)
);

CREATE INDEX IF NOT EXISTS ix_ent_docver_document
    ON enterprise_document_versions (tenant_id, document_id, version_number DESC);

-- -----------------------------------------------------------------------------
-- per-recipient responses
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enterprise_report_responses (
    id                bigserial PRIMARY KEY,
    tenant_id         uuid   NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    document_id       bigint NOT NULL,

    -- WHICH VERSION WAS ANSWERED. Without it, an acceptance of version 1 would silently read
    -- as an acceptance of version 3 after a revision -- the recipient would appear to have
    -- approved text they never saw.
    version_number    integer NOT NULL,

    -- 'beneficiary' or 'sponsor'. The two are tracked separately and are never merged.
    recipient_kind    text NOT NULL,
    -- Who answered, as free text: the external contact is not a platform user (xx201 s18 --
    -- "the recipient should not need a full SolarPro Enterprise subscription").
    recipient_name    text NOT NULL DEFAULT '',
    recipient_email   text NOT NULL DEFAULT '',

    -- ACCEPTED | REJECTED | MODIFICATION_REQUESTED  (xx201 s19)
    response          text NOT NULL,
    comments          text NOT NULL DEFAULT '',
    responded_at      timestamptz NOT NULL DEFAULT now(),

    -- POINTS AT THE VERSION, NOT MERELY THE DOCUMENT. Codex (HIGH, 2026-07-18): with only a
    -- document FK, a response could name version 3 while no version 3 exists -- the app would
    -- report "the sponsor accepted version 3" with no text to show for it, and an acceptance
    -- that cannot be evidenced is worse than no acceptance at all. `uq_docver_number` above is
    -- the UNIQUE that makes this reference legal.
    --
    -- The document FK is not repeated: versions already cascade from the document, so a
    -- deleted document still takes its versions and their responses with it.
    CONSTRAINT fk_resp_version FOREIGN KEY (tenant_id, document_id, version_number)
        REFERENCES enterprise_document_versions (tenant_id, document_id, version_number)
        ON DELETE CASCADE,

    -- One live answer per recipient per version. A recipient changing their mind supersedes
    -- their answer rather than accumulating two contradictory ones.
    CONSTRAINT uq_resp_recipient_version
        UNIQUE (tenant_id, document_id, version_number, recipient_kind),

    -- The vocabulary is closed at the database, not merely in Python. A typo'd response that
    -- reached this table would make the "accepted by both" rule silently unsatisfiable.
    CONSTRAINT ck_resp_kind CHECK (recipient_kind IN ('beneficiary', 'sponsor')),
    CONSTRAINT ck_resp_value CHECK (
        response IN ('ACCEPTED', 'REJECTED', 'MODIFICATION_REQUESTED'))
);

CREATE INDEX IF NOT EXISTS ix_ent_resp_document
    ON enterprise_report_responses (tenant_id, document_id, version_number);

-- -----------------------------------------------------------------------------
-- RLS -- same shape as 026, deliberately
-- -----------------------------------------------------------------------------
ALTER TABLE enterprise_document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE enterprise_report_responses  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_docver_member ON enterprise_document_versions;
CREATE POLICY ent_docver_member ON enterprise_document_versions
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

DROP POLICY IF EXISTS ent_resp_member ON enterprise_report_responses;
CREATE POLICY ent_resp_member ON enterprise_report_responses
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));

-- NOTE FOR THE EXTERNAL REVIEW PORTAL (the next slice, deliberately NOT built here):
-- these policies resolve tenants through current_enterprise_tenant_ids(), which reads
-- app.current_user_id. An UNAUTHENTICATED portal request has no such user, so it resolves to
-- no tenants and these policies grant nothing. That is correct and intended: the portal must
-- NOT be given a fake user to satisfy RLS. It will read through a narrow projection-only
-- function that validates a token first, per the Codex CRITICAL finding of 2026-07-18.
