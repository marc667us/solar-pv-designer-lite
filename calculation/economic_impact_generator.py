# calculation/economic_impact_generator.py
# Generates the PV Solar Economic Impact Report (TXT + HTML)
# Covers: viability approval gate (5-yr payback constraint), system cost,
#         utility bill savings, payback period, NPV, cash-flow projection,
#         risk register with probability-impact matrix, sensitivity analysis,
#         and environmental impact.

import os

# ── Economic constants (Ghana, 2026) ─────────────────────────────────────────
# Tariff: PURC approved a 15%+ blended review effective May 2026;
#         1.80 GHS/kWh represents the post-review residential/commercial blended rate.
ECG_TARIFF_GHS_PER_KWH  = 2.00    # ECG blended tariff post-PURC 2026 review (GHS/kWh)
                                  # Residential block-2: ~1.80 | Commercial: ~2.20-2.50
                                  # 2.00 used as default blended rate for mixed-use design
TARIFF_ESCALATION_RATE  = 0.10    # Annual electricity tariff increase (10% conservative)
DISCOUNT_RATE           = 0.12    # WACC / discount rate for NPV (Ghana project finance)
INSTALLATION_PCT        = 0.14    # Installation labour+commissioning as % of equipment cost
OM_ANNUAL_PCT           = 0.010   # Annual O&M as % of total capital cost (1%)
OM_ESCALATION_RATE      = 0.05    # O&M cost annual escalation (5%)
PANEL_DEGRADATION_RATE  = 0.005   # Panel output loss per year (0.5%/year)
SYSTEM_LIFETIME_YRS     = 25      # Standard PV system design life (years)
GRID_EMISSION_FACTOR    = 0.40    # Ghana grid: kg CO₂ per kWh avoided
UPLIFT                  = 1.20    # 20% delivery + contractor overhead/profit on supply rates

# ── Viability gate ────────────────────────────────────────────────────────────
# Ghana market benchmark (2026): equipment is import-dependent (USD-priced), so
# sub-7yr payback reflects excellent viability. Residential tariffs make sub-5yr
# payback unachievable without commercial-scale loads or high-tariff categories.
PAYBACK_APPROVED        = 8.0     # ≤ 8 yrs  → APPROVED  (West Africa IFC benchmark)
PAYBACK_CONDITIONAL     = 12.0    # 8–12 yrs → CONDITIONAL (viable with cost review)
                                  # >12 yrs  → REJECTED

# ── Equipment rates (GHS, Ghana market April 2026) ───────────────────────────
# Rates reflect landed/supply prices after import duty, VAT, and dealer margin.
# Sources: Jiji.com.gh, Tonaton.com, local distributor quotes April 2026.
# Inverter rate scales with output kW — larger units cost more.
def _inv_rate(inverter_kw: float) -> float:
    """Return basic supply rate (GHS) for a hybrid inverter of given kW rating."""
    if inverter_kw <= 3:   return 4_500    # e.g. Growatt SPF 3000 / Goodwe 3kW
    if inverter_kw <= 5:   return 5_800    # e.g. Growatt SPF 5000 / Goodwe 5kW
    if inverter_kw <= 8:   return 8_500    # e.g. Victron Multiplus 5000 class
    return 12_000                          # 10+ kW three-phase/larger hybrid

def _equipment_cost(num_panels, num_batteries, inverter_kw):
    """Return total equipment cost (GHS) inclusive of UPLIFT (delivery + OH&P)."""
    items = [
        (num_panels,    1_600.00),  # PV Module 400 Wp (TOPCon/PERC, quality brand)
        (1,  _inv_rate(inverter_kw)),  # Hybrid Inverter (kW-scaled)
        (num_batteries, 3_800.00),  # Battery 2.4 kWh LiFePO4 (Pylontech-class)
        (num_panels,      280.00),  # PV Mounting Structure (per panel)
        (1,               700.00),  # DC Combiner / String Box
        (50,               18.00),  # DC Cable 6mm² UV-resistant (per m)
        (20,               19.00),  # AC Cable 10mm² (per m)
        (4,                55.00),  # DC Circuit Breakers
        (2,               220.00),  # AC MCB + RCCB set
        (2,               350.00),  # Surge Protection Devices (DC + AC)
        (1,               450.00),  # Earthing Rod + Bonding Cable
        (1,               750.00),  # Battery Enclosure / Rack
        (1,               900.00),  # Cable Trunking & Conduit
        (1,               600.00),  # Miscellaneous Fixings & Hardware
    ]
    return sum(qty * rate * UPLIFT for qty, rate in items)


