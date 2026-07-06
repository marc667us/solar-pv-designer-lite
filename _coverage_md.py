

def _coverage_md(d):
    """Markdown 'Energy Coverage and Bill Comparison Analysis' section for the
    engineering/economic/proposal reports. Returns '' unless coverage is
    available. If coverage was not persisted (legacy project) but both a design
    and a saved bill_check exist, it is computed in-memory here — so reports are
    self-sufficient and NO state-mutating write is needed on any GET route.
    The bill-funded repayment capacity (coverage% of the customer's ACTUAL
    monthly bill) is surfaced as the suggested monthly installment amount."""
    d = d or {}
    cov = d.get("coverage")
    if (not cov or not cov.get("available")) and d.get("bill_check") and d.get("results"):
        try:
            _bc_refresh_coverage(d)          # in-memory only; not persisted
            cov = d.get("coverage")
        except Exception:
            cov = None
    if not cov or not cov.get("available"):
        return ""
    lines = [
        "## Energy Coverage and Bill Comparison Analysis",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Estimated full monthly consumption (from bill) | {cov['bill_monthly_kwh']:,.0f} kWh |",
        f"| Solar design monthly energy | {cov['designer_monthly_kwh']:,.0f} kWh |",
        f"| Energy coverage | {cov['coverage_pct']}% |",
        f"| Remaining grid energy | {cov['remaining_kwh']:,.0f} kWh |",
        f"| Coverage status | {cov['coverage_status']} |",
    ]
    if cov.get("bill_provided"):
        lines += [
            f"| Customer actual monthly bill (paid in full during design & install) | GHS {cov['actual_monthly_bill']:,.2f} |",
            f"| Expected bill reduction once commissioned & operating | GHS {cov['estimated_monthly_savings']:,.2f}/month |",
            f"| **Suggested monthly repayment capacity (post-commissioning, bill-funded)** | **GHS {cov['loan_repayment_capacity']:,.2f}** |",
        ]
    lines += [
        "",
        (f"_Coverage compares this design against the customer's estimated full monthly demand, "
         f"independently derived from their electricity bill using the live PURC "
         f"{cov.get('purc_quarter','')} tariff._"),
    ]
    if cov.get("bill_provided"):
        lines += [
            "",
            (f"_During the design and installation stage the customer continues to pay the full "
             f"grid bill. Only after the system is installed, commissioned and operating is the "
             f"monthly bill expected to reduce by approximately GHS "
             f"{cov['estimated_monthly_savings']:,.2f} (about {cov['coverage_pct']}% of the "
             f"current bill) — that reduction is what can be redirected toward the loan "
             f"repayment. Figures are indicative only; final approval rests with the financing "
             f"institution._"),
        ]
    lines.append("")
    return "\n".join(lines) + "\n"
