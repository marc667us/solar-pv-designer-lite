"""Fix _safe_card_payload to use SolarPro's real result-schema keys.

The original injection guessed at `pv_size_kw`, `annual_savings_usd`,
`payback_years`, `boq.modules_qty` etc. None of those exist on real
projects -- web_app.py:3116 saves results as:
    pv_kw, num_panels, bat_kwh, inv_kw, daily_kwh,
    economics: { annual_sav, payback, total_local, ... },
    boq_rows: [...], boq_grand: <number>

This patch replaces the function body in web_app.py via byte search.
Idempotent via SENTINEL check. Also rewrites
new_growth_layer_routes.py so future re-splices are clean.
"""
from __future__ import annotations
from pathlib import Path
import re, sys

ROOT = Path(__file__).parent
TARGET = ROOT / "web_app.py"
NEW_ROUTES_SRC = ROOT / "new_growth_layer_routes.py"

SENTINEL = b"# growth-payload-fix-real-schema-applied"

NEW_FN = (b'''def _safe_card_payload(project_row, asset_type):
    """Extract SAFE-TO-PUBLISH fields from project.data_json.
    Uses SolarPro\'s real schema (web_app.py:3116):
        results.pv_kw, results.num_panels, results.bat_kwh, results.inv_kw,
        results.daily_kwh, results.economics.{annual_sav, payback,
        total_local, ...}, results.boq_rows, results.boq_grand.
    NEVER includes: rate_buildup, supplier_private_prices, internal_notes,
    admin info, or full BOQ pricing. Privacy guardrail per spec \xc2\xa720.
    # ''' + SENTINEL + b'''
    """
    try:
        data = _gl_json.loads(project_row["data_json"] or "{}")
    except Exception:
        data = {}
    results = data.get("results") or {}
    eco = results.get("economics") or {}
    project_name = (project_row["name"] if "name" in project_row.keys()
                    else "Solar project")
    # Location lives at top of data, not inside results
    location = (data.get("location") or data.get("country")
                or data.get("location_label")
                or (data.get("location") or {}).get("label", "")
                or "")
    if isinstance(location, dict):
        location = location.get("label", "") or ""
    location = str(location)[:80]
    # Currency: prefer the symbol the user picked; else 3-letter code
    currency = (data.get("symbol") or data.get("currency") or "USD")
    currency = str(currency)[:6]

    # Real schema: results.pv_kw (legacy fallbacks for old projects)
    pv_kw = (results.get("pv_kw") or results.get("pv_size_kw")
             or results.get("system_kw") or 0)
    # Annual savings live INSIDE economics as `annual_sav`
    annual_savings = (eco.get("annual_sav")
                      or results.get("annual_savings_usd")
                      or results.get("annual_savings") or 0)
    # Payback INSIDE economics as `payback`
    payback = (eco.get("payback")
               or results.get("payback_years")
               or results.get("payback") or 0)
    try: payback = float(payback)
    except Exception: payback = 0
    if payback != payback or payback == float("inf"):  # NaN / inf guard
        payback = 0

    if asset_type == "solar_savings_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "payback_years": round(float(payback or 0), 1),
            "currency": currency,
        }
    if asset_type == "energy_score_card":
        # Energy-independence not directly stored; estimate from system type.
        system_type = (data.get("system_type", "") or "").lower()
        default_score = (95 if "off-grid" in system_type or "off grid" in system_type
                         else 70 if "hybrid" in system_type
                         else 35)
        score = (results.get("energy_independence_score")
                 or results.get("self_sufficiency_pct")
                 or results.get("solar_fraction_pct")
                 or default_score)
        return {
            "project_name": project_name, "location": location,
            "energy_score": round(float(score or 0), 0),
            "system_size_kw": round(float(pv_kw or 0), 2),
            "daily_kwh": round(float(results.get("daily_kwh") or 0), 1),
        }
    if asset_type == "boq_summary_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "module_count": int(results.get("num_panels") or 0),
            "battery_kwh": round(float(results.get("bat_kwh") or 0), 1),
            "inverter_kw": round(float(results.get("inv_kw") or 0), 1),
            # NO unit prices, NO supplier names, NO rate buildup.
        }
    if asset_type == "proposal_preview":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "payback_years": round(float(payback or 0), 1),
            "currency": currency,
        }
    if asset_type == "roof_before_after_card":
        return {
            "project_name": project_name, "location": location,
            "system_size_kw": round(float(pv_kw or 0), 2),
            "annual_savings": round(float(annual_savings or 0), 0),
            "currency": currency,
        }
    return {"project_name": project_name, "location": location}
''')


def _patch_web_app() -> int:
    """Find the existing _safe_card_payload(...) definition + replace it
    with NEW_FN. The original definition runs from
    'def _safe_card_payload(...' down to the matching '\\n\\ndef ' line."""
    src = TARGET.read_bytes()
    if SENTINEL in src:
        print("[skip] web_app.py payload fix already applied"); return 0
    # Match the function from its def line up to (but not including) the next
    # top-level def/blank-line boundary. Multiline regex on bytes.
    pattern = re.compile(
        rb"def _safe_card_payload\(project_row, asset_type\):.*?"
        rb"(?=\r?\n\r?\ndef _)",
        flags=re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        print("[fail] _safe_card_payload anchor not found in web_app.py")
        return 2
    new_src = src[:m.start()] + NEW_FN.rstrip(b"\r\n") + src[m.end():]
    TARGET.write_bytes(new_src)
    print(f"[ok] replaced _safe_card_payload (offset {m.start()}, "
          f"size {m.end() - m.start()} -> {len(NEW_FN.rstrip())} bytes)")
    return 0


def _patch_source() -> int:
    """Mirror the same fix in new_growth_layer_routes.py so re-splice is clean."""
    src = NEW_ROUTES_SRC.read_text(encoding="utf-8")
    if "growth-payload-fix-real-schema-applied" in src:
        print("[skip] new_growth_layer_routes.py already updated"); return 0
    # Find and replace
    pattern = re.compile(
        r"def _safe_card_payload\(project_row, asset_type\):.*?(?=\n\ndef _)",
        flags=re.DOTALL,
    )
    m = pattern.search(src)
    if not m:
        print("[warn] _safe_card_payload not found in source -- skipping"); return 0
    new_src = src[:m.start()] + NEW_FN.decode("utf-8").rstrip() + src[m.end():]
    NEW_ROUTES_SRC.write_text(new_src, encoding="utf-8")
    print("[ok] mirrored fix into new_growth_layer_routes.py")
    return 0


if __name__ == "__main__":
    rc = _patch_web_app() or _patch_source()
    sys.exit(rc)
