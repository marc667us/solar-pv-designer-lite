"""Assign installers and suppliers to a site, from the bids they won.

OWNER, 2026-07-18: "in the planning stage the installation must be assigned to installer and
suppliers, so reuse the installer and supplier list and bidding to select and sign qualified
contractors and suppliers to a particular site."

REUSE IS THE REQUIREMENT, not an implementation detail. Three things already exist and none of
them are rebuilt here:

  * `suppliers`      -- the marketplace supplier list, verified through /admin/marketplace,
                        already carrying rating, lead time and contact details.
  * `rfqs` / `rfq_responses` -- the existing bidding. A bid already IS a quoted price, a
                        currency and a lead time.
  * `enterprise_sites` -- the programme's sites.

This module is the link between them: WHICH company is doing WHAT at WHICH site, how far
through selection they are, and WHICH BID that decision came from.

THE STATES ARE THE OWNER'S OWN WORDS -- "select and sign":

    shortlisted  ->  awarded  ->  signed
                          \\-> withdrawn

`withdrawn` exists because a shortlist that cannot be un-shortlisted forces operators to
delete rows, and deleting rows destroys the record of who was considered -- which is exactly
what someone asks for when a procurement decision is questioned a year later.
"""

from __future__ import annotations

from . import txn

INSTALLER = "installer"
SUPPLIER = "supplier"
PARTY_ROLES = (INSTALLER, SUPPLIER)

SHORTLISTED = "shortlisted"
AWARDED = "awarded"
SIGNED = "signed"
WITHDRAWN = "withdrawn"
STATUSES = (SHORTLISTED, AWARDED, SIGNED, WITHDRAWN)

# What may follow what. A signed contract is NOT a step on the way to something else: undoing
# it is a commercial act (a termination), not a status edit, so it is terminal here and the
# operator has to record the reason elsewhere rather than quietly rewind the row.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    SHORTLISTED: (AWARDED, WITHDRAWN),
    AWARDED:     (SIGNED, WITHDRAWN),
    SIGNED:      (),
    WITHDRAWN:   (SHORTLISTED,),      # reconsidering someone is legitimate
}


class AssignmentError(Exception):
    """The assignment could not be made or moved as asked."""


def ensure_schema(c) -> None:
    """Create the SQLite mirror. No-op on Postgres, where migration 035 owns the schema.

    The CHECKs and the UNIQUE are the same as 035, not a looser approximation -- the suite
    runs on SQLite and production runs on Postgres, so a constraint present in only one of
    them is a constraint that is not really tested.
    """
    if txn.is_postgres():
        return

    c.execute("""
        CREATE TABLE IF NOT EXISTS enterprise_site_assignments (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id          TEXT    NOT NULL,
            programme_id       INTEGER NOT NULL,
            site_id            INTEGER NOT NULL,
            party_role         TEXT    NOT NULL,
            supplier_id        INTEGER NOT NULL,
            supplier_name      TEXT    NOT NULL DEFAULT '',
            source_rfq_id      INTEGER,
            source_response_id INTEGER,
            awarded_price      REAL,
            awarded_currency   TEXT    NOT NULL DEFAULT '',
            lead_time_days     INTEGER,
            status             TEXT    NOT NULL DEFAULT 'shortlisted',
            scope_note         TEXT    NOT NULL DEFAULT '',
            awarded_at         TEXT,
            signed_at          TEXT,
            created_by_user_id INTEGER,
            created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, site_id, party_role, supplier_id),
            CHECK (party_role IN ('installer', 'supplier')),
            CHECK (status IN ('shortlisted', 'awarded', 'signed', 'withdrawn')),
            CHECK (status <> 'signed' OR signed_at IS NOT NULL)
        )
    """)
    for ddl in (
        "CREATE INDEX IF NOT EXISTS ix_ent_siteassign_site "
        "ON enterprise_site_assignments (tenant_id, site_id, party_role)",
        "CREATE INDEX IF NOT EXISTS ix_ent_siteassign_programme "
        "ON enterprise_site_assignments (tenant_id, programme_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_ent_siteassign_supplier "
        "ON enterprise_site_assignments (tenant_id, supplier_id)",
    ):
        c.execute(ddl)


# --- the supplier list, reused ------------------------------------------------

