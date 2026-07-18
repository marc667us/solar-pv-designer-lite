-- 035 -- assign installers and suppliers to a site, from the bids they won
--
-- OWNER, 2026-07-18: "in the planning stage the installation must be assigned to installer
-- and suppliers, so reuse the installer and supplier list and bidding to select and sign
-- qualified contractors and suppliers to a particular site."
--
-- THE WHOLE POINT IS "REUSE". Nothing here re-implements suppliers or bidding:
--
--   * `suppliers`      -- the marketplace supplier list, already verified through
--                         /admin/marketplace, already carrying rating and lead time.
--   * `rfqs` / `rfq_responses` -- the existing bidding. A bid IS the quoted price, currency
--                         and lead time, and it is already stored.
--   * `enterprise_sites` -- the programme's sites (migration 026).
--
-- This table is the LINK, and only the link: WHICH supplier is doing WHAT at WHICH site,
-- and how far through selection they are. A second copy of a supplier, or of a price, would
-- be a second source of truth that drifts the first time either is edited.
--
-- WHY THE BID REFERENCE MATTERS. `source_response_id` points at the winning bid. Without it
-- an award is a name with no evidence -- nobody can answer "on what basis was this
-- contractor chosen, and at what price". With it, the answer is one join away, which is what
-- makes an award auditable rather than merely recorded.

CREATE TABLE IF NOT EXISTS enterprise_site_assignments (
    id                  bigserial PRIMARY KEY,
    tenant_id           uuid   NOT NULL REFERENCES enterprise_tenants(id) ON DELETE CASCADE,
    programme_id        bigint NOT NULL,
    site_id             bigint NOT NULL,

    -- WHAT they are doing here. The same company can be the installer on one site and a
    -- materials supplier on another, so the role belongs to the ASSIGNMENT, not the company.
    party_role          text   NOT NULL,          -- installer | supplier

    -- WHO. A plain id into the marketplace `suppliers` table rather than a foreign key: that
    -- table lives in the SQLite-era app schema, not in the enterprise migration set, and a
    -- cross-schema FK would make this migration fail on any database where the marketplace
    -- tables have not been created yet. The application layer resolves and validates it.
    supplier_id         integer NOT NULL,
    supplier_name       text   NOT NULL DEFAULT '',   -- denormalised for display only

    -- THE EVIDENCE. Which bid this award came from, and what it committed to. The price is
    -- copied because a quote is a point-in-time commitment: if the supplier later revises
    -- their standing prices, what they were AWARDED must not silently change with it.
    source_rfq_id       integer,
    source_response_id  integer,
    awarded_price       numeric,
    awarded_currency    text   NOT NULL DEFAULT '',
    lead_time_days      integer,

    -- HOW FAR ALONG. The owner's words were "select and sign", so the states are theirs:
    -- shortlisted (in the running) -> awarded (chosen) -> signed (contracted). `withdrawn`
    -- exists because a shortlist that cannot be un-shortlisted forces operators to delete
    -- rows, and deleting rows destroys the record of who was considered.
    status              text   NOT NULL DEFAULT 'shortlisted',
    scope_note          text   NOT NULL DEFAULT '',
    awarded_at          timestamptz,
    signed_at           timestamptz,
    created_by_user_id  integer,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_siteassign_site FOREIGN KEY (tenant_id, site_id)
        REFERENCES enterprise_sites (tenant_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_siteassign_programme FOREIGN KEY (tenant_id, programme_id)
        REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,

    -- One row per company per role per site. Awarding the same installer twice to the same
    -- site is not a second contract, it is a duplicate -- and it would make "who is the
    -- installer here" return two answers.
    CONSTRAINT uq_siteassign_party
        UNIQUE (tenant_id, site_id, party_role, supplier_id),

    CONSTRAINT ck_siteassign_role   CHECK (party_role IN ('installer', 'supplier')),
    CONSTRAINT ck_siteassign_status CHECK (
        status IN ('shortlisted', 'awarded', 'signed', 'withdrawn')),

    -- A signed assignment must record WHEN it was signed. A contract with no date is not
    -- evidence of anything, and this is the row an auditor reads.
    CONSTRAINT ck_siteassign_signed_has_date CHECK (
        status <> 'signed' OR signed_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS ix_ent_siteassign_site
    ON enterprise_site_assignments (tenant_id, site_id, party_role);
CREATE INDEX IF NOT EXISTS ix_ent_siteassign_programme
    ON enterprise_site_assignments (tenant_id, programme_id, status);
CREATE INDEX IF NOT EXISTS ix_ent_siteassign_supplier
    ON enterprise_site_assignments (tenant_id, supplier_id);

ALTER TABLE enterprise_site_assignments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ent_siteassign_member ON enterprise_site_assignments;
CREATE POLICY ent_siteassign_member ON enterprise_site_assignments
    FOR ALL USING (tenant_id IN (SELECT current_enterprise_tenant_ids()));
