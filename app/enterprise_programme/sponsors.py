"""A programme's FIRST, SECOND and THIRD sponsor -- chosen from the EXISTING funding registry.

OWNER, 2026-07-14:
  "potential sponsors must be registered in the system and programme can select them from a
   drop down list, there must be first sponsor, second sponsor and third, each case a drop
   down list of potential sponsors must be selected from dropdown list"
  ...and then, decisively:
  "look, check and reuse the funding in the standard design and reuse"

THIS MODULE OWNS NO TABLE. THAT IS THE POINT.
---------------------------------------------
The register already exists. `financial_institutions` -- the Project Funding module, shipped
2026-07-05 -- is a platform-wide registry of funders with an `approved` status gate, and it
already carries what a programme actually needs to know about a sponsor: loan_min, loan_max,
tenor_months, interest_min/max, fee_pct, supported_project_types.

An `enterprise_sponsors` table was written for this and then deleted before it shipped. It
would have been a poorer copy -- and worse, the two would have DRIFTED: an institution
approved in one register and unknown in the other, and an operator with no way to tell which
list was real. Reusing the registry is not a shortcut; it is the only version that stays true.

It is also what makes the feasibility study possible at all. "Determine if the bill can fund
the programme" is answerable precisely BECAUSE financial_institutions records loan_min and
loan_max. A hand-rolled sponsor table would have had to invent those columns, and they would
have been empty.

A SPONSOR IS AN INSTITUTION. IT IS NOT `sponsor_user_id`.
---------------------------------------------------------
The registry already has `sponsor_user_id`: the PERSON who holds the `programme_sponsor` post
and signs Gate 1 (control C01, the named post holder). Untouched. Conflating the two would
have the app asking a development bank to sign a stage gate.

THE PRELIMINARY SPONSOR LETTER IS A DOCUMENT, NOT A FLAG.
---------------------------------------------------------
A boolean would let a programme CLAIM a letter it does not hold -- and whether that letter
exists is exactly what the feasibility study is asked to determine. A claim is not evidence,
so this asks the documents table for the row.
"""

from __future__ import annotations

from . import rbac, txn

# The doc_type a preliminary sponsor letter is stored under in `enterprise_documents`.
PRELIMINARY_LETTER_DOC_TYPE = "preliminary_sponsor_letter"

# The three slots, in the owner's order.
SPONSOR_SLOTS: tuple[tuple[str, str], ...] = (
    ("sponsor_1_id", "First sponsor"),
    ("sponsor_2_id", "Second sponsor"),
    ("sponsor_3_id", "Third sponsor"),
)
SPONSOR_SLOT_COLUMNS = tuple(col for col, _label in SPONSOR_SLOTS)


class SponsorError(Exception):
    """A sponsor action was refused for a reason the operator can act on."""

    def __init__(self, control: str, message: str):
        super().__init__(message)
        self.control = control


def ensure_schema(c) -> None:
    """Add the three slots on SQLite. No-op on Postgres (migration 030 owns them).

    NO TABLE IS CREATED. `financial_institutions` belongs to the Project Funding module and is
    created by ITS `_ensure_fi_schema()`. Creating it here as well would give one table two
    owners and two definitions -- the exact drift this module exists to avoid.
    """
    if txn.is_postgres():
        return

    # Added by INSPECTION, not by hope: CREATE TABLE IF NOT EXISTS never widens a table that
    # already exists, and this project has been bitten by exactly that before
    # ([[feedback-solar-create-if-not-exists-schema-drift]]).
    have = {r[1] for r in c.execute(
        "PRAGMA table_info(enterprise_programme_registry)").fetchall()}
    for col in SPONSOR_SLOT_COLUMNS:
        if col not in have:
            c.execute(f"ALTER TABLE enterprise_programme_registry ADD COLUMN {col} TEXT")


# ---------------------------------------------------------------------------
# the register -- READ from the funding module, never written here
# ---------------------------------------------------------------------------

def approved_sponsors(c) -> list[dict]:
    """Every APPROVED funding institution, for the dropdowns.

    Output: [{institution_id, name, inst_type, country, loan_min, loan_max, ...}], by name.

    ONLY `approved` ONES. The funding registry has a `pending` state, and an institution that
    the platform has not vetted has no business appearing in a ministry's list of sponsors.
    This is the same filter the Project Funding module applies (`_ci_funding_institutions`).

    Returns [] rather than raising when the table does not exist yet -- the Project Funding
    module creates it lazily at first use, so on a fresh database it may genuinely not be
    there, and an empty dropdown is a truer answer than a 500.
    """
    try:
        rows = c.execute(
            "SELECT institution_id, name, inst_type, country, region, "
            "       loan_min, loan_max, tenor_months, interest_min, interest_max, fee_pct "
            "  FROM financial_institutions WHERE status='approved' ORDER BY name"
        ).fetchall()
    except Exception:
        return []

    return [
        {"institution_id": r[0], "name": r[1], "inst_type": r[2], "country": r[3],
         "region": r[4], "loan_min": r[5], "loan_max": r[6], "tenor_months": r[7],
         "interest_min": r[8], "interest_max": r[9], "fee_pct": r[10]}
        for r in rows
    ]


