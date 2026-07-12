"""Enterprise Solar Programme -- dropdown option sources (rebuild, slice 3).

THE OWNER'S RULE: minimise typing. Every selectable value in this module comes from a
dropdown, and every dropdown comes from here.

WHY THIS MATTERS BEYOND ERGONOMICS
----------------------------------
A status a user can TYPE is a status the state machine cannot reason about. The moment a
form accepts free text for a phase, a status or a role, the 16/14/20/21 vocabularies in
constants.py stop being a state machine and become a suggestion. So the options a form
offers and the values the server accepts are read from the SAME lists -- a value that was
never offered is a value the service refuses.

Location data is reused, not reinvented: countries come from the registry the rest of the
app already uses (config/global_solar_data.py).
"""

from __future__ import annotations

from .constants import (
    BENEFICIARY_FIELD_SPEC,
    BENEFICIARY_FIELDS,
    BENEFICIARY_TYPES,
    BUILDING_TYPES,
    DELIVERY_MODELS,
    DESIGN_STRATEGIES,
    ENERGY_SOURCES,
    FUNDING_ELIGIBILITY,
    FUNDING_SOURCES,
    LOAD_PROFILES,
    OM_MODELS,
    ORGANISATION_TYPES,
    OWNERSHIP_TYPES,
    PROGRAMME_STATUSES,
    PROJECT_STATUSES,
    ROLES,
    SOCIAL_IMPACT_CLASSES,
    SYSTEM_CONFIGURATIONS,
    TEMPLATE_PARAMETER_FIELDS,
    TEMPLATE_REQUIRED_DOCUMENTS,
)


def _pairs(items) -> list[dict]:
    """Turn (code, label) tuples into the {value,label} shape the templates render."""
    return [{"value": code, "label": label} for code, label in items]


def countries() -> list[dict]:
    """Every country the platform has solar data for.

    Input:  none.
    Output: list of {value,label} dicts, alphabetical.

    Reuses config/global_solar_data.get_countries() rather than shipping a second country
    list that would immediately start drifting from the first.
    """
    try:
        from config.global_solar_data import get_countries
        return [{"value": c, "label": c} for c in sorted(get_countries())]
    except Exception:
        # A missing registry must not take the form down -- the field simply offers
        # nothing rather than the page 500ing.
        return []


def organisation_types() -> list[dict]:
    return _pairs(ORGANISATION_TYPES)


def design_strategies() -> list[dict]:
    return _pairs(DESIGN_STRATEGIES)


def delivery_models() -> list[dict]:
    return _pairs(DELIVERY_MODELS)


def funding_sources() -> list[dict]:
    return _pairs(FUNDING_SOURCES)


def roles() -> list[dict]:
    return _pairs(ROLES)


def programme_statuses() -> list[dict]:
    """Read-only in the UI: status is DERIVED from the phase, never chosen.

    Offered here only so filters and reports can list them. No form writes a status --
    see workflows.py, "why status is never a parameter".
    """
    return [{"value": s, "label": s} for s in PROGRAMME_STATUSES]


def project_statuses() -> list[dict]:
    return [{"value": s, "label": s} for s in PROJECT_STATUSES]


def beneficiary_types() -> list[dict]:
    return _pairs(BENEFICIARY_TYPES)


def for_beneficiary_form() -> dict:
    """Every option list the beneficiary form needs, in one call.

    Input:  none.
    Output: {"fields": the field spec, "options": {source_name: [...]}, ...}

    The form is RENDERED from constants.BENEFICIARY_FIELD_SPEC and VALIDATED against the
    same list in beneficiaries.validate_fields -- the same discipline as the template form.
    A field cannot appear on the form without the validator knowing it, and a validator rule
    cannot exist for a field nobody can fill.
    """
    return {
        "fields": BENEFICIARY_FIELD_SPEC,
        "beneficiary_types": beneficiary_types(),
        "options": {
            "OWNERSHIP_TYPES":       _pairs(OWNERSHIP_TYPES),
            "BUILDING_TYPES":        _pairs(BUILDING_TYPES),
            "ENERGY_SOURCES":        _pairs(ENERGY_SOURCES),
            "FUNDING_ELIGIBILITY":   _pairs(FUNDING_ELIGIBILITY),
            "SOCIAL_IMPACT_CLASSES": _pairs(SOCIAL_IMPACT_CLASSES),
        },
    }


