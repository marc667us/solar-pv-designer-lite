"""Geo-sensitive equipment + installation compliance.

Per owner directive 2026-06-27: app must be geosensitive to installation
and equipment standards. All marketplace products and BOQ line items must
match the destination country's:
  - mains voltage (single-phase + three-phase)
  - mains frequency (50 / 60 Hz)
  - installation wiring code (BS 7671 / NEC 2023 / IEC 60364 / etc.)
  - acceptable equipment certification bodies (CE, UKCA, UL, ETL, KEBS,
    SONCAP, GS, JIS, ...)
  - plug socket type (relevant for AC loads + portable inverter outputs)

Pure-Python module. No DB, no external services. Importable from web_app.py
and from any future module that needs the same checks.
"""
from __future__ import annotations
import re
from typing import Iterable


# ---------------------------------------------------------------------------
# Country grid profile registry
# Keys: ISO 3166-1 alpha-2 country code (uppercase)
# Some long country names also map to the code via _COUNTRY_NAME_TO_CODE.
# ---------------------------------------------------------------------------

COUNTRY_GRID_PROFILES: dict[str, dict] = {
    # ── Africa ──────────────────────────────────────────────────────────
    "GH": {
        "country": "Ghana",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["G"],
        "wiring_code": "BS 7671 / IEC 60364",
        "equipment_standards": ["BS EN", "IEC 60364", "IEC 61215", "IEC 61730",
                                "IEC 62109 (inverter safety)"],
        "certification_bodies": ["CE", "UKCA", "TUV", "GS", "VDE",
                                 "Ghana Standards Authority (GSA)"],
        "earthing_system": "TN-S / TN-C-S",
        "regulator": "Energy Commission of Ghana / ECG / NEDCO",
    },
    "NG": {
        "country": "Nigeria",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["D", "G"],
        "wiring_code": "IEC 60364 / NESI / Nigerian Wiring Regs",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730",
                                "IEC 62109", "SONCAP"],
        "certification_bodies": ["CE", "TUV", "VDE", "SON (Standards Organisation of Nigeria)"],
        "earthing_system": "TN-C-S",
        "regulator": "NERC",
    },
    "KE": {
        "country": "Kenya",
        "voltage_v_single": 240, "voltage_v_three": 415,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["G"],
        "wiring_code": "KS IEC 60364 / KEBS KS 03-12",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730",
                                "IEC 62109", "KEBS"],
        "certification_bodies": ["CE", "TUV", "VDE", "KEBS"],
        "earthing_system": "TN-C-S",
        "regulator": "EPRA",
    },
    "ZA": {
        "country": "South Africa",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 10, "frequency_hz": 50,
        "plug_types": ["M", "N", "D"],
        "wiring_code": "SANS 10142-1 / IEC 60364",
        "equipment_standards": ["IEC 60364", "SANS 10142", "IEC 61215",
                                "IEC 61730", "IEC 62109"],
        "certification_bodies": ["CE", "TUV", "VDE", "SABS"],
        "earthing_system": "TN-C-S",
        "regulator": "NERSA",
    },
    "TZ": {
        "country": "Tanzania",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["D", "G"],
        "wiring_code": "IEC 60364 / TBS",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "TBS"],
        "certification_bodies": ["CE", "TUV", "TBS"],
        "earthing_system": "TN-S",
        "regulator": "EWURA",
    },
    "UG": {
        "country": "Uganda",
        "voltage_v_single": 240, "voltage_v_three": 415,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["G"],
        "wiring_code": "IEC 60364 / UNBS",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "UNBS"],
        "certification_bodies": ["CE", "TUV", "UNBS"],
        "regulator": "ERA",
    },
    "RW": {
        "country": "Rwanda",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "J"],
        "wiring_code": "IEC 60364 / RSB",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "RSB"],
        "certification_bodies": ["CE", "TUV", "RSB"],
        "regulator": "RURA",
    },
    "ET": {
        "country": "Ethiopia",
        "voltage_v_single": 220, "voltage_v_three": 380,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "F", "L"],
        "wiring_code": "IEC 60364 / EES",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CE", "TUV"],
        "regulator": "EEU",
    },
    "EG": {
        "country": "Egypt",
        "voltage_v_single": 220, "voltage_v_three": 380,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "F"],
        "wiring_code": "IEC 60364 / EOS",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "EOS"],
        "certification_bodies": ["CE", "TUV", "EOS"],
        "regulator": "EgyptERA",
    },
    "SN": {
        "country": "Senegal",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "D", "E", "K"],
        "wiring_code": "NF C 15-100 / IEC 60364",
        "equipment_standards": ["IEC 60364", "NF (French)", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CE", "NF", "TUV"],
        "regulator": "CRSE",
    },
    "CI": {
        "country": "Cote d'Ivoire",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "E"],
        "wiring_code": "NF C 15-100 / IEC 60364",
        "equipment_standards": ["IEC 60364", "NF", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CE", "NF", "TUV"],
        "regulator": "ANARE",
    },
    "ZM": {
        "country": "Zambia",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "D", "G"],
        "wiring_code": "IEC 60364 / ZABS",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "ZABS"],
        "certification_bodies": ["CE", "TUV", "ZABS"],
        "regulator": "ERB",
    },

    # ── Europe ──────────────────────────────────────────────────────────
    "GB": {
        "country": "United Kingdom",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 10, "frequency_hz": 50,
        "plug_types": ["G"],
        "wiring_code": "BS 7671",
        "equipment_standards": ["BS 7671", "BS EN", "IEC 61215", "IEC 61730",
                                "BS EN 62109"],
        "certification_bodies": ["UKCA", "CE", "BSI", "TUV"],
        "earthing_system": "TN-C-S / TN-S",
        "regulator": "Ofgem / DNO",
    },
    "DE": {
        "country": "Germany",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 10, "frequency_hz": 50,
        "plug_types": ["C", "F"],
        "wiring_code": "DIN VDE 0100 / IEC 60364",
        "equipment_standards": ["VDE", "DIN", "IEC 60364", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CE", "GS", "TUV", "VDE"],
        "regulator": "BNetzA",
    },
    "FR": {
        "country": "France",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 10, "frequency_hz": 50,
        "plug_types": ["C", "E"],
        "wiring_code": "NF C 15-100 / IEC 60364",
        "equipment_standards": ["NF", "IEC 60364", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CE", "NF", "TUV"],
        "regulator": "CRE",
    },

    # ── Americas ────────────────────────────────────────────────────────
    "US": {
        "country": "United States",
        "voltage_v_single": 120, "voltage_v_three": 208,
        "voltage_v_three_alt": 240,  # 240V split-phase residential
        "voltage_tolerance_pct": 5, "frequency_hz": 60,
        "plug_types": ["A", "B"],
        "wiring_code": "NEC 2023 (NFPA 70)",
        "equipment_standards": ["UL", "ETL", "ANSI", "IEEE 1547",
                                "UL 1741 (inverter)"],
        "certification_bodies": ["UL", "ETL", "CSA"],
        "earthing_system": "TN-C-S",
        "regulator": "FERC / state PUCs",
    },
    "CA": {
        "country": "Canada",
        "voltage_v_single": 120, "voltage_v_three": 208,
        "voltage_tolerance_pct": 6, "frequency_hz": 60,
        "plug_types": ["A", "B"],
        "wiring_code": "CSA C22.1 (Canadian Electrical Code)",
        "equipment_standards": ["CSA", "UL", "IEEE 1547"],
        "certification_bodies": ["CSA", "UL"],
        "regulator": "Provincial Energy Boards",
    },
    "BR": {
        "country": "Brazil",
        "voltage_v_single": 127,  # variable; some regions 220
        "voltage_v_three": 220,
        "voltage_tolerance_pct": 6, "frequency_hz": 60,
        "plug_types": ["N"],
        "wiring_code": "NBR 5410 / IEC 60364",
        "equipment_standards": ["NBR", "IEC 60364", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["INMETRO", "CE", "TUV"],
        "regulator": "ANEEL",
    },

    # ── Asia ────────────────────────────────────────────────────────────
    "IN": {
        "country": "India",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "D", "M"],
        "wiring_code": "IS 732 / IEC 60364",
        "equipment_standards": ["IS", "IEC 60364", "IEC 61215", "IEC 61730",
                                "BIS"],
        "certification_bodies": ["BIS", "CE", "TUV", "MNRE-listed"],
        "regulator": "CEA / MNRE",
    },
    "PK": {
        "country": "Pakistan",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,
        "plug_types": ["C", "D", "G"],
        "wiring_code": "IEC 60364 / PSQCA",
        "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730", "PSQCA"],
        "certification_bodies": ["CE", "TUV", "PSQCA"],
        "regulator": "NEPRA",
    },
    "JP": {
        "country": "Japan",
        "voltage_v_single": 100,  # 100V; east 50Hz / west 60Hz
        "voltage_v_three": 200,
        "voltage_tolerance_pct": 6, "frequency_hz": 50,  # default east; west=60
        "plug_types": ["A", "B"],
        "wiring_code": "JIS C / JEAC 8001",
        "equipment_standards": ["JIS", "PSE", "IEC 61215", "IEC 61730"],
        "certification_bodies": ["PSE", "JET", "CE"],
        "regulator": "METI",
    },
    "AU": {
        "country": "Australia",
        "voltage_v_single": 230, "voltage_v_three": 400,
        "voltage_tolerance_pct": 10, "frequency_hz": 50,
        "plug_types": ["I"],
        "wiring_code": "AS/NZS 3000",
        "equipment_standards": ["AS/NZS 3000", "AS/NZS 4777 (inverter)",
                                "IEC 61215", "IEC 61730"],
        "certification_bodies": ["CEC-listed", "RCM", "SAA"],
        "regulator": "AER / state DNSPs",
    },
}

