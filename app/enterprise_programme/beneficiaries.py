"""Enterprise Solar Programme -- the beneficiary register (rebuild, slice 5).

WHAT A BENEFICIARY IS
---------------------
The school, clinic, farm or community facility the programme exists to serve. It is the
unit that BECOMES a project: doc 3's project status list literally begins at "Beneficiary
Registered", and slice 7 turns a qualified beneficiary plus an approved template version
into a real SolarPro project.

So this module does not invent a status vocabulary. It uses the first six of doc 3's
PROJECT_STATUSES verbatim (constants.BENEFICIARY_STATUSES). A parallel set would have to be
mapped onto the project one at generation time, and a mapping is somewhere for the two to
disagree about what a site's state actually is.

THE 22 FIELDS ARE THE SAME 22 FIELDS
------------------------------------
constants.BENEFICIARY_FIELD_SPEC is what this register stores, what the import mapper
fills, what the manual form renders -- and it is keyed identically to the list a TEMPLATE
draws on when it declares `required_beneficiary_fields` (slice 4). That is deliberate and
a test enforces it: a template must not be able to demand a field the register cannot hold,
because the result is a site that can never qualify with nothing in the UI to explain why.

WHY APPROVAL IS A SEPARATE ACT FROM REGISTRATION
------------------------------------------------
Anyone with `beneficiary.import` (a District Coordinator, a Beneficiary Officer) can put a
site into the register. Only `beneficiary.approve` (a Programme Manager, a Regional
Manager) can admit it -- moving it to Qualification Pending, which is what makes it
eligible for the slice-6 survey and therefore, eventually, for money being spent on it.

The field officer who collects the data is not the person who decides the programme will
serve it. Control C02 (no beneficiary becomes a project without qualification) then sits on
top of that in slice 6.
"""

from __future__ import annotations

import unicodedata

from . import rbac, txn
from .constants import (
    BENEFICIARY_FIELD_SPEC,
    BENEFICIARY_STATUSES,
    BENEFICIARY_TRANSITIONS,
    BENEFICIARY_TYPES,
    BUILDING_TYPES,
    ENERGY_SOURCES,
    FUNDING_ELIGIBILITY,
    OWNERSHIP_TYPES,
    SOCIAL_IMPACT_CLASSES,
)
from .gates import EnterpriseGateError

_BENEFICIARY_TYPE_CODES = frozenset(code for code, _ in BENEFICIARY_TYPES)

# The vocabularies a `select` field may draw from, keyed by the `source` name in
# BENEFICIARY_FIELD_SPEC -- so the list the form offers and the list the validator accepts
# are provably the same object, exactly as in templates.py.
_VOCABULARIES: dict[str, frozenset[str]] = {
    "OWNERSHIP_TYPES":       frozenset(c for c, _ in OWNERSHIP_TYPES),
    "BUILDING_TYPES":        frozenset(c for c, _ in BUILDING_TYPES),
    "ENERGY_SOURCES":        frozenset(c for c, _ in ENERGY_SOURCES),
    "FUNDING_ELIGIBILITY":   frozenset(c for c, _ in FUNDING_ELIGIBILITY),
    "SOCIAL_IMPACT_CLASSES": frozenset(c for c, _ in SOCIAL_IMPACT_CLASSES),
}

# The attribute columns, in the order migration 027 declares them.
_FIELD_KEYS: list[str] = [f["key"] for f in BENEFICIARY_FIELD_SPEC]

# Editable while nobody has committed anything to it. Once a project has been generated the
# record is the specification of something being built, and changing it silently would make
# the register and the site disagree -- the same reasoning that freezes a template version.
_EDITABLE_STATUSES = frozenset({
    "Beneficiary Registered", "Qualification Pending", "Not Qualified",
})


class BeneficiaryError(EnterpriseGateError):
    """A register rule was broken. Carries a control code so a route can 404 a C13."""


# --- SQLite fallback schema (mirrors migration 027) --------------------------
# Local dev and the test suite run on SQLite, where the .sql migrations never execute.
# Creates tables only when ABSENT -- it must never widen or alter an existing column,
# because CREATE-IF-NOT-EXISTS silently does nothing against a table whose shape has
# drifted, and you then fail far from the cause
# (see memory: feedback-solar-create-if-not-exists-schema-drift).

