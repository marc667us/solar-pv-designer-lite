"""Report versions and per-recipient responses (revision xx201 s42-s43).

WHAT THIS EXISTS FOR
--------------------
Before this, a generated report had no history and no recipients. It could not answer:
what was sent, what changed, who has replied, and is it actually accepted?

Two rules from the owner's revision drive everything here:

  * EACH RECIPIENT ANSWERS SEPARATELY (s42, verbatim: "Do not use only one general report
    response"). A beneficiary may accept while a sponsor asks for changes.
  * A REPORT IS ACCEPTED ONLY WHEN BOTH HAVE ACCEPTED (s24, s29, s35). One missing answer is
    not an acceptance, and never silently becomes one.

The second rule is why `overall_status` refuses to collapse the two answers into one field in
the database: a stored blended status can go stale the moment either side replies again, and a
report that LOOKS accepted while the sponsor has not accepted it is the kind of error that
ends a programme. The status is therefore DERIVED, every time, from the answers on record.

WHERE THIS SITS
---------------
Subordinate to `enterprise_documents`, which remains the current report (it holds the
markdown, the doc_type and the tenant/programme scoping). Versions are that document's
history; responses hang off the document and name the version they answered. Codex
(2026-07-18) was explicit that a parallel document table would be a second source of truth
for "what does this report say", and the two would drift.
"""

from __future__ import annotations

from . import txn

# The recipients. Exactly two, because the owner's workflow has exactly two external parties
# (xx201 s17): the beneficiary organisation and the sponsor institution.
BENEFICIARY = "beneficiary"
SPONSOR = "sponsor"
RECIPIENT_KINDS = (BENEFICIARY, SPONSOR)

# What a recipient may answer (xx201 s19).
ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"
MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
RESPONSES = (ACCEPTED, REJECTED, MODIFICATION_REQUESTED)

# What the report as a whole is (xx201 s43).
AWAITING_RESPONSES = "AWAITING_RESPONSES"
MODIFICATION_REQUIRED = "MODIFICATION_REQUIRED"
ACCEPTED_BY_BOTH = "ACCEPTED_BY_BOTH"
OVERALL_REJECTED = "REJECTED"


class ReportResponseError(Exception):
    """A response or version could not be recorded as asked."""


def ensure_schema(c) -> None:
    """Create the SQLite mirror. No-op on Postgres, where migration 034 owns the schema.

    Input:  open DB connection.
    Output: none.

    The mirror must track migration 034 closely or the test suite stops meaning anything --
    the suite runs on SQLite and production runs on Postgres, so a constraint that exists in
    only one of them is a constraint that is not really tested. The CHECKs, the UNIQUEs, the
    composite FKs and the indexes below are therefore the same as 034, not a looser
    SQLite-only approximation.

    IT IS NOT A COMPLETE MIRROR, and the gaps are named here rather than left for someone to
    discover (Codex, 2026-07-18):

      * `tenant_id REFERENCES enterprise_tenants(id)` on both tables is NOT mirrored. The
        tenants table is owned by `tenancy.ensure_schema`, and requiring it here would force
        every caller of this function to stand that up first for a constraint that protects
        against a case the app cannot reach -- tenant ids come from the session, not from
        user input. The COMPOSITE FKs, which are the ones that actually stop cross-tenant
        attachment, ARE mirrored and ARE tested.
      * RLS policies cannot be mirrored: SQLite has no row-level security. Tenant scoping is
        therefore tested here at the query layer only; the policies are production-only and
        are asserted by migration review, not by this suite.
    """
    if txn.is_postgres():
        return

    c.execute("""
        CREATE TABLE IF NOT EXISTS enterprise_document_versions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id          TEXT    NOT NULL,
            document_id        INTEGER NOT NULL,
            version_number     INTEGER NOT NULL,
            markdown           TEXT    NOT NULL,
            change_summary     TEXT    NOT NULL DEFAULT '',
            created_by_user_id INTEGER,
            created_at         TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            -- Mirrors 034's fk_docver_document. Without it the test database happily stores
            -- versions of documents that do not exist, and the documents -> versions ->
            -- responses cascade cannot be proven where the suite actually runs.
            FOREIGN KEY (tenant_id, document_id)
                REFERENCES enterprise_documents (tenant_id, id) ON DELETE CASCADE,
            UNIQUE (tenant_id, document_id, version_number),
            CHECK (version_number >= 1)
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS ix_ent_docver_document
            ON enterprise_document_versions (tenant_id, document_id, version_number DESC)
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS enterprise_report_responses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id       TEXT    NOT NULL,
            document_id     INTEGER NOT NULL,
            version_number  INTEGER NOT NULL,
            recipient_kind  TEXT    NOT NULL,
            recipient_name  TEXT    NOT NULL DEFAULT '',
            recipient_email TEXT    NOT NULL DEFAULT '',
            response        TEXT    NOT NULL,
            comments        TEXT    NOT NULL DEFAULT '',
            responded_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            -- Mirrors migration 034's fk_resp_version. SQLite only ENFORCES this when the
            -- connection sets `PRAGMA foreign_keys=ON`, which the tests now do -- declaring
            -- it here keeps the mirror an actual mirror rather than a looser approximation.
            FOREIGN KEY (tenant_id, document_id, version_number)
                REFERENCES enterprise_document_versions
                           (tenant_id, document_id, version_number) ON DELETE CASCADE,
            UNIQUE (tenant_id, document_id, version_number, recipient_kind),
            CHECK (recipient_kind IN ('beneficiary', 'sponsor')),
            CHECK (response IN ('ACCEPTED', 'REJECTED', 'MODIFICATION_REQUESTED'))
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS ix_ent_resp_document
            ON enterprise_report_responses (tenant_id, document_id, version_number)
    """)


