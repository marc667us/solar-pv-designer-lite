"""Enterprise Solar Programme -- the lifecycle spine (slice 2).

WHAT THIS IS
------------
The ONLY way a programme changes phase or passes a gate. Every mutation is here so
that the guarantees below hold everywhere, rather than holding on whichever routes
remembered to check.

THE FIVE THINGS EVERY MATERIAL ACTION DOES, IN ORDER
----------------------------------------------------
    1. resolve the programme WITHIN THE CALLER'S TENANT      (control C13)
    2. check the caller's permission -- and for a gate, their ROLE  (rbac)
    3. check the transition is legal for the current phase   (constants.TRANSITIONS)
    4. run the gate predicates / control guards              (gates)
    5. write the row, THEN the audit -- and if the audit fails, roll ALL of it back
                                                             (control C12)

Step 5 is the one people get wrong. `write_audit_event` is non-raising by contract: it
returns False and swallows the error. That is correct for a login page and wrong here.
A gate approval that happened but left no trace is precisely the record an auditor asks
for and we cannot produce. So a failed audit write fails the action. Losing the
transition is recoverable; losing the evidence is not.

WHY STATUS IS NEVER A PARAMETER
-------------------------------
20 programme statuses and 16 phases are two views of one truth. If a caller could pass
a status, the two would drift and eventually contradict each other -- a programme
"Under Construction" sitting in the Feasibility phase. Status is DERIVED from the phase
(constants.PHASE_STATUS). There is no argument that sets it.

HOLDS ARE NOT AMNESIA
---------------------
SUSPENDED and ON_HOLD are not phases -- they are pseudo-states. A suspended programme
remembers the phase it was suspended FROM (`held_from_phase_code`) and resumes exactly
there. Doc 3 requires an approval record and an audit event to come back; a programme
that could quietly resume anywhere would make the hold meaningless.
"""

from __future__ import annotations

from . import flags, gates, rbac
from .constants import (
    DEFAULT_PHASE_CODE,
    DESIGN_STRATEGIES,
    GATE_AUTHORITY_HOLDER_COLUMN,
    GATE_CLOSING_PHASE,
    HOLD_STATES,
    OWNER_ROLE,
    PHASE_ENTRY_REQUIRED_GATES,
    PHASE_STATUS,
    PSEUDO_STATE_STATUS,
    PSEUDO_STATES,
    TRANSITIONS,
)
from . import txn
from .gates import EnterpriseGateError

_STRATEGY_CODES = frozenset(code for code, _ in DESIGN_STRATEGIES)

# The transaction and audit primitives now live in txn.py, because templates.py (slice 4)
# needs the same guarantees and each of these encodes a bug that was found the hard way.
# Re-exported under their original private names so this module -- and the tests that
# monkeypatch them -- read exactly as they did before.
_is_postgres = txn.is_postgres
_in_transaction = txn.in_transaction
_autocommit_is_on = txn.autocommit_is_on
_atomic = txn.atomic
_audit_on = txn.audit_on
_default_audit = txn.default_audit
_inserted_id = txn.inserted_id


# --- SQLite fallback schema (mirrors migration 026) -------------------------
# Local dev and the test suite run on SQLite, where the .sql migrations never execute.
# Creates tables only when ABSENT -- it must never widen or alter an existing column,
# because CREATE-IF-NOT-EXISTS silently does nothing against a table whose shape has
# drifted and you then fail far from the cause
# (see memory: feedback-solar-create-if-not-exists-schema-drift).