_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS enterprise_beneficiaries (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id               TEXT NOT NULL,
        programme_id            INTEGER NOT NULL,
        area_id                 INTEGER,
        code                    TEXT NOT NULL,
        beneficiary_type        TEXT NOT NULL,
        status                  TEXT NOT NULL DEFAULT 'Beneficiary Registered',
        name                    TEXT NOT NULL,
        region                  TEXT,
        district                TEXT,
        community               TEXT,
        address                 TEXT,
        gps_coordinates         TEXT,
        latitude                REAL,
        longitude               REAL,
        contact_person          TEXT,
        contact_details         TEXT,
        ownership               TEXT,
        building_type           TEXT,
        occupancy               REAL,
        existing_energy_source  TEXT,
        electricity_consumption REAL,
        tariff                  REAL,
        generator_details       TEXT,
        roof_area               REAL,
        land_availability       REAL,
        critical_loads          TEXT,
        priority_loads          TEXT,
        funding_eligibility     TEXT,
        social_impact_class     TEXT,
        priority_ranking        REAL,
        import_batch_id         INTEGER,
        approved_by_user_id     INTEGER,
        approved_at             TEXT,
        created_by_user_id      INTEGER,
        created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
        -- Present in migration 027 and missing here until the Supervisor pass. Without it a
        -- test can give a beneficiary an area_id belonging to another tenant and SQLite will
        -- take it, while Postgres refuses -- a divergence the suite could never catch.
        FOREIGN KEY (tenant_id, area_id)
            REFERENCES enterprise_geographic_areas (tenant_id, id),
        UNIQUE (tenant_id, id),
        -- So a project link can prove its beneficiary belongs to the programme it claims to
        -- serve (control C14). See migration 027.
        UNIQUE (tenant_id, programme_id, id),
        CONSTRAINT ck_ent_beneficiary_status CHECK (status IN (
            'Beneficiary Registered', 'Qualification Pending', 'Qualified',
            'Not Qualified', 'Template Assigned', 'Project Generated',
            'Rejected', 'Archived'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_beneficiary_code "
    "  ON enterprise_beneficiaries (tenant_id, programme_id, code)",
    "CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_status "
    "  ON enterprise_beneficiaries (tenant_id, programme_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_dup_probe "
    "  ON enterprise_beneficiaries (tenant_id, programme_id, community, name)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_import_batches (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        programme_id       INTEGER NOT NULL,
        filename           TEXT,
        status             TEXT NOT NULL DEFAULT 'Staged',
        column_mapping     TEXT NOT NULL DEFAULT '{}',
        default_type       TEXT NOT NULL DEFAULT '',
        total_rows         INTEGER NOT NULL DEFAULT 0,
        valid_rows         INTEGER NOT NULL DEFAULT 0,
        error_rows         INTEGER NOT NULL DEFAULT 0,
        duplicate_rows     INTEGER NOT NULL DEFAULT 0,
        imported_rows      INTEGER NOT NULL DEFAULT 0,
        created_by_user_id INTEGER,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        committed_at       TEXT,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
        UNIQUE (tenant_id, id),
        CONSTRAINT ck_ent_import_batch_status CHECK (status IN
            ('Staged', 'Committed', 'Cancelled'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS enterprise_import_rows (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id      TEXT NOT NULL,
        batch_id       INTEGER NOT NULL,
        row_no         INTEGER NOT NULL,
        raw_json       TEXT NOT NULL DEFAULT '{}',
        mapped_json    TEXT NOT NULL DEFAULT '{}',
        status         TEXT NOT NULL DEFAULT 'Valid',
        errors_json    TEXT NOT NULL DEFAULT '[]',
        beneficiary_id INTEGER,
        FOREIGN KEY (tenant_id, batch_id)
            REFERENCES enterprise_import_batches (tenant_id, id) ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, beneficiary_id)
            REFERENCES enterprise_beneficiaries (tenant_id, id) ON DELETE SET NULL,
        CONSTRAINT ck_ent_import_row_status CHECK (status IN
            ('Valid', 'Error', 'Duplicate', 'Imported', 'Skipped'))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_import_row "
    "  ON enterprise_import_rows (tenant_id, batch_id, row_no)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_site_qualifications (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        beneficiary_id     INTEGER NOT NULL,
        scores_json        TEXT NOT NULL DEFAULT '{}',
        total_score        REAL,
        decision           TEXT,
        notes              TEXT,
        scored_by_user_id  INTEGER,
        scored_at          TEXT,
        decided_by_user_id INTEGER,
        decided_at         TEXT,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, beneficiary_id)
            REFERENCES enterprise_beneficiaries (tenant_id, id) ON DELETE CASCADE,
        UNIQUE (tenant_id, id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS enterprise_project_links (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id           TEXT NOT NULL,
        programme_id        INTEGER NOT NULL,
        beneficiary_id      INTEGER NOT NULL,
        template_version_id INTEGER NOT NULL,
        project_kind        TEXT NOT NULL,
        project_id          INTEGER NOT NULL,
        status              TEXT NOT NULL DEFAULT 'Project Generated',
        engineering_approved_by_user_id INTEGER,
        engineering_approved_at TEXT,
        generated_by_user_id INTEGER,
        created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id, programme_id)
            REFERENCES enterprise_programme_registry (tenant_id, id) ON DELETE CASCADE,
        -- Programme-scoped, and the template version is a real FK: both halves of control
        -- C14's traceability chain. See migration 027.
        FOREIGN KEY (tenant_id, programme_id, beneficiary_id)
            REFERENCES enterprise_beneficiaries (tenant_id, programme_id, id)
            ON DELETE CASCADE,
        FOREIGN KEY (tenant_id, template_version_id)
            REFERENCES enterprise_template_versions (tenant_id, id),
        UNIQUE (tenant_id, id)
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ent_project_link_beneficiary "
    "  ON enterprise_project_links (tenant_id, beneficiary_id)",
    """
    CREATE TABLE IF NOT EXISTS enterprise_jobs (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id          TEXT NOT NULL,
        programme_id       INTEGER,
        job_type           TEXT NOT NULL,
        status             TEXT NOT NULL DEFAULT 'Queued',
        payload_json       TEXT NOT NULL DEFAULT '{}',
        total_items        INTEGER NOT NULL DEFAULT 0,
        done_items         INTEGER NOT NULL DEFAULT 0,
        failed_items       INTEGER NOT NULL DEFAULT 0,
        last_error         TEXT,
        attempts           INTEGER NOT NULL DEFAULT 0,
        created_by_user_id INTEGER,
        created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at         TEXT,
        finished_at        TEXT,
        CONSTRAINT ck_ent_job_status CHECK (status IN
            ('Queued', 'Running', 'Completed', 'Failed', 'Cancelled'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ent_job_drain ON enterprise_jobs (status, created_at)",
    # THE SQLITE MIRROR MUST BE A MIRROR (Supervisor slice-5, MED). These six exist in
    # migration 027 and were missing here. Indexes are "only" performance -- but a schema the
    # tests run against that is not the schema production runs against is how a divergence
    # ships: the suite goes green on a shape nobody deploys.
    "CREATE INDEX IF NOT EXISTS ix_ent_beneficiary_area "
    "  ON enterprise_beneficiaries (tenant_id, area_id)",
    "CREATE INDEX IF NOT EXISTS ix_ent_import_batch_programme "
    "  ON enterprise_import_batches (tenant_id, programme_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_ent_import_row_status "
    "  ON enterprise_import_rows (tenant_id, batch_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_ent_qualification_beneficiary "
    "  ON enterprise_site_qualifications (tenant_id, beneficiary_id)",
    "CREATE INDEX IF NOT EXISTS ix_ent_project_link_programme "
    "  ON enterprise_project_links (tenant_id, programme_id)",
    "CREATE INDEX IF NOT EXISTS ix_ent_job_programme "
    "  ON enterprise_jobs (tenant_id, programme_id, status)",
]


def ensure_schema(c) -> None:
    """Create the slice-5 tables on SQLite. No-op on Postgres (migration 027 owns them)."""
    if txn.is_postgres():
        return
    for stmt in _SQLITE_SCHEMA:
        c.execute(stmt)


# --- validation --------------------------------------------------------------


def validate_fields(fields: dict, *, require_name: bool = True) -> tuple[dict, list[str]]:
    """Check a beneficiary's attributes against BENEFICIARY_FIELD_SPEC.

    Input:  the submitted attribute dict; whether `name` is mandatory.
    Output: (clean dict, list of human-readable problems). Does NOT raise -- the importer
            needs to record a bad row and carry on to the next one, and a raising validator
            would make it abort the whole file on the first typo.

    Unknown keys are DROPPED, a known key with a bad value is a PROBLEM. Same rule as
    templates.validate_parameters, and for the same reason: silently discarding a value the
    user typed would tell them their record says something it does not.
    """
    clean: dict = {}
    problems: list[str] = []

    for field in BENEFICIARY_FIELD_SPEC:
        key, kind = field["key"], field["kind"]
        label = key.replace("_", " ")
        raw = fields.get(key)

        if raw is None or (isinstance(raw, str) and not raw.strip()):
            # `require_name` suppresses the check for the NAME only. Written as
            # `required and require_name` it suppressed EVERY required field -- correct today
            # only because `name` happens to be the sole one. The day a second field is marked
            # required, a partial update would silently stop enforcing it.
            if field.get("required") and (key != "name" or require_name):
                problems.append(f"{label} is required")
            continue

        if kind == "text":
            clean[key] = str(raw).strip()

        elif kind == "number":
            try:
                n = float(str(raw).strip().replace(",", ""))
            except (TypeError, ValueError):
                problems.append(f"{label}: {raw!r} is not a number")
                continue
            # float('NaN') and float('Infinity') both SUCCEED and NaN fails every
            # comparison silently -- the same hole Codex found in the template validator.
            if n != n or n in (float("inf"), float("-inf")):
                problems.append(f"{label}: {raw!r} is not a finite number")
                continue
            if n < 0:
                problems.append(f"{label} cannot be negative")
                continue
            clean[key] = int(n) if n.is_integer() else n

        elif kind == "select":
            value = str(raw).strip().lower().replace(" ", "_")
            allowed = _VOCABULARIES[field["source"]]
            if value not in allowed:
                problems.append(
                    f"{label}: {raw!r} is not one of {', '.join(sorted(allowed))}"
                )
                continue
            clean[key] = value

        elif kind == "gps":
            parsed = _parse_gps(raw)
            if parsed is None:
                problems.append(
                    f"{label}: {raw!r} is not a coordinate (expected 'lat, lon')"
                )
                continue
            lat, lon = parsed
            clean["gps_coordinates"] = f"{lat},{lon}"
            clean["latitude"] = lat
            clean["longitude"] = lon

    return clean, problems


def _parse_gps(raw) -> tuple[float, float] | None:
    """'5.6037, -0.1870' -> (5.6037, -0.187), or None if it is not a real coordinate.

    Parsed on WRITE, and the two numbers stored alongside the string, so that a map query
    or a distance calculation never has to parse a text column -- and so that a nonsense
    coordinate is caught by the person typing it rather than by a report six months later.
    """
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        parts = [str(raw[0]), str(raw[1])]
    else:
        parts = [p.strip() for p in str(raw).replace(";", ",").split(",")]
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except (TypeError, ValueError):
        return None
    if lat != lat or lon != lon:                     # NaN
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return lat, lon


# --- reading -----------------------------------------------------------------


_SELECT_COLUMNS = (
    "id, programme_id, code, beneficiary_type, status, area_id, import_batch_id, "
    "approved_by_user_id, created_at, " + ", ".join(_FIELD_KEYS) + ", latitude, longitude"
)


def _row_to_dict(row) -> dict:
    """Turn a _SELECT_COLUMNS row into the shape the templates and services read."""
    head = ["id", "programme_id", "code", "beneficiary_type", "status", "area_id",
            "import_batch_id", "approved_by_user_id", "created_at"]
    keys = head + _FIELD_KEYS + ["latitude", "longitude"]
    out = dict(zip(keys, row))
    out["editable"] = out["status"] in _EDITABLE_STATUSES
    out["next_states"] = BENEFICIARY_TRANSITIONS.get(out["status"], ())
    return out


def _load(c, tenant_id: str, beneficiary_id: int) -> dict:
    """Fetch a beneficiary IN THIS TENANT, or raise C13.

    The tenant id is in the WHERE clause, not checked afterwards: a beneficiary in another
    organisation and one that does not exist are the same answer, and the routes turn C13
    into a 404. Telling a stranger "that exists, but is not yours" IS the leak.
    """
    row = c.execute(
        f"SELECT {_SELECT_COLUMNS} FROM enterprise_beneficiaries "
        " WHERE tenant_id=? AND id=?",
        (tenant_id, beneficiary_id),
    ).fetchone()
    if row is None:
        raise BeneficiaryError("C13", "no such beneficiary in this organisation")
    return _row_to_dict(row)


def get_beneficiary(c, tenant_id: str, beneficiary_id: int) -> dict:
    """One beneficiary, tenant-scoped. Raises BeneficiaryError(C13) -> 404."""
    return _load(c, tenant_id, beneficiary_id)


def list_beneficiaries(c, tenant_id: str, programme_id: int, *,
                       status: str | None = None, limit: int = 500) -> list[dict]:
    """The register for one programme, newest first.

    Input:  connection, tenant id, programme id, optional status filter, a row cap.
    Output: list of dicts.

    The cap is real and the caller reports it. A programme with 4000 schools must not
    render 4000 table rows into one page and call that a feature.
    """
    sql = (f"SELECT {_SELECT_COLUMNS} FROM enterprise_beneficiaries "
           " WHERE tenant_id=? AND programme_id=?")
    params: list = [tenant_id, programme_id]
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return [_row_to_dict(r) for r in c.execute(sql, tuple(params)).fetchall()]


def count_by_status(c, tenant_id: str, programme_id: int) -> dict[str, int]:
    """{status: count} for the whole register -- computed by the DATABASE, not by counting
    a truncated page in Python."""
    rows = c.execute(
        "SELECT status, COUNT(*) FROM enterprise_beneficiaries "
        " WHERE tenant_id=? AND programme_id=? GROUP BY status",
        (tenant_id, programme_id),
    ).fetchall()
    counts = {s: 0 for s in BENEFICIARY_STATUSES}
    for status, n in rows:
        counts[status] = int(n)
    return counts


def canonical_code(code: str | None) -> str:
    """The one true form of a beneficiary code. Every write and every probe uses this.

    Input:  a code as a human or a spreadsheet typed it.
    Output: NFKC-normalised, uppercased, punctuation-collapsed. '' for nothing.

    WHY (Codex slice-5, HIGH). The unique index on (tenant, programme, code) is what makes
    re-importing a spreadsheet a no-op rather than a doubled register -- and a raw string
    comparison is not an identity check. `KP-01`, `kp-01` and `KP 01` are the same school to
    everybody except the database, and a ministry's spreadsheet contains all three. Worse,
    the same name typed on two machines can differ by Unicode composition alone (e.g. an
    accented character as one code point or as two), which no human will ever see and which
    would silently import the same site twice.

    So the code is canonicalised ONCE, here, and the canonical form is what is STORED. The
    index then means what it looks like it means.
    """
    if not code:
        return ""
    text = unicodedata.normalize("NFKC", str(code)).strip().upper()
    out = []
    for ch in text:
        out.append(ch if ch.isalnum() else "-")
    collapsed = "".join(out)
    while "--" in collapsed:
        collapsed = collapsed.replace("--", "-")
    return collapsed.strip("-")[:80]


def _canonical_text(value) -> str:
    """NFKC + casefold, for comparing a name or a community across machines."""
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def find_duplicate(c, tenant_id: str, programme_id: int, *, code: str | None,
                   name: str | None, community: str | None) -> int | None:
    """Is this beneficiary already in the register? Returns its id, or None.

    Input:  connection, tenant id, programme id, the candidate's code, name and community.
    Output: the existing beneficiary's id, or None.

    TWO probes, in order of confidence:
      1. The CODE. It is unique per programme by index -- this is a definitive answer, and
         it is what makes re-importing the same spreadsheet a no-op rather than a disaster.
      2. The NAME within the same COMMUNITY. Not definitive, and deliberately not treated
         as such: a match here marks the row Duplicate for a HUMAN to look at, it does not
         throw it away. Two schools in one village really can share a name.
    """
    canonical = canonical_code(code)
    if canonical:
        row = c.execute(
            "SELECT id FROM enterprise_beneficiaries "
            " WHERE tenant_id=? AND programme_id=? AND code=?",
            (tenant_id, programme_id, canonical),
        ).fetchone()
        if row:
            return int(row[0])

    if name and community:
        # Compared in PYTHON, not in SQL. LOWER() in SQLite is ASCII-only and neither engine
        # normalises Unicode composition, so "Ho Presbyterian" typed on two machines can be
        # two different strings that no human could tell apart. The candidate set is narrow
        # (one community in one programme, and the index makes it cheap), so the comparison
        # can afford to be correct.
        target_name = _canonical_text(name)
        target_community = _canonical_text(community)
        rows = c.execute(
            "SELECT id, name, community FROM enterprise_beneficiaries "
            " WHERE tenant_id=? AND programme_id=? AND community IS NOT NULL",
            (tenant_id, programme_id),
        ).fetchall()
        for bid, existing_name, existing_community in rows:
            if (_canonical_text(existing_name) == target_name
                    and _canonical_text(existing_community) == target_community):
                return int(bid)

    return None


class DuplicateIndex:
    """Every identity already spoken for in one programme -- read ONCE, then asked in memory.

    TWO PROBLEMS, ONE OBJECT (Supervisor slice-5, HIGH + MED):

    1. `find_duplicate()` only ever looked at the REGISTER, and nothing from the current file
       is in the register until commit. So a spreadsheet that listed Kpando Senior High twice
       -- the exact case this module exists for, two districts both claiming the same school
       -- staged both rows Valid and imported the school twice. Where the two rows shared a
       code, it was worse than a duplicate: the preview promised "0 duplicates", and the
       second row then died on the unique index at commit and was reported as a FAILURE, for
       a row the preview had just vouched for.

    2. Asked once per row, the name+community probe re-read every beneficiary in the
       programme and re-normalised each one in Python. A 2000-row import into a 4000-site
       programme is 8 million normalisations inside one HTTP request, on a 512 MiB instance
       behind a 120-second timeout. The import did not fail; the worker was killed.

    So the register is read once into two maps, and rows already seen IN THIS FILE are added
    to the same maps as they are staged. First writer wins: the earlier row is the original
    and the later one is the duplicate, which is the order a human reading the sheet expects.
    """

    def __init__(self):
        # canonical code            -> ("register", id) | ("row", row_no)
        self._by_code: dict[str, tuple[str, int]] = {}
        # (canonical name, canonical community) -> same
        self._by_name: dict[tuple[str, str], tuple[str, int]] = {}

    @classmethod
    def for_programme(cls, c, tenant_id: str, programme_id: int) -> "DuplicateIndex":
        """One query. The caller must already have established C13 on the programme."""
        index = cls()
        rows = c.execute(
            "SELECT id, code, name, community FROM enterprise_beneficiaries "
            " WHERE tenant_id=? AND programme_id=?",
            (tenant_id, programme_id),
        ).fetchall()
        for bid, code, name, community in rows:
            index.remember(("register", int(bid)), code=code, name=name, community=community)
        return index

    def find(self, *, code: str | None, name: str | None,
             community: str | None) -> tuple[str, int] | None:
        """("register", id) if it is already imported, ("row", n) if it is earlier in this
        file, None if it is new. The code is definitive; name+community is a flag for a
        human, not a verdict -- see find_duplicate()."""
        canonical = canonical_code(code)
        if canonical and canonical in self._by_code:
            return self._by_code[canonical]
        if name and community:
            key = (_canonical_text(name), _canonical_text(community))
            if key in self._by_name:
                return self._by_name[key]
        return None

    def remember(self, marker: tuple[str, int], *, code: str | None, name: str | None,
                 community: str | None) -> None:
        """setdefault, not assignment: the FIRST row to claim an identity keeps it."""
        canonical = canonical_code(code)
        if canonical:
            self._by_code.setdefault(canonical, marker)
        if name and community:
            self._by_name.setdefault(
                (_canonical_text(name), _canonical_text(community)), marker)


# --- writing -----------------------------------------------------------------


def _load_programme(c, tenant_id: str, programme_id: int) -> None:
    """C13 for the PARENT. Raised before any permission check, so a cross-tenant write
    answers 404 rather than 403 -- a 403 confirms the programme exists."""
    row = c.execute(
        "SELECT 1 FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
        (tenant_id, programme_id),
    ).fetchone()
    if row is None:
        raise BeneficiaryError("C13", "no such programme in this organisation")


def create_beneficiary(c, tenant_id: str, user_id: int, programme_id: int, *,
                       code: str, name: str, beneficiary_type: str, fields: dict | None = None,
                       import_batch_id: int | None = None, audit=None) -> int:
    """Add one site to the register. It starts at "Beneficiary Registered".

    Input:  connection, tenant id, acting user, programme id, code + name + type, the
            optional attribute dict, the import batch this came from (if any), audit hook.
    Output: the new beneficiary id.
    Raises: EnterprisePermissionError (403), BeneficiaryError (409 / C13).

    Registering is NOT approving. A field officer with `beneficiary.import` puts a site in;
    somebody with `beneficiary.approve` decides the programme will actually serve it.
    """
    _load_programme(c, tenant_id, programme_id)      # C13 FIRST -- before authz
    rbac.require_permission(c, tenant_id, user_id, "beneficiary.import",
                            programme_id=programme_id)

    # CANONICALISED, not merely stripped. The unique index below is the register's identity
    # check, and it can only mean what it looks like it means if the code it indexes is in
    # one form. See canonical_code().
    code = canonical_code(code)
    name = (name or "").strip()
    if not code or not name:
        raise BeneficiaryError("BENEFICIARY", "a beneficiary needs a code and a name")
    if beneficiary_type not in _BENEFICIARY_TYPE_CODES:
        raise BeneficiaryError(
            "BENEFICIARY", f"unknown beneficiary type {beneficiary_type!r}"
        )

    clean, problems = validate_fields(dict(fields or {}, name=name))
    if problems:
        raise BeneficiaryError("BENEFICIARY", "; ".join(problems))
    clean["name"] = name

    columns = ["tenant_id", "programme_id", "code", "beneficiary_type",
               "import_batch_id", "created_by_user_id"]
    values: list = [tenant_id, programme_id, code, beneficiary_type, import_batch_id,
                    user_id]
    for key, value in clean.items():
        columns.append(key)
        values.append(value)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        placeholders = ",".join("?" for _ in columns)
        try:
            cur = c.execute(
                f"INSERT INTO enterprise_beneficiaries ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                tuple(values),
            )
        except Exception as e:
            if _is_integrity_error(e):
                # The unique index on (tenant, programme, code) is what makes re-importing
                # the same spreadsheet a no-op instead of a duplicated register. Report it
                # as a conflict the operator can act on, not a 500.
                raise BeneficiaryError(
                    "BENEFICIARY",
                    f"a beneficiary with code {code!r} is already in this programme",
                ) from e
            raise
        beneficiary_id = txn.inserted_id(c, cur)

        _require_audit(
            audit("ENTERPRISE_BENEFICIARY_REGISTERED", user_id=user_id,
                  tenant_id=tenant_id,
                  details={"programme_id": programme_id, "beneficiary_id": beneficiary_id,
                           "code": code, "beneficiary_type": beneficiary_type,
                           "import_batch_id": import_batch_id}),
            "beneficiary register",
        )
    return beneficiary_id


def update_beneficiary(c, tenant_id: str, user_id: int, beneficiary_id: int,
                       fields: dict, *, audit=None) -> dict:
    """Correct a beneficiary's attributes.

    Input:  connection, tenant id, acting user, beneficiary id, the new attributes, audit.
    Output: the updated beneficiary.
    Raises: EnterprisePermissionError (403), BeneficiaryError (409 / C13).

    Refused once a project has been generated from it. At that point the record is the
    specification of something being built, and editing it silently would put the register
    and the site into disagreement with nothing to say which one moved -- the same argument
    that freezes a template version in slice 4.
    """
    existing = _load(c, tenant_id, beneficiary_id)          # C13 first
    rbac.require_permission(c, tenant_id, user_id, "beneficiary.import",
                            programme_id=existing["programme_id"])

    if existing["status"] not in _EDITABLE_STATUSES:
        raise BeneficiaryError(
            "BENEFICIARY",
            f"this beneficiary is {existing['status']}; its record can no longer be "
            "edited (a project may already have been generated from it)",
        )

    # A PARTIAL update: the caller sends the fields they are changing, not the whole record.
    # Demanding `name` here would make "correct this roof area" impossible without also
    # re-sending a name that is already correct -- and an absent field is left alone rather
    # than blanked, so nothing can be cleared by omission either.
    clean, problems = validate_fields(fields, require_name=False)
    if problems:
        raise BeneficiaryError("BENEFICIARY", "; ".join(problems))
    if not clean:
        return existing

    assignments = ", ".join(f"{k}=?" for k in clean)
    values = list(clean.values())

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        # Conditional on the status we READ. Between the check above and this write another
        # request can approve or generate from this beneficiary, and the edit would then
        # land on a record that is no longer editable. (The same race Codex found in the
        # template engine.)
        cur = c.execute(
            f"UPDATE enterprise_beneficiaries SET {assignments}, "
            "       updated_at=CURRENT_TIMESTAMP "
            " WHERE tenant_id=? AND id=? AND status=?",
            tuple(values + [tenant_id, beneficiary_id, existing["status"]]),
        )
        if getattr(cur, "rowcount", -1) == 0:
            raise BeneficiaryError(
                "BENEFICIARY",
                "somebody else changed this beneficiary while you were editing it; "
                "reload and try again",
            )
        _require_audit(
            audit("ENTERPRISE_BENEFICIARY_UPDATED", user_id=user_id, tenant_id=tenant_id,
                  details={"beneficiary_id": beneficiary_id,
                           "fields": sorted(clean.keys())}),
            "beneficiary update",
        )
    return _load(c, tenant_id, beneficiary_id)


def transition_beneficiary(c, tenant_id: str, user_id: int, beneficiary_id: int,
                           target: str, *, comment: str | None = None,
                           ai_recommendation_id: int | None = None, audit=None) -> dict:
    """Move a beneficiary through the register's state machine.

    Input:  connection, tenant id, acting user, beneficiary id, the target status,
            optional comment, optional AI recommendation attached as EVIDENCE, audit hook.
    Output: the updated beneficiary.
    Raises: EnterprisePermissionError (403), BeneficiaryError (409 / C13).

    Release 1 owns two of these moves and they are the ones that matter:

      Beneficiary Registered -> Qualification Pending   ADMIT it to the programme
      Beneficiary Registered -> Rejected                turn it away

    Both need `beneficiary.approve`, NOT the `beneficiary.import` that put the record here.
    The field officer who collects the data does not decide that the programme will spend
    money on the site. C11 applies: an AI recommendation is evidence, never the decision.

    The later moves (Qualified, Template Assigned, Project Generated) are in the vocabulary
    so the machine is complete, but slices 6 and 7 add the guards that make them legal --
    they are not reachable through this function's permission today.
    """
    # C11 FIRST: it touches no database, so it leaks nothing about what exists, and a
    # non-human actor should be told it may not decide rather than that it lacks a
    # permission it could never legitimately hold.
    from . import gates as gates_mod
    gates_mod.require_human_approval_actor(user_id, ai_recommendation_id)

    existing = _load(c, tenant_id, beneficiary_id)          # C13 next
    rbac.require_permission(c, tenant_id, user_id, "beneficiary.approve",
                            programme_id=existing["programme_id"])

    if target not in BENEFICIARY_STATUSES:
        raise BeneficiaryError("BENEFICIARY", f"unknown status {target!r}")

    legal = BENEFICIARY_TRANSITIONS.get(existing["status"], ())
    if target not in legal:
        raise BeneficiaryError(
            "BENEFICIARY",
            f"this beneficiary is {existing['status']}; it cannot become {target} "
            f"(allowed: {', '.join(legal) or 'none'})",
        )

    # Slice 6 owns qualification and slice 7 owns generation. Until their guards exist,
    # this function must not be a way to hand-wave a site into Qualified -- which would
    # walk straight around control C02 (no beneficiary becomes a project without
    # qualification) before C02 has anything to say.
    if target in ("Qualified", "Not Qualified"):
        raise BeneficiaryError(
            "C02",
            "site qualification ships in slice 6; a beneficiary cannot be marked "
            "Qualified by hand",
        )
    if target in ("Template Assigned", "Project Generated"):
        raise BeneficiaryError(
            "C03",
            "project generation ships in slice 7; a beneficiary cannot be marked "
            "generated by hand",
        )

    approving = target == "Qualification Pending"

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        if approving:
            cur = c.execute(
                "UPDATE enterprise_beneficiaries "
                "   SET status=?, approved_by_user_id=?, approved_at=CURRENT_TIMESTAMP, "
                "       updated_at=CURRENT_TIMESTAMP "
                " WHERE tenant_id=? AND id=? AND status=?",
                (target, user_id, tenant_id, beneficiary_id, existing["status"]),
            )
        else:
            cur = c.execute(
                "UPDATE enterprise_beneficiaries "
                "   SET status=?, updated_at=CURRENT_TIMESTAMP "
                " WHERE tenant_id=? AND id=? AND status=?",
                (target, tenant_id, beneficiary_id, existing["status"]),
            )
        if getattr(cur, "rowcount", -1) == 0:
            raise BeneficiaryError(
                "BENEFICIARY",
                f"this beneficiary is no longer {existing['status']} -- somebody else "
                "changed it. Reload and try again.",
            )

        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, ai_recommendation_id, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_id, existing["programme_id"], "beneficiary", str(beneficiary_id),
             "beneficiary_register", target, user_id, ai_recommendation_id, comment),
        )

        _require_audit(
            audit("ENTERPRISE_BENEFICIARY_TRANSITION", user_id=user_id,
                  tenant_id=tenant_id,
                  details={"beneficiary_id": beneficiary_id,
                           "programme_id": existing["programme_id"],
                           "from": existing["status"], "to": target,
                           "ai_recommendation_id": ai_recommendation_id}),
            f"beneficiary {target.lower()}",
        )
    return _load(c, tenant_id, beneficiary_id)


def _require_audit(written: bool, what: str) -> None:
    """C12 for this module. Delegates to the same guard the lifecycle uses."""
    from . import gates as gates_mod
    gates_mod.require_audit_written(written, what)


def _is_integrity_error(e: Exception) -> bool:
    """Is this a UNIQUE / CHECK / FK violation, on either driver?

    Matched by CLASS NAME rather than by importing psycopg2.IntegrityError, which is not
    installed in the SQLite dev environment. Both drivers name it `IntegrityError`
    (DB-API 2.0 requires it).
    """
    return any(k.__name__ == "IntegrityError" for k in type(e).__mro__)