def qualified_suppliers(c, *, role: str = SUPPLIER, limit: int = 200) -> list[dict]:
    """Suppliers that may be assigned, best-rated first.

    Input:  the role being filled.
    Output: the marketplace's own supplier rows, filtered to those fit to be offered work.

    ONLY ACTIVE SUPPLIERS. The owner asked to "select and sign QUALIFIED contractors and
    suppliers" -- offering a deactivated company is how a programme awards work to someone
    who is no longer trading. The marketplace already carries that flag; this honours it
    rather than inventing a second notion of qualified.
    """
    if role not in PARTY_ROLES:
        raise AssignmentError(f"unknown role {role!r}")
    try:
        rows = c.execute(
            "SELECT id, name, country, contact_name, email, phone, rating, "
            "       lead_time_days, categories "
            "FROM suppliers WHERE COALESCE(is_active, 1) = 1 "
            "ORDER BY rating DESC, name ASC LIMIT ?", (limit,)).fetchall()
    except Exception:
        # The marketplace tables live in the app schema, not the enterprise migration set. On
        # a database where they have not been created, an empty list is the honest answer --
        # this must not take the Planning page down.
        return []
    return [{"id": r[0], "name": r[1], "country": r[2] or "", "contact_name": r[3] or "",
             "email": r[4] or "", "phone": r[5] or "", "rating": r[6],
             "lead_time_days": r[7], "categories": r[8] or ""} for r in rows]


def bids_for_supplier(c, supplier_id: int, limit: int = 20) -> list[dict]:
    """That supplier's bids, newest first -- what an award can be based on.

    Reads `rfq_responses` directly. A bid already holds the price, the currency and the lead
    time the supplier committed to; re-entering any of it by hand would be a second version
    of a number that already exists.
    """
    try:
        rows = c.execute(
            "SELECT id, rfq_id, total_price, currency, lead_time_days, valid_until "
            "FROM rfq_responses WHERE supplier_id = ? ORDER BY id DESC LIMIT ?",
            (supplier_id, limit)).fetchall()
    except Exception:
        return []
    return [{"response_id": r[0], "rfq_id": r[1], "total_price": r[2],
             "currency": r[3] or "", "lead_time_days": r[4], "valid_until": r[5] or ""}
            for r in rows]


# --- assigning ----------------------------------------------------------------

def shortlist(c, tenant_id: str, programme_id: int, site_id: int, *,
              party_role: str, supplier_id: int, supplier_name: str = "",
              scope_note: str = "", user_id: int | None = None) -> int:
    """Put a company in the running for this site. Returns the assignment id.

    Shortlisting is deliberately separate from awarding. The owner's phrase was "select AND
    sign": those are two decisions, usually made by different people on different days, and
    collapsing them would mean the moment a company is considered is the moment it is hired.
    """
    if party_role not in PARTY_ROLES:
        raise AssignmentError(f"unknown role {party_role!r}")
    if not supplier_id:
        raise AssignmentError("a supplier must be chosen")

    existing = c.execute(
        "SELECT id, status FROM enterprise_site_assignments "
        "WHERE tenant_id = ? AND site_id = ? AND party_role = ? AND supplier_id = ?",
        (tenant_id, site_id, party_role, supplier_id)).fetchone()
    if existing:
        # Re-shortlisting someone previously withdrawn is legitimate; re-shortlisting an
        # active assignment is a mistake, and silently doing nothing would hide it.
        if existing[1] == WITHDRAWN:
            c.execute(
                "UPDATE enterprise_site_assignments SET status = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
                (SHORTLISTED, tenant_id, existing[0]))
            return int(existing[0])
        raise AssignmentError(
            f"that company is already {existing[1]} as {party_role} for this site")

    c.execute(
        "INSERT INTO enterprise_site_assignments "
        "(tenant_id, programme_id, site_id, party_role, supplier_id, supplier_name, "
        " scope_note, status, created_by_user_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (tenant_id, programme_id, site_id, party_role, supplier_id, supplier_name or "",
         scope_note or "", SHORTLISTED, user_id))
    row = c.execute(
        "SELECT id FROM enterprise_site_assignments "
        "WHERE tenant_id = ? AND site_id = ? AND party_role = ? AND supplier_id = ?",
        (tenant_id, site_id, party_role, supplier_id)).fetchone()
    return int(row[0])


def _move(c, tenant_id: str, assignment_id: int, to_status: str) -> dict:
    """Move one assignment, refusing a move the lifecycle does not allow."""
    row = c.execute(
        "SELECT status, party_role, site_id FROM enterprise_site_assignments "
        "WHERE tenant_id = ? AND id = ?", (tenant_id, assignment_id)).fetchone()
    if not row:
        raise AssignmentError("no such assignment")
    current = row[0]
    if to_status not in ALLOWED_TRANSITIONS.get(current, ()):
        raise AssignmentError(
            f"cannot go from {current} to {to_status}"
            + (" -- a signed contract is ended commercially, not by editing its status"
               if current == SIGNED else ""))
    return {"status": current, "party_role": row[1], "site_id": row[2]}


