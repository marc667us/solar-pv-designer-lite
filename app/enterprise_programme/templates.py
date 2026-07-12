"""Enterprise Solar Programme -- the template engine (rebuild, slice 4).

WHAT A TEMPLATE IS FOR
----------------------
A programme installs the same thing hundreds of times. A template is the definition of
that thing -- what system configuration, what standard sizes, what equipment, what a
beneficiary must supply before it counts as a site. Slice 7 generates projects from it.
Without it, "generate 400 school projects" means 400 hand-built designs, and the whole
premise of a programme (standardise once, repeat safely) is gone.

THE ONE RULE EVERYTHING ELSE SERVES: A VERSION IS FROZEN THE MOMENT IT LEAVES DRAFT
-----------------------------------------------------------------------------------
The master prompt (s13) says it plainly: "Projects created from templates must retain the
template version used. Later template changes must not silently overwrite completed or
approved project designs."

That is not a nice-to-have, it is the difference between an auditable programme and an
unauditable one. If version 3 could be edited after a school was built from it, then the
question "what were we supposed to have installed at Kpando SHS?" has no answer -- the
template says one thing and the building contains another, and nobody can tell which
changed. So:

    * Only a Draft may be edited (TEMPLATE_STATUSES_EDITABLE).
    * Submitting for review freezes the parameters. Forever.
    * A change is not an edit, it is a NEW VERSION -- created by copying the last one.
    * Publishing a version SUPERSEDES the previously published one; it never rewrites it,
      because something generated from it may exist in the physical world.

CONTROL C03 is the consumer: no project is generated without an approved template.
gates.require_approved_template_version reads status IN ('Approved','Published') and is
re-checked on the worker path in slice 7, because a guard that lives only in a route is a
guard the queue drainer skips.

SEPARATION OF DUTIES (doc 3, Gate 6 "Standardisation Approval")
---------------------------------------------------------------
`template.manage` (Programme Engineer) builds and edits. `template.approve` (Technical
Director) approves and publishes. They are different permissions held by different roles
on purpose: the person who writes the standard is not the person who certifies it.

What this does NOT claim is four-eyes. A user granted BOTH roles can author and approve
alone -- and an Enterprise Owner in a one-person pilot organisation will do exactly that.
Making that impossible needs an explicit "approver != author" rule, which doc 3 does not
ask for and which would deadlock most of this app's tenants today. Said out loud here so
nobody later reads the two permissions and infers a guarantee that is not there.
"""

from __future__ import annotations

import json
import math

from . import rbac, txn
from .constants import (
    BENEFICIARY_FIELDS,
    BENEFICIARY_TYPES,
    DELIVERY_MODELS,
    DESIGN_STRATEGIES,
    FUNDING_SOURCES,
    LOAD_PROFILES,
    OM_MODELS,
    SYSTEM_CONFIGURATIONS,
    TEMPLATE_PARAMETER_FIELDS,
    TEMPLATE_REQUIRED_DOCUMENTS,
    TEMPLATE_STATUSES_EDITABLE,
    TEMPLATE_STATUSES_GENERATIVE,
    TEMPLATE_TRANSITIONS,
)
from .gates import EnterpriseGateError

_BENEFICIARY_TYPE_CODES = frozenset(code for code, _ in BENEFICIARY_TYPES)
_STRATEGY_CODES = frozenset(code for code, _ in DESIGN_STRATEGIES)

# The vocabularies a `select` / `multiselect` parameter field may draw from. Keyed by the
# `source` name in constants.TEMPLATE_PARAMETER_FIELDS, so the list the form OFFERS and
# the list the validator ACCEPTS are provably the same object. EQUIPMENT_CATALOG is absent
# on purpose -- it is not a constant, it is a table, and it is validated against the DB.
_VOCABULARIES: dict[str, frozenset[str]] = {
    "SYSTEM_CONFIGURATIONS":      frozenset(c for c, _ in SYSTEM_CONFIGURATIONS),
    "LOAD_PROFILES":              frozenset(c for c, _ in LOAD_PROFILES),
    "BENEFICIARY_FIELDS":         frozenset(c for c, _ in BENEFICIARY_FIELDS),
    "TEMPLATE_REQUIRED_DOCUMENTS": frozenset(c for c, _ in TEMPLATE_REQUIRED_DOCUMENTS),
    "FUNDING_SOURCES":            frozenset(c for c, _ in FUNDING_SOURCES),
    "DELIVERY_MODELS":            frozenset(c for c, _ in DELIVERY_MODELS),
    "OM_MODELS":                  frozenset(c for c, _ in OM_MODELS),
}


class TemplateError(EnterpriseGateError):
    """A template rule was broken. Carries a control code, so a route can 404 a C13.

    Subclasses EnterpriseGateError rather than inventing a parallel exception hierarchy:
    the routes already turn that into "409, expressed as a flash" and 404 on C13, and a
    second exception type would need the same handling added at every call site -- which
    is how one of them ends up as an unhandled 500.
    """


