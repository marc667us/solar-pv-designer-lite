"""Wire country-aware compliance into /marketplace (public page).

Adds `?country=<code>` support. Resolves current country from query param ->
user.country -> 'GH' default. For each product in products_view, attaches a
_compliance dict {status: ok|warn|fail, count: int, summary: str} derived
from country_compliance.compliance_findings_for_product. Passes
selected_country + country_options through to the template so the picker
can render.

Idempotent via SENTINEL. Operates at byte level on web_app.py.
"""
from __future__ import annotations
from pathlib import Path
import sys

TARGET = Path(__file__).parent / "web_app.py"
SENTINEL = b"marketplace-country-compliance-2026-06-27"


# Inject the per-product compliance attachment + country resolution INSIDE
# marketplace_public. Anchor is the line where products_view is built.
OLD_BLOCK = (
    b"    products_view = []\r\n"
    b"    for p in products:\r\n"
    b"        d = dict(p)\r\n"
    b"        d[\"price_in_currency\"] = float(d.get(\"price_usd\") or 0) * float(rate)\r\n"
    b"        products_view.append(d)\r\n"
)
NEW_BLOCK = (
    b"    # " + SENTINEL + b"\r\n"
    b"    # Country resolution: ?country= overrides; else user.country; else 'GH'.\r\n"
    b"    _u_country = \"\"\r\n"
    b"    try:\r\n"
    b"        _u = current_user()\r\n"
    b"        if _u and \"country\" in _u.keys():\r\n"
    b"            _u_country = _u[\"country\"] or \"\"\r\n"
    b"    except Exception:\r\n"
    b"        pass\r\n"
    b"    selected_country = (request.args.get(\"country\") or _u_country or \"GH\").strip()\r\n"
    b"    products_view = []\r\n"
    b"    for p in products:\r\n"
    b"        d = dict(p)\r\n"
    b"        d[\"price_in_currency\"] = float(d.get(\"price_usd\") or 0) * float(rate)\r\n"
    b"        if _country_compliance is not None and selected_country:\r\n"
    b"            try:\r\n"
    b"                fs = _country_compliance.compliance_findings_for_product({\r\n"
    b"                    \"name\":           d.get(\"name\") or \"\",\r\n"
    b"                    \"spec\":           d.get(\"spec\") or \"\",\r\n"
    b"                    \"category_name\":  d.get(\"category_name\") or \"\",\r\n"
    b"                }, selected_country)\r\n"
    b"            except Exception:\r\n"
    b"                fs = []\r\n"
    b"            high = sum(1 for f in fs if f.get(\"severity\") == \"high\")\r\n"
    b"            med  = sum(1 for f in fs if f.get(\"severity\") == \"medium\")\r\n"
    b"            low  = sum(1 for f in fs if f.get(\"severity\") == \"low\")\r\n"
    b"            if high:    status = \"fail\"\r\n"
    b"            elif med:   status = \"warn\"\r\n"
    b"            elif low:   status = \"info\"\r\n"
    b"            else:       status = \"ok\"\r\n"
    b"            d[\"_compliance\"] = {\r\n"
    b"                \"status\":   status,\r\n"
    b"                \"count\":    len(fs),\r\n"
    b"                \"findings\": fs[:4],\r\n"
    b"                \"high\":     high, \"med\": med, \"low\": low,\r\n"
    b"            }\r\n"
    b"        products_view.append(d)\r\n"
)

# Pass the new template kwargs.
OLD_RENDER = (
    b"        filter_count=_filter_count,\r\n"
    b"    )\r\n"
)
NEW_RENDER = (
    b"        filter_count=_filter_count,\r\n"
    b"        selected_country=selected_country,\r\n"
    b"        country_options=(_country_compliance.COUNTRY_GRID_PROFILES\r\n"
    b"                          if _country_compliance is not None else {}),\r\n"
    b"    )\r\n"
)


def main() -> int:
    src = TARGET.read_bytes()
    if SENTINEL in src:
        print("[skip] marketplace country compliance already wired")
        return 0
    if OLD_BLOCK not in src:
        print("[fail] products_view loop anchor not found")
        return 2
    if OLD_RENDER not in src:
        print("[fail] render_template anchor not found")
        return 2
    src = src.replace(OLD_BLOCK, NEW_BLOCK, 1)
    src = src.replace(OLD_RENDER, NEW_RENDER, 1)
    TARGET.write_bytes(src)
    print("[ok] marketplace country compliance wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
