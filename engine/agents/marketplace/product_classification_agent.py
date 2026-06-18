"""Product Classification Agent — maps free-text product into the 18-category taxonomy.

Deterministic core (`classify_product`) uses keyword matching. The ADK
wrapper exists to plug into solar's agent runtime when Phase 2 adds an LLM
tie-break layer; Phase 1 ships the pure-Python core only — zero LLM cost,
fully testable, no flakiness.
"""
from __future__ import annotations

from typing import Tuple

from ._llm import call_zero_cost_llm, parse_json_classification


_LLM_ESCALATE_THRESHOLD = 0.55
_LLM_MIN_CONFIDENCE = 0.55  # ignore LLM verdicts that come back weaker than this

# Each entry: (canonical_category_code, list of lower-case keywords that imply it)
# Order matters: more specific terms first so 'transformer' beats 'dist' for transformers.
_CLASSIFICATION_RULES = [
    ("transformers",       ["transformer", "kva", "11kv", "dyn11", "step-up", "step-down"]),
    ("avr",                ["avr", "voltage regulator", "servo", "stabiliser", "stabilizer"]),
    ("hv_cables",          ["hv cable", "11kv cable", "high voltage cable", "33kv cable"]),
    ("lv_cables",          ["lv cable", "armoured cable", "swa cable", "xlpe", "pvc/swa", "0.6/1 kv", "0.6/1kv"]),
    ("wires",              ["single core wire", "pvc wire", "flexible wire", "earth wire", "fire-resistant wire"]),
    ("panel_boards",       ["panel board", "mcc panel", "ats panel", "synchronising panel", "pfc panel", "control panel"]),
    ("distribution_boards", ["distribution board", "consumer unit", "spn db", "tpn db", "metal clad db"]),
    ("isolators",          ["isolator", "isolating switch"]),
    ("fuse_switches",      ["fuse switch", "switch fuse", "hrc fuse", "changeover switch"]),
    ("conduit",            ["conduit", "pvc pipe", "gi conduit"]),
    ("steel_boxes",        ["steel box", "back box", "gang box"]),
    ("circular_boxes",     ["circular box", "junction box", "ceiling box"]),
    ("cable_trays",        ["cable tray", "ladder tray", "wire mesh tray"]),
    ("trunking",           ["trunking", "dado", "skirting"]),
    ("earthing",           ["earth rod", "earth bar", "earth clamp", "copper tape", "earthing", "lightning protection"]),
    ("sockets",            ["socket outlet", "13a socket", "usb socket"]),
    ("dp_switches",        ["dp switch", "20a switch", "water heater switch", "ac switch"]),
    ("light_switches",     ["light switch", "1 gang switch", "2 gang switch", "3 gang switch", "dimmer", "key switch"]),
    ("solar_equipment",    ["pv module", "solar panel", "solar inverter", "hybrid inverter", "battery storage", "mppt", "charge controller", "solar cable"]),
    ("ict_elv",            ["data outlet", "network switch", "access point", "cctv", "fire alarm", "access control"]),
]


def _classify_by_keywords(name: str, spec: str = "", brand: str = "") -> Tuple[str, float]:
    """Pure-keyword classifier — the deterministic core. Always available."""
    haystack = " ".join([name, spec, brand]).lower()
    if not haystack.strip():
        return ("", 0.0)
    best = ("", 0.0)
    for code, keywords in _CLASSIFICATION_RULES:
        hits = sum(1 for kw in keywords if kw in haystack)
        if hits == 0:
            continue
        # Confidence: 1 hit ≈ 0.60, 2 hits ≈ 0.85, 3+ hits → 1.0
        conf = min(1.0, 0.35 + 0.25 * hits)
        if conf > best[1]:
            best = (code, conf)
    return best


def _classify_by_llm(name: str, spec: str, brand: str) -> Tuple[str, float]:
    """Zero-cost LLM tie-break — returns ('', 0.0) if no LLM reachable.

    Asks the LLM for {"category": <code>, "confidence": <0..1>} and only
    accepts a verdict if the returned `category` matches one of our
    canonical 20 codes. Anything else falls back to ('', 0.0)."""
    valid_codes = {code for code, _ in _CLASSIFICATION_RULES}
    system = (
        "You classify electrical products. Reply with ONE JSON object only, "
        "no prose, no markdown. Schema: "
        '{"category": "<one of: ' + ", ".join(sorted(valid_codes)) + '>", '
        '"confidence": <float 0..1>}.'
    )
    prompt = (
        f"Product name: {name}\n"
        f"Brand: {brand}\n"
        f"Spec: {spec}\n\n"
        "Return JSON only."
    )
    reply = call_zero_cost_llm(prompt, system)
    parsed = parse_json_classification(reply)
    if not parsed:
        return ("", 0.0)
    cat = str(parsed.get("category", "")).strip()
    if cat not in valid_codes:
        return ("", 0.0)
    try:
        conf = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    return (cat, max(0.0, min(1.0, conf)))


def classify_product(name: str, spec: str = "", brand: str = "") -> Tuple[str, float]:
    """Return (category_code, confidence 0..1) for a free-text product description.

    Two-stage:
      1. Deterministic keyword classifier — instant, free, predictable.
      2. If keyword confidence < 0.55 (no keyword hits OR exactly 1 hit at
         the weakest tier), escalate to an LLM tie-break via the zero-cost
         chain (OpenRouter free Nemotron → Ollama → None). The higher of
         the two verdicts wins.

    The deterministic core is always tried first, so on a hot path where
    suppliers upload a CSV of 100 products the LLM is only consulted for
    the genuinely ambiguous rows."""
    kw_code, kw_conf = _classify_by_keywords(name, spec, brand)
    if kw_conf >= _LLM_ESCALATE_THRESHOLD:
        return (kw_code, kw_conf)
    # Either no keyword hit or only a weak one — try the LLM.
    llm_code, llm_conf = _classify_by_llm(name, spec, brand)
    if llm_conf >= _LLM_MIN_CONFIDENCE and llm_conf > kw_conf:
        return (llm_code, llm_conf)
    # LLM unreachable or rejected — keep the deterministic verdict.
    return (kw_code, kw_conf)


def _make_adk_agent():
    """Lazy ADK construction — returns None when google-adk isn't installed."""
    try:
        from google.adk.agents import LlmAgent  # type: ignore
    except Exception:
        return None

    class _ProductClassificationAgent(LlmAgent):
        def __init__(self) -> None:
            super().__init__(
                name="product_classification_agent",
                model="ollama/llama3.2",
                instruction=(
                    "Given a product name and spec, return JSON "
                    '{"category": str, "subcategory": str, "confidence": float}. '
                    "Categories: " + ", ".join(c for c, _ in _CLASSIFICATION_RULES) + "."
                ),
            )

    return _ProductClassificationAgent


def ProductClassificationAgent():  # noqa: N802 — callable that matches LlmAgent constructor shape
    cls = _make_adk_agent()
    if cls is None:
        # ADK not available — return a deterministic shim with the same surface.
        class _Shim:
            name = "product_classification_agent"

            def run(self, *, name: str, spec: str = "", brand: str = "") -> dict:
                code, conf = classify_product(name, spec, brand)
                return {"category": code, "confidence": conf}

        return _Shim()
    return cls()