# Country full name (lowercase) -> ISO2 code for resilient lookups
_COUNTRY_NAME_TO_CODE = {
    p["country"].lower(): code for code, p in COUNTRY_GRID_PROFILES.items()
}
# Common alternative spellings
_COUNTRY_NAME_TO_CODE.update({
    "uk": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "usa": "US", "america": "US",
    "ivory coast": "CI", "cote d'ivoire": "CI",
})

# Defaults when a country is unknown or unspecified: assume IEC 60364 +
# 230/400V/50Hz (the most common global setup; covers most of Africa,
# Europe, Asia, Oceania). NEVER trust this if you actually know the
# country -- pass it in.
_DEFAULT_PROFILE = {
    "country": "Unspecified",
    "voltage_v_single": 230, "voltage_v_three": 400,
    "voltage_tolerance_pct": 10, "frequency_hz": 50,
    "wiring_code": "IEC 60364",
    "equipment_standards": ["IEC 60364", "IEC 61215", "IEC 61730"],
    "certification_bodies": ["CE", "TUV"],
}


def resolve_country_code(value):
    """Accept ISO2 code OR country name; return uppercase ISO2 or None."""
    if not value:
        return None
    v = str(value).strip()
    if len(v) == 2 and v.upper() in COUNTRY_GRID_PROFILES:
        return v.upper()
    return _COUNTRY_NAME_TO_CODE.get(v.lower())


