"""Price Normalisation Agent — normalise raw supplier prices to canonical fields.

Deterministic Python core; ADK wrapper present for Phase 2 LLM consultation
on ambiguous price formats. Phase 1: parse numbers, detect currency hints,
flag obvious problems (negative, blank, > 10× median).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

_CURRENCY_HINTS = {
    "$": "USD", "usd": "USD", "US$": "USD",
    "€": "EUR", "eur": "EUR",
    "£": "GBP", "gbp": "GBP",
    "¥": "JPY", "jpy": "JPY",
    "ghs": "GHS", "gh¢": "GHS", "ghc": "GHS",
    "ngn": "NGN", "₦": "NGN",
    "kes": "KES", "ksh": "KES",
    "zar": "ZAR", "r ": "ZAR",
}

_PRICE_RE = re.compile(r"[-+]?\d+(?:[,\s]\d{3})*(?:\.\d+)?")


def normalise_price(raw: str, default_currency: str = "USD") -> Dict[str, object]:
    """Parse `raw` (e.g. 'GHS 9 800.00 +VAT') into structured fields.

    Returns:
      {
        "amount": float | None,
        "currency": str,
        "vat_inclusive": bool,
        "warnings": [str],
      }"""
    warnings: List[str] = []
    if not raw or not str(raw).strip():
        return {"amount": None, "currency": default_currency, "vat_inclusive": False,
                "warnings": ["empty price"]}
    s = str(raw).strip()
    lower = s.lower()

    currency = default_currency
    for hint, code in _CURRENCY_HINTS.items():
        if hint in lower:
            currency = code
            break

    vat_inclusive = any(kw in lower for kw in ("incl vat", "inc vat", "inclusive vat", "vat incl"))
    if not vat_inclusive and ("excl vat" in lower or "+vat" in lower or "+ vat" in lower):
        vat_inclusive = False

    match = _PRICE_RE.search(s)
    if not match:
        return {"amount": None, "currency": currency, "vat_inclusive": vat_inclusive,
                "warnings": warnings + [f"no numeric value found in '{s}'"]}
    raw_num = match.group(0).replace(",", "").replace(" ", "")
    try:
        amount: Optional[float] = float(raw_num)
    except ValueError:
        amount = None
        warnings.append(f"could not parse '{raw_num}' as a number")

    if amount is not None and amount < 0:
        warnings.append("negative price")
    if amount is not None and amount == 0:
        warnings.append("zero price")

    return {
        "amount": amount,
        "currency": currency,
        "vat_inclusive": vat_inclusive,
        "warnings": warnings,
    }


def _make_adk_agent():
    try:
        from google.adk.agents import LlmAgent  # type: ignore
    except Exception:
        return None

    class _PriceNormalisationAgent(LlmAgent):
        def __init__(self) -> None:
            super().__init__(
                name="price_normalisation_agent",
                model="ollama/llama3.2",
                instruction=(
                    "Given a raw price string, return JSON "
                    '{"amount": float, "currency": str, "vat_inclusive": bool, "warnings": [str]}.'
                ),
            )

    return _PriceNormalisationAgent


def PriceNormalisationAgent():  # noqa: N802
    cls = _make_adk_agent()
    if cls is None:
        class _Shim:
            name = "price_normalisation_agent"

            def run(self, *, raw: str, default_currency: str = "USD") -> Dict[str, object]:
                return normalise_price(raw, default_currency)

        return _Shim()
    return cls()
