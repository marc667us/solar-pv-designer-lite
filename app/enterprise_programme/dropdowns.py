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
    DELIVERY_MODELS,
    DESIGN_STRATEGIES,
    FUNDING_SOURCES,
    ORGANISATION_TYPES,
    PROGRAMME_STATUSES,
    PROJECT_STATUSES,
    ROLES,
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
