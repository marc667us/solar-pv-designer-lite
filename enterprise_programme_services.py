"""Enterprise Solar Programme Management -- service layer (Phase 1).

Deterministic Python only. No LLM call is made anywhere in Phase 1.

AI POSTURE (ADR, see docs/ARCHITECTURE_DECISIONS.md): this module does NOT use
Google ADK. Owner decision, mirroring the AI-SOC precedent -- ADK's Gemini key
is exhausted (HTTP 429, quota 0) and the platform rule has an ADR escape hatch.
Programme "intelligence" here is deterministic scoring; any later LLM enrichment
must go through the EXISTING api_manager.py `_AIClient.chat()` gateway (which is
already budget-gated by ai_budget.py) and must be labelled a recommendation
pending human approval -- never an automatic decision.

Everything in this file is pure-ish: it takes data in and returns data out. All
DB access goes through enterprise_programme_repository.
"""

from __future__ import annotations

import re
from typing import Any

import enterprise_programme_repository as repo


# Programme types are CONFIGURATION, not application logic (File B §3 forbids
# hard-coding the system to a fixed list). This seeds the dropdown; the column
# is free TEXT, so an operator can introduce a type we never anticipated.
PROGRAMME_TYPES: list[tuple[str, str]] = [
    ("residential", "Residential / Home Energy Independence"),
    ("school", "School / Education"),
    ("hospital", "Hospital / Health Facility"),
    ("government", "Government / Ministry Office"),
    ("agriculture", "Agriculture / Irrigation"),
    ("water", "Water Supply"),
    ("industrial", "Industrial / Manufacturing"),
    ("mining", "Mining Electrification"),
    ("minigrid", "Community Mini-Grid"),
    ("utility", "Utility-Scale Generation / Solar Farm"),
    ("storage", "Battery Energy Storage"),
    ("hybrid", "Hybrid Solar / Grid / Generator"),
    ("other", "Other"),
]

BENEFICIARY_TYPES: list[tuple[str, str]] = [
    ("household", "Household / Home"),
    ("school", "School"),
    ("hospital", "Hospital"),
    ("clinic", "Clinic / Health Centre"),
    ("university", "University"),
    ("government_office", "Government Office"),
    ("farm", "Farm"),
    ("factory", "Factory"),
    ("water_facility", "Water Facility"),
    ("community", "Community"),
    ("generation_site", "Generation Site"),
    ("other", "Other"),
]

# Which existing SolarPro design engine a programme routes its projects to.
DESIGN_STRATEGIES: list[tuple[str, str]] = [
    ("standard", "Standard Design (reuses the residential/commercial sizing chain)"),
    ("generation_station", "Generation Station (reuses the large-scale solar farm engine)"),
    ("mixed", "Mixed (both, decided per beneficiary)"),
]

PROGRAMME_STATUSES = ["draft", "active", "on_hold", "completed", "archived"]

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{1,39}$")


def validate_programme(data: dict) -> list[str]:
    """Validate a programme create/edit payload.

    Input:  the raw form dict.
    Output: a list of human-readable errors ([] means valid).
    """
    errors: list[str] = []

    name = (data.get("name") or "").strip()
    if not name:
        errors.append("Programme name is required.")
    elif len(name) > 200:
        errors.append("Programme name must be 200 characters or fewer.")

    code = (data.get("programme_code") or "").strip()
    if not code:
        errors.append("Programme code is required.")
    elif not _CODE_RE.match(code):
        errors.append(
            "Programme code must be 2-40 characters: letters, digits, - _ / only."
        )

    if data.get("design_strategy") not in [s[0] for s in DESIGN_STRATEGIES]:
        errors.append("Choose a valid design strategy.")

    if data.get("status") and data["status"] not in PROGRAMME_STATUSES:
        errors.append("Invalid programme status.")

    for field, label in (
        ("target_beneficiaries", "Target beneficiaries"),
        ("target_capacity_kwp", "Target capacity (kWp)"),
        ("budget_amount", "Programme budget"),
    ):
        raw = data.get(field)
        if raw in (None, ""):
            continue
        try:
            if float(raw) < 0:
                errors.append(f"{label} cannot be negative.")
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number.")

    return errors


def validate_beneficiary(data: dict) -> list[str]:
    """Validate a beneficiary payload. Returns [] when valid."""
    errors: list[str] = []

    if not (data.get("name") or "").strip():
        errors.append("Beneficiary name is required.")

    for field, label, lo, hi in (
        ("latitude", "Latitude", -90.0, 90.0),
        ("longitude", "Longitude", -180.0, 180.0),
    ):
        raw = data.get(field)
        if raw in (None, ""):
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number.")
            continue
        if not (lo <= v <= hi):
            errors.append(f"{label} must be between {lo} and {hi}.")

    for field, label in (
        ("load_kwh_day", "Daily load (kWh)"),
        ("target_capacity_kwp", "Target capacity (kWp)"),
    ):
        raw = data.get(field)
        if raw in (None, ""):
            continue
        try:
            if float(raw) < 0:
                errors.append(f"{label} cannot be negative.")
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number.")

    return errors