_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS enterprise_programme_registry (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id            TEXT NOT NULL,
        code                 TEXT NOT NULL,
        name                 TEXT NOT NULL,
        description          TEXT,
        organisation_type    TEXT,
        design_strategy      TEXT NOT NULL DEFAULT 'standard',
        country              TEXT,
        sponsor_user_id      INTEGER,
        director_user_id     INTEGER,
        manager_user_id      INTEGER,
        current_phase_code   TEXT NOT NULL DEFAULT 'P01_CONCEPT',
        status               TEXT NOT NULL DEFAULT 'Concept',
        held_from_phase_code TEXT,
        target_capacity_kwp  REAL,
        target_beneficiaries INTEGER,
        created_by_user_id   INTEGER,
        created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_programme_code "
    "  ON enterprise_programme_registry (tenant_id, code)",
    "CREATE INDEX IF NOT EXISTS ix_ent_programme_tenant_status "
    "  ON enterprise_programme_registry (tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_ent_programme_tenant_created "
    "  ON enterprise_programme_registry (tenant_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_programme_phase_states (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id     TEXT NOT NULL,
        programme_id  INTEGER NOT NULL,
        phase_code    TEXT NOT NULL,
        sequence_no   INTEGER NOT NULL,
        status        TEXT NOT NULL DEFAULT 'Not Started',
        started_at    TEXT,
        completed_at  TEXT,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_phase "
    "  ON enterprise_programme_phase_states (tenant_id, programme_id, phase_code)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_stage_gates (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        programme_id       INTEGER NOT NULL,
        gate_code          TEXT NOT NULL,
        phase_code         TEXT NOT NULL,
        status             TEXT NOT NULL DEFAULT 'Pending',
        approving_role     TEXT NOT NULL,
        decided_by_user_id INTEGER,
        decided_at         TEXT,
        comment            TEXT,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_gate "
    "  ON enterprise_stage_gates (tenant_id, programme_id, gate_code)",
    "CREATE INDEX IF NOT EXISTS ix_ent_gate_status "
    "  ON enterprise_stage_gates (tenant_id, programme_id, status)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_workflow_transitions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id       TEXT NOT NULL,
        programme_id    INTEGER NOT NULL,
        from_phase_code TEXT,
        to_phase_code   TEXT NOT NULL,
        gate_code       TEXT,
        actor_user_id   INTEGER NOT NULL,
        note            TEXT,
        created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_transition_programme "
    "  ON enterprise_workflow_transitions (tenant_id, programme_id, id)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_approvals (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id            TEXT NOT NULL,
        -- NULLABLE: a tenant-wide template's approval belongs to no programme.
        -- See migration 026 for the full reasoning.
        programme_id         INTEGER,
        subject_type         TEXT NOT NULL,
        subject_id           TEXT,
        approval_type        TEXT NOT NULL,
        decision             TEXT NOT NULL,
        decided_by_user_id   INTEGER,
        decided_by_role      TEXT,
        ai_recommendation_id INTEGER,
        comment              TEXT,
        created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_approval_programme "
    "  ON enterprise_approvals (tenant_id, programme_id, approval_type)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_documents (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        programme_id       INTEGER NOT NULL,
        doc_type           TEXT NOT NULL,
        title              TEXT NOT NULL,
        uri                TEXT,
        uploaded_by_user_id INTEGER,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_document_programme "
    "  ON enterprise_documents (tenant_id, programme_id, doc_type)",
    # The geography tree, sites and template tables are created by migration 026 and are
    # mirrored here so the fallback really is a mirror. Slices 3-4 fill them; the schema
    # existing early costs nothing and keeps SQLite and Postgres the same shape, which is
    # what stops a test suite from passing against a schema production does not have.
    """
    CREATE TABLE IF NOT EXISTS enterprise_geographic_areas (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id    TEXT NOT NULL,
        programme_id INTEGER,
        parent_id    INTEGER,
        level        TEXT NOT NULL,
        code         TEXT NOT NULL,
        name         TEXT NOT NULL,
        country      TEXT,
        created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
        FOREIGN KEY (tenant_id, parent_id)
            REFERENCES enterprise_geographic_areas (tenant_id, id) ON DELETE CASCADE,
        UNIQUE (tenant_id, id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_geo_programme "
    "  ON enterprise_geographic_areas (tenant_id, programme_id, level)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_sites (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id    TEXT NOT NULL,
        programme_id INTEGER NOT NULL,
        area_id      INTEGER,
        code         TEXT NOT NULL,
        name         TEXT NOT NULL,
        latitude     REAL,
        longitude    REAL,
        status       TEXT NOT NULL DEFAULT 'Registered',
        created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE
        FOREIGN KEY (tenant_id, area_id)
            REFERENCES enterprise_geographic_areas (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_site_code "
    "  ON enterprise_sites (tenant_id, programme_id, code)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_programme_templates (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        programme_id       INTEGER,
        code               TEXT NOT NULL,
        name               TEXT NOT NULL,
        beneficiary_type   TEXT,
        design_strategy    TEXT NOT NULL DEFAULT 'standard',
        created_by_user_id INTEGER,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_code "
    "  ON enterprise_programme_templates (tenant_id, code)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_template_versions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id           TEXT NOT NULL,
        template_id         INTEGER NOT NULL,
        version_no          INTEGER NOT NULL,
        status              TEXT NOT NULL DEFAULT 'Draft',
        parameters_json     TEXT NOT NULL DEFAULT '{}',
        approved_by_user_id INTEGER,
        approved_at         TEXT,
        created_by_user_id  INTEGER,
        created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, template_id)
            REFERENCES enterprise_programme_templates (tenant_id, id) ON DELETE CASCADE,
        -- So a generated project can hold a tenant-scoped FK to the exact version it was
        -- built from (control C14). See migration 026.
        UNIQUE (tenant_id, id),
        CONSTRAINT ck_ent_template_version_status CHECK (status IN
            ('Draft','Review','Approved','Published','Superseded','Archived'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_version "
    "  ON enterprise_template_versions (tenant_id, template_id, version_no)",
    "CREATE INDEX IF NOT EXISTS ix_ent_template_version_status "
    "  ON enterprise_template_versions (tenant_id, status)",
    # One Published and one Draft per template -- see migration 026 for why the database,
    # and not just the service, has to say so.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_one_published "
    "  ON enterprise_template_versions (tenant_id, template_id) WHERE status='Published'",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_template_one_draft "
    "  ON enterprise_template_versions (tenant_id, template_id) WHERE status='Draft'",
    # Template immutability, enforced by the database. The SQLite twin of migration 026's
    # trg_ent_template_version_is_frozen. Two triggers rather than one because SQLite has
    # no IF/RETURN inside a trigger body -- the condition goes in the WHEN clause.
    #
    # DELIBERATELY NARROWER THAN POSTGRES. Migration 026 also guards INSERT and DELETE (so
    # that delete-then-reinsert cannot forge a version). SQLite does NOT, because the
    # backup restore path -- new_admin_backup_routes.py -- restores every table by
    # DELETE-then-INSERT, and on Postgres it can turn triggers off for the duration
    # (`SET session_replication_role='replica'`) while SQLite has no equivalent. Guarding
    # INSERT/DELETE here would therefore break restore on the one backend that cannot opt
    # out. Production is Postgres; SQLite is dev and tests, where the service-layer guard
    # (which the tests exercise) is the one that matters.
    """
    CREATE TRIGGER IF NOT EXISTS trg_ent_template_version_frozen
    BEFORE UPDATE OF parameters_json ON enterprise_template_versions
    FOR EACH ROW WHEN OLD.status <> 'Draft'
                  AND NEW.parameters_json <> OLD.parameters_json
    BEGIN
        SELECT RAISE(ABORT, 'template version is frozen: its parameters cannot be changed once it has left Draft -- create a new version instead');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_ent_template_version_no_resurrect
    BEFORE UPDATE OF status ON enterprise_template_versions
    FOR EACH ROW WHEN NEW.status = 'Draft'
                  AND OLD.status NOT IN ('Draft', 'Review')
    BEGIN
        SELECT RAISE(ABORT, 'a template version cannot return to Draft once approved -- something may already have been generated from it');
    END
    """,
]


def ensure_schema(c) -> None:
    """Create the slice-2 tables on SQLite. No-op on Postgres (migration 026 owns it).

    Input:  open DB connection.
    Output: none.

    The tenant-scoped composite FKs above are declared exactly as migration 026 declares
    them -- but SQLite only ENFORCES foreign keys when a connection asks it to
    (`PRAGMA foreign_keys=ON`, per connection, off by default).

    This function deliberately does NOT turn that on. The PRAGMA applies to the whole
    app's connection, and this database has legacy tables that predate FK discipline;
    switching it on globally could start rejecting writes that have always been allowed,
    which is not slice 2's call to make. The test fixture DOES turn it on, so the
    constraints are genuinely exercised, and Postgres enforces them for real in production.
    The gap is dev-only SQLite, where they are declarative.
    """
    if _is_postgres():
        return
    for stmt in _SQLITE_SCHEMA:
        c.execute(stmt)


# --- reading ----------------------------------------------------------------


def _load_programme(c, tenant_id: str, programme_id: int):
    """Fetch a programme, enforcing control C13 (tenant scope).

    Input:  connection, ACTIVE tenant id (never one taken from the URL), programme id.
    Output: tuple (id, tenant_id, current_phase_code, status, held_from_phase_code,
            sponsor_user_id).
    Raises: EnterpriseGateError C13 -- with the same message whether the programme
            belongs to someone else or does not exist. Distinguishing them would leak
            the existence of other organisations' programmes.
    """
    # tenant_id is in the WHERE clause, not checked afterwards in Python. The boundary
    # belongs in the query: it is where every other statement in this module puts it, it
    # uses the (tenant_id, ...) indexes, and another tenant's row is never loaded into
    # this process at all -- so no future refactor can log or return it by accident.
    row = c.execute(
        "SELECT id, tenant_id, current_phase_code, status, held_from_phase_code, "
        "       sponsor_user_id "
        "  FROM enterprise_programme_registry WHERE id=? AND tenant_id=?",
        (programme_id, tenant_id),
    ).fetchone()
    if row is None:
        # Same error whether it belongs to another tenant or does not exist -- telling
        # them apart would leak the existence of other organisations' programmes.
        raise EnterpriseGateError("C13", "no such programme in this organisation")
    return row


def get_programme_state(c, tenant_id: str, programme_id: int) -> dict:
    """The programme's current position in the lifecycle, plus what it may do next.

    Input:  connection, tenant id, programme id.
    Output: dict with phase, status, held_from, gate_to_leave, allowed_transitions.

    The UI renders `allowed_transitions` as the dropdown. That is the point of a state
    machine: the user is never offered a move the server would refuse.
    """
    row = _load_programme(c, tenant_id, programme_id)
    phase, status, held_from = row[2], row[3], row[4]
    return {
        "programme_id": programme_id,
        "current_phase_code": phase,
        "status": status,
        "held_from_phase_code": held_from,
        "gate_to_leave": GATE_CLOSING_PHASE.get(phase),
        "allowed_transitions": list(allowed_transitions(phase, status)),
    }


def allowed_transitions(phase_code: str, status: str) -> tuple[str, ...]:
    """The legal next states from here.

    Input:  the programme's current phase code, its current status.
    Output: tuple of phase codes and/or pseudo-states.

    A held programme's only legal move is to resume the phase it was held from (which
    resume_from_hold does, gated on an approval record) or to be cancelled outright.
    A terminal programme has no moves at all.
    """
    if status in ("Suspended", "On Hold"):
        return ("RESUME", "CANCELLED")
    if status in ("Cancelled", "Closed"):
        # Doc 3 lists Archived as a real programme status, and it is reached from here:
        # a finished or abandoned programme is archived out of the active register. It is
        # the one move a terminal programme still has.
        return ("ARCHIVED",)
    if status == "Archived":
        return ()
    return TRANSITIONS.get(phase_code, ())


# --- creating ---------------------------------------------------------------


def create_programme(c, tenant_id: str, user_id: int, *, code: str, name: str,
                     design_strategy: str = "standard", sponsor_user_id: int | None = None,
                     country: str | None = None, description: str | None = None,
                     audit=None) -> int:
    """Register a programme at Phase 1 / status Concept, and seed its phases and gates.

    Input:  connection, tenant id, acting user id, programme code + name, design
            strategy code, optional sponsor/country/description, optional audit hook.
    Output: the new programme id.
    Raises: EnterprisePermissionError (403), ValueError, EnterpriseGateError (409).

    Every programme is born with all 16 phase rows and all 14 gate rows already
    present, Pending. Seeding them up-front rather than lazily is what lets the UI show
    the whole road ahead -- including the gates that will block it -- from day one, and
    removes the class of bug where a gate row is simply missing and the check that
    would have failed never runs.

    The starting phase and status are not parameters. A programme starts at Concept.
    """
    rbac.require_permission(c, tenant_id, user_id, "programme.create")

    if design_strategy not in _STRATEGY_CODES:
        raise ValueError(f"unknown design strategy: {design_strategy!r}")
    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise ValueError("programme code and name are required")

    # A sponsor who is not in this organisation is not a sponsor. Without this, a
    # programme could name a stranger (or a user from another tenant) and Gate 1's
    # predicate -- which only checks the column is non-NULL -- would happily pass.
    if sponsor_user_id is not None:
        member = c.execute(
            "SELECT 1 FROM enterprise_tenant_memberships "
            " WHERE tenant_id=? AND user_id=? AND status='active'",
            (tenant_id, sponsor_user_id),
        ).fetchone()
        if not member:
            raise ValueError(
                "the named sponsor is not an active member of this organisation"
            )

    # A programme CODE is unique within its organisation -- migration 026 declares
    # `CREATE UNIQUE INDEX ux_ent_programme_code ON enterprise_programme_registry
    # (tenant_id, code)`. Nothing here used to check it, so re-using a code raised a raw
    # IntegrityError ("duplicate key value violates unique constraint"), which the route
    # does not catch either. It escaped to the catch-all handler and became the friendly
    # error page -- so the owner pressed Register, got a "hiccup", changed nothing, pressed
    # Register again, and got the same hiccup forever, with nothing anywhere telling them
    # the ONE thing they needed to know: that code is taken.
    #
    # Checked here rather than only caught below because on Postgres a constraint violation
    # ABORTS THE TRANSACTION -- so by the time the error is raised the savepoint is already
    # unwinding, and the cheap, clean answer is to not send the statement at all.
    clash = c.execute(
        "SELECT 1 FROM enterprise_programme_registry WHERE tenant_id=? AND code=?",
        (tenant_id, code),
    ).fetchone()
    if clash:
        raise ValueError(
            f"A programme with the code {code!r} already exists in this organisation. "
            f"Programme codes must be unique -- please choose a different one."
        )

    audit = audit or _audit_on(c)
    try:
        with _atomic(c):
            cur = c.execute(
                "INSERT INTO enterprise_programme_registry "
                "(tenant_id, code, name, description, design_strategy, country, "
                " sponsor_user_id, current_phase_code, status, created_by_user_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (tenant_id, code, name, description, design_strategy, country,
                 sponsor_user_id, DEFAULT_PHASE_CODE, PHASE_STATUS[DEFAULT_PHASE_CODE],
                 user_id),
            )
            programme_id = _inserted_id(c, cur)

            from .constants import GATES, PHASES  # local: keeps the module header short

            # executemany, not 30 separate round trips. The database is remote (Render free
            # tier), so each INSERT is a network hop; seeding a programme should cost 3 trips,
            # not 31. The seeding later slices add (beneficiary import) will be far larger.
            c.executemany(
                "INSERT INTO enterprise_programme_phase_states "
                "(tenant_id, programme_id, phase_code, sequence_no, status) "
                "VALUES (?,?,?,?,?)",
                [(tenant_id, programme_id, phase_code, seq,
                  "In Progress" if phase_code == DEFAULT_PHASE_CODE else "Not Started")
                 for phase_code, seq, _label in PHASES],
            )
            c.executemany(
                "INSERT INTO enterprise_stage_gates "
                "(tenant_id, programme_id, gate_code, phase_code, status, approving_role) "
                "VALUES (?,?,?,?,?,?)",
                [(tenant_id, programme_id, gate_code, phase_code, "Pending", authority)
                 for gate_code, phase_code, _label, authority in GATES],
            )

            # Naming a sponsor GRANTS them the sponsor role on this programme.
            #
            # Without this the model contradicts itself: approve_gate requires the approver to
            # hold `programme_sponsor` AND to be the person the programme named -- so naming a
            # sponsor who does not already hold the role tenant-wide would produce a programme
            # whose Gate 1 literally nobody can sign. The grant is PROGRAMME-SCOPED, so being
            # sponsor of one programme confers no authority over any other.
            #
            # But granting a role is TENANT-ADMIN's job, and `programme_sponsor` carries
            # `programme.approve`. If merely holding `programme.create` were enough to confer
            # it, programme creation would be a side door into role assignment. So: an admin
            # may name anyone; a non-admin creator may only name someone who ALREADY holds the
            # role. Today every role with `programme.create` also has `tenant.admin`, so this
            # changes nothing -- it is here so that the day someone adds a create-only role,
            # the side door does not open with it.
            if sponsor_user_id is not None:
                if rbac.has_permission(c, tenant_id, user_id, "tenant.admin"):
                    _grant_role(c, tenant_id, sponsor_user_id, "programme_sponsor",
                                programme_id=programme_id, granted_by=user_id)
                elif "programme_sponsor" not in rbac.roles_for_user(
                        c, tenant_id, sponsor_user_id, programme_id=programme_id):
                    raise rbac.EnterprisePermissionError("tenant.admin", tenant_id)

            gates.require_audit_written(
                audit("ENTERPRISE_PROGRAMME_CREATED", user_id=user_id, tenant_id=tenant_id,
                      details={"programme_id": programme_id, "code": code,
                               "design_strategy": design_strategy,
                               "sponsor_user_id": sponsor_user_id}),
                "programme create",
            )
    except Exception as e:
        # A racing duplicate: two people registering the same code at the same instant slip
        # past the pre-check above and collide on ux_ent_programme_code. Same user-facing
        # answer, so it must not surface as a stack trace and a "hiccup" page.
        if txn.is_integrity_error(e):
            raise ValueError(
                f"A programme with the code {code!r} already exists in this organisation. "
                f"Programme codes must be unique -- please choose a different one."
            ) from e
        raise

    return programme_id


def _grant_role(c, tenant_id: str, user_id: int, role_code: str, *,
                programme_id: int | None = None, granted_by: int | None = None) -> None:
    """Grant a role, scoped to one programme when given. Idempotent.

    Input:  connection, tenant id, the user receiving the role, the role code, the
            programme it is scoped to (None = tenant-wide), the granting user.
    Output: none.

    Re-granting is a no-op rather than an error: the unique index on
    enterprise_role_assignments already says a grant is a fact, not an event.
    """
    ignore = ("ON CONFLICT DO NOTHING" if _is_postgres() else "")
    verb = "INSERT" if _is_postgres() else "INSERT OR IGNORE"
    c.execute(
        f"{verb} INTO enterprise_role_assignments "
        "(tenant_id, user_id, role_code, scope_type, scope_id, created_by_user_id) "
        f"VALUES (?,?,?,?,?,?) {ignore}",
        (tenant_id, user_id, role_code,
         "programme" if programme_id else "tenant", programme_id, granted_by),
    )



def register_document(c, tenant_id: str, user_id: int, programme_id: int, *,
                      doc_type: str, title: str, uri: str | None = None,
                      audit=None) -> int:
    """Attach a required document to a programme (concept note, charter, business case...).

    Input:  connection, tenant id, acting user id, programme id, doc type + title,
            optional uri, optional audit hook.
    Output: the new document id.

    Doc 3 lists required documents per gate; the gate predicates in gates.py check that
    the document is REGISTERED. Whether its contents are any good is the named
    authority's judgement -- which is exactly why a specific human role has to sign the
    gate rather than the system auto-passing it.
    """
    _load_programme(c, tenant_id, programme_id)  # C13 FIRST -- see note below
    rbac.require_permission(c, tenant_id, user_id, "programme.edit",
                            programme_id=programme_id)

    audit = audit or _audit_on(c)
    with _atomic(c):
        cur = c.execute(
            "INSERT INTO enterprise_documents "
            "(tenant_id, programme_id, doc_type, title, uri, uploaded_by_user_id) "
            "VALUES (?,?,?,?,?,?)",
            (tenant_id, programme_id, doc_type, title, uri, user_id),
        )
        doc_id = _inserted_id(c, cur)
        gates.require_audit_written(
            audit("ENTERPRISE_DOCUMENT_REGISTERED", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id, "doc_type": doc_type}),
            "document register",
        )
    return doc_id


# --- gates ------------------------------------------------------------------


def _require_named_post_holder(c, tenant_id: str, programme_id: int, authority: str,
                               user_id: int) -> None:
    """If the programme NAMED a holder for this gate's authority, only they may sign.

    Input:  connection, tenant id, programme id, the gate's approving role, the approver.
    Output: none.
    Raises: EnterprisePermissionError (403).

    Holding the role is necessary and NOT sufficient. Gate 1's authority is the Programme
    Sponsor; if this programme named Bob as its sponsor, then Carol -- who also holds the
    programme_sponsor role tenant-wide, on other programmes -- must not be able to sign
    Bob's gate. Otherwise `sponsor_user_id` is decoration and control C01 is satisfied by
    an approval the actual sponsor never gave.

    When the post is UNFILLED (column NULL) the role check alone applies: an organisation
    that has not named a director can still have its directors approve Gate 5.
    """
    column = GATE_AUTHORITY_HOLDER_COLUMN.get(authority)
    if not column:
        return  # this authority is a role, not a named post (e.g. steering_committee)

    row = c.execute(
        f"SELECT {column} FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    named = row[0] if row else None
    if named is None:
        return
    if int(named) != int(user_id):
        raise rbac.EnterprisePermissionError(f"role:{authority}", tenant_id)


def approve_gate(c, tenant_id: str, programme_id: int, gate_code: str, user_id: int,
                 *, comment: str | None = None, ai_recommendation_id: int | None = None,
                 audit=None) -> None:
    """Approve a stage gate. The named authority, and nobody else, may do this.

    Input:  connection, tenant id, programme id, gate code, the approving user,
            optional comment, optional AI recommendation attached as EVIDENCE,
            optional audit hook.
    Output: none.
    Raises: EnterprisePermissionError (403) if the caller does not hold the gate's
            approving role; EnterpriseGateError / GateBlockedError (409) if the gate's
            evidence is missing or the gate is deferred beyond Release 1.

    THREE checks, and all three are load-bearing:

      C11 -- a human must be the approver. An AI recommendation may be attached as
             supporting evidence; it can never BE the decision. There is no service
             account or "system" pseudo-user that satisfies this.
      ROLE -- doc 3 names an approving authority PER GATE. Gate 1 is the Programme
             Sponsor's, Gate 6 the Technical Director's. Holding the generic
             `programme.approve` permission is NOT sufficient: the right person signs,
             or nobody does. (rbac.require_role, not require_permission.)
      PREDICATES -- the gate's required evidence must actually exist (gates.evaluate_gate).

    Approving an already-approved gate is a no-op, not an error: a double-click must not
    produce a second approval record.

    THE OWNER MAY ALWAYS SIGN (owner directive, 2026-07-13: "owner must have the authority
    to issue all approvals")
    ------------------------------------------------------------------------------------
    The organisation's owner -- the person who created it, who holds `tenant.admin` -- may
    approve ANY gate, whatever role it names and whoever holds the post.

    This closes a real trap. The ROLE check and the NAMED POST HOLDER check are separate,
    and the second one bites the owner specifically: a programme records a sponsor, a
    director and a manager BY USER ID, and if the owner names a colleague as sponsor then
    the owner -- who holds `programme_sponsor` and owns the entire organisation -- can never
    sign Gate 1 or Gate 4 on that programme. The ministry's principal is locked out of their
    own lifecycle by an appointment they themselves made.

    WHAT THE OVERRIDE DOES *NOT* DO, and this is the important half: it grants AUTHORITY, not
    EXEMPTION FROM EVIDENCE. `gates.evaluate_gate` still runs, unchanged, below. The owner
    can sign any gate; they cannot sign a gate whose required document does not exist. An
    owner who could skip the evidence would make every gate in the module decorative, and
    that is not what "authority to approve" means.

    C11 also still holds: the approver is a human. An AI recommendation remains evidence,
    never the decision.

    Every override is RECORDED AS AN OVERRIDE in the audit trail (`owner_override`, plus the
    authority it stood in for and the post holder it bypassed). Accountability is the point
    of the named-post-holder rule, and an override that left no trace would destroy it; one
    that leaves a trace merely moves the accountability onto the owner, where it belongs.
    """
    gates.require_human_approval_actor(user_id, ai_recommendation_id)
    _load_programme(c, tenant_id, programme_id)  # C13

    authority = gates.gate_authority(gate_code)

    # The normal checks run FIRST and unchanged, for everyone including the owner. The owner
    # is only ever RESCUED from a refusal -- so `override_used` is true only when the owner
    # would genuinely have been turned away, and an owner who legitimately holds the
    # authority signs as that authority, exactly as before. An "override" flag that fired on
    # every approval the owner ever made would tell an auditor nothing.
    override_used = False
    try:
        rbac.require_role(c, tenant_id, user_id, authority, programme_id=programme_id)
        _require_named_post_holder(c, tenant_id, programme_id, authority, user_id)
    except rbac.EnterprisePermissionError:
        # The OWNER ROLE, not the `tenant.admin` PERMISSION. Codex, HIGH: `org_admin` also
        # carries `tenant.admin`, so keying the rescue off the permission would have handed
        # C01 bypass to every delegated administrator -- and then stamped the approvals table
        # `enterprise_owner`, naming a person who is not the owner. The directive is "the
        # OWNER must have the authority to issue all approvals"; it is not "administrators
        # may sign in other people's names".
        if OWNER_ROLE not in rbac.roles_for_user(c, tenant_id, user_id):
            raise
        override_used = True

    row = c.execute(
        "SELECT status FROM enterprise_stage_gates "
        " WHERE tenant_id=? AND programme_id=? AND gate_code=?",
        (tenant_id, programme_id, gate_code),
    ).fetchone()
    if row is None:
        raise EnterpriseGateError(gate_code, "this gate is not seeded on this programme")
    if row[0] == "Approved":
        return

    # GOVERNANCE IS ADVISORY (owner, 2026-07-14: "reduce and loosen governance").
    #
    # The gate no longer REFUSES. But it still LOOKS, and what it finds is recorded: an
    # approval made without its evidence says so, on the approval row and in the audit trail.
    # That distinction is the whole point. "Loosen governance" means the app stops standing in
    # the operator's way; it does not mean it starts telling a funder that evidence existed
    # when it did not. An auditor can still separate the approvals that were evidenced from
    # the ones that were not -- which is the only thing that made the record worth keeping.
    evidence_missing = ""
    try:
        gates.evaluate_gate(c, tenant_id, programme_id, gate_code)
    except EnterpriseGateError as e:
        if not flags.advisory_governance(c):
            raise                                    # strict mode: the gate still blocks
        evidence_missing = str(e)

    audit = audit or _audit_on(c)
    with _atomic(c):
        c.execute(
            "UPDATE enterprise_stage_gates "
            "   SET status='Approved', decided_by_user_id=?, "
            "       decided_at=CURRENT_TIMESTAMP, comment=? "
            " WHERE tenant_id=? AND programme_id=? AND gate_code=?",
            (user_id, comment, tenant_id, programme_id, gate_code),
        )
        # The capacity they ACTUALLY signed in. Recording `programme_sponsor` for an owner
        # who is not the sponsor and never held the post would put a false statement in the
        # approvals table -- the one table whose entire purpose is to say who decided what.
        signed_as = OWNER_ROLE if override_used else authority

        # AN APPROVAL MADE WITHOUT ITS EVIDENCE SAYS SO, IN THE APPROVAL ITSELF. The comment
        # column is what a funder or an auditor reads; leaving it silent would let an
        # unevidenced approval be indistinguishable from an evidenced one, and at that point
        # the whole table stops being worth reading.
        stored_comment = comment or ""
        if evidence_missing:
            stored_comment = (
                (stored_comment + " — ") if stored_comment else ""
            ) + f"APPROVED WITHOUT EVIDENCE: {evidence_missing}"

        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, decided_by_role, ai_recommendation_id, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (tenant_id, programme_id, "gate", gate_code, "stage_gate", "Approved",
             user_id, signed_as, ai_recommendation_id, stored_comment),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_GATE_APPROVED", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id, "gate": gate_code,
                           "role": signed_as,
                           # An override is a real event and is named as one. The gate's own
                           # authority is kept alongside it, so the record says exactly what
                           # was stood in for rather than merely that somebody signed.
                           "owner_override": override_used,
                           "authority_required": authority,
                           # Empty when the gate's evidence was there. Non-empty is the
                           # single field an auditor greps for.
                           "evidence_missing": evidence_missing,
                           "ai_recommendation_id": ai_recommendation_id}),
            f"gate {gate_code} approval",
        )


# --- transitions ------------------------------------------------------------


def transition_programme_phase(c, tenant_id: str, programme_id: int, target: str,
                               user_id: int, *, note: str | None = None,
                               audit=None) -> dict:
    """Move a programme to another phase, or into a hold/terminal state.

    Input:  connection, tenant id, programme id, target phase code or pseudo-state
            ('SUSPENDED', 'ON_HOLD', 'CANCELLED', 'CLOSED'), acting user, optional note,
            optional audit hook.
    Output: the new state dict (same shape as get_programme_state).
    Raises: EnterprisePermissionError (403), EnterpriseGateError (409).

    THE ADVANCE RULE: to move FORWARD out of a phase, the gate that closes that phase
    must already be Approved. Moving BACKWARD (rework: Feasibility -> Needs Assessment)
    needs no gate -- gates guard progress, not retreat -- but it is still recorded and
    audited, because "who sent this back, and when" is exactly the question a steering
    committee asks.

    C01 is enforced on top: no programme leaves Concept without its sponsor having
    approved Gate 1.
    """
    # C13 BEFORE the permission check, deliberately. If we authorised first, a
    # cross-tenant POST from a user without programme.edit would raise 403 -- and a 403
    # confirms the programme EXISTS, which is precisely what C13 forbids. "Does it exist
    # for you" is a strictly earlier question than "may you do this".
    row = _load_programme(c, tenant_id, programme_id)
    rbac.require_permission(c, tenant_id, user_id, "programme.edit",
                            programme_id=programme_id)
    current_phase, status = row[2], row[3]

    if status == "Archived":
        raise EnterpriseGateError(
            "LIFECYCLE", "programme is Archived; it has no further transitions"
        )
    if status in ("Cancelled", "Closed"):
        # A terminal programme can still be ARCHIVED -- filed out of the active register.
        # Nothing else.
        if target != "ARCHIVED":
            raise EnterpriseGateError(
                "LIFECYCLE",
                f"programme is {status}; the only remaining move is ARCHIVED",
            )
        return _apply_pseudo_state(c, tenant_id, programme_id, current_phase, target,
                                   user_id, note, audit)
    if status in ("Suspended", "On Hold"):
        # A held programme may still be CANCELLED outright -- allowed_transitions() has
        # always advertised that, and refusing it here contradicted our own dropdown and
        # could strand a programme whose phase has no CANCELLED edge of its own (a
        # programme held from Needs Assessment could never be cancelled at all). Any OTHER
        # move still requires an explicit, approved resume.
        if target != "CANCELLED":
            raise EnterpriseGateError(
                "LIFECYCLE",
                f"programme is {status}; it must be resumed (which needs an approval) "
                "before it can move",
            )
        return _apply_pseudo_state(c, tenant_id, programme_id, current_phase, target,
                                   user_id, note, audit)

    # ADVISORY GOVERNANCE: any phase is reachable from any phase (owner, 2026-07-14: "user
    # must be able to work at any phase", "reduce and loosen governance"). The step-by-step
    # march was the single loudest block in the module -- a programme that had done the
    # feasibility work could not be MOVED to Feasibility without first passing through Needs.
    #
    # The target must still BE a phase. "Any phase" is not "any string": a typo'd or
    # hand-rolled target would otherwise write a phase code no screen can render and no
    # gate is seeded against, and the programme would simply disappear from its own lifecycle.
    from .constants import PHASE_CODES
    if not flags.advisory_governance(c):
        legal = TRANSITIONS.get(current_phase, ())
        if target not in legal:
            raise EnterpriseGateError(
                "LIFECYCLE",
                f"illegal transition {current_phase} -> {target}; "
                f"allowed: {', '.join(legal) or 'none'}",
            )
    elif target not in PHASE_CODES:
        raise EnterpriseGateError("LIFECYCLE", f"no such lifecycle phase: {target}")

    if target in PSEUDO_STATES:
        # NOTE, deliberately: leaving P16_EXPANSION for CLOSED does NOT require an
        # expansion approval, and that is not an oversight (a reviewer flagged it as one).
        # The expansion approval authorises SPENDING THE NEXT TRANCHE -- cloning the
        # programme to a new Concept, or re-planning from Structuring. Closing is the
        # opposite decision: it is the choice NOT to expand. Demanding an approval-to-
        # expand before you are allowed to stop expanding would make winding a programme
        # down harder than continuing it, which is precisely backwards.
        return _apply_pseudo_state(c, tenant_id, programme_id, current_phase, target,
                                   user_id, note, audit)

    # A real phase move. Is it forward (advance) or backward (rework)?
    from .constants import PHASES

    seq = {p[0]: p[1] for p in PHASES}
    advancing = seq[target] > seq[current_phase]
    gate_code = GATE_CLOSING_PHASE.get(current_phase) if advancing else None

    # P16 (Expansion and Replication) is the one phase whose legal exits both point
    # BACKWARD -- clone to a new Concept, or re-plan from Structuring. Sequence numbers
    # therefore class them as "rework" and would wave them through on programme.edit
    # alone (Codex slice-2 review, MEDIUM). But doc 3 gates P16's exit on an EXPANSION
    # APPROVAL RECORD, and an expansion is the most consequential thing a programme
    # does: it spends the next tranche. So it is guarded explicitly, independently of
    # direction.
    if current_phase == "P16_EXPANSION" and not flags.advisory_governance(c):
        _require_expansion_approval(c, tenant_id, programme_id)

    # Two independent sets of gates, and BOTH must hold:
    #
    #   1. EXIT  -- only when advancing: the gate closing the phase being left.
    #   2. ENTRY -- on EVERY entry, forward or backward: what the destination demands
    #               (constants.PHASE_ENTRY_REQUIRED_GATES).
    #
    # The entry set is what stops a programme routing AROUND a gate. Doc 3 permits
    # P06 -> P09 and P09 -> P10; chained, an exit-only rule let a programme reach
    # Mobilisation with no funding close and no contract award. The hole is a property of
    # the destination, not of the route, so the check belongs on the destination.
    required: list[str] = []
    if advancing:
        # C01 -- nothing leaves Concept without an approved sponsor. ADVISORY now: a
        # programme whose sponsor is still being courted can still be worked on, which is the
        # ordinary case (the owner's own words: beneficiaries register and track progress; the
        # sponsor is often the LAST thing settled, not the first).
        if not flags.advisory_governance(c):
            gates.require_approved_sponsor(c, tenant_id, programme_id)
        if gate_code:
            required.append(gate_code)
    for entry_gate in PHASE_ENTRY_REQUIRED_GATES.get(target, ()):
        if entry_gate not in required:
            required.append(entry_gate)

    # ADVISORY GOVERNANCE (owner, 2026-07-14: "reduce and loosen governance"; "user must be
    # able to work at any phase"). An unapproved gate no longer REFUSES the move -- it is
    # recorded on the transition instead, so the programme's history still shows that it
    # moved past a gate that had not been approved. The app stops blocking; it does not start
    # pretending the gate was passed.
    advisory = flags.advisory_governance(c)
    unapproved: list[str] = []
    for required_gate in required:
        g = c.execute(
            "SELECT status FROM enterprise_stage_gates "
            " WHERE tenant_id=? AND programme_id=? AND gate_code=?",
            (tenant_id, programme_id, required_gate),
        ).fetchone()
        if not g or g[0] != "Approved":
            if not advisory:
                raise EnterpriseGateError(
                    required_gate,
                    f"{required_gate} must be approved before moving "
                    f"{current_phase} -> {target}",
                )
            unapproved.append(required_gate)

    if unapproved:
        note = ((note + " — ") if note else "") + (
            "moved past unapproved gate(s): " + ", ".join(unapproved))

    audit = audit or _audit_on(c)
    with _atomic(c):
        c.execute(
            "UPDATE enterprise_programme_registry "
            "   SET current_phase_code=?, status=?, held_from_phase_code=NULL, "
            "       updated_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=?",
            (target, PHASE_STATUS[target], tenant_id, programme_id),
        )
        if advancing:
            # Only an advance completes the phase being left. A rework transition sends
            # the programme BACK into an earlier phase, which does not mean the phase it
            # is leaving is finished -- it means it was not.
            c.execute(
                "UPDATE enterprise_programme_phase_states "
                "   SET status='Completed', completed_at=CURRENT_TIMESTAMP "
                " WHERE tenant_id=? AND programme_id=? AND phase_code=?",
                (tenant_id, programme_id, current_phase),
            )
        c.execute(
            "UPDATE enterprise_programme_phase_states "
            "   SET status='In Progress', started_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND programme_id=? AND phase_code=?",
            (tenant_id, programme_id, target),
        )
        c.execute(
            "INSERT INTO enterprise_workflow_transitions "
            "(tenant_id, programme_id, from_phase_code, to_phase_code, gate_code, "
            " actor_user_id, note) VALUES (?,?,?,?,?,?,?)",
            (tenant_id, programme_id, current_phase, target, gate_code, user_id, note),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_PHASE_TRANSITION", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id, "from": current_phase,
                           "to": target, "gate": gate_code,
                           "direction": "advance" if advancing else "rework"}),
            "phase transition",
        )

    return get_programme_state(c, tenant_id, programme_id)


def _require_expansion_approval(c, tenant_id: str, programme_id: int) -> None:
    """A programme may only leave P16 once an expansion has been approved.

    Input:  connection, tenant id, programme id.
    Output: none.
    Raises: EnterpriseGateError.

    Doc 3 gives P16 no numbered gate but requires "an expansion approval record". Without
    this check the two legal P16 exits both look like backward rework to the sequence
    comparison and would need nothing but programme.edit.
    """
    row = c.execute(
        "SELECT 1 FROM enterprise_approvals "
        " WHERE tenant_id=? AND programme_id=? AND approval_type='expansion' "
        "   AND decision='Approved' LIMIT 1",
        (tenant_id, programme_id),
    ).fetchone()
    if not row:
        raise EnterpriseGateError(
            "P16",
            "expansion or replication requires an approved expansion record before the "
            "programme may leave the Expansion phase",
        )


def approve_expansion(c, tenant_id: str, programme_id: int, user_id: int,
                      *, comment: str | None = None, ai_recommendation_id: int | None = None,
                      audit=None) -> None:
    """Record the expansion approval that unlocks P16's exits.

    Input:  connection, tenant id, programme id, the approving user, optional comment,
            optional AI recommendation attached as EVIDENCE, optional audit hook.
    Output: none.
    Raises: EnterprisePermissionError (403), EnterpriseGateError (409).

    Requires `programme.approve` and, per C11, a human decision-maker. Gate 14 (Benefits
    and Performance Review) is the Steering Committee's judgement that the programme
    WORKED; this is the separate decision to spend more money doing it again.
    """
    gates.require_human_approval_actor(user_id, ai_recommendation_id)
    row = _load_programme(c, tenant_id, programme_id)  # C13 first -- see transition note
    rbac.require_permission(c, tenant_id, user_id, "programme.approve",
                            programme_id=programme_id)
    if row[2] != "P16_EXPANSION":
        raise EnterpriseGateError(
            "P16", "the programme is not in the Expansion phase"
        )

    audit = audit or _audit_on(c)
    with _atomic(c):
        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, ai_recommendation_id, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_id, programme_id, "programme", str(programme_id), "expansion",
             "Approved", user_id, ai_recommendation_id, comment),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_EXPANSION_APPROVED", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id}),
            "expansion approval",
        )


def _apply_pseudo_state(c, tenant_id, programme_id, current_phase, target, user_id,
                        note, audit) -> dict:
    """Suspend, hold, cancel or close a programme.

    Input:  connection, tenant id, programme id, the phase it is leaving, the
            pseudo-state, acting user, note, audit hook.
    Output: the new state dict.

    A HOLD remembers where it came from (`held_from_phase_code`) so resume_from_hold
    can put it back exactly there. A TERMINAL state does not -- there is nowhere to go
    back to.
    """
    audit = audit or _audit_on(c)
    held_from = current_phase if target in HOLD_STATES else None
    with _atomic(c):
        c.execute(
            "UPDATE enterprise_programme_registry "
            "   SET status=?, held_from_phase_code=?, updated_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=?",
            (PSEUDO_STATE_STATUS[target], held_from, tenant_id, programme_id),
        )
        c.execute(
            "INSERT INTO enterprise_workflow_transitions "
            "(tenant_id, programme_id, from_phase_code, to_phase_code, actor_user_id, note) "
            "VALUES (?,?,?,?,?,?)",
            (tenant_id, programme_id, current_phase, target, user_id, note),
        )
        action = ("ENTERPRISE_PROGRAMME_HELD" if target in HOLD_STATES
                  else "ENTERPRISE_PROGRAMME_TERMINATED")
        gates.require_audit_written(
            audit(action, user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id, "state": target,
                           "held_from": held_from, "note": note}),
            f"programme {target.lower()}",
        )
    return get_programme_state(c, tenant_id, programme_id)


def resume_from_hold(c, tenant_id: str, programme_id: int, user_id: int,
                     *, comment: str | None = None, audit=None) -> dict:
    """Bring a SUSPENDED / ON_HOLD programme back to the phase it was held from.

    Input:  connection, tenant id, programme id, acting user, optional comment,
            optional audit hook.
    Output: the new state dict.
    Raises: EnterprisePermissionError (403), EnterpriseGateError (409).

    Doc 3: "Returning from SUSPENDED or ON_HOLD requires an approval record and audit
    event." So this needs `programme.approve` -- a strictly HIGHER bar than the
    `programme.edit` that ordinary transitions need, and it writes an approval row.

    The asymmetry is the point. A Programme Manager holds `programme.edit`: he can drive
    the lifecycle, and he can put a programme on hold. He does not hold
    `programme.approve`, so he cannot lift the hold he just applied -- it has to escalate
    to a sponsor, director or steering committee. A hold that the same person could step
    back over would be a speed bump, not a control.

    (Note what this does NOT claim: it is not four-eyes. An Enterprise Owner holds both
    permissions and can hold and resume alone. Making that impossible needs a separate
    "approver != requester" rule, which doc 3 does not ask for and which would deadlock
    the single-admin organisations that are most of this app's users today.)

    It resumes the remembered phase. It cannot be used to jump somewhere new.
    """
    row = _load_programme(c, tenant_id, programme_id)  # C13 first -- see transition note
    rbac.require_permission(c, tenant_id, user_id, "programme.approve",
                            programme_id=programme_id)
    status, held_from = row[3], row[4]

    if status not in ("Suspended", "On Hold"):
        raise EnterpriseGateError("LIFECYCLE", f"programme is not held (status {status})")
    if not held_from:
        raise EnterpriseGateError(
            "LIFECYCLE", "the held-from phase was not recorded; cannot resume safely"
        )

    audit = audit or _audit_on(c)
    with _atomic(c):
        c.execute(
            "UPDATE enterprise_programme_registry "
            "   SET status=?, current_phase_code=?, held_from_phase_code=NULL, "
            "       updated_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=?",
            (PHASE_STATUS[held_from], held_from, tenant_id, programme_id),
        )
        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, comment) VALUES (?,?,?,?,?,?,?,?)",
            (tenant_id, programme_id, "programme", str(programme_id), "resume_from_hold",
             "Approved", user_id, comment),
        )
        c.execute(
            "INSERT INTO enterprise_workflow_transitions "
            "(tenant_id, programme_id, from_phase_code, to_phase_code, actor_user_id, note) "
            "VALUES (?,?,?,?,?,?)",
            (tenant_id, programme_id, status, held_from, user_id, comment),
        )
        gates.require_audit_written(
            audit("ENTERPRISE_PROGRAMME_RESUMED", user_id=user_id, tenant_id=tenant_id,
                  details={"programme_id": programme_id, "resumed_to": held_from}),
            "programme resume",
        )
    return get_programme_state(c, tenant_id, programme_id)
