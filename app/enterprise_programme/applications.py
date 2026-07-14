"""BENEFICIARY APPLICATIONS -- submitted through the organisation, approved at three levels.

OWNER, 2026-07-14:
  "we don't need to do proving to any entity rather the beneficiaries must register for the
   program and track progress from when they submit app to when their approved"
  "the users of the beneficiary must register via their organisation platform and
   applications must be submitted through the organisation. the first level of application is
   the beneficiary organisation, the programme level approval and finally sponsor level
   approval"
  "all approvals must be set by the individual approving entities"
  "check my bill must be run for each user automatically after their application to make sure
   they can pay load"

THE CHAIN
---------
    beneficiary user submits
            |   (through their ORGANISATION -- never straight to the programme)
            v
      L1  the beneficiary organisation approves
            v
      L2  the programme approves
            v
      L3  the sponsor approves            <- final

EACH ENTITY APPROVES FOR ITSELF, AND ONLY FOR ITSELF.
-----------------------------------------------------
This is the rule the whole module turns on, and it is the OPPOSITE of the stage-gate owner
override (commit 5417e53, where the owner may sign a gate in another post's place). That
override is scoped to stage gates and does not reach here.

A chain in which one party can set all three levels is not a chain -- it is one signature
wearing three hats. A sponsor who later asks "did the beneficiary organisation actually vouch
for this applicant?" would get an answer that means nothing. So:

  * L1 is settable ONLY by a member of the applicant's own beneficiary organisation.
  * L2 is settable ONLY by a member of the programme's organisation.
  * L3 is settable ONLY by a user linked to a sponsor the programme has actually named.

...and the levels are STRICTLY ORDERED. The programme cannot approve an applicant the
beneficiary organisation has not yet vouched for; the sponsor cannot approve one the programme
has not. Skipping a level would let the last signature be collected first and the earlier ones
rubber-stamped afterwards, which is how approval chains rot.

THE BILL CHECK IS EVIDENCE, NOT A GATE.
---------------------------------------
Check-My-Bill runs automatically on submission and its result is attached. An applicant whose
bill cannot carry the load is FLAGGED for the level-1 reviewer, not rejected: an unaffordable
bill today is very often exactly who a subsidised solar programme exists to reach. Deciding is
the organisation's job; the app's job is to tell them.

It calls web_app's own `_bc_compute` / `_bc_funding_model` -- the same engine behind
/bill-check. A programme applicant and a retail walk-in with the same bill must get the same
answer, or the number means nothing.
"""

from __future__ import annotations

import json

from . import rbac, txn

# The chain, in order. The names are the owner's.
LEVELS: tuple[tuple[int, str, str], ...] = (
    (1, "organisation", "Beneficiary organisation"),
    (2, "programme",    "Programme"),
    (3, "sponsor",      "Sponsor"),
)
LEVEL_LABELS = {n: label for n, _key, label in LEVELS}

# An application's own status, derived from the levels -- never set by a caller. Two views of
# one truth drift the moment a caller can set both (the same reasoning as programme status,
# which is derived from the phase).
STATUS_SUBMITTED = "Submitted"
STATUS_L1 = "Organisation approved"
STATUS_L2 = "Programme approved"
STATUS_APPROVED = "Approved"
STATUS_RETURNED = "Returned for more information"
STATUS_REJECTED = "Rejected"

DECISION_APPROVED = "Approved"
DECISION_RETURNED = "Returned"
DECISION_REJECTED = "Rejected"
DECISIONS = (DECISION_APPROVED, DECISION_RETURNED, DECISION_REJECTED)


class ApplicationError(Exception):
    """An application action was refused for a reason the operator can act on."""

    def __init__(self, control: str, message: str):
        super().__init__(message)
        self.control = control