def programme_dashboard(get_db, org_id: int, user_id: int,
                        programme_id: int) -> dict[str, Any] | None:
    """Roll up one programme's KPIs from REAL rows -- never invented values.

    Input:  org_id (from membership), users.id, programme_id (untrusted, re-scoped).
    Output: dict of programme + phases + counts, or None if not the caller's.

    File B §28 requires every KPI to have a documented calculation source and
    forbids invented values in production views. Each number below is a COUNT or
    SUM over rows this organisation actually owns; where a figure cannot yet be
    computed in Phase 1 (energy generated, budget spent, CO2 avoided) it is
    simply ABSENT rather than faked.
    """
    programme = repo.get_programme(get_db, org_id, user_id, programme_id)
    if not programme:
        return None

    phases = repo.list_phases(get_db, org_id, user_id, programme_id)
    beneficiaries, beneficiary_total = repo.list_beneficiaries(
        get_db, org_id, user_id, programme_id, limit=5, offset=0
    )
    links = repo.list_links(get_db, org_id, user_id, programme_id)

    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)
        rows = c.execute(
            "SELECT qualification_status AS s, COUNT(*) AS n "
            "FROM enterprise_beneficiaries "
            "WHERE programme_id=? AND organisation_id=? GROUP BY qualification_status",
            (programme_id, org_id),
        ).fetchall()
    by_status = {
        (r["s"] if hasattr(r, "keys") else r[0]): int(r["n"] if hasattr(r, "keys") else r[1])
        for r in rows
    }

    target_beneficiaries = int(programme.get("target_beneficiaries") or 0)
    registered = beneficiary_total
    coverage_pct = (
        round(registered * 100.0 / target_beneficiaries, 1)
        if target_beneficiaries > 0 else None
    )

    return {
        "programme": programme,
        "phases": phases,
        "phase_count": len(phases),
        "recent_beneficiaries": beneficiaries,
        "kpi": {
            # source: COUNT(enterprise_beneficiaries) for this programme
            "beneficiaries_registered": registered,
            "beneficiaries_approved": by_status.get("approved", 0),
            "beneficiaries_draft": by_status.get("draft", 0),
            "beneficiaries_rejected": by_status.get("rejected", 0),
            # source: programme.target_beneficiaries (operator-entered)
            "beneficiaries_target": target_beneficiaries,
            # source: registered / target
            "coverage_pct": coverage_pct,
            # source: COUNT(enterprise_programme_project_links)
            "projects_linked": len(links),
            "projects_standard": sum(
                1 for l in links if l.get("project_kind") == "standard"
            ),
            "projects_generation_station": sum(
                1 for l in links if l.get("project_kind") == "generation_station"
            ),
            # source: COUNT(enterprise_programme_phases)
            "phases": len(phases),
        },
        "links": links,
    }


def org_dashboard(get_db, org_id: int, user_id: int) -> dict[str, Any]:
    """Portfolio-level rollup across every programme in the organisation.

    Every figure is a COUNT/SUM over real rows. No placeholder values.
    """
    with get_db() as c:
        repo.apply_enterprise_guc(c, user_id)

        prow = c.execute(
            "SELECT COUNT(*) AS n, "
            "       COALESCE(SUM(target_capacity_kwp), 0) AS kwp, "
            "       COALESCE(SUM(budget_amount), 0) AS budget "
            "FROM enterprise_programmes WHERE organisation_id=?",
            (org_id,),
        ).fetchone()

        arow = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_programmes "
            "WHERE organisation_id=? AND status='active'",
            (org_id,),
        ).fetchone()

        brow = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_beneficiaries WHERE organisation_id=?",
            (org_id,),
        ).fetchone()

        lrow = c.execute(
            "SELECT COUNT(*) AS n FROM enterprise_programme_project_links "
            "WHERE organisation_id=?",
            (org_id,),
        ).fetchone()

    def _get(row, key, idx):
        if row is None:
            return 0
        return row[key] if hasattr(row, "keys") else row[idx]

    return {
        "programmes_total": int(_get(prow, "n", 0) or 0),
        "programmes_active": int(_get(arow, "n", 0) or 0),
        "target_capacity_kwp": float(_get(prow, "kwp", 1) or 0),
        "total_budget": float(_get(prow, "budget", 2) or 0),
        "beneficiaries_total": int(_get(brow, "n", 0) or 0),
        "projects_linked": int(_get(lrow, "n", 0) or 0),
    }


def default_org_name(user: dict | None) -> str:
    """Best-effort organisation name for the bootstrap form.

    Reuses whatever the user already told us (`org_name`, then `company`) rather
    than making them retype it. These are the flat report-stamping TEXT columns
    on `users` -- they are NOT an organisation entity, which is precisely why
    this module has to create one.
    """
    if not user:
        return ""
    for key in ("org_name", "company", "name"):
        try:
            val = (user[key] if hasattr(user, "keys") else getattr(user, key, "")) or ""
        except Exception:
            val = ""
        if str(val).strip():
            return str(val).strip()[:200]
    return ""