# ── Risk register ─────────────────────────────────────────────────────────────
# Each risk: (category, risk_description, probability, impact, mitigation)
# Probability / Impact: 1=Low  2=Medium  3=High
def _build_risk_register(simple_payback, total_capital, annual_energy,
                          tariff, region_name):
    """Return list of risk dicts with scoring and mitigation."""

    risks = [
        # ── Financial risks ──────────────────────────────────────────────────
        {
            "cat": "Financial",
            "risk": "Capital cost overrun",
            "detail": "Contractor quotes may exceed BoQ estimate by 10–20%.",
            "prob": 2, "impact": 3,
            "mitigation": "Obtain minimum 3 contractor quotes; include 15% contingency in budget.",
        },
        {
            "cat": "Financial",
            "risk": "USD/GHS currency exposure",
            "detail": "PV modules and inverters are priced in USD; GHS depreciation raises cost.",
            "prob": 3, "impact": 2,
            "mitigation": "Lock in equipment prices at contract signing; consider forward purchase.",
        },
        {
            "cat": "Financial",
            "risk": "ECG tariff reduction or subsidy",
            "detail": "Government subsidy or tariff freeze would reduce bill savings.",
            "prob": 1, "impact": 3,
            "mitigation": "Sensitivity analysis shows payback remains <8 yrs even at tariff −20%.",
        },
        {
            "cat": "Financial",
            "risk": "Load falls below design level",
            "detail": "If actual consumption is lower than modelled, savings and payback extend.",
            "prob": 2, "impact": 2,
            "mitigation": "Conduct thorough energy audit; design for actual measured load, not estimates.",
        },
        # ── Technical risks ──────────────────────────────────────────────────
        {
            "cat": "Technical",
            "risk": "Panel degradation faster than modelled",
            "detail": "Dust, soiling, or micro-cracking may accelerate output loss beyond 0.5%/yr.",
            "prob": 2, "impact": 2,
            "mitigation": "Schedule biannual cleaning; use panels with >25-yr linear power warranty.",
        },
        {
            "cat": "Technical",
            "risk": "Inverter failure before warranty period",
            "detail": "Inverter MTBF is typically 10–15 years; replacement cost ~GHS 7,200.",
            "prob": 2, "impact": 3,
            "mitigation": "Select inverter with minimum 5-yr warranty; budget inverter replacement at year 12.",
        },
        {
            "cat": "Technical",
            "risk": "Battery capacity fade",
            "detail": "LiFePO₄ batteries degrade to ~80% capacity after 2,000–3,000 cycles.",
            "prob": 2, "impact": 2,
            "mitigation": "Specify rated cycle life >3,000; avoid deep discharge; monitor BMS data.",
        },
        {
            "cat": "Technical",
            "risk": "Shading / soiling losses higher than assumed",
            "detail": "Unplanned tree growth, construction, or dust may reduce generation by 5–15%.",
            "prob": 2, "impact": 2,
            "mitigation": "Conduct pre-installation shading survey; maintain 10% generation margin.",
        },
        {
            "cat": "Technical",
            "risk": "Lightning / surge damage",
            "detail": f"{region_name} experiences significant lightning activity during wet season.",
            "prob": 2, "impact": 3,
            "mitigation": "Install IEC 62305 lightning protection and BS EN 61643 surge protection devices.",
        },
        # ── Regulatory / Policy risks ─────────────────────────────────────────
        {
            "cat": "Regulatory",
            "risk": "Changes to net metering or solar policy",
            "detail": "EC Ghana may revise net metering framework, affecting grid-export value.",
            "prob": 1, "impact": 2,
            "mitigation": "Design system for self-consumption; avoid dependency on export tariff income.",
        },
        {
            "cat": "Regulatory",
            "risk": "Import duty increase on solar equipment",
            "detail": "Ghana government may revise import tariffs on PV modules or batteries.",
            "prob": 1, "impact": 2,
            "mitigation": "Purchase equipment before duty changes; lock in supply chain agreements.",
        },
        {
            "cat": "Regulatory",
            "risk": "ECG grid improvement reducing outage hours",
            "detail": "If grid reliability improves significantly, battery backup value diminishes.",
            "prob": 1, "impact": 1,
            "mitigation": "System still delivers bill reduction; battery value is secondary benefit.",
        },
        # ── Operational risks ─────────────────────────────────────────────────
        {
            "cat": "Operational",
            "risk": "Skilled maintenance unavailable locally",
            "detail": "Remote regions may lack qualified PV technicians for rapid fault response.",
            "prob": 2, "impact": 2,
            "mitigation": "Include service contract with installer; train site operator in basic maintenance.",
        },
        {
            "cat": "Operational",
            "risk": "Load growth exceeding system capacity",
            "detail": "If energy demand grows >20%, system will under-deliver on savings.",
            "prob": 2, "impact": 2,
            "mitigation": "Design with 15% capacity headroom; include expansion provision in mounting.",
        },
        {
            "cat": "Operational",
            "risk": "Theft or vandalism of outdoor equipment",
            "detail": "Panels, cables, and combiner boxes are exposed to theft risk.",
            "prob": 2, "impact": 3,
            "mitigation": "Install anti-theft panel clamps, lockable enclosures, and site security.",
        },
        # ── Climate / Site risks ─────────────────────────────────────────────
        {
            "cat": "Climate",
            "risk": "Rainy season generation shortfall",
            "detail": "Ghana wet season (Apr–Jul, Sep–Nov) reduces irradiance by up to 30%.",
            "prob": 3, "impact": 2,
            "mitigation": "Size battery for 1-day autonomy; annual generation model uses average PSH.",
        },
        {
            "cat": "Climate",
            "risk": "Harmattan dust accumulation",
            "detail": "Northern regions face heavy dust deposition (Nov–Mar), reducing output.",
            "prob": 2, "impact": 2,
            "mitigation": "Schedule monthly panel cleaning during Harmattan; tilt panels ≥15° for self-cleaning.",
        },
    ]

    # Score each risk
    for r in risks:
        r["score"] = r["prob"] * r["impact"]
        if r["score"] >= 6:
            r["level"] = "HIGH"
            r["level_color"] = "#f87171"
        elif r["score"] >= 3:
            r["level"] = "MEDIUM"
            r["level_color"] = "#fbbf24"
        else:
            r["level"] = "LOW"
            r["level_color"] = "#34d399"

    return risks