# --- reading ----------------------------------------------------------------


def _load_template(c, tenant_id: str, template_id: int):
    """Fetch a template IN THIS TENANT, or raise C13.

    Input:  connection, tenant id, template id.
    Output: the row (id, code, name, beneficiary_type, design_strategy, programme_id).
    Raises: TemplateError with control C13.

    The tenant id is in the WHERE clause, not checked afterwards. A template in another
    organisation and a template that does not exist are the same answer, and the routes
    turn C13 into a 404 -- telling a stranger "that exists but is not yours" is itself
    the leak.
    """
    row = c.execute(
        "SELECT id, code, name, beneficiary_type, design_strategy, programme_id "
        "  FROM enterprise_programme_templates WHERE tenant_id=? AND id=?",
        (tenant_id, template_id),
    ).fetchone()
    if row is None:
        raise TemplateError("C13", "no such template in this organisation")
    return row


def _load_version(c, tenant_id: str, version_id: int):
    """Fetch a version IN THIS TENANT, or raise C13.

    Input:  connection, tenant id, template version id.
    Output: the row (id, template_id, version_no, status, parameters_json).
    Raises: TemplateError with control C13.
    """
    row = c.execute(
        "SELECT id, template_id, version_no, status, parameters_json "
        "  FROM enterprise_template_versions WHERE tenant_id=? AND id=?",
        (tenant_id, version_id),
    ).fetchone()
    if row is None:
        raise TemplateError("C13", "no such template version in this organisation")
    return row


def list_templates(c, tenant_id: str) -> list[dict]:
    """Every template in the tenant, with the state of its newest version.

    Input:  connection, tenant id.
    Output: list of dicts, newest template first.

    TWO queries, not one per template. The obvious shape -- loop the templates and call
    list_versions for each -- costs one round trip per template on a remote Postgres, and
    decodes the parameter blob of every version of every template to render an index that
    displays neither. The version rows are fetched once for the whole tenant and grouped in
    memory, and the parameters are left encoded, because nothing on this page reads them.
    """
    rows = c.execute(
        "SELECT id, code, name, beneficiary_type, design_strategy, programme_id "
        "  FROM enterprise_programme_templates WHERE tenant_id=? ORDER BY id DESC",
        (tenant_id,),
    ).fetchall()
    if not rows:
        return []

    version_rows = c.execute(
        "SELECT template_id, id, version_no, status, created_at "
        "  FROM enterprise_template_versions WHERE tenant_id=? "
        " ORDER BY template_id, version_no DESC",
        (tenant_id,),
    ).fetchall()

    by_template: dict[int, list[dict]] = {}
    for template_id, vid, version_no, status, created_at in version_rows:
        by_template.setdefault(int(template_id), []).append({
            "id": vid, "version_no": version_no, "status": status,
            "created_at": created_at,
            "editable": status in TEMPLATE_STATUSES_EDITABLE,
            "generative": status in TEMPLATE_STATUSES_GENERATIVE,
        })

    out = []
    for r in rows:
        versions = by_template.get(int(r[0]), [])
        out.append({
            "id": r[0], "code": r[1], "name": r[2], "beneficiary_type": r[3],
            "design_strategy": r[4], "programme_id": r[5],
            "versions": versions,
            "latest": versions[0] if versions else None,
            # What slice 7 would actually generate from, today. None means this template
            # cannot produce a project yet, which is the honest thing to show on a list.
            "generative_version": _generative_version_row(versions),
        })
    return out


def list_versions(c, tenant_id: str, template_id: int) -> list[dict]:
    """All versions of one template, newest first."""
    rows = c.execute(
        "SELECT id, version_no, status, parameters_json, approved_by_user_id, "
        "       approved_at, created_by_user_id, created_at "
        "  FROM enterprise_template_versions "
        " WHERE tenant_id=? AND template_id=? ORDER BY version_no DESC",
        (tenant_id, template_id),
    ).fetchall()
    return [
        {"id": r[0], "version_no": r[1], "status": r[2],
         "parameters": _decode(r[3]), "approved_by": r[4], "approved_at": r[5],
         "created_by": r[6], "created_at": r[7],
         "editable": r[2] in TEMPLATE_STATUSES_EDITABLE,
         "generative": r[2] in TEMPLATE_STATUSES_GENERATIVE,
         "next_states": TEMPLATE_TRANSITIONS.get(r[2], ())}
        for r in rows
    ]


def _generative_version_row(versions: list[dict]) -> dict | None:
    """Which version a project would be generated from: the Published one, else Approved.

    Input:  the version list from list_versions (newest first).
    Output: one version dict, or None.

    Published outranks Approved. There is at most one Published version per template --
    publish_version supersedes the incumbent in the same transaction -- so this is a
    lookup, not a tie-break. Among Approved-but-unpublished versions the newest wins.
    """
    for v in versions:
        if v["status"] == "Published":
            return v
    for v in versions:
        if v["status"] == "Approved":
            return v
    return None


