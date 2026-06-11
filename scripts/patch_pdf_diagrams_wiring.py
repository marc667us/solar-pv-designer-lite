"""
Byte-safe patcher: wires pdf_diagrams into web_app.py PDF export routes.

Per project CLAUDE.md:
  - web_app.py has CRLF + mojibake; Edit tool corrupts it.
  - Use byte-level patching, preserve CRLF, idempotent.

Patches:
  H. Insert _diagrams_markdown helper before _fmt.
  1. export_pdf_boq          (BOQ — Bill of Quantities)
  2. export_pdf_installation (Installation Report)
  3. export_pdf_pv           (PV System Design Report)
  4. export_pdf_proposal     (PV Solar Proposal)

Re-running is safe: each patch checks for a marker first.
"""

from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBAPP = ROOT / "web_app.py"


HELPER_BLOCK = (
    b"# AI_BUDGET_LEDGER_MARKER_HELPER_DIAGRAMS\r\n"
    b"def _diagrams_markdown(d, r):\r\n"
    b"    \"\"\"Return markdown block with SLD + topology + mounting-plan PNG embeds.\r\n"
    b"    Lazy-imports pdf_diagrams so the module is optional at runtime. Best-effort\r\n"
    b"    rendering: if a value is missing or matplotlib trips, returns an empty\r\n"
    b"    string and the PDF still ships without diagrams.\"\"\"\r\n"
    b"    try:\r\n"
    b"        import pdf_diagrams as _pdfd\r\n"
    b"    except Exception:\r\n"
    b"        return \"\"\r\n"
    b"    try:\r\n"
    b"        pv_kw       = float(r.get(\"pv_kw\") or d.get(\"pv_kw\") or 0)\r\n"
    b"        inv_kw      = float(r.get(\"inv_kw\") or 0)\r\n"
    b"        bat_kwh     = float(r.get(\"bat_kwh\") or 0)\r\n"
    b"        num_bat     = int(r.get(\"num_bat\") or 1)\r\n"
    b"        mppt_a      = int(r.get(\"mppt_a\") or 60)\r\n"
    b"        num_panels  = int(r.get(\"num_panels\") or 0)\r\n"
    b"        panel_wp    = int(r.get(\"panel_wp\") or 400)\r\n"
    b"        chemistry   = r.get(\"chemistry\") or \"LiFePO4\"\r\n"
    b"        system_type = (d.get(\"system_type\") or \"hybrid\").lower()\r\n"
    b"        daily_kwh   = float(d.get(\"daily_kwh\") or 0)\r\n"
    b"        psh         = float(d.get(\"psh\") or 5.0)\r\n"
    b"        mounting    = d.get(\"mounting_type\") or \"rooftop_pitched\"\r\n"
    b"    except Exception:\r\n"
    b"        return \"\"\r\n"
    b"    try:\r\n"
    b"        sld  = _pdfd.single_line_diagram_b64(pv_kw, inv_kw, bat_kwh, num_bat,\r\n"
    b"                                              mppt_a, chemistry, system_type)\r\n"
    b"        topo = _pdfd.system_topology_b64(pv_kw, inv_kw, bat_kwh, daily_kwh,\r\n"
    b"                                          psh, system_type)\r\n"
    b"        plan = (_pdfd.mounting_plan_b64(num_panels, panel_wp, \"landscape\", mounting)\r\n"
    b"                if num_panels > 0 else \"\")\r\n"
    b"    except Exception:\r\n"
    b"        return \"\"\r\n"
    b"    md = \"# Design Diagrams\\n\\n\"\r\n"
    b"    md += \"## Single Line Diagram\\n\\n![Single Line Diagram](\" + sld + \")\\n\\n\"\r\n"
    b"    md += \"## System Topology\\n\\n![System Topology](\" + topo + \")\\n\\n\"\r\n"
    b"    if plan:\r\n"
    b"        md += \"## Mounting Plan\\n\\n![Mounting Plan](\" + plan + \")\\n\\n\"\r\n"
    b"    md += \"---\\n\\n\"\r\n"
    b"    return md\r\n"
    b"\r\n"
    b"\r\n"
)

ROUTES = [
    (b"return _render_pdf(f\"Bill of Quantities", "BOQ"),
    (b"return _render_pdf(f\"Installation Report", "Installation"),
    (b"return _render_pdf(f\"PV System Design Report", "PV"),
    (b"return _render_pdf(f\"PV Solar Proposal", "Proposal"),
]
# Each route: insert `md = _diagrams_markdown(d, r) + md\r\n    ` directly
# before the `return _render_pdf(...)` line. The indent is 4 spaces (route body).
PREPEND_LINE = b"md = _diagrams_markdown(d, r) + md\r\n    "


def main() -> int:
    data = WEBAPP.read_bytes()
    original = data
    patched = 0

    # ── Patch H: helper insertion ───────────────────────────────────────────
    helper_marker = b"AI_BUDGET_LEDGER_MARKER_HELPER_DIAGRAMS"
    if helper_marker in data:
        print("[H] helper already present")
    else:
        # Insert right before `def _fmt(v, dec=2):`
        anchor = b"def _fmt(v, dec=2):"
        if anchor not in data:
            print("[H] ERROR: _fmt anchor not found")
            return 2
        if data.count(anchor) != 1:
            print(f"[H] ERROR: _fmt anchor matched {data.count(anchor)} times, expected 1")
            return 2
        data = data.replace(anchor, HELPER_BLOCK + anchor, 1)
        patched += 1
        print("[H] inserted _diagrams_markdown helper")

    # ── Patches 1-4: route wires ────────────────────────────────────────────
    for anchor, name in ROUTES:
        existing_marker = b"_diagrams_markdown(d, r) + md\r\n    " + anchor
        if existing_marker in data:
            print(f"[{name}] already patched")
            continue
        if anchor not in data:
            print(f"[{name}] ERROR: anchor not found: {anchor!r}")
            return 2
        if data.count(anchor) != 1:
            print(f"[{name}] ERROR: anchor matched {data.count(anchor)} times")
            return 2
        data = data.replace(anchor, PREPEND_LINE + anchor, 1)
        patched += 1
        print(f"[{name}] wired _diagrams_markdown prepend")

    if data == original:
        print("\nNo changes - all patches already applied.")
        return 0

    backup = WEBAPP.with_suffix(".py.bak_pdf_diagrams")
    if not backup.exists():
        backup.write_bytes(original)
        print(f"Backup written: {backup.name}")
    WEBAPP.write_bytes(data)
    print(f"\nApplied {patched} patch(es). web_app.py size: "
          f"{len(original):,} -> {len(data):,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