def get_country_profile(country_code_or_name):
    """Return the profile dict for a country code/name. Falls back to a
    default global profile (IEC 60364, 230V/50Hz) so callers can always
    rely on the returned dict having every key."""
    code = resolve_country_code(country_code_or_name)
    return COUNTRY_GRID_PROFILES.get(code, _DEFAULT_PROFILE)


# ---------------------------------------------------------------------------
# Spec parsing (best-effort from free-text product spec strings)
# ---------------------------------------------------------------------------

_VOLTAGE_RE = re.compile(
    # Accepts: 230V, 230 V, 230VAC, 230Vac, 230V-AC, 230V/AC, 230VDC
    # but NOT: Vmp=41.8V (preceded by '='), Voc=49.5V (PV DC nominals via
    # the small-DC drop list below).
    r"(?<![=:])(\d{2,4})\s*[Vv](?:[\-\s/]?(?:[Aa][Cc]|[Dd][Cc]))?\b",
)
_FREQUENCY_RE = re.compile(
    r"\b(50|60)\s*[Hh][Zz]\b",
    flags=re.IGNORECASE,
)


def parse_voltages(spec_text):
    """Return a sorted list of voltages mentioned in the spec text.
    E.g. '230VAC, 12VDC battery, 400V three-phase' -> [12, 230, 400].
    Empty list if nothing recognisable."""
    if not spec_text:
        return []
    matches = _VOLTAGE_RE.findall(spec_text)
    out = []
    for m in matches:
        try:
            v = int(m)
        except (TypeError, ValueError):
            continue
        # Drop obviously non-mains values (DC battery 12/24/48; PV Vmp etc.)
        if v in (3, 5, 9, 12, 24, 48, 96):  # DC-only nominals
            continue
        if 50 <= v <= 1500:
            out.append(v)
    return sorted(set(out))


