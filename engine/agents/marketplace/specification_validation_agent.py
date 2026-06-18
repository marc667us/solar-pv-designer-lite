"""Specification Validation Agent — flags missing required spec fields per category.

Required-field map is the deterministic source of truth. The ADK wrapper is
for Phase 2 LLM-driven "is this spec field actually present even though the
column name is different?" judgements; Phase 1 is strict string lookup.
"""
from __future__ import annotations

from typing import Dict, List

# Required spec fields per category code. Empty list = no strict requirement
# beyond name + price (categories like sockets are simple).
REQUIRED_FIELDS: Dict[str, List[str]] = {
    "transformers":       ["kva_rating", "voltage_ratio", "phase", "vector_group", "cooling_type"],
    "hv_cables":          ["conductor_material", "cores", "size_mm2", "insulation", "voltage_rating"],
    "lv_cables":          ["conductor_material", "cores", "size_mm2", "insulation", "voltage_rating"],
    "wires":              ["conductor_material", "size_mm2", "insulation", "voltage_rating"],
    "panel_boards":       ["current_rating", "short_circuit_rating", "number_of_ways", "ip_rating"],
    "distribution_boards": ["number_of_ways", "phase", "incomer_rating"],
    "isolators":          ["current_rating", "voltage_rating", "poles"],
    "fuse_switches":      ["current_rating", "voltage_rating"],
    "earthing":           ["material", "size"],
    "sockets":            ["current_rating", "gang"],
    "dp_switches":        ["current_rating"],
    "light_switches":     ["gang", "way"],
}


def validate_spec(category_code: str, spec_fields: Dict[str, str]) -> Dict[str, object]:
    """Return {"missing_fields": [...], "status": "ok" | "incomplete"}.

    spec_fields is a dict of {field_name: value}; values are checked as
    non-empty strings."""
    required = REQUIRED_FIELDS.get(category_code, [])
    if not required:
        return {"missing_fields": [], "status": "ok"}
    missing = [f for f in required if not str(spec_fields.get(f, "") or "").strip()]
    return {
        "missing_fields": missing,
        "status": "ok" if not missing else "incomplete",
    }


def _make_adk_agent():
    try:
        from google.adk.agents import LlmAgent  # type: ignore
    except Exception:
        return None

    class _SpecificationValidationAgent(LlmAgent):
        def __init__(self) -> None:
            super().__init__(
                name="specification_validation_agent",
                model="ollama/llama3.2",
                instruction=(
                    "Given a product category and its spec fields, return JSON "
                    '{"missing_fields": [str], "status": "ok"|"incomplete"}.'
                ),
            )

    return _SpecificationValidationAgent


def SpecificationValidationAgent():  # noqa: N802
    cls = _make_adk_agent()
    if cls is None:
        class _Shim:
            name = "specification_validation_agent"

            def run(self, *, category_code: str, spec_fields: Dict[str, str]) -> Dict[str, object]:
                return validate_spec(category_code, spec_fields)

        return _Shim()
    return cls()
