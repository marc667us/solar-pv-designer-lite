"""Product Classification Agent — maps free-text product into the 18-category taxonomy.

Deterministic core (`classify_product`) uses keyword matching. The ADK
wrapper exists to plug into solar's agent runtime when Phase 2 adds an LLM
tie-break layer; Phase 1 ships the pure-Python core only — zero LLM cost,
fully testable, no flakiness.
"""
from __future__ import annotations

from typing import Tuple

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


def classify_product(name: str, spec: str = "", brand: str = "") -> Tuple[str, float]:
    """Return (category_code, confidence 0..1) for a free-text product description."""
    haystack = " ".join([name, spec, brand]).lower()
    if not haystack.strip():
        return ("", 0.0)
    best = ("", 0.0)
    for code, keywords in _CLASSIFICATION_RULES:
        hits = sum(1 for kw in keywords if kw in haystack)
        if hits == 0:
            continue
        # Confidence: 1 hit ≈ 0.55, 2 hits ≈ 0.80, 3+ hits → 1.0
        conf = min(1.0, 0.35 + 0.25 * hits)
        if conf > best[1]:
            best = (code, conf)
    return best


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