def parse_frequencies(spec_text):
    """Return list of frequencies in Hz mentioned (50 / 60). Empty if none."""
    if not spec_text:
        return []
    return sorted({int(m) for m in _FREQUENCY_RE.findall(spec_text)})


def parse_certifications(spec_text):
    """Return list of recognised certification body acronyms in the spec.
    Match-set is small + curated to avoid false positives."""
    if not spec_text:
        return []
    out = []
    for token in ("CE", "UKCA", "UL", "ETL", "CSA", "TUV", "VDE", "GS",
                  "BSI", "KEBS", "SONCAP", "SON", "SABS", "NF", "BIS",
                  "INMETRO", "PSE", "JIS", "ANSI", "RCM", "SAA",
                  "MNRE", "RoHS", "REACH"):
        if re.search(rf"\b{re.escape(token)}\b", spec_text):
            out.append(token)
    return out


# ---------------------------------------------------------------------------
# Compliance findings
# ---------------------------------------------------------------------------

def voltage_compatible(product_voltage, profile):
    """True if the product's voltage is within tolerance of the country's
    single-phase OR three-phase mains. Tolerance comes from profile."""
    if not product_voltage:
        return None  # unknown -- caller decides
    tol_pct = profile.get("voltage_tolerance_pct", 10) / 100.0
    for key in ("voltage_v_single", "voltage_v_three", "voltage_v_three_alt"):
        v = profile.get(key)
        if v and abs(product_voltage - v) <= v * tol_pct:
            return True
    return False


# Categories that are mains-bound. Other categories (PV modules, DC
# batteries, raw cables, structures, fasteners) are AC-frequency-
# agnostic and skip voltage/frequency checks.
_AC_BOUND_CATEGORIES = {
    "inverter", "inverters", "ups", "ac_loads", "appliances",
    "lighting", "sockets", "outlets", "switches",
    "switchgear", "panels", "distribution", "transformers",
    "power_system", "ac_cables", "generators", "motors",
}


def is_ac_bound(category_code, category_name=""):
    cc = (category_code or "").lower()
    cn = (category_name or "").lower()
    if cc in _AC_BOUND_CATEGORIES: return True
    for kw in _AC_BOUND_CATEGORIES:
        if kw in cn: return True
    return False