_SQLITE_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS enterprise_applications (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        -- The PROGRAMME's tenant. The application lives with the programme it is for.
        tenant_id              TEXT NOT NULL,
        programme_id           INTEGER NOT NULL,
        -- The applicant, and the organisation they belong to. `applicant_org_tenant_id` is
        -- what makes level 1 answerable: it names WHICH organisation must vouch for them.
        applicant_user_id      INTEGER NOT NULL,
        applicant_org_tenant_id TEXT NOT NULL,

        site_name              TEXT NOT NULL,
        contact_email          TEXT,
        contact_phone          TEXT,
        country                TEXT,
        region                 TEXT,
        -- What they pay now. The bill check runs on these.
        monthly_bill           REAL,
        monthly_kwh            REAL,
        tariff_category        TEXT,
        -- "checks for area" (owner). Roof/ground area available, m2.
        area_m2                REAL,

        bill_check_json        TEXT,
        affordable             INTEGER,          -- 1 / 0 / NULL (not computed)

        status                 TEXT NOT NULL DEFAULT 'Submitted',

        l1_decision            TEXT,
        l1_by_user_id          INTEGER,
        l1_at                  TEXT,
        l1_note                TEXT,
        l2_decision            TEXT,
        l2_by_user_id          INTEGER,
        l2_at                  TEXT,
        l2_note                TEXT,
        l3_decision            TEXT,
        l3_by_user_id          INTEGER,
        l3_at                  TEXT,
        l3_note                TEXT,
        l3_sponsor_id          TEXT,             -- WHICH sponsor signed

        created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_app_programme "
    "  ON enterprise_applications (tenant_id, programme_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_ent_app_applicant "
    "  ON enterprise_applications (applicant_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_ent_app_org "
    "  ON enterprise_applications (applicant_org_tenant_id, status)",
    # WHO MAY SIGN FOR A SPONSOR. The funding registry (financial_institutions) holds contact
    # details, not logins -- so a sponsor's contact person is invited as a user and linked
    # here. Without this table "the sponsor approves" has no subject, and level 3 would have
    # to be set by somebody else on their behalf, which is the one thing the owner forbade.
    """
    CREATE TABLE IF NOT EXISTS enterprise_sponsor_users (
        institution_id  TEXT NOT NULL,
        user_id         INTEGER NOT NULL,
        added_by_user_id INTEGER,
        created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (institution_id, user_id)
    )
    """,
)


def ensure_schema(c) -> None:
    """Create the application tables on SQLite. No-op on Postgres (migration 031 owns them)."""
    if txn.is_postgres():
        return
    for stmt in _SQLITE_SCHEMA:
        c.execute(stmt)


# ---------------------------------------------------------------------------
# submitting
# ---------------------------------------------------------------------------