# --- versions ---------------------------------------------------------------

def next_version_number(c, tenant_id: str, document_id: int) -> int:
    """The version number a new revision should take. 1 when there is no history yet."""
    row = c.execute(
        "SELECT MAX(version_number) FROM enterprise_document_versions "
        "WHERE tenant_id = ? AND document_id = ?",
        (tenant_id, document_id)).fetchone()
    return int((row[0] if row and row[0] else 0)) + 1


def save_version(c, tenant_id: str, document_id: int, markdown: str, *,
                 change_summary: str = "", user_id: int | None = None) -> int:
    """Record a new version of a report. Returns the version number assigned.

    Input:  tenant, the parent document, the markdown of THIS version, why it exists.
    Output: the new version number.

    Versions are append-only. A revision never overwrites the version a recipient already
    answered -- if it did, an acceptance would silently transfer to text the recipient never
    saw, which is the whole reason responses name their version.
    """
    if not (markdown or "").strip():
        raise ReportResponseError("a version must have content")

    number = next_version_number(c, tenant_id, document_id)
    c.execute(
        "INSERT INTO enterprise_document_versions "
        "(tenant_id, document_id, version_number, markdown, change_summary, "
        " created_by_user_id) VALUES (?,?,?,?,?,?)",
        (tenant_id, document_id, number, markdown, change_summary or "", user_id))
    return number


def list_versions(c, tenant_id: str, document_id: int) -> list[dict]:
    """Every version of a report, newest first."""
    rows = c.execute(
        "SELECT version_number, change_summary, created_by_user_id, created_at "
        "FROM enterprise_document_versions "
        "WHERE tenant_id = ? AND document_id = ? "
        "ORDER BY version_number DESC",
        (tenant_id, document_id)).fetchall()
    return [{"version_number": r[0], "change_summary": r[1] or "",
             "created_by_user_id": r[2], "created_at": r[3]} for r in rows]


def get_version(c, tenant_id: str, document_id: int, version_number: int) -> dict | None:
    """One version's stored markdown, or None."""
    row = c.execute(
        "SELECT version_number, markdown, change_summary, created_at "
        "FROM enterprise_document_versions "
        "WHERE tenant_id = ? AND document_id = ? AND version_number = ?",
        (tenant_id, document_id, version_number)).fetchone()
    if not row:
        return None
    return {"version_number": row[0], "markdown": row[1],
            "change_summary": row[2] or "", "created_at": row[3]}


# --- responses --------------------------------------------------------------

def record_response(c, tenant_id: str, document_id: int, *, version_number: int,
                    recipient_kind: str, response: str, comments: str = "",
                    recipient_name: str = "", recipient_email: str = "") -> None:
    """Record one recipient's answer to one version of a report.

    Input:  tenant, document, the version being answered, who is answering, their decision.
    Output: none.

    A recipient answering twice for the same version SUPERSEDES their previous answer rather
    than accumulating two contradictory ones -- otherwise "has the sponsor accepted?" has two
    answers and the acceptance rule cannot be evaluated.
    """
    if recipient_kind not in RECIPIENT_KINDS:
        raise ReportResponseError(f"unknown recipient {recipient_kind!r}")
    if response not in RESPONSES:
        raise ReportResponseError(f"unknown response {response!r}")

    # The version must EXIST. Codex (HIGH, 2026-07-18): otherwise the app can record "the
    # sponsor accepted version 3" with no version 3 to show for it -- an acceptance that
    # cannot be evidenced, which is worse than no acceptance at all. Migration 034's FK
    # enforces this on Postgres; SQLite only honours FKs when PRAGMA foreign_keys is ON, so
    # the check is made here as well rather than trusting the weaker of the two engines.
    if get_version(c, tenant_id, document_id, version_number) is None:
        raise ReportResponseError(
            f"no version {version_number} of document {document_id} to respond to")

    # ONE ATOMIC UPSERT ON THE NATURAL KEY, not select-then-insert. Codex (2026-07-18)
    # proposed this and it fixes two things at once:
    #
    #   * THE RACE. Two responses arriving together -- entirely possible once the external
    #     portal exists and both recipients hold the same link -- could both see "no existing
    #     row" and both INSERT. One would then violate uq_resp_recipient_version and 500 on a
    #     recipient who did nothing wrong.
    #   * TENANT SCOPING BECOMES INTRINSIC. The conflict target IS the natural key, which
    #     starts with tenant_id, so there is no longer a write that COULD omit it. That is
    #     stronger than a filter a later refactor has to remember to keep.
    #
    # `ON CONFLICT ... DO UPDATE` is supported by Postgres and by SQLite >= 3.24 (2018); this
    # module's other tables already rely on the same construct via _Store.set in api_manager.
    c.execute(
        "INSERT INTO enterprise_report_responses "
        "(tenant_id, document_id, version_number, recipient_kind, recipient_name, "
        " recipient_email, response, comments) VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT (tenant_id, document_id, version_number, recipient_kind) "
        "DO UPDATE SET response = excluded.response, comments = excluded.comments, "
        "              recipient_name = excluded.recipient_name, "
        "              recipient_email = excluded.recipient_email, "
        # A changed answer is a NEW answer and must carry its own time. Codex (Q7,
        # 2026-07-18): leaving the original timestamp made the record say the sponsor
        # answered before they actually did -- and this row is the evidence for whether a
        # programme was authorised to proceed, so its clock has to be right.
        "              responded_at = CURRENT_TIMESTAMP",
        (tenant_id, document_id, version_number, recipient_kind, recipient_name or "",
         recipient_email or "", response, comments or ""))