def get_sponsor(c, institution_id: str) -> dict | None:
    """One approved institution, or None. The registry is platform-wide, not tenant-scoped."""
    for s in approved_sponsors(c):
        if s["institution_id"] == institution_id:
            return s
    return None


def set_programme_sponsors(c, tenant_id: str, user_id: int, programme_id: int, *,
                           sponsor_1_id=None, sponsor_2_id=None, sponsor_3_id=None,
                           audit=None) -> None:
    """Name a programme's first, second and third sponsor from the approved registry.

    Input:  connection, tenant, acting user, programme, three institution ids (any may be
            blank, meaning "not named").
    Output: none.
    Raises: EnterprisePermissionError (403), SponsorError, EnterpriseGateError (C13 -> 404).

    EVERY ID IS CHECKED AGAINST THE APPROVED REGISTRY. They arrive from a form, and a form is
    a request, not a fact: a hand-rolled POST naming a `pending` institution -- one the
    platform has not vetted -- would otherwise write it straight onto the programme and print
    it on the feasibility study as a sponsor.
    """
    from . import workflows
    workflows._load_programme(c, tenant_id, programme_id)            # C13 FIRST
    rbac.require_permission(c, tenant_id, user_id, "programme.edit",
                            programme_id=programme_id)

    chosen = [_slot(sponsor_1_id), _slot(sponsor_2_id), _slot(sponsor_3_id)]

    approved = {s["institution_id"] for s in approved_sponsors(c)}
    for sid in chosen:
        if sid is not None and sid not in approved:
            raise SponsorError(
                "SPONSOR",
                f"“{sid}” is not an approved funding institution — pick one from the list",
            )

    named = [s for s in chosen if s is not None]
    if len(named) != len(set(named)):
        # The same institution as both first and second sponsor is not a preference order; it
        # is a mistake, and it would make the feasibility study count its capacity twice.
        raise SponsorError(
            "SPONSOR",
            "the same institution is named in more than one slot — first, second and third "
            "must be different",
        )

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        c.execute(
            "UPDATE enterprise_programme_registry "
            "   SET sponsor_1_id=?, sponsor_2_id=?, sponsor_3_id=? "
            " WHERE tenant_id=? AND id=?",
            (chosen[0], chosen[1], chosen[2], tenant_id, programme_id),
        )
        if not audit("ENTERPRISE_PROGRAMME_SPONSORS_SET", user_id=user_id,
                     tenant_id=tenant_id,
                     details={"programme_id": programme_id,
                              "sponsor_1_id": chosen[0], "sponsor_2_id": chosen[1],
                              "sponsor_3_id": chosen[2]}):
            # C12 -- audit or nothing.
            raise SponsorError(
                "C12",
                "the sponsors were not saved, because the audit record could not be written")


def programme_sponsors(c, tenant_id: str, programme_id: int) -> list[dict]:
    """The programme's three sponsors, in order, resolved against the registry.

    Output: [{slot, slot_label, institution_id, sponsor}] -- `sponsor` is None for an unnamed
            slot, so the screen renders all three rows without deciding which are missing.

    A sponsor named earlier and since UN-APPROVED resolves to None with its id retained, so
    the screen can say so rather than silently dropping an institution the programme believes
    it has.
    """
    row = c.execute(
        "SELECT sponsor_1_id, sponsor_2_id, sponsor_3_id "
        "  FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    if not row:
        raise SponsorError("C13", "no such programme in this organisation")

    by_id = {s["institution_id"]: s for s in approved_sponsors(c)}
    out = []
    for i, (col, label) in enumerate(SPONSOR_SLOTS):
        sid = row[i]
        out.append({"slot": col, "slot_label": label,
                    "institution_id": sid,
                    "sponsor": by_id.get(sid) if sid else None})
    return out


def has_preliminary_letter(c, tenant_id: str, programme_id: int) -> dict:
    """Does the programme HOLD a preliminary sponsor letter? Ask the documents table.

    Output: {"found": bool, "document_id": int | None, "title": str | None}.

    The owner asked the feasibility study to "determine if there is a preliminary sponsor
    letter from the sponsor". So it must find a real uploaded document. A checkbox somebody
    ticked is a claim, and the study exists to check claims.
    """
    r = c.execute(
        "SELECT id, title FROM enterprise_documents "
        " WHERE tenant_id=? AND programme_id=? AND doc_type=? "
        " ORDER BY id DESC LIMIT 1",
        (tenant_id, programme_id, PRELIMINARY_LETTER_DOC_TYPE),
    ).fetchone()
    if not r:
        return {"found": False, "document_id": None, "title": None}
    return {"found": True, "document_id": r[0], "title": r[1]}


# ---------------------------------------------------------------------------

def _slot(v):
    """A form field to an institution id. "" means NOT NAMED."""
    s = (v or "").strip() if isinstance(v, str) else v
    return s or None