def submit_application(c, tenant_id: str, programme_id: int, *,
                       applicant_user_id: int, applicant_org_tenant_id: str,
                       site_name: str, contact_email: str = "", contact_phone: str = "",
                       country: str = "", region: str = "",
                       monthly_bill=None, monthly_kwh=None, tariff_category: str = "",
                       area_m2=None, audit=None) -> int:
    """A beneficiary user applies to a programme, through their organisation.

    Input:  connection, the PROGRAMME's tenant, the programme, the applicant and the
            organisation they belong to, and what they pay now.
    Output: the new application's id.
    Raises: ApplicationError.

    THE ORGANISATION IS NOT OPTIONAL. "applications must be submitted through the
    organisation" -- an application with no organisation has nobody who can give it a level-1
    approval, so it could never be approved at all. Refusing it at submission is kinder than
    accepting it into a queue nobody is able to clear.

    The bill check runs here, automatically, and never fails the submission: an engine that is
    unavailable must not stop a school from applying. `affordable` is left NULL in that case,
    which is honestly "not computed" rather than dishonestly "no".
    """
    site_name = (site_name or "").strip()
    if not site_name:
        raise ApplicationError("APP", "the application needs a site or household name")
    if not (applicant_org_tenant_id or "").strip():
        raise ApplicationError(
            "APP",
            "an application must be submitted through a beneficiary organisation — without "
            "one there is nobody who can give it its first approval",
        )

    bill_json, affordable = _run_bill_check(
        monthly_bill=monthly_bill, monthly_kwh=monthly_kwh,
        tariff_category=tariff_category, country=country, region=region)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        cur = c.execute(
            "INSERT INTO enterprise_applications "
            "(tenant_id, programme_id, applicant_user_id, applicant_org_tenant_id, "
            " site_name, contact_email, contact_phone, country, region, "
            " monthly_bill, monthly_kwh, tariff_category, area_m2, "
            " bill_check_json, affordable, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tenant_id, programme_id, applicant_user_id, applicant_org_tenant_id,
             site_name, (contact_email or "").strip() or None,
             (contact_phone or "").strip() or None,
             (country or "").strip() or None, (region or "").strip() or None,
             _num(monthly_bill), _num(monthly_kwh),
             (tariff_category or "").strip() or None, _num(area_m2),
             bill_json, affordable, STATUS_SUBMITTED),
        )
        aid = int(txn.inserted_id(c, cur))

        if not audit("ENTERPRISE_APPLICATION_SUBMITTED",
                     user_id=applicant_user_id, tenant_id=tenant_id,
                     details={"application_id": aid, "programme_id": programme_id,
                              "org_tenant_id": applicant_org_tenant_id,
                              "site_name": site_name, "affordable": affordable}):
            raise ApplicationError(
                "C12",
                "the application was not saved, because its audit record could not be written")
    return aid


def _run_bill_check(*, monthly_bill, monthly_kwh, tariff_category, country, region):
    """Run Check-My-Bill for this applicant. Returns (json_or_None, affordable_or_None).

    REUSES web_app's `_bc_compute` / `_bc_funding_model` -- the engine behind /bill-check. A
    programme applicant and a retail walk-in with the same bill must get the same answer, or
    the number means nothing to anybody.

    NEVER RAISES. The bill check is evidence for a human reviewer, not a precondition of
    applying; an engine that is down must not stop a school from submitting. When it cannot
    run, `affordable` is None -- "not computed", which is the truth, rather than False, which
    would be an accusation.
    """
    bill = _num(monthly_bill)
    kwh = _num(monthly_kwh)
    if not bill and not kwh:
        return None, None            # nothing to compute from; not a failure

    try:
        import web_app
        payload = {
            "actual_bill": bill or 0,
            "actual_kwh": kwh,
            "category": tariff_category or "Residential Standard (0-300 kWh/month)",
        }
        sd = web_app.get_solar_data(country, region) or {} if country else {}
        if sd.get("psh"):
            payload["peak_sun_hours"] = sd["psh"]

        result = web_app._bc_compute(payload)
        result["funding"] = web_app._bc_funding_model(result)
    except Exception:
        return None, None

    # CAN THEY PAY THE LOAD? The funding model already answers it: during the loan the
    # applicant pays (what the grid still charges) + (the repayment). If that combined outlay
    # is no worse than the bill they pay today, the bill itself carries the system.
    affordable = None
    try:
        net_change_pct = float((result.get("funding") or {}).get("net_change_pct"))
        affordable = 1 if net_change_pct <= 0 else 0
    except (TypeError, ValueError):
        affordable = None

    return json.dumps(result), affordable


# ---------------------------------------------------------------------------
# the three levels
# ---------------------------------------------------------------------------

