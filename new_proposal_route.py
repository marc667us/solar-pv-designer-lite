def export_pdf_proposal(pid):
    """PDF export — Full Technical & Financial Proposal (superset of all reports)."""
    gate = _paid_only(pid)
    if gate: return gate
    project = get_project(pid)
    if not project or "results" not in project["data"]:
        return redirect(url_for("project_results", pid=pid))
    d   = project["data"]
    r   = project["data"]["results"]
    eco = r.get("economics", {})
    sym = d.get("symbol", "$")
    phase   = d.get("phase", "single")
    v_ac    = 415 if phase == "three" else 230
    chem    = r.get("chemistry", "LiFePO4")
    voltage = d.get("voltage", 48)
    pps         = 2 if voltage <= 24 else 4 if voltage <= 48 else 8
    num_strings = math.ceil(r["num_panels"] / pps) if r.get("num_panels") else 0
    last_panels = (r["num_panels"] - (num_strings - 1) * pps) if num_strings else 0

    # Monthly generation
    monthly_factors = [0.88,0.90,0.95,1.00,1.05,1.08,1.10,1.08,1.03,0.98,0.92,0.88]
    base_monthly    = r["daily_kwh"] * 30.44
    months_list     = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly         = [(m, round(base_monthly * f, 1)) for m, f in zip(months_list, monthly_factors)]
    offset_factor   = 1.0 if d.get("system_type") == "off-grid" else 0.8
    annual_offset_kwh = r["daily_kwh"] * 365 * offset_factor
    trees = int(round(eco.get("co2_yr", 0) / 21.77, 0)) if eco.get("co2_yr") else 0
    cars  = round(eco.get("co2_yr", 0) / 4600, 2) if eco.get("co2_yr") else 0

    # Redesign recommendations (may be empty)
    try:
        recs = calc_recommendations(eco, d, r)
    except Exception:
        recs = []

    # ── Header ──────────────────────────────────────────────────────────────
    md = f"""# Solar PV System Proposal — {project["name"]}

**Location:** {d.get("region","")}, {d.get("country","")}
**System Type:** {d.get("system_type","off-grid").title()} | **PV Capacity:** {_fmt(r["pv_kw"],2)} kWp
**Battery:** {_fmt(r["bat_kwh"],2)} kWh {r.get("chemistry","LiFePO4")} | **Inverter:** {_fmt(r["inv_kw"],1)} kW
**Project Verdict:** {eco.get("verdict","—")} | **Bankability:** {eco.get("bankability","—")}

Prepared by: SolarPro Global Â· BS 7671:2018 Â· IEC 60364 Â· IEC 62305 Â· IEC 62446 Â· IEEE

This proposal is a **superset of all individual engineering reports** — it consolidates the Site Assessment,
PV Design, AC Cable, BOQ, Energy Impact, Economic Analysis, Installation Work Plan, and Staffing Plan
into a single deliverable suitable for client award and bank submission.

---

# PART A — TECHNICAL PROPOSAL

## A1. Site Assessment & Solar Resource

| Parameter | Value |
|---|---|
| Location | {d.get("region","")}, {d.get("country","")} |
| Peak Sun Hours | {d.get("psh",5.0)} h/day |
| Average Temperature | {d.get("avg_temp",28)}Â°C |
| Electricity Tariff | {sym}{d.get("tariff",0)}/kWh |
| System Type | {d.get("system_type","off-grid").title()} |
| Phase | {d.get("phase","single").title()}-Phase |
| DC Voltage | {d.get("voltage",48)} V |
| Autonomy | {d.get("autonomy",1)} day(s) |
| Battery Chemistry | {d.get("chemistry","LiFePO4")} |
| Exchange Rate | 1 USD = {d.get("fx_usd",1.0)} {d.get("currency","USD")} |

## A2. Electrical Load Analysis

| Parameter | Value |
|---|---|
| Total Daily Energy | {_fmt(r["daily_kwh"],3)} kWh/day |
| Annual Energy | {_fmt(r["daily_kwh"]*365,0)} kWh/year |
| Connected Peak Load | {_fmt(r.get("peak_kw",0),2)} kW |
| Diversified Peak Load | {_fmt(r.get("div_peak_kw",0),2)} kW |

# Load Schedule

| Category | Appliance | Power (W) | Qty | Hours/day | kWh/day |
|---|---|---|---|---|---|
"""
    for ld in d.get("loads", []):
        kwh = round(ld.get("wattage",0)*ld.get("quantity",1)*ld.get("hours",0)/1000, 3)
        md += (f"| {ld.get('category','')} | {ld.get('name','')} | "
               f"{int(ld.get('wattage',0))} | {int(ld.get('quantity',1))} | "
               f"{ld.get('hours',0)} | **{kwh}** |\n")
    md += f"| | **TOTAL** | | | | **{_fmt(r['daily_kwh'],3)}** |\n"

    md += f"""
## A3. Engineering Sizing Calculations

| Component | Calculation | Result |
|---|---|---|
| PV Array | {_fmt(r["daily_kwh"],3)} kWh Ã· ({d.get("psh",5)} h Ã— 75% BOS) | **{_fmt(r["pv_kw"],2)} kWp â†' {r["num_panels"]} Ã— {r.get("panel_wp",400)} Wp** |
| Battery | {_fmt(r["daily_kwh"],3)} Ã— {d.get("autonomy",1)} day Ã· ({int(r.get("chem_dod",0.9)*100)}% DoD) | **{_fmt(r["bat_kwh"],2)} kWh â†' {r["num_bat"]} Ã— {_fmt(r["unit_bat_kwh"],2)} kWh** |
| Inverter | Peak load {_fmt(r.get("peak_kw",0),2)} kW Ã— 1.25 SF | **{_fmt(r["inv_kw"],1)} kW** |
| MPPT | Array {_fmt(r["pv_kw"],2)} kWp Ã· {d.get("voltage",48)} V bus | **{r.get("mppt_a","—")} A** |

## A4. PV Array Design

| Parameter | Value |
|---|---|
| PV Array Capacity | {_fmt(r.get("pv_kw",0),2)} kWp |
| Number of Panels | {r.get("num_panels",0)} Ã— {r.get("panel_wp",400)} Wp |
| Panel Technology | Monocrystalline PERC, BS EN 61215 |
| Panels per String | {pps} in series |
| Number of Strings | {num_strings} parallel |
| Last String Panels | {last_panels} modules |
| String Voc (est.) | {pps*24} V |
| Temperature Derating Factor | {r.get("temp_derating","—")} |
| BOS Efficiency | 75% |
| Tilt Angle | 10—15Â° minimum (self-cleaning) |
| Orientation | Equator-facing (south in N. hemisphere) |
| Design Standard | IEC 61215 / IEC 61730 |

## A5. Battery Storage Design

| Parameter | Value |
|---|---|
| Total Battery Capacity | {_fmt(r.get("bat_kwh",0),2)} kWh |
| Number of Units | {r.get("num_bat",0)} Ã— {_fmt(r.get("unit_bat_kwh",0),2)} kWh each |
| Chemistry | {chem} |
| Depth of Discharge (DoD) | {int((r.get("chem_dod",0.9))*100)}% |
| Cycle Life | {r.get("chem_cycles","4,000+")} cycles |
| Lifetime | {r.get("chem_life","12")} years |
| Autonomy | {d.get("autonomy",1)} day(s) |
| BMS | Built-in per unit |
| Mounting | Ventilated steel rack, â‰¥ 300mm clearance |

## A6. Inverter & Charge Controller

| Parameter | Value |
|---|---|
| Inverter Rating | {_fmt(r.get("inv_kw",0),1)} kW |
| Type | Hybrid Inverter/Charger |
| Recommended Brands | {r.get("inv_brand","Victron / Growatt / Deye")} |
| MPPT Rating | {r.get("mppt_a","—")} A |
| DC Input Voltage | {d.get("voltage",48)} V |
| AC Output | {"415 V three-phase" if phase=="three" else "230 V single-phase"} |
| Inverter Efficiency | â‰¥ 95% |

## A7. AC Cable Schedule (BS 7671)

| Circuit | Size (mmÂ²) | Capacity (A) | Breaker (A) | Volt Drop | Compliant |
|---|---|---|---|---|---|
"""
    for c in r.get("ac_cables", []):
        md += (f"| {c.get('circuit','')} | {c.get('cable_size_mm2','')} mmÂ² | "
               f"{c.get('cable_capacity','')} A | {c.get('breaker_a','')} A | "
               f"{c.get('vd_percent','')}% | {'✓ Yes' if c.get('vd_ok') else 'âœ— Review'} |\n")

    md += """
## A8. AC Cable Voltage Drop Working (BS 7671 Appendix 4)

Per-circuit step-by-step working for design verification and bank review.

"""
    for c in r.get("ac_cables", []):
        vd_limit_v = c["vd_limit_pct"] / 100 * c["voltage_v"]
        phase_note = "(Ã—0.866 three-phase factor already applied)" if c["phase"] == "three" else ""
        result_str = "✓ PASS" if c["vd_ok"] else "âœ— FAIL — increase cable size"
        md += f"""### {c["circuit"]}

**Cable selected: {c["cable_size_mm2"]} mmÂ² {c["core_type"]}** &nbsp;|&nbsp; {c["cable_capacity"]} A capacity &nbsp;|&nbsp; {c["breaker_a"]} A protective device

| Parameter | Symbol | Value |
|---|---|---|
| Nominal voltage | Vn | {c["voltage_v"]} V ({c["phase"].title()}-Phase) |
| Load power | P | {c["power_kw"]} kW |
| Design current | Ib | **{c["design_current"]} A** |
| Cable length | L | **{c["length_m"]} m** |
| Installation method | — | Method {c["install_method"]} — {c["install_desc"]} |
| Ambient temperature | Ta | {c["ambient_c"]}Â°C |
| Temperature factor | Ct | {c["temp_factor"]} |
| Grouping factor | Cg | {c["group_factor"]} |
| Minimum Iz required | Iz_min | {c["i_z_required"]} A |
| Tabulated mV/A/m | — | **{c["vd_mv_am"]}** mV/A/m {phase_note} |
| Actual VD | — | {c["vd_mv_am"]} Ã— {c["design_current"]} Ã— {c["length_m"]} / 1000 = **{c["vd_volts"]:.3f} V** ({c["vd_percent"]:.3f}%) |
| Permitted limit | — | {c["vd_limit_pct"]}% of {c["voltage_v"]} V = {vd_limit_v:.2f} V |
| Result | — | **{result_str}** |

"""

    md += """### Cable Calculation Notes

| Item | Reference |
|---|---|
| VD tabulated values | BS 7671:2018 Appendix 4, Tables 4D2B / 4D5B |
| 3-phase VD factor Ã—0.866 | = âˆš3/2, IEC 60364-5-52 |
| Temperature correction | BS 7671 Table 4B2 (ref 30Â°C) |
| Grouping correction | BS 7671 Table 4B1 |
| VD limits | Inverterâ†'DB: 1.5% Â· Main feeder: 2.5% Â· Sub-distribution: 3.0% Â· Grid/Gen: 2.0% |
| Breaker coordination | Next standard size above Ib Ã— 1.05; must not exceed cable Iz |

## A9. Wire Colour Code (BS 7671 / IEC 60364)

| Conductor | Colour |
|---|---|
| DC Positive (+) | Red |
| DC Negative (âˆ') | Blue |
| AC Line / Phase | Brown |
| AC Neutral | Grey |
| Protective Earth (PE) | Green/Yellow |
| Battery Circuit | Purple |

## A10. Pre-Installation Site Assessment Checklist

The following must be verified on site before installation begins. Each item is marked Pass / Fail / N/A
with remarks. Sign-off by the consultant and the client is required before mobilisation.

### A10.1 Site Suitability & Solar Resource

| # | Item | Status |
|---|---|:---:|
"""
    insp_sections = [
        ("A10.1", [
            f"Location {d.get('region','')}, {d.get('country','')} has adequate solar irradiance (â‰¥ 4 PSH/day)",
            f"Roof/ground area sufficient for {r['num_panels']} panels (approx. {r['num_panels']*2} mÂ² minimum)",
            "Panel orientation achievable — equator-facing surface available",
            "No permanent shading obstruction between 9am—3pm (buildings, trees, towers)",
            "Roof pitch â‰¥ 10Â° or flat roof with tilt framing available",
            "No planned construction or tree growth likely to cause future shading",
            "Access to roof/ground area is safe and adequate for installation and maintenance",
        ]),
        ("A10.2 Structural & Roof Assessment", [
            "Roof/structure type identified (concrete slab / IBR metal sheet / clay tile / flat membrane)",
            "Structure age and condition acceptable for 25-year system life",
            f"Load capacity adequate — supports ~{r['num_panels']*20} kg PV array weight",
            f"For ground mount: {r['num_panels']*4} mÂ² land area available, level and stable",
            "Existing skylights, vents, or services do not conflict with array footprint",
            "Roof waterproofing in acceptable condition prior to installation",
            "No asbestos-containing materials identified in roof structure",
        ]),
        ("A10.3 Existing Electrical Infrastructure", [
            "Existing main distribution board (MDB) identified and accessible",
            "MDB has spare capacity / ways for new solar incomer",
            "Existing earthing / earth rod present — condition to be tested",
            f"Current utility connection is {'3-phase 415V' if phase=='three' else 'single-phase 230V'} — matches proposed system",
            "Available space for inverter and battery bank within equipment room",
            "Equipment room is dry, secure, and ventilated",
            "Cable routing path from array to equipment room identified and clear",
            "Existing wiring checked — no obvious overloads or faults",
        ]),
        ("A10.4 Load & Demand Validation", [
            f"Daily demand {_fmt(r['daily_kwh'],2)} kWh/day verified against actual utility bills",
            f"Peak connected load {_fmt(r.get('peak_kw',0),2)} kW confirmed — no major loads omitted",
            "Critical loads (medical, refrigeration, security) identified for backup priority",
            "Load profile reasonably consistent — no major seasonal variation",
            "Future load growth in next 3—5 years factored into sizing",
            f"High-draw appliances (A/C, pumps) confirmed compatible with {_fmt(r['inv_kw'],1)} kW inverter",
        ]),
        ("A10.5 Grid Connection & Regulatory", [
            "Utility grid connection available at site",
            f"Net metering / feed-in tariff policy investigated for {d.get('country','')}",
            "Anti-islanding protection required — inverter has built-in function",
            "Local installation code compliance confirmed (BS 7671 / IEC 60364 / national standard)",
            "Planning authority notified of proposed installation (if required)",
        ]),
        ("A10.6 Health, Safety & Access", [
            "Safe roof access route confirmed — scaffolding / MEWP requirements noted",
            "Electrical isolation of existing installation possible before work begins",
            "No asbestos, hazardous materials, or restricted zones on site",
            "Client / occupants can remain during installation or relocation required",
            "Fire risk assessed — battery room ventilation and extinguisher provision confirmed",
        ]),
    ]
    # First section already has its sub-heading rendered in the leading md block; emit its rows then the others
    for j, item in enumerate(insp_sections[0][1], 1):
        md += f"| {j} | {item} | â˜ |\n"
    for sec_title, items in insp_sections[1:]:
        md += f"\n### {sec_title}\n\n| # | Item | Status |\n|---|---|:---:|\n"
        for j, item in enumerate(items, 1):
            md += f"| {j} | {item} | â˜ |\n"

    md += f"""

---

# PART B — FINANCIAL PROPOSAL

## B1. Bill of Quantities (BOQ)

| No. | Description | Specification | Qty | Unit | Basic Rate ({sym}) | Total Rate ({sym}) | Amount ({sym}) |
|---|---|---|---|---|---|---|---|
"""
    for row in r.get("boq_rows", []):
        spec = str(row.get("spec","")).replace("|", "Â·")  # pipes break markdown tables
        md += (f"| {row['no']} | {row['desc']} | {spec} | "
               f"{row['qty']} | {row['unit']} | "
               f"{_fmt(row['basic'],2)} | {_fmt(row['total_r'],2)} | "
               f"**{_fmt(row['amount'],2)}** |\n")
    md += f"| | | | | | | **GRAND TOTAL** | **{sym} {_fmt(r['boq_grand'],2)}** |\n"

    md += f"""
*Note: Total Rate = Basic Rate Ã— 1.08 (8% supply/procurement markup — delivery, overheads & profit)*

### BOQ Notes

- Rates: Total Rate = Basic Rate Ã— 1.08 (8% supply/procurement markup)
- Quantities subject to detailed design review and site survey
- Cable lengths are estimated — confirm actual lengths on site
- Subject to contractor quotation; excludes site-specific VAT / import duties
- DC cable sizes and AC cable sizes are calculated from actual system design

## B2. CAPEX Breakdown

| Item | Amount ({sym}) |
|---|---|
| Equipment Supply (incl. 8% markup) | {_fmt(eco.get("equip_local",0),0)} |
| Installation Labour ({eco.get("install_rate_pct",15)}%) | {_fmt(eco.get("install_local",0),0)} |
| **Total CAPEX** | **{_fmt(eco.get("total_local",0),0)}** |
| Contingency (10%) — advisory | {_fmt(eco.get("total_local",0)*0.1,0)} |
| **Budget (incl. contingency)** | **{_fmt(eco.get("total_local",0)*1.1,0)}** |

## B3. Financial Summary

| Item | Value |
|---|---|
| Equipment Supply (incl. markup) | {sym} {_fmt(eco.get("equip_local",0),0)} |
| Installation Labour ({eco.get("install_rate_pct",15)}%) | {sym} {_fmt(eco.get("install_local",0),0)} |
| **Total CAPEX** | **{sym} {_fmt(eco.get("total_local",0),0)}** |
| Contingency (10%) | {sym} {_fmt(eco.get("total_local",0)*0.1,0)} |
| Budget with contingency | {sym} {_fmt(eco.get("total_local",0)*1.1,0)} |

## B4. Return on Investment

| Metric | Value |
|---|---|
| Annual Solar Generation | {_fmt(eco.get("annual_kwh",0),0)} kWh/year |
| Gross Annual Savings (Yr 1) | {sym} {_fmt(eco.get("annual_sav",0),0)}/year |
| Annual O&M Cost | {sym} {_fmt(eco.get("om_yr1",0),0)}/year |
| **Net Annual Benefit (Yr 1)** | **{sym} {_fmt(eco.get("net_yr1",0),0)}/year** |
| Simple Payback Period | {_fmt(eco.get("payback",0),1)} years |
| Net Present Value (25yr) | {sym} {_fmt(eco.get("npv",0),0)} |
| Internal Rate of Return | {"%.1f" % eco.get("irr_pct",0) if eco.get("irr_pct") else "N/A"}% |
| 25-Year ROI | {_fmt(eco.get("roi_pct",0),0)}% |
| Cumulative Savings (25yr) | {sym} {_fmt(eco.get("cumul_25",0),0)} |
| Annual COâ‚‚ Avoided | {_fmt(eco.get("co2_yr",0),2)} tonnes/year |

## B5. Project Assessment & Verdict Reasons

**Verdict:** {eco.get("verdict","—")} | **Bankability:** {eco.get("bankability","—")}

"""
    for reason in eco.get("verdict_reasons", []):
        md += f"- {reason}\n"
    if eco.get("bankability") and eco.get("bankability") != "BANKABLE":
        md += f"\n**Bankability assessment ({eco.get('bankability','—')}):**\n\n"
        for reason in eco.get("bank_reasons", []):
            md += f"- {reason}\n"

    md += f"""
## B6. Loan Structure & Bankability

| Parameter | Value |
|---|---|
| Total Investment | {sym} {_fmt(eco.get("total_local",0),0)} |
| Loan Amount (70%) | {sym} {_fmt(eco.get("loan_amt",0),0)} |
| Client Equity (30%) | {sym} {_fmt(eco.get("equity",0),0)} |
| Interest Rate | 15% p.a. |
| Loan Tenor | 7 years |
| Monthly Repayment | {sym} {_fmt(eco.get("pmt",0),0)}/month |
| Annual Debt Service | {sym} {_fmt(eco.get("annual_pmt",0),0)}/year |
| **DSCR** | **{_fmt(eco.get("dscr",0),2)} — {eco.get("bankability","—")}** |

## B7. Monthly Generation & Savings Profile

| Month | Generation (kWh) | Grid Offset (kWh) | Savings ({sym}) |
|---|---|---|---|
"""
    annual_gen = r["daily_kwh"] * 365
    base_avg   = annual_gen / 12
    for m, kwh in monthly:
        offset_kwh = round(kwh * offset_factor, 1)
        saving = round(kwh * d.get("tariff", 0), 1)
        md += f"| {m} | {kwh} | {offset_kwh} | {sym} {saving} |\n"
    md += (f"| **Annual Total** | **{_fmt(annual_gen,0)}** | "
           f"**{_fmt(annual_offset_kwh,0)}** | **{sym} {_fmt(eco.get('annual_sav',0),0)}** |\n")

    md += f"""
## B8. Environmental Impact

| Metric | Value |
|---|---|
| Annual COâ‚‚ Avoided | {_fmt(eco.get("co2_yr",0),2)} tonnes/year |
| 25-Year COâ‚‚ Avoided | {_fmt(eco.get("co2_yr",0)*25,1)} tonnes |
| Equivalent Trees Planted | {trees} trees/year |
| Equivalent Cars Removed | {cars} cars/year |
| Grid Emission Factor | 0.40 kg COâ‚‚/kWh |
| Carbon Status | **Carbon Positive** |

## B9. 25-Year Cash Flow Projection

| Year | Gross Saving | O&M | Net Saving | Cumulative |
|---|---|---|---|---|
"""
    for cf in eco.get("cf_rows", []):
        flag = " â—„ BREAK-EVEN" if eco.get("breakeven") and cf["yr"] == eco["breakeven"] else ""
        md += (f"| {cf['yr']} | {sym}{_fmt(cf['gross'],0)} | {sym}{_fmt(cf['om'],0)} | "
               f"{sym}{_fmt(cf['net'],0)} | {sym}{_fmt(cf['cumul'],0)}{flag} |\n")

    md += "\n*Assumptions: Tariff escalation 8%/yr, Discount rate 12%, O&M 1.2%/yr, Degradation 0.5%/yr, Life 25 years*\n"

    if recs:
        md += f"\n## B10. Redesign Recommendations\n\n"
        md += "The following engineering and financial improvements are recommended to achieve project approval and bankability:\n\n"
        for i, rec in enumerate(recs, 1):
            priority_label = "HIGH PRIORITY" if rec["priority"]==1 else "MEDIUM PRIORITY" if rec["priority"]==2 else "ADVISORY"
            md += f"### {i}. {rec['title']} [{priority_label}] ({rec['category']})\n\n"
            md += f"**Action:** {rec['action']}\n\n"
            md += f"**Expected Impact:** {rec['impact']}\n\n"

    # ── PART C — Project Delivery (Material Schedule, Programme, Staffing, Safety) ──
    md += f"""---

# PART C — PROJECT DELIVERY

## C1. Material & Equipment Schedule

### C1.1 PV Array & Mounting

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 1.1 | Solar PV Panels | {r.get("panel_wp",400)} Wp Monocrystalline PERC, Tier 1, Voc â‰ˆ 24 V | {r["num_panels"]} | Modules |
| 1.2 | Aluminium Mounting Rails | 40Ã—40 mm anodised aluminium | {int(r["num_panels"]*1.2)} | m |
| 1.3 | Mid & End Clamps | Stainless steel SS304 | {r["num_panels"]*4} | Sets |
| 1.4 | Roof Mounting Brackets | Galvanised steel, tilt-adjustable | {int(r["num_panels"]*1.5)} | No. |
| 1.5 | DC Solar Cable (strings) | 6 mmÂ² TÃœV UV-resistant, red & black | {int(r["num_panels"]*8)} | m |
| 1.6 | MC4 Connectors | IP67, 1000 VDC rated | {r["num_panels"]*4} | Pairs |
| 1.7 | DC Main Cable (combinerâ†'inverter) | 10 mmÂ² DC solar cable | 30 | m |
| 1.8 | Earthing Cable for Panel Frames | 6 mmÂ² green/yellow | {int(r["num_panels"]*3)} | m |

### C1.2 DC Combiner & Protection

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 2.1 | DC Combiner Box | IP65, {min(num_strings,4)}-string, lockable | 1 | No. |
| 2.2 | String Fuses | 10A DC PV fuse, 1000 VDC | {num_strings*2} | No. |
| 2.3 | DC Surge Protection Device | Type 2, 1000 VDC, IEC 61643-31 | 1 | No. |
| 2.4 | DC Main Isolator | 3-pole DC-rated, lockable | 1 | No. |
| 2.5 | Metallic Cable Conduit | 20 mm steel conduit | 25 | m |
| 2.6 | Cable Tray / Trunking | 50Ã—50 mm galvanised steel | 10 | m |

### C1.3 Inverter, Battery & MPPT

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 3.1 | Hybrid Inverter / Charger | {_fmt(r["inv_kw"],1)} kW, {d.get("voltage",48)}V DC, built-in MPPT {r.get("mppt_a","—")}A | 1 | No. |
| 3.2 | Lithium Battery Units | {_fmt(r["unit_bat_kwh"],2)} kWh {chem}, {d.get("voltage",48)}V, BMS | {r["num_bat"]} | No. |
| 3.3 | Battery Steel Rack | Powder-coated, for {r["num_bat"]} units | {max(1,(r["num_bat"]+1)//2)} | No. |
| 3.4 | Battery DC Fuse (ANL) | 1.25 Ã— max charge current | {r["num_bat"]} | No. |
| 3.5 | Battery DC Cable | 25 mmÂ² flexible, red & black | {r["num_bat"]*4} | m |
| 3.6 | BMS Communication Cable | RS485 / CAN bus | {r["num_bat"]} | Cables |
| 3.7 | Inverter Wall Bracket | Heavy-duty steel | 1 | Set |

### C1.4 AC Distribution & Protection

| # | Description | Specification | Qty | Unit |
|---|---|---|---|---|
| 4.1 | Main AC Distribution Board | {"18-way" if phase=="single" else "12-way 3-ph"}, IP40 | 1 | No. |
| 4.2 | RCCB Incomer | {r["ac_cables"][0]["breaker_a"] if r.get("ac_cables") else 63}A, 30mA, Type A, BS EN 61008 | 1 | No. |
| 4.3 | MCB Lighting | 10A Type B, 6kA | 2 | No. |
| 4.4 | MCB Sockets | 16A Type B, 6kA | 3 | No. |
| 4.5 | MCB Air Conditioning | 32A Type C, 6kA | 1 | No. |
| 4.6 | MCB Pumps / Motors | 16A Type C, 6kA | 2 | No. |
| 4.7 | AC Surge Protection Device | Type 2, 230/415V, BS EN 61643 | 1 | No. |
"""
    for i, c in enumerate(r.get("ac_cables", []), start=8):
        md += f"| 4.{i} | AC Cable — {c['circuit']} | {c['cable_size_mm2']} mmÂ² Cu XLPE/PVC | {c.get('length_m',20)+5} | m |\n"

    md += f"""
### C1.5 Earthing, Bonding & Sundries

| # | Description | Qty | Unit |
|---|---|---|---|
| 5.1 | Copper Earth Rod (16 mm dia., 2.4 m) | 2 | No. |
| 5.2 | Earth Rod Clamp & Driver | 2 | Sets |
| 5.3 | Earth Busbar (10-way copper) | 1 | No. |
| 5.4 | Main Earthing Conductor (16 mmÂ² G/Y) | 15 | m |
| 5.5 | Bonding Cables (6 mmÂ² G/Y) | 40 | m |
| 5.6 | Cable Labels (PVC self-laminating) | 200 | No. |
| 5.7 | Cable Ties UV-resistant | 1 | Box (200) |
| 5.8 | Warning / Safety Labels (BS EN 60445) | 1 | Set |
| 5.9 | IP65 Cable Glands (M20—M32) | 20 | No. |
| 5.10 | UV-Resistant Silicone Sealant | 4 | Tubes |

### C1.6 Test & Commissioning Instruments

| Instrument | Purpose | Acceptance Standard |
|---|---|---|
| Insulation Resistance Tester (Megger) | Cable insulation integrity | â‰¥ 1 MÎ© (IEC 60364-6) |
| Earth Electrode Resistance Tester | Earth rod resistance | â‰¤ 10 Î© (BS 7430) |
| Clamp Earth Tester | Non-invasive earth continuity | â‰¤ 0.1 Î© (BS 7671 Ch.61) |
| Digital Multimeter (1000V DC) | String Voc, polarity | CAT III 1000V |
| DC Clamp Meter (1000V / 60A DC) | String Isc, battery current | CAT III 600V |
| RCD Tester | Trip time verification | â‰¤ 40 ms (BS EN 61008) |
| Voltage Drop Tester | Full-load volt drop | â‰¤ 3% (BS 7671 App 4) |
| Thermal Imaging Camera | Hot-spot detection | IEC 62446-3 |

## C2. Installation Programme

The installation follows a **7-phase methodology** aligned with BS 7671:2018, IEC 60364, and IEC 62446.
Each phase has defined entry criteria, activities, deliverables, and sign-off before the next phase begins.
**Total programme: 12 working days (weather permitting).**

| Phase | Activity | Days | Duration |
|---|---|---|---|
| 1 | Mobilisation & Site Preparation | Days 1—2 | 2 days |
| 2 | Civil & Structural Works | Days 2—4 | 3 days |
| 3 | PV Panel Installation | Days 4—6 | 3 days |
| 4 | Equipment Room Fit-Out | Days 5—7 | 3 days |
| 5 | DC & AC Wiring | Days 7—9 | 3 days |
| 6 | Earthing, Bonding & Pre-commissioning Tests | Days 9—10 | 2 days |
| 7 | Commissioning, Testing & Handover | Days 10—12 | 3 days |

### Programme Notes

- **Total duration:** 12 working days (weather-permitting)
- **Weather hold:** No roof work in rain, lightning, or wind > 25 mph
- **Working hours:** 07:30—17:30 Mon—Fri; 07:30—13:00 Sat if required
- **Parallel working:** Phases 3 and 4 overlap (Days 5—7) — civil and electrical teams work simultaneously

## C3. Installation Phase Detail

### Phase 1 — Mobilisation & Site Preparation (Days 1—2)

**Activities:** Deliver and inventory all equipment on site; set up site compound and secure storage for
panels and batteries; install temporary power and lighting; brief all staff on HSE plan; prepare roof
access (scaffold or MEWP); mark out equipment room layout and cable routes.

**Sign-off outputs:** Signed delivery notes, site induction records, HSE risk assessment signed.

### Phase 2 — Civil & Structural Works (Days 2—4)

**Activities:** Install roof mounting brackets/L-feet at designed spacing; assemble and level aluminium
mounting rails; verify tilt angle; core through roof/walls for DC cable entry — seal immediately;
fix conduit supports and tray brackets along cable route; install metallic conduit from roof to
equipment room.

**Sign-off outputs:** Waterproofing test, structural load check (if required), as-installed conduit sketch.

### Phase 3 — PV Panel Installation (Days 4—6)

**Activities:** Mount panels row-by-row, bottom to top; torque clamps to spec; connect in series strings
with MC4 connectors; verify polarity; install string fuses in combiner box; record fuse ratings; run
and label DC string cables in conduit.

**Sign-off outputs:** String cable labels at both ends, visual inspection — no cracked panels.

### Phase 4 — Equipment Room Fit-Out (Days 5—7)

**Activities:** Fix inverter wall bracket; mount and level inverter; assemble battery rack; anchor to
floor or wall; install batteries; connect in parallel per wiring diagram; connect BMS communication
cables; configure settings; fix DC isolator and AC DB at correct heights; install earth busbar;
run main earthing conductor.

**Sign-off outputs:** Inverter mounting record, battery connection torque check, room layout photo.

### Phase 5 — DC & AC Wiring (Days 7—9)

**Activities:** Run DC main cable combiner â†' inverter (double-check polarity); connect battery cables
with ANL fuses; wire AC output inverter â†' DB incomer; install RCCB, MCBs, SPD in DB; run all AC
final circuit cables; label both ends at every junction.

**Sign-off outputs:** As-installed wiring diagram, cable schedule with actual lengths, labels verified.

### Phase 6 — Earthing, Bonding & Pre-commissioning Tests (Days 9—10)

**Activities:** Drive earth rods to â‰¥ 2.4 m depth; connect to earth busbar; bond all metalwork —
panel frames, inverter, battery rack, DB; test earth electrode resistance (â‰¤ 10 Î© before proceeding);
insulation resistance test all circuits â‰¥ 1 MÎ©; continuity all earth/bonding conductors â‰¤ 0.1 Î©;
polarity check on all DC strings (signed by two technicians).

**Sign-off outputs:** Earth resistance certificate, IR test schedule, polarity check record.

### Phase 7 — Commissioning, Testing & Handover (Days 10—12)

**Activities:** Energise inverter; verify AC output voltage and frequency; test MPPT tracking;
confirm generation on inverter display; RCD trip time test â‰¤ 40 ms; MCB overload test per circuit;
voltage drop test under full load â‰¤ 3%; 7-day performance monitoring (generation vs design);
client handover training; issue O&M manual and warranties.

**Sign-off outputs:** Full commissioning test schedule, 7-day monitoring log, Installation
Completion Certificate, O&M manual issued.

## C4. Staffing Plan

### C4.1 Project Team

| Role | No. | Key Qualifications | Days on Site |
|---|---|---|---|
| Project Engineer / Site Manager | 1 | BEng Electrical, 18th Ed BS 7671, Solar PV cert, IOSH | All 12 days |
| Senior Electrical Technician | 1 | C&G 2365 NVQ L3, 18th Ed + 2391, ECS Gold, Work at Height | All 12 days |
| Electrical Apprentice / Assistant | 1 | NVQ L2 Electrical, Manual Handling, CSCS Green | All 12 days |
| Structural / Civil Technician | 1 | Roof mounting experience, PASMA/IPAF, CSCS | Days 1—6 |
| HSE Officer (part-time) | 1 | NEBOSH General, First Aid at Work | Days 1—2, 9—10 |

**Total peak headcount: 5 persons on site (Days 1—2 and 4—6)**

### C4.2 Staff Deployment by Phase

| Phase | Activity | Days | Proj. Eng. | Sr. Tech | Apprentice | Civil Tech | HSE Officer |
|---|---|---|---|---|---|---|---|
| 1 | Mobilisation | 1—2 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | Civil Works | 2—4 | ✓ (part) | — | ✓ | ✓ | ✓ (part) |
| 3 | PV Installation | 4—6 | ✓ | ✓ | ✓ | ✓ | ✓ (part) |
| 4 | Equipment Fit-Out | 5—7 | ✓ | ✓ | ✓ | — | — |
| 5 | DC & AC Wiring | 7—9 | ✓ | ✓ | ✓ | — | — |
| 6 | Earthing & Testing | 9—10 | ✓ | ✓ | ✓ | — | ✓ (part) |
| 7 | Commissioning | 10—12 | ✓ | ✓ | ✓ | — | — |

### C4.3 Key Responsibilities

**Project Engineer / Site Manager** — Overall technical quality, programme, safety, and client
communication. Signs off each phase, approves all test results, issues the Installation Completion
Certificate. Holds valid BS 7671 certification and Solar PV design qualification.

**Senior Electrical Technician** — Leads all electrical installation activities. Performs and records
all pre-commissioning and commissioning tests. Configures inverter and BMS settings. Mentors the
apprentice.

**Electrical Apprentice / Assistant** — Supports wiring, cable pulling, labelling, and containment
installation. Assists the senior technician and updates the material schedule as items are installed.

**Structural / Civil Technician** — Installs all roof mounting structure. Responsible for panel
mounting, tilt angle accuracy, and waterproofing of all roof penetrations.

**HSE Officer (part-time)** — Daily toolbox talks. Inspects PPE and access equipment. Maintains site
accident log. Emergency response coordinator.

### C4.4 Mandatory PPE — All Personnel

| Item | Standard |
|---|---|
| Safety helmet | EN 397 — all roof and overhead work |
| Safety boots (steel toe cap, anti-slip) | EN ISO 20345 |
| High-visibility vest / jacket (Class 2) | EN ISO 20471 |
| Safety glasses (drilling, cutting, chemicals) | EN 166 |
| Electrical insulated gloves (live-adjacent work) | EN 60903 |
| Full body harness (work at height > 2 m) | EN 361 |
| Anti-static wrist strap (inverter electronics) | IEC 61340-5 |

### C4.5 Site Safety Procedures

- Daily toolbox talk before work — attendance signed by all personnel
- Written risk assessment and method statement on site at all times
- Permit to work before any work on or near energised equipment
- Two-person rule — no solo working on roof or electrical equipment
- All access equipment inspected daily; defective items tagged out of service
- Emergency evacuation plan posted at site entrance and briefed on Day 1
- First aid kit and COâ‚‚ fire extinguisher on site at all times
- Any near-miss reported within 2 hours; incident report completed within 24 hours

## C5. Testing & Verification Schedule

| Test | Standard | Acceptance Criteria |
|---|---|---|
| Insulation Resistance | IEC 60364-6 | â‰¥ 1 MÎ© |
| Earth Continuity | BS 7671 | â‰¤ 0.1 Î© |
| Earth Electrode Resistance | BS 7430 | â‰¤ 10 Î© |
| RCD Trip Time | BS EN 61008 | â‰¤ 40ms |
| DC String Polarity | IEC 62446 | No reversed polarity |
| DC Open-Circuit Voltage | IEC 62446 | Within 5% of Voc |
| AC Output Voltage | BS 7671 | 230V Â±10% |
| Voltage Drop | BS 7671 | â‰¤ 3% final circuits |
| 7-Day Performance Check | IEC 62446 | â‰¥ 90% design output |

## C6. Warranties & O&M

| Item | Warranty |
|---|---|
| PV Panels — Product | 12 years |
| PV Panels — Performance | 25 years (â‰¥80% output) |
| Battery — Cycle Life | {r.get("chem_cycles","4,000+")} cycles / {r.get("chem_life","12")} years |
| Inverter | 5 years (extendable) |
| Installation Workmanship | 2 years |
| Annual O&M Cost (Yr 1) | {sym} {_fmt(eco.get("om_yr1",0),0)} |

---

# PROJECT VERDICT

**Verdict:** {eco.get("verdict","—")} | **Bankability:** {eco.get("bankability","—")}

{chr(10).join("- " + r2 for r2 in eco.get("verdict_reasons",[]))}

**DSCR:** {_fmt(eco.get("dscr",0),2)} | **Simple Payback:** {_fmt(eco.get("payback",0),1)} years | **25-yr NPV:** {sym} {_fmt(eco.get("npv",0),0)}

---

*Full Technical & Financial Proposal (Superset) — {project["name"]}*
*Generated by SolarPro Global Â· Intelligent PV Solar Design Platform*
*BS 7671:2018 Â· IEC 60364 Â· IEC 62305 Â· IEC 62446 Â· IEC 61215 Â· IEEE*
*All figures are indicative and subject to final site survey and detailed design.*
"""
    fname = f"Proposal_{project['name'].replace(' ','_')}.pdf"
    md = _diagrams_markdown(d, r) + md
    return _render_pdf(f"Solar PV Proposal — {project['name']}", md, fname)
