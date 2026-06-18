"""Supplier Product Agent — orchestrates the per-row ingestion pipeline.

Given a raw row from a supplier upload, runs:
  1. Product Classification Agent → category_code, confidence
  2. Specification Validation Agent → missing_fields
  3. Price Normalisation Agent → amount, currency, warnings

Returns a structured row with the three agents' outputs joined. This is the
function the FastAPI / Flask upload route calls per parsed row to decide
whether to accept, queue for review, or reject.
"""
from __future__ import annotations

from typing import Dict, List

from .product_classification_agent import classify_product
from .specification_validation_agent import validate_spec
from .price_normalisation_agent import normalise_price


def classify_extracted_row(row: Dict[str, str], default_currency: str = "USD") -> Dict[str, object]:
    """Run the full Phase 1 pipeline on one parsed supplier row.

    `row` keys (canonical): name, brand, model, spec, price (raw string),
    plus any fielded specs (kva_rating, voltage_rating, cores, ...).

    Returns:
      {
        "classification": {"category": str, "confidence": float},
        "validation":     {"missing_fields": [str], "status": str},
        "price":          {"amount": float|None, "currency": str, ...},
        "verdict":        "accept" | "review" | "reject",
        "reasons":        [str],   # human-readable
      }"""
    name = (row.get("name") or "").strip()
    spec = (row.get("spec") or "").strip()
    brand = (row.get("brand") or "").strip()

    cls = classify_product(name, spec, brand)
    classification = {"category": cls[0], "confidence": cls[1]}

    validation = validate_spec(cls[0], row)
    price = normalise_price(row.get("price", ""), default_currency)

    reasons: List[str] = []
    verdict = "accept"

    if not name:
        verdict = "reject"
        reasons.append("missing product name")
    if not cls[0]:
        verdict = "reject" if verdict != "reject" else verdict
        reasons.append("could not classify into any category")
    elif cls[1] < 0.55:
        verdict = "review" if verdict == "accept" else verdict
        reasons.append(f"low classification confidence ({cls[1]:.2f})")
    if validation["status"] != "ok":
        verdict = "review" if verdict == "accept" else verdict
        reasons.append(
            "missing required spec fields: " + ", ".join(validation["missing_fields"])
        )
    if price["amount"] is None or (price.get("warnings") and any(
        "zero price" in w or "negative price" in w for w in price["warnings"]
    )):
        verdict = "reject"
        reasons.append("invalid price")

    return {
        "classification": classification,
        "validation": validation,
        "price": price,
        "verdict": verdict,
        "reasons": reasons,
    }


def _make_adk_agent():
    try:
        from google.adk.agents import LlmAgent  # type: ignore
    except Exception:
        return None

    class _SupplierProductAgent(LlmAgent):
        def __init__(self) -> None:
            super().__init__(
                name="supplier_product_agent",
                model="ollama/llama3.2",
                instruction=(
                    "Coordinate Product Classification, Specification Validation, and "
                    "Price Normalisation across one supplier row. Return a verdict."
                ),
            )

    return _SupplierProductAgent


def SupplierProductAgent():  # noqa: N802
    cls = _make_adk_agent()
    if cls is None:
        class _Shim:
            name = "supplier_product_agent"

            def run(self, *, row: Dict[str, str], default_currency: str = "USD") -> Dict[str, object]:
                return classify_extracted_row(row, default_currency)

        return _Shim()
    return cls()