def responses_for(c, tenant_id: str, document_id: int,
                  version_number: int) -> dict[str, dict]:
    """Every recipient's answer to one version, keyed by recipient kind.

    A recipient who has not answered is ABSENT from the result, never present with a blank
    or a default. "Has not answered" and "answered neutrally" are different facts and the
    acceptance rule turns on the difference.
    """
    rows = c.execute(
        "SELECT recipient_kind, response, comments, recipient_name, recipient_email, "
        "       responded_at "
        "FROM enterprise_report_responses "
        "WHERE tenant_id = ? AND document_id = ? AND version_number = ?",
        (tenant_id, document_id, version_number)).fetchall()
    return {r[0]: {"response": r[1], "comments": r[2] or "", "recipient_name": r[3] or "",
                   "recipient_email": r[4] or "", "responded_at": r[5]} for r in rows}


def overall_status(responses: dict[str, dict]) -> str:
    """The report's status, DERIVED from the recipients' answers. xx201 s43, in its order.

    Input:  the mapping returned by `responses_for`.
    Output: one of AWAITING_RESPONSES / MODIFICATION_REQUIRED / ACCEPTED_BY_BOTH / REJECTED.

    THE ORDER OF THESE RULES IS THE SPEC'S OWN AND IS NOT ARBITRARY:

      1. Any REJECTED  -> REJECTED. A rejection is decisive and outranks the other answer;
         a report one party has rejected is not "awaiting" anything.
      2. Any MODIFICATION_REQUESTED -> MODIFICATION_REQUIRED. Work is owed.
      3. BOTH accepted -> ACCEPTED_BY_BOTH.
      4. Otherwise      -> AWAITING_RESPONSES.

    Rules 3 and 4 are the ones that matter most: acceptance requires BOTH recipients to be
    present AND accepting. One acceptance and one silence is AWAITING, never accepted. This
    function is deliberately pure -- given the same answers it returns the same status, and it
    can be reasoned about and tested without a database.
    """
    # ONLY THE TWO REQUIRED RECIPIENTS COUNT. Codex (MEDIUM, 2026-07-18): reading every value
    # in the mapping let an unknown third party swing the result -- {"auditor": REJECTED}
    # returned REJECTED, a status xx201 does not define for anyone but the beneficiary and the
    # sponsor. An acceptance could not be forged that way, but a REJECTION could, and a report
    # killed by a party with no standing is the same defect wearing the opposite sign.
    values = [responses.get(kind, {}).get("response") for kind in RECIPIENT_KINDS]

    if OVERALL_REJECTED in values:
        return OVERALL_REJECTED
    if MODIFICATION_REQUESTED in values:
        return MODIFICATION_REQUIRED
    # Every recipient must be present and accepting. `all()` over the two required kinds --
    # NOT over `values` -- because `all()` of an empty or partial list is vacuously true, and
    # that would report an unanswered report as accepted by both.
    if all(responses.get(kind, {}).get("response") == ACCEPTED for kind in RECIPIENT_KINDS):
        return ACCEPTED_BY_BOTH
    return AWAITING_RESPONSES


def status_for(c, tenant_id: str, document_id: int, version_number: int) -> str:
    """The overall status of one version of a report, read from the database."""
    return overall_status(responses_for(c, tenant_id, document_id, version_number))


__all__ = [
    "ReportResponseError",
    "BENEFICIARY", "SPONSOR", "RECIPIENT_KINDS",
    "ACCEPTED", "REJECTED", "MODIFICATION_REQUESTED", "RESPONSES",
    "AWAITING_RESPONSES", "MODIFICATION_REQUIRED", "ACCEPTED_BY_BOTH",
    "ensure_schema", "next_version_number", "save_version", "list_versions", "get_version",
    "record_response", "responses_for", "overall_status", "status_for",
]