def equipment_catalog(c, limit: int = 500) -> list[dict]:
    """Products the template may name as its standard equipment.

    Input:  a DB connection; an upper bound on how many products to offer.
    Output: list of {value,label} dicts -- value is the equipment_catalog id.

    Reads the LIVE marketplace catalogue -- the same `equipment_catalog` table the BOQ and
    procurement modules price against -- rather than shipping a second product list that
    would immediately start drifting from the first (the same reasoning as countries()).

    The catalogue is global, not tenant-scoped: a product register that every tenant sees
    is the entire point of a marketplace, and nothing here is visible that /marketplace
    does not already show to an anonymous visitor.

    The limit is real and is NOT silent: the caller reports it. The catalogue holds ~600
    products, and a 600-option checkbox grid is not a picker, it is a wall. Slice 7 will
    need a searchable one; until a template needs more than 500 candidates this is honest
    and cheap.
    """
    try:
        rows = c.execute(
            "SELECT ec.id, ec.name, COALESCE(ec.brand,''), COALESCE(ec.unit,'') "
            "  FROM equipment_catalog ec "
            " ORDER BY ec.name LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception:
        # The marketplace table is not part of this module's schema. If it is absent (a
        # bare test DB, a partial deploy) the template form simply offers no equipment
        # rather than 500ing -- exactly how countries() degrades.
        return []
    out = []
    for r in rows:
        brand = f" -- {r[2]}" if r[2] else ""
        unit = f" ({r[3]})" if r[3] else ""
        out.append({"value": r[0], "label": f"{r[1]}{brand}{unit}"})
    return out


def for_template_form(c) -> dict:
    """Every option list the template parameter form needs, in one call.

    Input:  a DB connection (the equipment catalogue is a table, not a constant).
    Output: {"fields": the parameter schema, "options": {source_name: [...]}, ...}

    The form is RENDERED from constants.TEMPLATE_PARAMETER_FIELDS and VALIDATED against
    the same list in templates.validate_parameters. That is deliberate: a field cannot
    appear on the form without the validator knowing about it, and a validator rule cannot
    exist for a field nobody can fill. They cannot drift because they are the same list.
    """
    return {
        "fields": TEMPLATE_PARAMETER_FIELDS,
        "beneficiary_types": beneficiary_types(),
        "design_strategies": design_strategies(),
        "options": {
            "SYSTEM_CONFIGURATIONS":       _pairs(SYSTEM_CONFIGURATIONS),
            "LOAD_PROFILES":               _pairs(LOAD_PROFILES),
            "BENEFICIARY_FIELDS":          _pairs(BENEFICIARY_FIELDS),
            "TEMPLATE_REQUIRED_DOCUMENTS": _pairs(TEMPLATE_REQUIRED_DOCUMENTS),
            "FUNDING_SOURCES":             _pairs(FUNDING_SOURCES),
            "DELIVERY_MODELS":             _pairs(DELIVERY_MODELS),
            "OM_MODELS":                   _pairs(OM_MODELS),
            "EQUIPMENT_CATALOG":           equipment_catalog(c),
        },
    }


def for_programme_form() -> dict:
    """Everything the create/edit-programme form needs, in one call.

    Input:  none.
    Output: dict of option lists keyed by field name.

    No region list: a programme is registered against a COUNTRY, and geography below that
    belongs to sites (slice 6), which will bring its own picker and its own cascade. An
    option list with no field to fill reads as a feature that exists when it does not.
    """
    return {
        "organisation_types": organisation_types(),
        "design_strategies": design_strategies(),
        "delivery_models": delivery_models(),
        "funding_sources": funding_sources(),
        "countries": countries(),
    }