def decide(c, tenant_id: str, user_id: int, application_id: int, *,
           level: int, decision: str, note: str = "", audit=None) -> dict:
    """One entity sets ITS OWN approval. Nobody sets anybody else's.

    Input:  connection, the PROGRAMME's tenant, the acting user, the application, which LEVEL
            they are signing, the decision, an optional note.
    Output: the application, refreshed.
    Raises: EnterprisePermissionError (403), ApplicationError (C13 -> 404, or a refusal).

    The authority for each level is checked against a DIFFERENT entity -- see
    `_require_authority_for_level`. That function is the module.
    """
    if level not in (1, 2, 3):
        raise ApplicationError("APP", f"no such approval level: {level}")
    if decision not in DECISIONS:
        raise ApplicationError("APP", f"no such decision: {decision}")

    app = get_application(c, tenant_id, application_id)         # C13

    _require_authority_for_level(c, tenant_id, user_id, app, level)
    _require_previous_levels_passed(app, level)

    if app[f"l{level}_decision"]:
        raise ApplicationError(
            "APP",
            f"{LEVEL_LABELS[level]} has already decided this application "
            f"({app[f'l{level}_decision']})",
        )

    sponsor_id = app["sponsor_can_sign"] if level == 3 else None

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        c.execute(
            f"UPDATE enterprise_applications "
            f"   SET l{level}_decision=?, l{level}_by_user_id=?, "
            f"       l{level}_at=CURRENT_TIMESTAMP, l{level}_note=? "
            f" WHERE tenant_id=? AND id=?",
            (decision, user_id, (note or "").strip() or None, tenant_id, application_id),
        )
        if level == 3 and sponsor_id:
            c.execute(
                "UPDATE enterprise_applications SET l3_sponsor_id=? "
                " WHERE tenant_id=? AND id=?",
                (sponsor_id, tenant_id, application_id),
            )

        fresh = get_application(c, tenant_id, application_id)
        status = _derive_status(fresh)
        c.execute(
            "UPDATE enterprise_applications SET status=? WHERE tenant_id=? AND id=?",
            (status, tenant_id, application_id),
        )

        if not audit("ENTERPRISE_APPLICATION_DECIDED", user_id=user_id, tenant_id=tenant_id,
                     details={"application_id": application_id,
                              "programme_id": app["programme_id"],
                              "level": level, "level_name": LEVEL_LABELS[level],
                              "decision": decision, "status": status,
                              "sponsor_id": sponsor_id}):
            raise ApplicationError(
                "C12",
                "the decision was not saved, because its audit record could not be written")

    return get_application(c, tenant_id, application_id)


def _require_authority_for_level(c, tenant_id: str, user_id: int, app: dict,
                                 level: int) -> None:
    """Only the entity whose level it is may set it. This function IS the owner's rule.

    L1 -- a member of the APPLICANT'S OWN beneficiary organisation. Not the programme's.
    L2 -- a member of the PROGRAMME's organisation, holding `programme.edit`.
    L3 -- a user LINKED to a sponsor the programme has actually named.

    There is deliberately no owner override here. The stage-gate override (5417e53) lets the
    owner sign a gate in another POST's place -- posts inside one organisation. These are
    three DIFFERENT ORGANISATIONS, and an owner who could sign for all three would be
    producing a chain of one signature wearing three hats.
    """
    if level == 1:
        org = app["applicant_org_tenant_id"]
        # `programme.edit` WITHIN THE BENEFICIARY ORGANISATION'S OWN TENANT. Passing the
        # programme's tenant here instead would let programme staff -- who hold that
        # permission on the programme -- approve on the organisation's behalf, which is the
        # exact confusion this whole function exists to prevent.
        rbac.require_permission(c, org, user_id, "programme.edit")
        return

    if level == 2:
        rbac.require_permission(c, tenant_id, user_id, "programme.edit",
                                programme_id=app["programme_id"])
        return

    # level 3 -- the sponsor.
    sponsor_id = _sponsor_the_user_may_sign_for(c, tenant_id, user_id, app["programme_id"])
    if not sponsor_id:
        raise rbac.EnterprisePermissionError(
            "C11",
            "only a sponsor named on this programme may give the final approval",
        )
    app["sponsor_can_sign"] = sponsor_id


