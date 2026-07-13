-- =============================================================================
-- 028 -- Enterprise Programme: lifecycle document generation + source uploads
-- =============================================================================
--
-- WHAT THIS ADDS
-- --------------
-- Two capabilities the owner asked for, on top of the document REGISTER that migration
-- 026 already created:
--
--   1. An operator ticks lifecycle activities (doc 3's "Main Activities", 453 of them
--      across 16 phases) and the app GENERATES a document covering exactly those.
--   2. An operator UPLOADS a document -- a policy, a needs assessment, a ministry brief --
--      and that document becomes the source material the generated document is built from.
--
-- WHY IT EXTENDS enterprise_documents RATHER THAN ADDING A TABLE
-- -------------------------------------------------------------
-- `enterprise_documents` is already the programme's document register, it is already
-- tenant-scoped, already carries the composite FK to the programme, and already has an RLS
-- policy. A generated document and an uploaded document ARE documents on that programme --
-- Gate 6 asks "is there a standardisation pack", and it should not have to ask two tables.
-- A second table would have duplicated the tenancy, the FK, the policy and the index, and
-- then required every reader to UNION them.
--
-- The cost is that a register row now carries a blob. That is handled by never selecting
-- `content` unless the caller is actually downloading the file -- see documents.py, which
-- lists and reads by explicit column list and never uses SELECT *.
--
-- IDEMPOTENT. Every statement is ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS, so
-- re-running is safe. Per the project's migration discipline the statements are separate,
-- so one failing does not roll back the rest.

-- The kind of document this row is:
--   'registered' -- the pre-existing behaviour: a title and a URI, no content. (DEFAULT, so
--                   every row migration 026 created keeps its exact current meaning.)
--   'uploaded'   -- an operator uploaded a real file; content + extracted_text are filled.
--   'generated'  -- the app produced it from selected activities; markdown + activity_codes
--                   are filled, and source_document_id points at the upload it was drawn
--                   from (NULL if it was generated from programme data alone).
ALTER TABLE enterprise_documents
    ADD COLUMN IF NOT EXISTS doc_kind text NOT NULL DEFAULT 'registered';

-- The uploaded file, as uploaded. Kept so the operator can download exactly what they put
-- in -- an extracted-text-only store quietly loses the original, and "the system changed my
-- document" is not a conversation worth having with a ministry.
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS file_name  text;
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS mime_type  text;
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS byte_size  integer NOT NULL DEFAULT 0;
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS content    bytea;

-- The text pulled out of the upload (PDF via pypdf, DOCX via python-docx, XLSX via openpyxl,
-- plain text as-is). This -- not `content` -- is what document generation reads, because
-- generation needs words, not bytes, and re-parsing a PDF on every generate would be both
-- slow and non-deterministic across library versions.
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS extracted_text text;

-- A generated document, in the form it was generated. The PDF is rendered from this on
-- download rather than stored, so a PDF-rendering fix improves every document ever made
-- instead of only the ones made after it.
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS markdown text;

-- WHICH activities this document answers -- a JSON array of activity codes (P03_A07...).
-- This is what makes a generated document accountable: it can always say what it covers,
-- and the lifecycle board can show which activities have a document behind them and which
-- are still bare. Without it a generated document is just a file with a date on it.
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS activity_codes text;

-- The uploaded document this one was generated FROM, if any. Traceability, in the same
-- spirit as C14: an output can always name its input.
ALTER TABLE enterprise_documents ADD COLUMN IF NOT EXISTS source_document_id bigint;

-- The register is now read by kind ("show me this programme's uploads" / "...its generated
-- documents"), so the index that serves it should know about kind.
CREATE INDEX IF NOT EXISTS ix_ent_document_kind
    ON enterprise_documents (tenant_id, programme_id, doc_kind);


-- -----------------------------------------------------------------------------
-- PART 2 -- what the app ASKS, and what the operator ANSWERS
-- -----------------------------------------------------------------------------
-- The app writes each lifecycle activity from the programme's description, its records and
-- any uploaded source document. Where none of those say enough, it does NOT invent the
-- content and it does not silently leave a hole: it ASKS THE OPERATOR A QUESTION, and the
-- answer becomes the content.
--
-- ANSWERS BELONG TO THE PROGRAMME AND THE ACTIVITY -- NOT TO A DOCUMENT.
-- "Which institution is sponsoring this programme?" has one answer, and it is just as true
-- in the concept note as in the business case. Keying answers to a document would ask the
-- operator the same question again for every document they ever generate, and would let two
-- documents of the same programme give two different answers to the same question -- which
-- is precisely the drift the whole template/version engine exists to prevent.
--
-- So: answer it once, and every document the programme ever generates knows it.
CREATE TABLE IF NOT EXISTS enterprise_activity_answers (
    id                 bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id       bigint NOT NULL,
    activity_code      text NOT NULL,
    question           text NOT NULL,
    answer             text,
    answered_by_user_id integer,
    answered_at        timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_activity_answer_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
);

-- One outstanding question per activity per programme. This is the constraint that makes
-- "answer it once" true rather than merely intended: without it, two generates of the same
-- activity would stack up two identical questions and the operator would answer both.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_activity_answer
    ON enterprise_activity_answers (tenant_id, programme_id, activity_code);

-- The questionnaire reads "what is still unanswered for this programme", so that is what
-- the index serves.
CREATE INDEX IF NOT EXISTS ix_ent_activity_answer_open
    ON enterprise_activity_answers (tenant_id, programme_id, answered_at);

ALTER TABLE enterprise_activity_answers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_activity_answer_member ON enterprise_activity_answers;
CREATE POLICY ent_activity_answer_member ON enterprise_activity_answers
    FOR ALL
    USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));