def generative_version(c, tenant_id: str, template_id: int) -> dict | None:
    """The version slice 7 would generate from, or None if the template cannot yet."""
    _load_template(c, tenant_id, template_id)  # C13
    return _generative_version_row(list_versions(c, tenant_id, template_id))


def generative_from(versions: list[dict]) -> dict | None:
    """Same answer as generative_version, from a version list the caller already has.

    For a page that has just called list_versions and should not pay for the same rows
    twice. Public so that routes do not have to reach into a private to avoid a query.
    """
    return _generative_version_row(versions)


def get_template(c, tenant_id: str, template_id: int) -> dict:
    """One template's header row, tenant-scoped.

    Input:  connection, tenant id, template id.
    Output: dict.
    Raises: TemplateError with control C13 -- which the routes turn into a 404.
    """
    row = _load_template(c, tenant_id, template_id)
    return {"id": row[0], "code": row[1], "name": row[2], "beneficiary_type": row[3],
            "design_strategy": row[4], "programme_id": row[5]}


def _decode(raw) -> dict:
    """parameters_json -> dict, on either backend.

    Postgres `jsonb` comes back already decoded by psycopg2; SQLite hands back the TEXT we
    stored. Both are handled rather than assumed, because the backend that would surface
    the assumption is the one that only runs in production.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


# --- validation -------------------------------------------------------------


def validate_parameters(c, tenant_id: str, parameters: dict) -> dict:
    """Check a parameter set against TEMPLATE_PARAMETER_FIELDS and return the clean form.

    Input:  connection (to validate equipment ids), tenant id, the submitted dict.
    Output: a NEW dict containing only known keys, with coerced values.
    Raises: TemplateError (control TEMPLATE) listing every problem at once.

    THE RULE, same as everywhere else in this module's vocabularies: a value that was
    never offered cannot be stored. A select must hold one code from its list; a
    multiselect only codes from its list; a number_list only positive numbers. Unknown
    keys are DROPPED rather than rejected -- a stale form field should not brick a save --
    but a known key with a bad value is an error, because silently discarding it would
    tell the user their template says something it does not.

    Reports EVERY failure, not the first. A form that rejects one field per round trip is
    a form people give up on and work around.
    """
    if not isinstance(parameters, dict):
        raise TemplateError("TEMPLATE", "template parameters must be an object")

    clean: dict = {}
    problems: list[str] = []

    for field in TEMPLATE_PARAMETER_FIELDS:
        key, kind, label = field["key"], field["kind"], field["label"]
        required = field.get("required", False)
        raw = parameters.get(key)

        if raw is None or raw == "" or raw == []:
            if required:
                problems.append(f"{label} is required")
            continue

        if kind == "select":
            allowed = _VOCABULARIES[field["source"]]
            value = str(raw).strip()
            if value not in allowed:
                problems.append(f"{label}: {value!r} is not one of the offered options")
                continue
            clean[key] = value

        elif kind == "multiselect":
            values = [str(v).strip() for v in _as_list(raw) if str(v).strip()]
            if field["source"] == "EQUIPMENT_CATALOG":
                clean[key] = _validate_equipment_ids(c, values, problems, label)
                continue
            allowed = _VOCABULARIES[field["source"]]
            unknown = [v for v in values if v not in allowed]
            if unknown:
                problems.append(
                    f"{label}: {', '.join(sorted(unknown))} "
                    "not among the offered options"
                )
                continue
            if required and not values:
                problems.append(f"{label} is required")
                continue
            clean[key] = sorted(set(values))

        elif kind == "number_list":
            numbers = []
            for v in _as_list(raw):
                try:
                    n = float(v)
                except (TypeError, ValueError):
                    problems.append(f"{label}: {v!r} is not a number")
                    numbers = None
                    break
                # float("NaN") and float("Infinity") both SUCCEED, and NaN fails every
                # comparison silently -- `NaN <= 0` is False, so a NaN would sail through
                # the range check below and land in the stored standard, where slice 7
                # would try to size a PV array to it. (Codex slice-4, MED.)
                if not math.isfinite(n):
                    problems.append(f"{label}: {v!r} is not a finite number")
                    numbers = None
                    break
                if n <= 0:
                    problems.append(f"{label}: {v} must be greater than zero")
                    numbers = None
                    break
                # Store 50, not 50.0. These are read back into a form field and shown to a
                # human; "50.0 kWp" reads like a measurement when it is a nameplate size.
                numbers.append(int(n) if n.is_integer() else n)
            if numbers is None:
                continue
            if required and not numbers:
                problems.append(f"{label} is required")
                continue
            clean[key] = sorted(set(numbers))

        elif kind == "number":
            try:
                n = float(raw)
            except (TypeError, ValueError):
                problems.append(f"{label}: {raw!r} is not a number")
                continue
            if not math.isfinite(n):   # see the number_list branch above
                problems.append(f"{label}: {raw!r} is not a finite number")
                continue
            if n < 0:
                problems.append(f"{label} cannot be negative")
                continue
            clean[key] = int(n) if n.is_integer() else n

        elif kind == "bool":
            clean[key] = _as_bool(raw)

        else:  # pragma: no cover - a field kind nobody implemented
            problems.append(f"{label}: unsupported field kind {kind!r}")

    if problems:
        raise TemplateError("TEMPLATE", "; ".join(problems))
    return clean


def _validate_equipment_ids(c, values, problems: list[str], label: str) -> list[int]:
    """Equipment is picked from the LIVE catalogue, so it is checked against the table.

    Input:  connection, the submitted ids, the problem list to append to, the field label.
    Output: the validated ids as ints.

    equipment_catalog is the marketplace's product table -- the same catalogue the BOQ and
    procurement modules price against. It is deliberately NOT tenant-scoped: the product
    register is global to the platform (that is the whole point of a marketplace), so this
    checks existence, not ownership. Nothing here leaks anything a user cannot already see
    at /marketplace.
    """
    ids: list[int] = []
    for v in values:
        try:
            ids.append(int(v))
        except (TypeError, ValueError):
            problems.append(f"{label}: {v!r} is not a product id")
            return []
    if not ids:
        return []

    placeholders = ",".join("?" for _ in ids)
    try:
        rows = c.execute(
            f"SELECT id FROM equipment_catalog WHERE id IN ({placeholders})",
            tuple(ids),
        ).fetchall()
    except Exception:
        # FAILS CLOSED (Codex slice-4, MED). The earlier version returned the ids
        # unvalidated on the theory that a missing marketplace table should not block a
        # template save -- but that is a validator that stops validating exactly when it
        # cannot see the data, which is when an attacker would most like it to stop. The
        # form offers nothing in that state anyway, so anything submitted was not offered.
        problems.append(
            f"{label}: the product catalogue is unavailable, so equipment cannot be "
            "verified; save the template without equipment and add it once the catalogue "
            "is reachable"
        )
        return []

    found = {int(r[0]) for r in rows}
    missing = sorted(set(ids) - found)
    if missing:
        problems.append(
            f"{label}: product id(s) {', '.join(str(m) for m in missing)} "
            "are not in the catalogue"
        )
        return []
    return sorted(found)


def _as_list(raw) -> list:
    """Normalise a multi-value field, however the form or the API expressed it.

    Input:  a list (checkbox group / JSON array), a bare value, or a comma-separated
            string ("5, 10, 15" -- how the standard-sizes field is typed).
    Output: a flat list with empties dropped.

    Handles BOTH shapes because both really arrive: a checkbox group posts repeated keys
    and reaches here as a list, while the number-list fields are one text input and reach
    here as a single string inside a one-element list. Splitting only the bare-string case
    would silently turn "5,10,15" into one unparseable value.
    """
    items = list(raw) if isinstance(raw, (list, tuple, set)) else [raw]
    out: list = []
    for item in items:
        if isinstance(item, str) and "," in item:
            out.extend(part.strip() for part in item.split(","))
        else:
            out.append(item)
    return [i for i in out if not (isinstance(i, str) and not i.strip())]


def _as_bool(raw) -> bool:
    """HTML checkboxes post 'on'; JSON posts true; a re-saved template posts True."""
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "on", "yes")


# --- writing ----------------------------------------------------------------


def create_template(c, tenant_id: str, user_id: int, *, code: str, name: str,
                    beneficiary_type: str, design_strategy: str = "standard",
                    programme_id: int | None = None, parameters: dict | None = None,
                    audit=None) -> tuple[int, int]:
    """Register a template. It is born with version 1, in Draft.

    Input:  connection, tenant id, acting user, code + name, beneficiary type, design
            strategy, optional programme to scope it to, optional initial parameters,
            optional audit hook.
    Output: (template_id, version_id).
    Raises: EnterprisePermissionError (403), TemplateError (409).

    A template with no version is a template nothing can be done with -- there would be
    nothing to edit, submit or approve, and the UI would have to invent an empty state for
    a row that should never exist. So version 1 is created in the same transaction.

    Initial parameters are OPTIONAL and are NOT validated for completeness here: a Draft
    is allowed to be incomplete (that is what a draft is). The full check happens at
    submit_for_review, where being incomplete stops mattering.
    """
    rbac.require_permission(c, tenant_id, user_id, "template.manage",
                            programme_id=programme_id)

    code = (code or "").strip()
    name = (name or "").strip()
    if not code or not name:
        raise TemplateError("TEMPLATE", "a template needs a code and a name")
    if beneficiary_type not in _BENEFICIARY_TYPE_CODES:
        raise TemplateError("TEMPLATE", f"unknown beneficiary type {beneficiary_type!r}")
    if design_strategy not in _STRATEGY_CODES:
        raise TemplateError("TEMPLATE", f"unknown design strategy {design_strategy!r}")

    exists = c.execute(
        "SELECT 1 FROM enterprise_programme_templates WHERE tenant_id=? AND code=?",
        (tenant_id, code),
    ).fetchone()
    if exists:
        raise TemplateError("TEMPLATE", f"template code {code!r} is already used")

    # A draft may be partial, but a value that IS given must still be a legal one --
    # otherwise the bad value survives until submit and the user is told, days later,
    # that a field they filled in at the start was never valid.
    clean = validate_parameters(c, tenant_id, parameters) if parameters else {}

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        cur = c.execute(
            "INSERT INTO enterprise_programme_templates "
            "(tenant_id, programme_id, code, name, beneficiary_type, design_strategy, "
            " created_by_user_id) VALUES (?,?,?,?,?,?,?)",
            (tenant_id, programme_id, code, name, beneficiary_type, design_strategy,
             user_id),
        )
        template_id = txn.inserted_id(c, cur)

        cur = c.execute(
            "INSERT INTO enterprise_template_versions "
            "(tenant_id, template_id, version_no, status, parameters_json, "
            " created_by_user_id) VALUES (?,?,?,?,?,?)",
            (tenant_id, template_id, 1, "Draft", json.dumps(clean), user_id),
        )
        version_id = txn.inserted_id(c, cur)

        _require_audit(
            audit("ENTERPRISE_TEMPLATE_CREATED", user_id=user_id, tenant_id=tenant_id,
                  details={"template_id": template_id, "code": code,
                           "beneficiary_type": beneficiary_type,
                           "design_strategy": design_strategy,
                           "version_id": version_id}),
            "template create",
        )
    return template_id, version_id


def save_draft_parameters(c, tenant_id: str, user_id: int, version_id: int,
                          parameters: dict, *, audit=None) -> dict:
    """Edit a DRAFT version's parameters. The only write that ever mutates a version.

    Input:  connection, tenant id, acting user, version id, the new parameters,
            optional audit hook.
    Output: the stored (validated) parameters.
    Raises: EnterprisePermissionError (403), TemplateError (409 / C13).

    Refuses on ANY status but Draft. This is the immutability rule, and it is enforced
    here rather than in the route because the route is not the only caller -- an import,
    an API client or a future agent would each otherwise need to remember it.
    """
    version = _load_version(c, tenant_id, version_id)     # C13 first
    template = _load_template(c, tenant_id, version[1])
    rbac.require_permission(c, tenant_id, user_id, "template.manage",
                            programme_id=template[5])

    status = version[3]
    if status not in TEMPLATE_STATUSES_EDITABLE:
        raise TemplateError(
            "C03",
            f"version {version[2]} is {status} and is frozen; create a new version to "
            "change it (projects may already have been generated from this one)",
        )

    clean = validate_parameters(c, tenant_id, parameters)

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        # `AND status='Draft'` is the real guard; the check above is only the good error
        # message. Between reading the status and writing, another request can submit this
        # version for review -- and then this UPDATE would mutate a FROZEN version, which
        # is the one thing this module exists to make impossible. Conditioning the write on
        # the status we checked closes that window on both backends. (Codex slice-4, HIGH.)
        cur = c.execute(
            "UPDATE enterprise_template_versions SET parameters_json=? "
            " WHERE tenant_id=? AND id=? AND status='Draft'",
            (json.dumps(clean), tenant_id, version_id),
        )
        _require_changed_one_row(cur, version[2], "Draft")
        _require_audit(
            audit("ENTERPRISE_TEMPLATE_VERSION_EDITED", user_id=user_id,
                  tenant_id=tenant_id,
                  details={"template_id": version[1], "version_id": version_id,
                           "fields": sorted(clean.keys())}),
            "template draft edit",
        )
    return clean


def create_version(c, tenant_id: str, user_id: int, template_id: int, *,
                   from_version_id: int | None = None, audit=None) -> int:
    """Start a new DRAFT version, copying an existing one.

    Input:  connection, tenant id, acting user, template id, the version to copy from
            (defaults to the newest), optional audit hook.
    Output: the new version id.
    Raises: EnterprisePermissionError (403), TemplateError (409 / C13).

    THIS IS HOW A TEMPLATE CHANGES. Not by editing an approved version -- by copying it
    into a new draft, changing that, and putting the new one through the same approval.
    The old version stays exactly as it was, so anything generated from it still means
    what it meant.

    Only ONE open draft per template at a time. Two concurrent drafts of the same standard
    is not a feature, it is two people about to overwrite each other's work and then argue
    about which one the Technical Director approved.
    """
    template = _load_template(c, tenant_id, template_id)  # C13
    rbac.require_permission(c, tenant_id, user_id, "template.manage",
                            programme_id=template[5])

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        # Everything from here -- the one-open-Draft check, the next version number, the
        # insert -- is a read-modify-write on this template's version set, so it happens
        # under the template lock and inside ONE transaction. Read outside it and two
        # concurrent callers both see "no open draft", both compute the same next_no, and
        # the loser gets a raw UNIQUE-constraint traceback instead of an explanation.
        # (Codex slice-4, MED.)
        _lock_template(c, tenant_id, template_id)

        versions = list_versions(c, tenant_id, template_id)
        if not versions:  # pragma: no cover - create_template always seeds version 1
            raise TemplateError("TEMPLATE", "this template has no versions to copy")

        open_draft = next((v for v in versions if v["status"] == "Draft"), None)
        if open_draft:
            raise TemplateError(
                "TEMPLATE",
                f"version {open_draft['version_no']} is still a Draft; finish or archive "
                "it before starting another",
            )

        if from_version_id is None:
            source = versions[0]
        else:
            row = _load_version(c, tenant_id, from_version_id)
            if int(row[1]) != int(template_id):
                raise TemplateError("C13", "that version belongs to a different template")
            source = {"version_no": row[2], "parameters": _decode(row[4])}

        next_no = max(v["version_no"] for v in versions) + 1

        try:
            cur = c.execute(
                "INSERT INTO enterprise_template_versions "
                "(tenant_id, template_id, version_no, status, parameters_json, "
                " created_by_user_id) VALUES (?,?,?,?,?,?)",
                (tenant_id, template_id, next_no, "Draft",
                 json.dumps(source["parameters"]), user_id),
            )
        except Exception as e:
            # The unique indexes on (tenant_id, template_id, version_no) and on "one Draft
            # per template" are the DB's backstop for the races above. If one of them fires
            # anyway -- a caller outside this lock, a partitioned Postgres -- the user gets
            # a conflict they can act on, not a 500 with a driver traceback in it.
            if _is_integrity_error(e):
                raise TemplateError(
                    "TEMPLATE",
                    "another draft of this template was created at the same time; "
                    "reload and try again",
                ) from e
            raise
        version_id = txn.inserted_id(c, cur)
        _require_audit(
            audit("ENTERPRISE_TEMPLATE_VERSION_CREATED", user_id=user_id,
                  tenant_id=tenant_id,
                  details={"template_id": template_id, "version_id": version_id,
                           "version_no": next_no,
                           "copied_from": source["version_no"]}),
            "template version create",
        )
    return version_id


def _transition_version(c, tenant_id: str, user_id: int, version_id: int, target: str,
                        *, permission: str, action: str, comment: str | None,
                        ai_recommendation_id: int | None, audit) -> dict:
    """The single write path for every version state change. All of them go through here.

    Input:  connection, tenant id, acting user, version id, target status, the permission
            it needs, the audit action name, optional comment, optional AI recommendation,
            audit hook.
    Output: the new version state dict.
    Raises: EnterprisePermissionError (403), TemplateError (409 / C13).

    Written once rather than four times because every one of these needs the SAME five
    things -- C13, the permission, a legal edge in TEMPLATE_TRANSITIONS, C11 (a human
    decides), and an audit row inside the transaction. Four copies would be four chances
    to forget one, and the one everybody forgets is the last.
    """
    from . import gates as gates_mod

    approving = target in ("Approved", "Published")
    if approving:
        # C11 FIRST -- an AI recommendation is evidence, never the decision. Same guard and
        # same position as workflows.approve_gate: it touches no database, so it leaks
        # nothing about what exists, and a non-human actor should be told it is not allowed
        # to decide rather than that it lacks a permission it could never legitimately hold.
        gates_mod.require_human_approval_actor(user_id, ai_recommendation_id)

    version = _load_version(c, tenant_id, version_id)      # C13 next -- before authz, so
    template = _load_template(c, tenant_id, version[1])    # a stranger gets 404, not 403
    rbac.require_permission(c, tenant_id, user_id, permission, programme_id=template[5])

    status = version[3]
    legal = TEMPLATE_TRANSITIONS.get(status, ())
    if target not in legal:
        raise TemplateError(
            "TEMPLATE",
            f"version {version[2]} is {status}; it cannot become {target} "
            f"(allowed: {', '.join(legal) or 'none'})",
        )

    if target == "Review":
        # Completeness is checked HERE and not at save: a Draft is allowed to be
        # half-finished, but the moment it is offered for approval it must be a whole
        # standard. Otherwise the Technical Director is asked to certify a template with
        # no PV sizes in it.
        _require_complete(c, tenant_id, _decode(version[4]))

    audit = audit or txn.audit_on(c)
    with txn.atomic(c):
        if target == "Published":
            # Serialise publication PER TEMPLATE before touching any version. Without this,
            # two Approved versions published concurrently on Postgres each supersede an
            # incumbent the other cannot see yet, and BOTH end up Published -- after which
            # "which version does this template build from" has two answers. The partial
            # unique index added by migration 026 is the backstop; this is the lock that
            # means users see a wait, not an error. (Codex slice-4, HIGH.)
            _lock_template(c, tenant_id, version[1])

            # The incumbent is SUPERSEDED, not deleted and not rewritten -- projects
            # generated from it exist, and their provenance has to keep resolving.
            c.execute(
                "UPDATE enterprise_template_versions SET status='Superseded' "
                " WHERE tenant_id=? AND template_id=? AND status='Published' AND id<>?",
                (tenant_id, version[1], version_id),
            )

        # Every status write is conditioned on the status we READ. Two approvers racing a
        # version in Review -- one approving, one rejecting -- would otherwise both find it
        # legal and the loser would overwrite the winner, landing an already-Approved
        # version back in Draft (and therefore editable again). The rowcount check turns
        # that race into a clean 409. (Codex slice-4, HIGH.)
        if approving:
            cur = c.execute(
                "UPDATE enterprise_template_versions "
                "   SET status=?, approved_by_user_id=?, approved_at=CURRENT_TIMESTAMP "
                " WHERE tenant_id=? AND id=? AND status=?",
                (target, user_id, tenant_id, version_id, status),
            )
        else:
            cur = c.execute(
                "UPDATE enterprise_template_versions SET status=? "
                " WHERE tenant_id=? AND id=? AND status=?",
                (target, tenant_id, version_id, status),
            )
        _require_changed_one_row(cur, version[2], status)

        c.execute(
            "INSERT INTO enterprise_approvals "
            "(tenant_id, programme_id, subject_type, subject_id, approval_type, "
            " decision, decided_by_user_id, ai_recommendation_id, comment) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_id, template[5], "template_version", str(version_id),
             "template_version", target, user_id, ai_recommendation_id, comment),
        )

        _require_audit(
            audit(action, user_id=user_id, tenant_id=tenant_id,
                  details={"template_id": version[1], "version_id": version_id,
                           "version_no": version[2], "from": status, "to": target,
                           "ai_recommendation_id": ai_recommendation_id}),
            f"template version {target.lower()}",
        )

    return get_version_state(c, tenant_id, version_id)


def submit_for_review(c, tenant_id: str, user_id: int, version_id: int, *,
                      comment: str | None = None, audit=None) -> dict:
    """Draft -> Review. THE FREEZE. After this the parameters can never change again."""
    return _transition_version(
        c, tenant_id, user_id, version_id, "Review",
        permission="template.manage", action="ENTERPRISE_TEMPLATE_VERSION_SUBMITTED",
        comment=comment, ai_recommendation_id=None, audit=audit,
    )


def approve_version(c, tenant_id: str, user_id: int, version_id: int, *,
                    comment: str | None = None, ai_recommendation_id: int | None = None,
                    audit=None) -> dict:
    """Review -> Approved. Needs `template.approve` (the Technical Director's, per Gate 6).

    An approved version MAY generate projects (C03). Publishing is a further step that
    makes it THE version for the template -- approval alone is enough to build from.
    """
    return _transition_version(
        c, tenant_id, user_id, version_id, "Approved",
        permission="template.approve", action="ENTERPRISE_TEMPLATE_VERSION_APPROVED",
        comment=comment, ai_recommendation_id=ai_recommendation_id, audit=audit,
    )


def reject_version(c, tenant_id: str, user_id: int, version_id: int, *,
                   comment: str | None = None, audit=None) -> dict:
    """Review -> Draft. The approver sends it back, and it becomes editable again.

    This is the ONLY route from a frozen state back to an editable one, and it is
    deliberately available only BEFORE approval. Nothing has been generated from a
    rejected draft, so unfreezing it destroys no provenance.
    """
    return _transition_version(
        c, tenant_id, user_id, version_id, "Draft",
        permission="template.approve", action="ENTERPRISE_TEMPLATE_VERSION_REJECTED",
        comment=comment, ai_recommendation_id=None, audit=audit,
    )


def publish_version(c, tenant_id: str, user_id: int, version_id: int, *,
                    comment: str | None = None, audit=None) -> dict:
    """Approved -> Published, superseding whatever was published before."""
    return _transition_version(
        c, tenant_id, user_id, version_id, "Published",
        permission="template.approve", action="ENTERPRISE_TEMPLATE_VERSION_PUBLISHED",
        comment=comment, ai_recommendation_id=None, audit=audit,
    )


def archive_version(c, tenant_id: str, user_id: int, version_id: int, *,
                    comment: str | None = None, audit=None) -> dict:
    """Any state -> Archived. Files a version out of use without deleting it.

    THE PERMISSION DEPENDS ON WHAT IS BEING ARCHIVED, and that is not a nicety:

      * A DRAFT is the author's own unfinished work. Nobody has reviewed it, nothing has
        been generated from it, and archiving it destroys no provenance -- so
        `template.manage` (the author's permission) is enough. Requiring the Technical
        Director here created a dead end: create_version refuses to open a second draft
        while one is still open, so an engineer who started a draft down the wrong path
        could neither finish it, discard it, nor start again, until somebody with
        `template.approve` came and cleared it for them.
      * ANYTHING THAT HAS LEFT DRAFT is a certified standard, possibly with projects built
        from it. Retiring one is a governance act: `template.approve`.
    """
    version = _load_version(c, tenant_id, version_id)   # C13 first, as everywhere
    is_draft = version[3] in TEMPLATE_STATUSES_EDITABLE
    return _transition_version(
        c, tenant_id, user_id, version_id, "Archived",
        permission="template.manage" if is_draft else "template.approve",
        action="ENTERPRISE_TEMPLATE_VERSION_ARCHIVED",
        comment=comment, ai_recommendation_id=None, audit=audit,
    )


def _require_complete(c, tenant_id: str, parameters: dict) -> None:
    """Every REQUIRED parameter field must be present before a version leaves Draft.

    Input:  connection, tenant id, the version's stored parameters.
    Output: none.
    Raises: TemplateError listing what is missing.

    Re-runs the full validator rather than only checking for presence. The stored values
    were legal when they were saved, but a vocabulary can change underneath them between
    slices -- and a template that references an option the platform no longer offers must
    not be approvable, because slice 7 would then generate from it and fail per project
    instead of once, here, where a human is looking.
    """
    validate_parameters(c, tenant_id, parameters)


def get_version_state(c, tenant_id: str, version_id: int) -> dict:
    """One version's full state, for a route or a caller that just changed it."""
    row = _load_version(c, tenant_id, version_id)
    return {
        "id": row[0], "template_id": row[1], "version_no": row[2], "status": row[3],
        "parameters": _decode(row[4]),
        "editable": row[3] in TEMPLATE_STATUSES_EDITABLE,
        "generative": row[3] in TEMPLATE_STATUSES_GENERATIVE,
        "next_states": TEMPLATE_TRANSITIONS.get(row[3], ()),
    }


def _require_audit(written: bool, what: str) -> None:
    """C12 for this module. Delegates to the same guard the lifecycle uses."""
    from . import gates as gates_mod
    gates_mod.require_audit_written(written, what)


def _require_changed_one_row(cur, version_no, expected_status: str) -> None:
    """The conditional UPDATE must have hit exactly the row we checked.

    Input:  the cursor from an `UPDATE ... AND status=?`, the version number and the
            status we expected, for the error message.
    Output: none.
    Raises: TemplateError (409).

    Zero rows means somebody else moved this version between our read and our write. That
    is not an error to swallow -- it is precisely the race that would otherwise let a
    frozen version be edited, so it must abort the transaction (and, because the audit row
    is written in the same transaction, abort cleanly with nothing recorded).

    A driver that does not report rowcount returns -1; treat that as "cannot verify" and
    let it pass rather than failing every write on an exotic driver. sqlite3 and psycopg2
    both report it, which is every backend this app actually runs on.
    """
    rowcount = getattr(cur, "rowcount", -1)
    if rowcount == 0:
        raise TemplateError(
            "TEMPLATE",
            f"version {version_no} is no longer {expected_status} -- somebody else changed "
            "it while you were working. Reload and try again.",
        )


def _is_integrity_error(e: Exception) -> bool:
    """Is this exception a UNIQUE / CHECK / FK violation, on either driver?

    Input:  an exception raised by an INSERT or UPDATE.
    Output: bool.

    Matched by CLASS NAME rather than by importing sqlite3.IntegrityError and
    psycopg2.IntegrityError: psycopg2 is not installed in the SQLite dev environment, and
    an import-time dependency on it here would take the module down where it works fine.
    Both drivers name the class `IntegrityError` (DB-API 2.0 says so).
    """
    for klass in type(e).__mro__:
        if klass.__name__ == "IntegrityError":
            return True
    return False


def _lock_template(c, tenant_id: str, template_id: int) -> None:
    """Serialise concurrent writers of ONE template's versions.

    Input:  connection, tenant id, template id.
    Output: none.

    `SELECT ... FOR UPDATE` on the parent row, on Postgres only. SQLite needs nothing: a
    write transaction takes a lock on the whole database file, so its writers are already
    serialised by the engine. The lock is released by the caller's COMMIT -- and because it
    is taken inside txn.atomic, there is a caller's commit to release it.
    """
    if not txn.is_postgres():
        return
    c.execute(
        "SELECT id FROM enterprise_programme_templates "
        " WHERE tenant_id=? AND id=? FOR UPDATE",
        (tenant_id, template_id),
    )