def _sponsor_the_user_may_sign_for(c, tenant_id: str, user_id: int,
                                   programme_id: int) -> str | None:
    """Which of the programme's named sponsors, if any, this user may sign for.

    A user linked to an institution that this programme has NOT named is a sponsor -- of some
    other programme. They may not sign here.
    """
    from . import sponsors

    try:
        named = {s["institution_id"]
                 for s in sponsors.programme_sponsors(c, tenant_id, programme_id)
                 if s.get("institution_id")}
    except Exception:
        return None
    if not named:
        return None

    try:
        rows = c.execute(
            "SELECT institution_id FROM enterprise_sponsor_users WHERE user_id=?",
            (user_id,),
        ).fetchall()
    except Exception:
        return None

    for r in rows:
        if r[0] in named:
            return r[0]
    return None


def _require_previous_levels_passed(app: dict, level: int) -> None:
    """The chain is ORDERED. Level 3 cannot sign what level 1 has not.

    Without this the last signature could be collected first and the earlier ones
    rubber-stamped afterwards -- which is how an approval chain becomes a formality.
    """
    for earlier in range(1, level):
        d = app[f"l{earlier}_decision"]
        if d != DECISION_APPROVED:
            raise ApplicationError(
                "APP",
                f"{LEVEL_LABELS[level]} cannot decide this yet — "
                f"{LEVEL_LABELS[earlier]} has "
                + (f"{d.lower()} it" if d else "not decided it yet"),
            )


def _derive_status(app: dict) -> str:
    """The application's status, DERIVED from the three levels. Never set by a caller.

    Two views of one truth drift the moment a caller can set both -- the same reasoning that
    keeps programme status derived from its phase.
    """
    for n in (1, 2, 3):
        d = app[f"l{n}_decision"]
        if d == DECISION_REJECTED:
            return STATUS_REJECTED
        if d == DECISION_RETURNED:
            return STATUS_RETURNED
        if d != DECISION_APPROVED:
            break

    if app["l3_decision"] == DECISION_APPROVED:
        return STATUS_APPROVED
    if app["l2_decision"] == DECISION_APPROVED:
        return STATUS_L2
    if app["l1_decision"] == DECISION_APPROVED:
        return STATUS_L1
    return STATUS_SUBMITTED


# ---------------------------------------------------------------------------
# reading -- the applicant's tracker, and the reviewers' queues
# ---------------------------------------------------------------------------

_COLS = (
    "id, tenant_id, programme_id, applicant_user_id, applicant_org_tenant_id, "
    "site_name, contact_email, contact_phone, country, region, monthly_bill, monthly_kwh, "
    "tariff_category, area_m2, bill_check_json, affordable, status, "
    "l1_decision, l1_by_user_id, l1_at, l1_note, "
    "l2_decision, l2_by_user_id, l2_at, l2_note, "
    "l3_decision, l3_by_user_id, l3_at, l3_note, l3_sponsor_id, created_at"
)
_KEYS = [k.strip() for k in _COLS.split(",")]


def get_application(c, tenant_id: str, application_id: int) -> dict:
    """One application. C13: another organisation's application does not exist."""
    r = c.execute(
        f"SELECT {_COLS} FROM enterprise_applications WHERE tenant_id=? AND id=?",
        (tenant_id, application_id),
    ).fetchone()
    if not r:
        raise ApplicationError("C13", "no such application in this organisation")
    return dict(zip(_KEYS, r))