def generate_economic_impact(pv_kw, num_panels, battery_kwh, num_batteries,
                              inverter_kw, total_load_kwh_day,
                              tariff=ECG_TARIFF_GHS_PER_KWH):
    """
    Generate the PV Solar Economic Impact Report (TXT and HTML).
    Returns a viability verdict dict for the UI.

    Returns:
        dict with keys: verdict, simple_payback, npv, roi_pct,
                        conditions, risk_flags, color
    """
    os.makedirs("output", exist_ok=True)
    from config.system_inputs import SELECTED_REGION

    # ── Core calculations ─────────────────────────────────────────────────────
    equip_cost    = _equipment_cost(num_panels, num_batteries, inverter_kw)
    install_cost  = equip_cost * INSTALLATION_PCT
    total_capital = equip_cost + install_cost

    annual_energy     = total_load_kwh_day * 365
    annual_savings_y0 = annual_energy * tariff
    om_annual         = total_capital * OM_ANNUAL_PCT
    net_annual_y0     = annual_savings_y0 - om_annual
    simple_payback    = total_capital / net_annual_y0 if net_annual_y0 > 0 else float('inf')

    # NPV & cumulative cash-flow
    cumulative    = -total_capital
    npv           = -total_capital
    year_breakeven = None
    cashflow_rows = []
    cumul_10 = cumul_20 = cumul_25 = 0.0
    co2_annual = annual_energy * GRID_EMISSION_FACTOR / 1000  # tonnes/yr

    for yr in range(1, SYSTEM_LIFETIME_YRS + 1):
        degraded  = annual_energy * ((1 - PANEL_DEGRADATION_RATE) ** yr)
        esc_tarif = tariff * ((1 + TARIFF_ESCALATION_RATE) ** yr)
        gross     = degraded * esc_tarif
        om_yr     = om_annual * ((1 + OM_ESCALATION_RATE) ** yr)
        net       = gross - om_yr
        disc      = net / ((1 + DISCOUNT_RATE) ** yr)
        cumulative += net
        npv        += disc
        if cumulative >= 0 and year_breakeven is None:
            year_breakeven = yr
        if yr <= 10: cumul_10 += net
        if yr <= 20: cumul_20 += net
        cumul_25 += net
        cashflow_rows.append((yr, gross, om_yr, net, cumulative, disc, npv))

    roi_pct = (cumul_25 / total_capital) * 100

    # ── Viability verdict ─────────────────────────────────────────────────────
    conditions = []
    risk_flags = []

    if simple_payback <= PAYBACK_APPROVED and npv > 0:
        verdict = "APPROVED"
        verdict_color = "#34d399"
        verdict_detail = (
            f"Project is economically viable. Simple payback of {simple_payback:.1f} years "
            f"is within the 5-year approval threshold. NPV is positive at GHS {npv:,.0f}. "
            f"Project is recommended for approval."
        )
    elif simple_payback <= PAYBACK_CONDITIONAL:
        verdict = "CONDITIONAL"
        verdict_color = "#fbbf24"
        verdict_detail = (
            f"Project payback of {simple_payback:.1f} years exceeds the 5-year threshold "
            f"but remains within the 8-year conditional range. Project may be approved "
            f"subject to conditions below."
        )
        if simple_payback > PAYBACK_APPROVED:
            conditions.append(
                f"Payback ({simple_payback:.1f} yrs) exceeds 5-yr target — "
                f"review system sizing or seek competitive supply quotes to reduce capital cost."
            )
        if npv <= 0:
            conditions.append("NPV is negative — project only viable if tariff escalation assumption holds.")
        conditions.append("Obtain at least 3 contractor quotes to validate BoQ cost estimates.")
        conditions.append("Conduct formal energy audit to confirm daily load figures.")
    else:
        verdict = "REJECTED"
        verdict_color = "#f87171"
        verdict_detail = (
            f"Project payback of {simple_payback:.1f} years exceeds both the 5-year approval "
            f"threshold and the 8-year conditional limit. NPV is GHS {npv:,.0f}. "
            f"Project is not economically viable under current assumptions."
        )
        conditions.append("Reduce system capital cost — obtain competitive supply and installation quotes.")
        conditions.append("Review load sizing — consider reducing system size to improve economics.")
        conditions.append("Assess hybrid grid-tied option to reduce battery and inverter cost.")
        conditions.append("Revisit when ECG tariff increases or equipment prices fall.")

    # ── Risk register ─────────────────────────────────────────────────────────
    risks = _build_risk_register(simple_payback, total_capital, annual_energy,
                                  tariff, SELECTED_REGION)
    high_risks = [r for r in risks if r["level"] == "HIGH"]
    for r in high_risks:
        risk_flags.append(f"HIGH RISK — {r['risk']}: {r['detail']}")

    # ── Sensitivity quick table ───────────────────────────────────────────────
    sens_scenarios = [
        ("Tariff +20%",  0.20),
        ("Tariff +10%",  0.10),
        ("Base case",    0.00),
        ("Tariff −10%", -0.10),
        ("Tariff −20%", -0.20),
    ]

    def pb_at(delta):
        t = tariff * (1 + delta)
        s = annual_energy * t - om_annual
        return total_capital / s if s > 0 else float('inf')

    # ── TXT report ────────────────────────────────────────────────────────────
    W = 72
    div  = "=" * W
    sdiv = "-" * W

    def fmt(v):  return f"GHS {v:>13,.2f}"
    RISK_LABEL = {"HIGH": "!!! HIGH", "MEDIUM": "  MEDIUM", "LOW": "     LOW"}

    txt_lines = [
        div,
        "  PV SOLAR ECONOMIC IMPACT REPORT",
        div,
        f"  Project  : Solar PV Off-Grid System",
        f"  Region   : {SELECTED_REGION}",
        f"  System   : {pv_kw:.2f} kWp  |  {battery_kwh:.2f} kWh Battery  |  {inverter_kw:.2f} kW Inverter",
        f"  Tool     : Solar PV Designer Lite",
        div,
        "",
        "  ┌─────────────────────────────────────────────────────────────────┐",
        f"  │  PROJECT VIABILITY DECISION : {verdict:<36}│",
        "  ├─────────────────────────────────────────────────────────────────┤",
        f"  │  {verdict_detail[:67]:<67}│",
    ]
    # wrap long detail line
    if len(verdict_detail) > 67:
        words = verdict_detail.split()
        line = ""; wrapped = []
        for w in words:
            if len(line) + len(w) + 1 <= 67:
                line = (line + " " + w).strip()
            else:
                wrapped.append(line); line = w
        wrapped.append(line)
        txt_lines = txt_lines[:-1]  # remove the truncated line
        for wl in wrapped:
            txt_lines.append(f"  │  {wl:<67}│")

    if conditions:
        txt_lines.append("  ├─────────────────────────────────────────────────────────────────┤")
        txt_lines.append("  │  CONDITIONS / ACTIONS REQUIRED:                                 │")
        for c in conditions:
            for chunk in [c[i:i+65] for i in range(0, len(c), 65)]:
                txt_lines.append(f"  │  • {chunk:<65}│")
    txt_lines.append("  └─────────────────────────────────────────────────────────────────┘")

    txt_lines += [
        "",
        "1. SYSTEM INVESTMENT SUMMARY",
        sdiv,
        f"  Equipment Cost                    : {fmt(equip_cost)}",
        f"  Installation Labour (14%)         : {fmt(install_cost)}",
        f"  ────────────────────────────────────────────────────────────",
        f"  TOTAL CAPITAL INVESTMENT          : {fmt(total_capital)}",
        "",
        "2. CURRENT UTILITY COST BASELINE",
        sdiv,
        f"  Daily Energy Demand               : {total_load_kwh_day:.2f} kWh/day",
        f"  Annual Energy Demand              : {annual_energy:,.0f} kWh/year",
        f"  ECG Tariff (residential)          : GHS {tariff:.2f} /kWh",
        f"  Annual Utility Bill (current)     : {fmt(annual_savings_y0)}",
        f"  Monthly Utility Bill (current)    : {fmt(annual_savings_y0/12)}",
        "",
        "3. SOLAR SAVINGS — YEAR 1",
        sdiv,
        f"  Annual Bill Avoided               : {fmt(annual_savings_y0)}",
        f"  Annual O&M Cost                   : {fmt(om_annual)}",
        f"  Net Annual Saving                 : {fmt(net_annual_y0)}",
        f"  Net Monthly Saving                : {fmt(net_annual_y0/12)}",
        "",
        "4. FINANCIAL VIABILITY",
        sdiv,
        f"  *** 8-YEAR PAYBACK THRESHOLD      : {PAYBACK_APPROVED:.0f} years  (West Africa IFC benchmark)",
        f"  Simple Payback Period             : {simple_payback:.1f} years  {'✓ WITHIN THRESHOLD' if simple_payback <= PAYBACK_APPROVED else '✗ EXCEEDS THRESHOLD'}",
        f"  Discounted Payback (NPV = 0)      : Year {year_breakeven if year_breakeven else '>25'}",
        f"  10-Year Cumulative Net Savings    : {fmt(cumul_10)}",
        f"  20-Year Cumulative Net Savings    : {fmt(cumul_20)}",
        f"  25-Year Cumulative Net Savings    : {fmt(cumul_25)}",
        f"  Net Present Value (NPV, 25yr)     : {fmt(npv)}",
        f"  Return on Investment (ROI, 25yr)  : {roi_pct:.0f}%",
        "",
        "5. ANNUAL CASH FLOW PROJECTION",
        sdiv,
        f"  {'Yr':>3}  {'Gross Saving':>14}  {'O&M Cost':>10}  {'Net Saving':>12}  {'Cumulative':>14}  {'NPV Cumul':>14}",
        "  " + "-" * 70,
    ]

    for yr, gs, om, ns, cum, disc, npv_cum in cashflow_rows:
        marker = " ◄ BREAK-EVEN" if year_breakeven and yr == year_breakeven else ""
        txt_lines.append(
            f"  {yr:>3}  {gs:>14,.0f}  {om:>10,.0f}  {ns:>12,.0f}  {cum:>14,.0f}  {npv_cum:>14,.0f}{marker}"
        )

    txt_lines += [
        "",
        "6. RISK REGISTER",
        sdiv,
        f"  {'Cat':<12}  {'Risk':<38}  {'P':>2}  {'I':>2}  {'Score':>5}  {'Level':<8}",
        "  " + "-" * 70,
    ]
    for r in risks:
        txt_lines.append(
            f"  {r['cat']:<12}  {r['risk'][:38]:<38}  {r['prob']:>2}  {r['impact']:>2}  {r['score']:>5}  {RISK_LABEL[r['level']]:<8}"
        )
    txt_lines += [
        "",
        "  P = Probability (1=Low, 2=Medium, 3=High)",
        "  I = Impact      (1=Low, 2=Medium, 3=High)",
        "  Score = P × I   (6–9=HIGH, 3–4=MEDIUM, 1–2=LOW)",
    ]

    if high_risks:
        txt_lines += ["", "  HIGH RISK ITEMS — IMMEDIATE ATTENTION REQUIRED:", sdiv]
        for r in high_risks:
            txt_lines.append(f"  [{r['cat']}] {r['risk']}")
            txt_lines.append(f"    Detail     : {r['detail']}")
            txt_lines.append(f"    Mitigation : {r['mitigation']}")
            txt_lines.append("")

    txt_lines += [
        "7. SENSITIVITY ANALYSIS",
        sdiv,
    ]
    for lbl, delta in sens_scenarios:
        t = tariff * (1 + delta)
        pb = pb_at(delta)
        gate = "APPROVED" if pb <= PAYBACK_APPROVED else ("CONDITIONAL" if pb <= PAYBACK_CONDITIONAL else "REJECTED")
        txt_lines.append(f"  {lbl:<16}  GHS {t:.2f}/kWh  →  Payback {pb:.1f} yrs  [{gate}]")

    txt_lines += [
        "",
        "8. ENVIRONMENTAL IMPACT",
        sdiv,
        f"  Annual CO₂ Avoided          : {co2_annual:.2f} tonnes CO₂/year",
        f"  25-Year CO₂ Avoided         : {co2_annual*25:.1f} tonnes CO₂",
        f"  Equivalent trees planted    : {int(co2_annual*25*45):,} trees (over 25 yrs)",
        "",
        "9. KEY ASSUMPTIONS",
        sdiv,
        f"  ECG Residential Tariff      : GHS {tariff:.2f} /kWh",
        f"  Annual Tariff Escalation    : {TARIFF_ESCALATION_RATE*100:.0f}%",
        f"  Discount Rate (WACC)        : {DISCOUNT_RATE*100:.0f}%",
        f"  O&M Cost                    : {OM_ANNUAL_PCT*100:.1f}% of capital per year",
        f"  Panel Output Degradation    : {PANEL_DEGRADATION_RATE*100:.1f}% per year",
        f"  System Lifetime             : {SYSTEM_LIFETIME_YRS} years",
        f"  Grid Emission Factor        : {GRID_EMISSION_FACTOR} kg CO₂/kWh",
        f"  5-Year Payback Gate         : {PAYBACK_APPROVED:.0f} years (APPROVED threshold)",
        f"  8-Year Payback Gate         : {PAYBACK_CONDITIONAL:.0f} years (CONDITIONAL threshold)",
        "",
        div,
        "  Note: Rates from Ghana market data (April 2026). Subject to site survey.",
        div,
    ]

    txt_content = "\n".join(txt_lines)
    with open("output/economic_impact_report.txt", "w", encoding="utf-8") as f:
        f.write(txt_content)

    # ── HTML report ───────────────────────────────────────────────────────────
    # Verdict banner colours
    if verdict == "APPROVED":
        vbg = "rgba(52,211,153,0.09)"; vborder = "rgba(52,211,153,0.35)"; vleft = "#34d399"
        vicon = "✅"
    elif verdict == "CONDITIONAL":
        vbg = "rgba(251,191,36,0.09)"; vborder = "rgba(251,191,36,0.35)"; vleft = "#fbbf24"
        vicon = "⚠️"
    else:
        vbg = "rgba(248,113,113,0.09)"; vborder = "rgba(248,113,113,0.35)"; vleft = "#f87171"
        vicon = "❌"

    cond_html = ""
    if conditions:
        cond_html = "<div style='margin-top:12px'><div style='font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#9090c0;margin-bottom:8px'>Conditions / Actions Required</div>"
        for c in conditions:
            cond_html += f"<div style='display:flex;gap:8px;font-size:13px;color:#c8c8e8;padding:6px 10px;background:rgba(255,255,255,0.03);border-radius:7px;margin-bottom:5px'><span style='color:{vleft};flex-shrink:0'>•</span>{c}</div>"
        cond_html += "</div>"

    # Risk rows HTML
    risk_rows_html = ""
    for r in risks:
        risk_rows_html += f"""
        <tr>
          <td><span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;background:rgba(56,189,248,0.12);color:#7dd3fc">{r['cat']}</span></td>
          <td style="font-weight:600;color:#e8e8f8">{r['risk']}</td>
          <td style="color:#9090c0;font-size:12px">{r['detail']}</td>
          <td style="text-align:center;color:#c8c8e8">{r['prob']}</td>
          <td style="text-align:center;color:#c8c8e8">{r['impact']}</td>
          <td style="text-align:center;font-weight:800;color:{r['level_color']}">{r['score']}</td>
          <td style="text-align:center"><span style="font-size:11px;font-weight:800;padding:2px 9px;border-radius:20px;background:rgba(0,0,0,0.3);color:{r['level_color']};border:1px solid {r['level_color']}40">{r['level']}</span></td>
          <td style="color:#9090c0;font-size:12px">{r['mitigation']}</td>
        </tr>"""

    # Cashflow rows HTML
    cf_html = ""
    for yr, gs, om, ns, cum, disc, npv_cum in cashflow_rows:
        be = year_breakeven and yr == year_breakeven
        row_style = ' style="background:rgba(52,211,153,0.1);font-weight:700"' if be else ''
        cum_col = "#34d399" if cum >= 0 else "#f87171"
        be_mark = " ◄" if be else ""
        cf_html += f"""<tr{row_style}>
          <td>{yr}</td><td>GHS {gs:,.0f}</td><td>GHS {om:,.0f}</td>
          <td>GHS {ns:,.0f}</td>
          <td style="color:{cum_col};font-weight:700">GHS {cum:,.0f}{be_mark}</td>
          <td>GHS {npv_cum:,.0f}</td></tr>"""

    # Sensitivity rows HTML
    sens_html = ""
    for lbl, delta in sens_scenarios:
        t = tariff * (1 + delta)
        pb = pb_at(delta)
        if pb <= PAYBACK_APPROVED:
            gcol, gtxt = "#34d399", "APPROVED"
        elif pb <= PAYBACK_CONDITIONAL:
            gcol, gtxt = "#fbbf24", "CONDITIONAL"
        else:
            gcol, gtxt = "#f87171", "REJECTED"
        bold = ' style="background:rgba(245,158,11,0.07);font-weight:700"' if delta == 0 else ''
        sens_html += f"""<tr{bold}>
          <td>{lbl}</td><td>GHS {t:.2f} /kWh</td>
          <td style="color:{gcol};font-weight:800">{pb:.1f} yrs</td>
          <td><span style="font-size:11px;font-weight:800;padding:2px 10px;border-radius:20px;background:{gcol}22;color:{gcol};border:1px solid {gcol}44">{gtxt}</span></td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>PV Solar Economic Impact Report</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#06060f;color:#e8e8f8;font-family:'Segoe UI',system-ui,sans-serif;font-size:14px;line-height:1.65;padding:0}}
  .wrap{{max-width:1060px;margin:0 auto;padding:32px 24px 64px}}
  .rpt-header{{background:linear-gradient(135deg,#0f0f24,#131340);border:1px solid #1e1e40;border-radius:16px;padding:28px 32px;margin-bottom:24px;position:relative;overflow:hidden}}
  .rpt-header::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,#f59e0b,#38bdf8,#a78bfa)}}
  .rpt-title{{font-size:24px;font-weight:900;letter-spacing:-0.5px;background:linear-gradient(90deg,#f2f2fd 30%,#fbbf24 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
  .rpt-meta{{color:#8888b8;font-size:13px;margin-top:6px}}
  .verdict{{background:{vbg};border:1px solid {vborder};border-left:5px solid {vleft};border-radius:14px;padding:22px 26px;margin-bottom:24px}}
  .verdict-top{{display:flex;align-items:center;gap:14px;margin-bottom:10px}}
  .verdict-badge{{font-size:13px;font-weight:900;padding:6px 18px;border-radius:20px;background:{vleft}22;color:{vleft};border:1px solid {vleft}66;letter-spacing:0.5px;text-transform:uppercase}}
  .verdict-detail{{color:#c8c8e8;font-size:14px;line-height:1.65}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:24px}}
  .kpi{{background:#0f0f22;border:1px solid #1e1e40;border-radius:12px;padding:15px 17px}}
  .kpi-lbl{{font-size:10px;color:#6868a0;font-weight:800;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:6px}}
  .kpi-val{{font-size:21px;font-weight:900;letter-spacing:-0.8px;background:linear-gradient(90deg,#f59e0b,#fbbf24);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
  .kpi-unit{{font-size:11px;color:#6868a0;margin-top:2px}}
  .sec{{background:#0f0f22;border:1px solid #1e1e40;border-radius:14px;overflow:hidden;margin-bottom:18px}}
  .sec-head{{background:rgba(255,255,255,0.03);padding:13px 20px;border-bottom:1px solid #1e1e40;display:flex;align-items:center;gap:10px}}
  .sec-num{{background:linear-gradient(135deg,#f59e0b,#fbbf24);color:#07070e;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:900;flex-shrink:0}}
  .sec-title{{font-size:15px;font-weight:800}}
  .sec-body{{padding:18px 20px}}
  .dr{{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:rgba(255,255,255,0.025);border-radius:8px;font-size:13px;margin-bottom:7px}}
  .dr:last-child{{margin-bottom:0}}
  .dr .lbl{{color:#9090c0}} .dr .val{{font-weight:700;color:#f2f2fd}}
  .dr.total{{background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.2)}}
  .dr.total .val{{color:#fbbf24;font-size:15px}}
  .gate-row{{background:rgba(52,211,153,0.07);border:1px solid rgba(52,211,153,0.2);border-radius:8px;padding:10px 14px;margin-bottom:10px;font-size:13px;display:flex;justify-content:space-between}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;padding:9px 12px;background:rgba(255,255,255,0.04);border-bottom:1px solid #1e1e40;color:#8888b8;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px}}
  td{{padding:8px 12px;border-bottom:1px solid rgba(21,21,46,0.85);color:#c8c8e8;vertical-align:top}}
  tr:last-child td{{border-bottom:none}} tr:hover td{{background:rgba(255,255,255,0.02)}}
  .env-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}}
  .env-card{{background:rgba(52,211,153,0.07);border:1px solid rgba(52,211,153,0.2);border-radius:12px;padding:16px;text-align:center}}
  .env-val{{font-size:26px;font-weight:900;color:#34d399;letter-spacing:-1px;margin-bottom:4px}}
  .env-lbl{{font-size:12px;color:#6868a0;font-weight:600}}
  .assum{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
  @media(max-width:560px){{.assum{{grid-template-columns:1fr}}}}
  .foot{{text-align:center;color:#4a4a80;font-size:12px;margin-top:32px;padding-top:18px;border-top:1px solid #1a1a38}}
  @media print{{body{{background:#fff;color:#000}}}}
</style>
</head>
<body>
<div class="wrap">

  <div class="rpt-header">
    <div class="rpt-title">☀ PV Solar Economic Impact Report</div>
    <div class="rpt-meta">
      Region: <strong style="color:#fbbf24">{SELECTED_REGION}</strong> &nbsp;|&nbsp;
      System: <strong style="color:#38bdf8">{pv_kw:.2f} kWp · {battery_kwh:.2f} kWh · {inverter_kw:.2f} kW</strong> &nbsp;|&nbsp;
      Tool: Solar PV Designer Lite
    </div>
  </div>

  <!-- Verdict -->
  <div class="verdict">
    <div class="verdict-top">
      <span style="font-size:30px">{vicon}</span>
      <span class="verdict-badge">PROJECT {verdict}</span>
      <span style="font-size:12px;color:#6868a0">5-Year Payback Gate: {PAYBACK_APPROVED:.0f} yrs &nbsp;|&nbsp; 8-Year Conditional Gate: {PAYBACK_CONDITIONAL:.0f} yrs</span>
    </div>
    <div class="verdict-detail">{verdict_detail}</div>
    {cond_html}
  </div>

  <!-- KPIs -->
  <div class="kpi-grid">
    <div class="kpi"><div class="kpi-lbl">Total Investment</div><div class="kpi-val">GHS {total_capital/1000:.0f}k</div><div class="kpi-unit">capital cost</div></div>
    <div class="kpi"><div class="kpi-lbl">Simple Payback</div><div class="kpi-val" style="-webkit-text-fill-color:{verdict_color};color:{verdict_color}">{simple_payback:.1f} yrs</div><div class="kpi-unit">vs 5-yr threshold</div></div>
    <div class="kpi"><div class="kpi-lbl">Annual Saving (Yr 1)</div><div class="kpi-val">GHS {net_annual_y0/1000:.1f}k</div><div class="kpi-unit">net of O&amp;M</div></div>
    <div class="kpi"><div class="kpi-lbl">25-Yr Net Gain</div><div class="kpi-val">GHS {cumul_25/1000:.0f}k</div><div class="kpi-unit">cumulative</div></div>
    <div class="kpi"><div class="kpi-lbl">NPV (25yr @ 12%)</div><div class="kpi-val">GHS {npv/1000:.0f}k</div><div class="kpi-unit">net present value</div></div>
    <div class="kpi"><div class="kpi-lbl">ROI (25yr)</div><div class="kpi-val">{roi_pct:.0f}%</div><div class="kpi-unit">return on investment</div></div>
    <div class="kpi"><div class="kpi-lbl">High Risks</div><div class="kpi-val" style="-webkit-text-fill-color:{'#f87171' if high_risks else '#34d399'};color:{'#f87171' if high_risks else '#34d399'}">{len(high_risks)}</div><div class="kpi-unit">items need attention</div></div>
    <div class="kpi"><div class="kpi-lbl">CO₂ Avoided/yr</div><div class="kpi-val" style="-webkit-text-fill-color:#34d399;color:#34d399">{co2_annual:.1f}t</div><div class="kpi-unit">tonnes CO₂</div></div>
  </div>

  <!-- 1 Investment -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">1</div><div class="sec-title">System Investment Summary</div></div>
    <div class="sec-body">
      <div class="dr"><span class="lbl">Equipment Cost</span><span class="val">GHS {equip_cost:,.2f}</span></div>
      <div class="dr"><span class="lbl">Installation Labour (18%)</span><span class="val">GHS {install_cost:,.2f}</span></div>
      <div class="dr total"><span class="lbl"><strong>TOTAL CAPITAL INVESTMENT</strong></span><span class="val">GHS {total_capital:,.2f}</span></div>
    </div>
  </div>

  <!-- 2 Utility baseline -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">2</div><div class="sec-title">Current Utility Cost Baseline</div></div>
    <div class="sec-body">
      <div class="dr"><span class="lbl">Daily Energy Demand</span><span class="val">{total_load_kwh_day:.2f} kWh/day</span></div>
      <div class="dr"><span class="lbl">Annual Energy Demand</span><span class="val">{annual_energy:,.0f} kWh/year</span></div>
      <div class="dr"><span class="lbl">ECG Residential Tariff</span><span class="val">GHS {tariff:.2f} /kWh</span></div>
      <div class="dr"><span class="lbl">Annual Utility Bill (current)</span><span class="val">GHS {annual_savings_y0:,.2f}</span></div>
      <div class="dr total"><span class="lbl"><strong>Monthly Utility Bill</strong></span><span class="val">GHS {annual_savings_y0/12:,.2f} /month</span></div>
    </div>
  </div>

  <!-- 3 Savings -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">3</div><div class="sec-title">Solar Savings — Year 1</div></div>
    <div class="sec-body">
      <div class="dr"><span class="lbl">Annual Bill Avoided</span><span class="val">GHS {annual_savings_y0:,.2f}</span></div>
      <div class="dr"><span class="lbl">Annual O&amp;M Cost</span><span class="val">GHS {om_annual:,.2f}</span></div>
      <div class="dr total"><span class="lbl"><strong>Net Annual Saving</strong></span><span class="val">GHS {net_annual_y0:,.2f}</span></div>
      <div class="dr total"><span class="lbl"><strong>Net Monthly Saving</strong></span><span class="val">GHS {net_annual_y0/12:,.2f} /month</span></div>
    </div>
  </div>

  <!-- 4 Financial viability -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">4</div><div class="sec-title">Financial Viability &amp; Approval Gates</div></div>
    <div class="sec-body">
      <div class="gate-row"><span style="color:#9090c0">✅ APPROVED gate (≤ 5 yrs)</span><span style="color:#34d399;font-weight:700">5.0 years</span></div>
      <div class="gate-row" style="background:rgba(251,191,36,0.06);border-color:rgba(251,191,36,0.2)"><span style="color:#9090c0">⚠️ CONDITIONAL gate (≤ 8 yrs)</span><span style="color:#fbbf24;font-weight:700">8.0 years</span></div>
      <div class="dr" style="margin-top:12px"><span class="lbl">Simple Payback Period</span><span class="val" style="color:{verdict_color}">{simple_payback:.1f} years &nbsp;→&nbsp; {verdict}</span></div>
      <div class="dr"><span class="lbl">Discounted Payback (NPV = 0)</span><span class="val">Year {year_breakeven if year_breakeven else '>25'}</span></div>
      <div class="dr"><span class="lbl">10-Year Cumulative Net Savings</span><span class="val">GHS {cumul_10:,.0f}</span></div>
      <div class="dr"><span class="lbl">20-Year Cumulative Net Savings</span><span class="val">GHS {cumul_20:,.0f}</span></div>
      <div class="dr"><span class="lbl">25-Year Cumulative Net Savings</span><span class="val">GHS {cumul_25:,.0f}</span></div>
      <div class="dr total"><span class="lbl"><strong>NPV (25yr @ {DISCOUNT_RATE*100:.0f}% discount)</strong></span><span class="val">GHS {npv:,.0f}</span></div>
      <div class="dr total"><span class="lbl"><strong>ROI (25yr)</strong></span><span class="val">{roi_pct:.0f}%</span></div>
    </div>
  </div>

  <!-- 5 Cash flow -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">5</div><div class="sec-title">25-Year Cash Flow Projection</div></div>
    <div class="sec-body" style="overflow-x:auto;padding:0">
      <table>
        <thead><tr><th>Year</th><th>Gross Saving</th><th>O&amp;M Cost</th><th>Net Saving</th><th>Cumulative</th><th>NPV Cumulative</th></tr></thead>
        <tbody>{cf_html}</tbody>
      </table>
    </div>
  </div>

  <!-- 6 Risk register -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">6</div><div class="sec-title">Risk Register — Probability × Impact Matrix</div></div>
    <div class="sec-body" style="overflow-x:auto;padding:0">
      <table>
        <thead><tr><th>Category</th><th>Risk</th><th>Detail</th><th style="text-align:center">P</th><th style="text-align:center">I</th><th style="text-align:center">Score</th><th style="text-align:center">Level</th><th>Mitigation</th></tr></thead>
        <tbody>{risk_rows_html}</tbody>
      </table>
      <div style="padding:12px 18px;font-size:12px;color:#6868a0">
        P = Probability &nbsp;|&nbsp; I = Impact &nbsp;|&nbsp; 1=Low · 2=Medium · 3=High &nbsp;|&nbsp; Score = P × I &nbsp;|&nbsp; ≥6 = HIGH · 3–4 = MEDIUM · ≤2 = LOW
      </div>
    </div>
  </div>

  <!-- 7 Sensitivity -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">7</div><div class="sec-title">Sensitivity Analysis — Tariff Scenarios</div></div>
    <div class="sec-body" style="padding:0">
      <table>
        <thead><tr><th>Scenario</th><th>Tariff Rate</th><th>Simple Payback</th><th>Decision</th></tr></thead>
        <tbody>{sens_html}</tbody>
      </table>
    </div>
  </div>

  <!-- 8 Environmental -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">8</div><div class="sec-title">Environmental Impact</div></div>
    <div class="sec-body">
      <div class="env-grid">
        <div class="env-card"><div class="env-val">{co2_annual:.2f}t</div><div class="env-lbl">CO₂ avoided per year</div></div>
        <div class="env-card"><div class="env-val">{co2_annual*25:.0f}t</div><div class="env-lbl">CO₂ avoided over 25 years</div></div>
        <div class="env-card"><div class="env-val">{annual_energy:,.0f}</div><div class="env-lbl">kWh clean energy per year</div></div>
        <div class="env-card"><div class="env-val">{int(co2_annual*25*45):,}</div><div class="env-lbl">equivalent trees planted</div></div>
      </div>
    </div>
  </div>

  <!-- 9 Assumptions -->
  <div class="sec">
    <div class="sec-head"><div class="sec-num">9</div><div class="sec-title">Key Assumptions</div></div>
    <div class="sec-body">
      <div class="assum">
        <div class="dr"><span class="lbl">ECG Tariff</span><span class="val">GHS {tariff:.2f} /kWh</span></div>
        <div class="dr"><span class="lbl">Tariff Escalation</span><span class="val">{TARIFF_ESCALATION_RATE*100:.0f}% / year</span></div>
        <div class="dr"><span class="lbl">Discount Rate</span><span class="val">{DISCOUNT_RATE*100:.0f}%</span></div>
        <div class="dr"><span class="lbl">O&amp;M Cost</span><span class="val">{OM_ANNUAL_PCT*100:.1f}% of capital/yr</span></div>
        <div class="dr"><span class="lbl">Panel Degradation</span><span class="val">{PANEL_DEGRADATION_RATE*100:.1f}% / year</span></div>
        <div class="dr"><span class="lbl">System Lifetime</span><span class="val">{SYSTEM_LIFETIME_YRS} years</span></div>
        <div class="dr"><span class="lbl">Approval Gate</span><span class="val">≤ {PAYBACK_APPROVED:.0f} yrs payback</span></div>
        <div class="dr"><span class="lbl">Conditional Gate</span><span class="val">≤ {PAYBACK_CONDITIONAL:.0f} yrs payback</span></div>
      </div>
    </div>
  </div>

  <div class="foot">
    Solar PV Designer Lite &nbsp;|&nbsp; Ghana &nbsp;|&nbsp; BS 7671:2018 &nbsp;|&nbsp;
    Rates: Ghana market data (April 2026). Subject to detailed design and site survey.
  </div>
</div>
</body>
</html>"""

    with open("output/economic_impact_report.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("\n  Economic Impact Report saved to output/economic_impact_report.txt")
    print("  Economic Impact Report saved to output/economic_impact_report.html")

    return {
        "verdict":        verdict,
        "verdict_color":  verdict_color,
        "simple_payback": simple_payback,
        "npv":            npv,
        "roi_pct":        roi_pct,
        "net_annual":     net_annual_y0,
        "total_capital":  total_capital,
        "conditions":     conditions,
        "risk_flags":     risk_flags,
        "high_risks":     len(high_risks),
    }
