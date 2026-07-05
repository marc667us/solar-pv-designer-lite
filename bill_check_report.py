"""
Shared "Check My Bill" report helpers (owner 2026-07-05).

The saved bill-check snapshot lives at projects.data_json['bill_check'] (written
by /project/<pid>/bill-check/save). This module renders it as a Markdown block so
the emailed / downloaded Economic and Energy Impact PDF reports carry the verified
bill the bank reviews. Kept in a clean standalone module (web_app.py has mixed
CRLF/Windows-1252 bytes that make embedded newline literals fragile). Reusable /
importable per the reusability rule.
"""
from __future__ import annotations

__all__ = ["bill_check_md"]


def bill_check_md(d) -> str:
    """Return a Markdown block for the saved Check My Bill snapshot in project
    data `d` (dict), or '' if no check has been saved. `d['symbol']` supplies the
    currency prefix (defaults to 'GHS ')."""
    bc = (d or {}).get("bill_check") if isinstance(d, dict) else None
    if not bc:
        return ""
    sym = (d.get("symbol") or "GHS ") if isinstance(d, dict) else "GHS "
    exp = bc.get("expected") or {}
    en = bc.get("energy") or {}
    tm = bc.get("tariff_meta") or {}
    actual = bc.get("actual_bill") or 0
    rows = [
        ("Customer category", str(exp.get("category_applied") or "-")),
        ("Estimated monthly consumption",
         "{:,.0f} kWh".format(en.get("monthly_kwh") or 0)),
        ("Expected PURC bill", "{}{:,.2f}".format(sym, exp.get("total") or 0)),
    ]
    # Only report an actual bill when the customer entered one. Running Check My
    # Bill from the load schedule alone leaves actual_bill = 0; printing "GHS 0.00"
    # reads as a broken/zero bill in a lender-facing report (owner 2026-07-05).
    if actual > 0:
        rows.append(("Actual bill", "{}{:,.2f}".format(sym, actual)))
    else:
        rows.append(("Actual bill",
                     "Not provided - expected PURC bill used as the baseline"))
    if bc.get("difference") is not None:
        dp = bc.get("difference_pct")
        extra = " ({:+.1f}%)".format(dp) if dp is not None else ""
        rows.append(("Difference (actual - expected)",
                     "{}{:,.2f}{}".format(sym, bc.get("difference") or 0, extra)))
    if bc.get("effective_tariff") is not None:
        rows.append(("Effective tariff",
                     "{}{:.4f}/kWh".format(sym, bc.get("effective_tariff"))))
    if bc.get("confidence"):
        rows.append(("Estimate confidence", str(bc.get("confidence")).title()))
    if bc.get("saved_at"):
        rows.append(("Checked on", str(bc.get("saved_at"))))

    lines = ["", "## Bill Verification - Check My Bill", ""]
    if tm.get("effective_from"):
        lines.append(
            "*Audited against the PURC tariff effective %s.*"
            % tm.get("effective_from"))
        lines.append("")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    for label, val in rows:
        lines.append("| %s | %s |" % (label, val))
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