def track(c, application_id: int, applicant_user_id: int) -> dict:
    """What the APPLICANT sees: where their application is, and what happens next.

    Input:  connection, the application, and the user asking.
    Output: {application, steps: [{level, label, state, at, note}], next}.
    Raises: ApplicationError (C13) when it is not theirs.

    SCOPED TO THE APPLICANT, not to a tenant. This is the one read in the module that a
    beneficiary user makes about their OWN row, and they are not a member of the programme's
    organisation -- so a tenant-scoped read would deny them their own application. It is keyed
    on `applicant_user_id` instead, which is exactly as tight.
    """
    r = c.execute(
        f"SELECT {_COLS} FROM enterprise_applications "
        f" WHERE id=? AND applicant_user_id=?",
        (application_id, applicant_user_id),
    ).fetchone()
    if not r:
        raise ApplicationError("C13", "no such application")
    app = dict(zip(_KEYS, r))

    steps = []
    for n, _key, label in LEVELS:
        d = app[f"l{n}_decision"]
        if d == DECISION_APPROVED:
            state = "approved"
        elif d in (DECISION_RETURNED, DECISION_REJECTED):
            state = d.lower()
        elif all(app[f"l{e}_decision"] == DECISION_APPROVED for e in range(1, n)):
            state = "waiting"          # this one is the ball
        else:
            state = "pending"          # not its turn yet
        steps.append({"level": n, "label": label, "state": state,
                      "at": app[f"l{n}_at"], "note": app[f"l{n}_note"]})

    nxt = next((s["label"] for s in steps if s["state"] == "waiting"), None)
    return {"application": app, "steps": steps, "next_with": nxt}


def my_applications(c, applicant_user_id: int) -> list[dict]:
    """Every application this beneficiary user has submitted."""
    rows = c.execute(
        f"SELECT {_COLS} FROM enterprise_applications "
        f" WHERE applicant_user_id=? ORDER BY id DESC",
        (applicant_user_id,),
    ).fetchall()
    return [dict(zip(_KEYS, r)) for r in rows]


def inbox(c, *, level: int, tenant_id: str = "", org_tenant_id: str = "",
          programme_id: int | None = None) -> list[dict]:
    """The applications waiting on ONE entity -- the queue a reviewer actually clears.

    L1: pass `org_tenant_id`  -- the beneficiary organisation's own queue.
    L2: pass `tenant_id` (the programme's) and optionally `programme_id`.
    L3: pass `tenant_id` (the programme's) and optionally `programme_id`.

    Only applications whose EARLIER levels have all approved are returned. A reviewer's queue
    should contain only what they can actually act on; showing them work that is blocked on
    somebody else is how a queue stops being read.
    """
    where = ["l%d_decision IS NULL" % level]
    params: list = []

    for earlier in range(1, level):
        where.append(f"l{earlier}_decision = ?")
        params.append(DECISION_APPROVED)

    if level == 1:
        if not org_tenant_id:
            raise ApplicationError("APP", "the organisation's inbox needs its tenant id")
        where.append("applicant_org_tenant_id = ?")
        params.append(org_tenant_id)
    else:
        if not tenant_id:
            raise ApplicationError("APP", "this inbox needs the programme's tenant id")
        where.append("tenant_id = ?")
        params.append(tenant_id)

    if programme_id is not None:
        where.append("programme_id = ?")
        params.append(programme_id)

    rows = c.execute(
        f"SELECT {_COLS} FROM enterprise_applications "
        f" WHERE {' AND '.join(where)} ORDER BY id",
        tuple(params),
    ).fetchall()
    return [dict(zip(_KEYS, r)) for r in rows]


# ---------------------------------------------------------------------------

def link_sponsor_user(c, institution_id: str, user_id: int, added_by_user_id: int) -> None:
    """Let a person sign for a funding institution.

    The funding registry holds contact details, not logins. Level 3 says "the sponsor
    approves" -- this is what gives that sentence a subject. Without it somebody else would
    have to approve on the sponsor's behalf, which the owner explicitly forbade.
    """
    c.execute(
        "INSERT OR REPLACE INTO enterprise_sponsor_users "
        "(institution_id, user_id, added_by_user_id) VALUES (?,?,?)",
        (institution_id, user_id, added_by_user_id),
    )


def _num(v):
    """A form field to a number, or None. A blank box is not a zero."""
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
