"""Marketplace ADK agents — Phase 1 specialists.

Per CLAUDE.md §0.1 every agent in solar is Google ADK. These four mirror the
shading_agent.py pattern: ADK class as the wrapper, deterministic Python core
as the source of truth, LLM as an optional consultative layer for ambiguous
cases (Phase 2 wires that part — Phase 1 ships deterministic-only).

Exports:
  - SupplierProductAgent      : ingest products from supplier forms / CSV / XLSX
  - ProductClassificationAgent: map free-text product into the 18-category taxonomy
  - SpecificationValidationAgent: detect missing required spec fields per category
  - PriceNormalisationAgent   : normalise currency / unit / VAT-incl flag
"""
from .supplier_product_agent import SupplierProductAgent, classify_extracted_row
from .product_classification_agent import ProductClassificationAgent, classify_product
from .specification_validation_agent import (
    SpecificationValidationAgent,
    REQUIRED_FIELDS,
    validate_spec,
)
from .price_normalisation_agent import PriceNormalisationAgent, normalise_price

__all__ = [
    "SupplierProductAgent",
    "ProductClassificationAgent",
    "SpecificationValidationAgent",
    "PriceNormalisationAgent",
    "classify_extracted_row",
    "classify_product",
    "validate_spec",
    "normalise_price",
    "REQUIRED_FIELDS",
]