def award(c, tenant_id: str, assignment_id: int, *, response_id: int | None = None,
          rfq_id: int | None = None, price=None, currency: str = "",
          lead_time_days: int | None = None) -> None:
    """Choose this company for the site, recording the bid it won on.

    ONE AWARD PER ROLE PER SITE. Two awarded installers on one site is not a richer record,
    it is an unanswerable question -- so awarding a second one is refused rather than
    silently allowed. Withdraw the first if the decision has changed.

    The price is COPIED from the bid, not referenced. A quote is a point-in-time commitment:
    if the supplier revises their standing prices next month, what they were awarded must not
    change with it.
    """
    ctx = _move(c, tenant_id, assignment_id, AWARDED)

    clash = c.execute(
        "SELECT supplier_name FROM enterprise_site_assignments "
        "WHERE tenant_id = ? AND site_id = ? AND party_role = ? AND id <> ? "
        "AND status IN (?, ?)",
        (tenant_id, ctx["site_id"], ctx["party_role"], assignment_id,
         AWARDED, SIGNED)).fetchone()
    if clash:
        raise AssignmentError(
            f"this site already has an awarded {ctx['party_role']}"
            f"{' (' + clash[0] + ')' if clash[0] else ''} -- withdraw that one first")

    c.execute(
        "UPDATE enterprise_site_assignments SET status = ?, source_response_id = ?, "
        "source_rfq_id = ?, awarded_price = ?, awarded_currency = ?, lead_time_days = ?, "
        "awarded_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
        "WHERE tenant_id = ? AND id = ?",
        (AWARDED, response_id, rfq_id, price, currency or "", lead_time_days,
         tenant_id, assignment_id))


def sign(c, tenant_id: str, assignment_id: int) -> None:
    """Record that the contract is signed. Only an awarded company can be signed."""
    _move(c, tenant_id, assignment_id, SIGNED)
    c.execute(
        "UPDATE enterprise_site_assignments SET status = ?, "
        "signed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP "
        "WHERE tenant_id = ? AND id = ?", (SIGNED, tenant_id, assignment_id))


def withdraw(c, tenant_id: str, assignment_id: int) -> None:
    """Take a company out of the running. The row survives -- who was considered is part of
    the procurement record, and deleting it is how that record disappears."""
    _move(c, tenant_id, assignment_id, WITHDRAWN)
    c.execute(
        "UPDATE enterprise_site_assignments SET status = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE tenant_id = ? AND id = ?",
        (WITHDRAWN, tenant_id, assignment_id))


# --- reading ------------------------------------------------------------------

def for_site(c, tenant_id: str, site_id: int) -> list[dict]:
    """Everyone attached to this site, signed first."""
    rows = c.execute(
        "SELECT id, party_role, supplier_id, supplier_name, status, awarded_price, "
        "       awarded_currency, lead_time_days, source_rfq_id, source_response_id, "
        "       scope_note, awarded_at, signed_at "
        "FROM enterprise_site_assignments WHERE tenant_id = ? AND site_id = ? "
        "ORDER BY CASE status WHEN 'signed' THEN 0 WHEN 'awarded' THEN 1 "
        "                     WHEN 'shortlisted' THEN 2 ELSE 3 END, supplier_name",
        (tenant_id, site_id)).fetchall()
    keys = ("id", "party_role", "supplier_id", "supplier_name", "status", "awarded_price",
            "awarded_currency", "lead_time_days", "source_rfq_id", "source_response_id",
            "scope_note", "awarded_at", "signed_at")
    return [dict(zip(keys, r)) for r in rows]


def coverage(c, tenant_id: str, programme_id: int) -> dict:
    """How much of the programme actually has a contractor.

    The number a planner is asked for is not "how many assignments exist" but "how many sites
    are still without an installer" -- so that is what this answers.
    """
    sites = c.execute(
        "SELECT COUNT(*) FROM enterprise_sites WHERE tenant_id = ? AND programme_id = ?",
        (tenant_id, programme_id)).fetchone()[0] or 0

    def _covered(role):
        return c.execute(
            "SELECT COUNT(DISTINCT site_id) FROM enterprise_site_assignments "
            "WHERE tenant_id = ? AND programme_id = ? AND party_role = ? "
            "AND status IN (?, ?)",
            (tenant_id, programme_id, role, AWARDED, SIGNED)).fetchone()[0] or 0

    installers, suppliers_ = _covered(INSTALLER), _covered(SUPPLIER)
    return {"sites": sites,
            "sites_with_installer": installers,
            "sites_with_supplier": suppliers_,
            "sites_without_installer": max(0, sites - installers),
            "signed": c.execute(
                "SELECT COUNT(*) FROM enterprise_site_assignments "
                "WHERE tenant_id = ? AND programme_id = ? AND status = ?",
                (tenant_id, programme_id, SIGNED)).fetchone()[0] or 0}


__all__ = ["AssignmentError", "INSTALLER", "SUPPLIER", "PARTY_ROLES",
           "SHORTLISTED", "AWARDED", "SIGNED", "WITHDRAWN", "STATUSES",
           "ALLOWED_TRANSITIONS", "ensure_schema", "qualified_suppliers",
           "bids_for_supplier", "shortlist", "award", "sign", "withdraw",
           "for_site", "coverage"]