def compliance_findings_for_product(product, country_code_or_name):
    """Inspect a single product dict against a country's grid profile.
    Returns a list of findings: [{severity, code, message}].

    Expected product keys (any may be missing):
        name, spec, category_code, category_name, voltage_v, frequency_hz,
        compliance_standards (comma-separated)

    severity: high | medium | low
    code: machine-readable finding key (e.g. 'voltage_mismatch')
    """
    profile = get_country_profile(country_code_or_name)
    if profile is _DEFAULT_PROFILE and not country_code_or_name:
        # No country specified -- nothing to check against.
        return []
    findings = []

    cat_code = product.get("category_code") or product.get("cat_code") or ""
    cat_name = product.get("category_name") or product.get("category") or ""
    ac_bound = is_ac_bound(cat_code, cat_name)

    spec = (product.get("spec") or product.get("description") or "")

    # Structured voltage_v wins over parsed spec.
    voltages = []
    if product.get("voltage_v"):
        try: voltages = [int(product["voltage_v"])]
        except (TypeError, ValueError): pass
    if not voltages:
        voltages = parse_voltages(spec)

    if ac_bound and voltages:
        if not any(voltage_compatible(v, profile) for v in voltages):
            findings.append({
                "severity": "high",
                "code": "voltage_mismatch",
                "message": ("Voltage " + "/".join(str(v) + "V" for v in voltages)
                            + " does not match "
                            + profile["country"]
                            + " mains ("
                            + str(profile["voltage_v_single"]) + "V single-phase / "
                            + str(profile["voltage_v_three"]) + "V three-phase, +-"
                            + str(profile["voltage_tolerance_pct"]) + "%)."),
            })

    # Frequency
    freqs = []
    if product.get("frequency_hz"):
        try: freqs = [int(product["frequency_hz"])]
        except (TypeError, ValueError): pass
    if not freqs:
        freqs = parse_frequencies(spec)
    if ac_bound and freqs:
        if profile["frequency_hz"] not in freqs:
            findings.append({
                "severity": "high",
                "code": "frequency_mismatch",
                "message": ("Frequency " + "/".join(str(f) + "Hz" for f in freqs)
                            + " does not match "
                            + profile["country"]
                            + " mains (" + str(profile["frequency_hz"]) + "Hz)."),
            })

    # Certification body coverage
    listed = []
    if product.get("compliance_standards"):
        listed = [s.strip() for s in str(product["compliance_standards"]).split(",") if s.strip()]
    if not listed:
        listed = parse_certifications(spec)
    # Certification check is only meaningful for AC-bound products. PV
    # modules / structures / DC components are governed by IEC product
    # standards (IEC 61215 etc.) which aren't certification BODIES.
    if ac_bound:
        expected = set(profile.get("certification_bodies", []))
        listed_upper = {s.upper() for s in listed}
        overlap = listed_upper & {e.upper() for e in expected}
        if expected and listed and not overlap:
            findings.append({
                "severity": "medium",
                "code": "no_accepted_certification",
                "message": ("No accepted certification body listed for "
                            + profile["country"]
                            + " (accepts: " + ", ".join(sorted(expected)) + "). "
                            + "Found: " + ", ".join(sorted(listed)) + "."),
            })
        elif expected and not listed:
            findings.append({
                "severity": "low",
                "code": "no_certification_declared",
                "message": ("AC-bound product with no certification declared. "
                            + profile["country"] + " accepts: "
                            + ", ".join(sorted(expected)) + "."),
            })

    return findings


def compliance_findings_for_lines(items, lines, country_code_or_name):
    """Run compliance_findings_for_product over every BOQ line.
    Returns BOQ-shape findings: [{severity, line_no, message, code}].
    line_no is 1-based."""
    if not country_code_or_name:
        return []
    out = []
    for idx, line in enumerate(lines, start=1):
        it = line.get("item") if isinstance(line, dict) else None
        if it is None:
            continue
        keys = it.keys() if hasattr(it, "keys") else []
        get = (lambda k: (it[k] if k in keys else None)) if keys else (lambda k: None)
        product = {
            "name": get("catalog_name") or get("custom_name") or "",
            "spec": get("catalog_spec") or get("spec") or "",
            "category_code": get("category_code") or "",
            "category_name": get("category_name") or get("category") or "",
        }
        # Pass through structured fields if present
        for k in ("voltage_v", "frequency_hz", "compliance_standards"):
            v = get(k)
            if v is not None:
                product[k] = v
        for f in compliance_findings_for_product(product, country_code_or_name):
            out.append({
                "severity": f["severity"],
                "line_no": idx,
                "message": "[" + product["name"] + "] " + f["message"],
                "code": f["code"],
            })
    return out


__all__ = [
    "COUNTRY_GRID_PROFILES",
    "resolve_country_code",
    "get_country_profile",
    "parse_voltages",
    "parse_frequencies",
    "parse_certifications",
    "voltage_compatible",
    "is_ac_bound",
    "compliance_findings_for_product",
    "compliance_findings_for_lines",
]
