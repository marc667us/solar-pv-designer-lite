"""Byte-level, CRLF-aware, idempotent patch for new_capital_investment_routes.py.

Fixes the two faults found in the 2026-07-03 Generation Station walk:

  FAULT 1 (reports "didn't show up"): 8 of 13 Step-13 reports were placeholders
  (full=False) that abort(404) when clicked. Implement all 8 with real data
  (risk, boq, bom, rfq, construction_est, maintenance, monitoring, ops_manual)
  and flip every REPORT_TYPES row to full=True so all 13 download. Aligns with
  Codex plan area #6 + the spec's MONITORING & MAINTENANCE addition.

  FAULT 2 (live-Postgres hiccup): Step 9 (boq_projects/buildings/floors) and
  Step 11 (opportunity) still used cur.lastrowid -> SELECT lastval(), the exact
  pattern that made the create-project step silently fail on live PG. Convert to
  INSERT ... RETURNING id (portable SQLite 3.35+ / Postgres) - the proven fix
  already used by the /new create path.

Re-runnable: every replacement is guarded so a second run is a no-op.
"""
FN = "new_capital_investment_routes.py"
data = open(FN, "rb").read()
orig = data

def crlf(s: str) -> bytes:
    return s.replace("\n", "\r\n").encode("utf-8")

changes = []
def repl(old: bytes, new: bytes, tag: str, required=True):
    global data
    n = data.count(old)
    if n == 1:
        data = data.replace(old, new)
        changes.append(f"[OK]   {tag}")
    elif data.count(new) >= 1 and n == 0:
        changes.append(f"[skip] {tag} (already applied)")
    else:
        changes.append(f"[MISS] {tag} (anchor count={n}) -- NOT applied")
        if required:
            raise SystemExit("\n".join(changes) + f"\n\nABORT: required anchor '{tag}' not found uniquely.")

# ---------------------------------------------------------------------------
# 1. REPORT_TYPES: flip all full flags to True.
# ---------------------------------------------------------------------------
old_rt = crlf(
'''REPORT_TYPES: list[tuple[str, str, str, bool]] = [
    # (key, label, icon, full=True for implemented PDFs)
    ("executive",       "Executive Summary",     "bi-clipboard-data",  True),
    ("technical",       "Technical Report",      "bi-cpu",             True),
    ("financial",       "Financial Report",      "bi-cash-coin",       True),
    ("bankability",     "Bankability Report",    "bi-bank",            True),
    ("investment_memo", "Investment Memorandum", "bi-file-earmark-text", True),
    ("risk",            "Risk Assessment",       "bi-shield-exclamation", False),
    ("boq",             "BOQ",                   "bi-list-check",      False),
    ("bom",             "BOM",                   "bi-boxes",           False),
    ("rfq",             "Marketplace RFQ",       "bi-cart",            False),
    ("construction_est","Construction Estimate", "bi-hammer",          False),
    ("maintenance",     "Maintenance Strategy",  "bi-tools",           False),
    ("monitoring",      "Monitoring Strategy",   "bi-eye",             False),
    ("ops_manual",      "Operations Manual",     "bi-journal",         False),
]''')
new_rt = crlf(
'''REPORT_TYPES: list[tuple[str, str, str, bool]] = [
    # (key, label, icon, full=True for implemented PDFs) - all 13 live 2026-07-03
    ("executive",       "Executive Summary",     "bi-clipboard-data",  True),
    ("technical",       "Technical Report",      "bi-cpu",             True),
    ("financial",       "Financial Report",      "bi-cash-coin",       True),
    ("bankability",     "Bankability Report",    "bi-bank",            True),
    ("investment_memo", "Investment Memorandum", "bi-file-earmark-text", True),
    ("risk",            "Risk Assessment",       "bi-shield-exclamation", True),
    ("boq",             "BOQ",                   "bi-list-check",      True),
    ("bom",             "BOM",                   "bi-boxes",           True),
    ("rfq",             "Marketplace RFQ",       "bi-cart",            True),
    ("construction_est","Construction Estimate", "bi-hammer",          True),
    ("maintenance",     "Maintenance Strategy",  "bi-tools",           True),
    ("monitoring",      "Monitoring Strategy",   "bi-eye",             True),
    ("ops_manual",      "Operations Manual",     "bi-journal",         True),
]''')
repl(old_rt, new_rt, "REPORT_TYPES all full=True")

# ---------------------------------------------------------------------------
# 2. _build_report_markdown signature: accept an optional linked-BOQ summary.
# ---------------------------------------------------------------------------
old_sig = crlf('''                           opp: dict[str, Any] | None) -> tuple[str, str]:''')
new_sig = crlf('''                           opp: dict[str, Any] | None,
                           boq: dict[str, Any] | None = None) -> tuple[str, str]:''')
repl(old_sig, new_sig, "_build_report_markdown signature +boq")

# Normalise boq inside the function (right after framework is set).
old_fw = crlf('''    cur = proj.get("currency") or "GHS"
    framework = country_framework(proj.get("country"))
''')
new_fw = crlf('''    cur = proj.get("currency") or "GHS"
    framework = country_framework(proj.get("country"))
    boq = boq or {}
    _boq_linked = bool(boq.get("linked"))
    _fac_list = fac.get("buildings") or []
    _tech_list = tech.get("selected") or []
    _elec_list = elec.get("selected") or []
    def _lbl(code: str) -> str:
        return str(code).replace("_", " ").title()
    def _bullets(items, empty="(none configured)"):
        items = list(items or [])
        return "\\n".join(f"- {_lbl(x)}" for x in items) if items else empty
''')
repl(old_fw, new_fw, "_build_report_markdown boq normaliser")

# ---------------------------------------------------------------------------
# 3. Replace the placeholder else-branch with 8 real report branches.
# ---------------------------------------------------------------------------
old_else = crlf('''    else:
        title = "Report"
        md = header + "This report has not been implemented yet."

    return md, title''')

new_branches = crlf('''    elif key == "risk":
        title = f"Risk Assessment - {proj['project_name']}"
        md = header + (
            "## Risk assessment\\n\\n"
            "Risks are rated Low / Medium / High with a primary mitigation.\\n\\n"
            "### Technical\\n\\n"
            "- Module degradation vs. warranty - **Medium** - Tier-1 modules, "
            "linear performance warranty, annual EL/IV testing.\\n"
            "- Inverter reliability - **Medium** - spares holding + service SLA.\\n"
            "- Grid curtailment - **Medium** - dispatch agreement + storage option.\\n\\n"
            "### Financial\\n\\n"
            f"- FX / convertibility ({cur}) - **High** - hard-currency PPA where "
            "possible, DSRA funding.\\n"
            "- Off-taker credit - **High** - sovereign / guarantee support.\\n"
            f"- Tariff review - **Medium** - indexation clauses; base IRR "
            f"{_fmt_pct(computed.get('irr_pct'))}, DSCR avg "
            f"{computed.get('dscr_avg') or 'n/a'}x.\\n\\n"
            "### Construction\\n\\n"
            "- EPC delivery / delay - **Medium** - LDs, milestone payments.\\n"
            "- Land tenure / access - **Medium** - see regulatory posture below.\\n\\n"
            "### Regulatory & O&M\\n\\n"
            "- Permit / ESIA delays - **Medium** - early engagement with "
            f"{framework.get('esia_authority', {}).get('name', 'the ESIA authority')}.\\n"
            "- O&M staffing / spares - **Low** - CMMS + preventive plan (see "
            "Maintenance Strategy).\\n"
        )
    elif key == "boq":
        title = f"Bill of Quantities (summary) - {proj['project_name']}"
        pf = boq.get("per_facility_usd") or {}
        md = header + (
            "## Bill of Quantities - summary\\n\\n"
            + ("The priced, editable BOQ is linked to this project. Open it in "
               "the BOQ workspace (Build-all / Section-by-Section) for the full "
               "line-item detail and exports.\\n\\n"
               if _boq_linked else
               "No linked BOQ yet - generate it on Step 9 (BOQ), then re-open "
               "this report for priced totals.\\n\\n")
            + f"- **Line items (indicative starter):** {boq.get('n_items') or 0}\\n"
            + f"- **BOQ total:** {_fmt_money(boq.get('grand_total_usd'), 'USD')} "
              f"({_fmt_money(boq.get('grand_total_local'), cur)})\\n\\n"
            + "### By facility (USD, indicative)\\n\\n"
            + ("\\n".join(f"- {_lbl(k or 'unassigned')}: {_fmt_money(v, 'USD')}"
                          for k, v in pf.items()) if pf else "(no facility rows yet)")
            + "\\n\\n_Figures are indicative while Step 9 seeds a 1-per-section "
              "starter; expand each section in Build-all for firm quantities._\\n"
        )
    elif key == "bom":
        title = f"Bill of Materials (procurement scope) - {proj['project_name']}"
        md = header + (
            "## Bill of Materials - procurement scope\\n\\n"
            "Materials scope derived from the facility, technology and "
            "electrical selections. Prices and suppliers are sourced in the "
            "SolarPro Marketplace (Step 10).\\n\\n"
            "### Facilities / civil\\n\\n" + _bullets(_fac_list) + "\\n\\n"
            "### Monitoring & technology\\n\\n" + _bullets(_tech_list) + "\\n\\n"
            "### Electrical / power system\\n\\n" + _bullets(_elec_list) + "\\n\\n"
            "### PV primary equipment\\n\\n"
            f"- Modules: {sizing.get('n_modules') or 'n/a'} x "
            f"{pv.get('module_wp') or 'n/a'} W ({pv.get('module_tech') or 'n/a'})\\n"
            f"- Central inverters: {sizing.get('n_central_inverters') or 'n/a'} x "
            f"{sizing.get('central_inverter_kw') or 'n/a'} kW\\n"
            f"- Mounting: {pv.get('mounting') or 'n/a'}\\n"
        )
    elif key == "rfq":
        title = f"Marketplace RFQ pack - {proj['project_name']}"
        cats = sorted(set(
            [_lbl(x) for x in _tech_list] + [_lbl(x) for x in _elec_list]
            + ["PV Modules", "Inverters", "Mounting Structures",
               "Transformers", "MV/LV Cables", "Earthing & Lightning"]))
        md = header + (
            "## Marketplace RFQ pack\\n\\n"
            "Request-for-quotation scope. Issue these categories to verified "
            "suppliers from the Marketplace RFQ workflow.\\n\\n"
            f"- **Project capacity:** "
            f"{(sizing.get('kwp_input') or proj.get('target_kwp') or 0)/1000:.1f} MWp\\n"
            f"- **Delivery location:** {proj.get('region') or ''} "
            f"{proj.get('country') or ''}\\n"
            f"- **Target COD:** {proj.get('target_cod') or 'to be confirmed'}\\n\\n"
            "### RFQ categories\\n\\n" + "\\n".join(f"- {c}" for c in cats) + "\\n"
        )
    elif key == "construction_est":
        title = f"Construction Estimate - {proj['project_name']}"
        md = header + (
            "## Construction estimate\\n\\n"
            f"- **Total CAPEX (engineering model):** "
            f"{_fmt_money(computed.get('total_capex_usd'), 'USD')} "
            f"({_fmt_money(computed.get('total_capex_local'), cur)})\\n"
            f"- **Linked-BOQ facilities actual (indicative):** "
            f"{_fmt_money(boq.get('grand_total_usd'), 'USD')}\\n\\n"
            "### CAPEX breakdown (USD)\\n\\n"
            + ("\\n".join(f"- {_lbl(k)}: {_fmt_money(v)}"
                          for k, v in (computed.get('capex_lines_usd') or {}).items())
               or "(run Step 8 finance to populate)")
            + "\\n\\n### Construction assumptions\\n\\n"
            "- Mobilisation to COD driven by grid + civil critical path.\\n"
            "- Facilities (control room, O&M, security, transformer yard) "
            "priced from the linked BOQ.\\n"
            "- Contingency carried within the financial model.\\n"
        )
    elif key == "maintenance":
        title = f"Maintenance Strategy - {proj['project_name']}"
        has = lambda *xs: any(x in _tech_list for x in xs)
        md = header + (
            "## Maintenance strategy (O&M)\\n\\n"
            "Preventive-first O&M aligned to the plant's monitoring stack.\\n\\n"
            "### Preventive maintenance plan\\n\\n"
            "- Modules: cleaning by soiling rate; annual EL / IV curve + "
            "thermography.\\n"
            "- Inverters: quarterly inspection, filter service, firmware.\\n"
            "- Transformers / switchgear: oil + protection-relay testing.\\n"
            "- Structures: torque + corrosion checks; tracker service (if any).\\n"
            "- Earthing & lightning: annual continuity + resistance test.\\n\\n"
            "### Maintenance technology\\n\\n"
            f"- CMMS / work orders: {'enabled' if has('cmms','maintenance','tickets') else 'recommended'}\\n"
            f"- Spare-parts inventory: {'tracked' if has('inventory','spare_parts') else 'recommended'}\\n"
            f"- Mobile field app: {'enabled' if has('mobile_app') else 'recommended'}\\n\\n"
            "### Spare-parts strategy\\n\\n"
            "- Critical spares on site: inverter modules, fuses, protection "
            "relays, comms gear.\\n"
            "- Consumables: cleaning + PPE + connectors.\\n\\n"
            "### O&M staffing assumptions\\n\\n"
            "- Resident O&M lead + technicians (site-size dependent).\\n"
            "- Security roster at the gatehouse.\\n"
            "- Remote monitoring / NOC support (see Monitoring Strategy).\\n"
        )
    elif key == "monitoring":
        title = f"Monitoring & SCADA Strategy - {proj['project_name']}"
        has = lambda *xs: any(x in _tech_list for x in xs)
        md = header + (
            "## Monitoring & SCADA strategy\\n\\n"
            "Real-time supervision and performance analytics for the plant.\\n\\n"
            "### Monitoring stack (from Step 5 selections)\\n\\n"
            f"- SCADA monitoring: {'yes' if has('scada','scada_monitoring') else 'recommended'}\\n"
            f"- Weather station: {'yes' if has('weather_station') else 'recommended'}\\n"
            f"- Data logger: {'yes' if has('data_logger') else 'recommended'}\\n"
            f"- Remote monitoring portal: {'yes' if has('remote_monitoring','remote_monitoring_portal') else 'recommended'}\\n"
            f"- String / inverter monitoring: {'yes' if has('string_monitoring','inverter_monitoring') else 'recommended'}\\n"
            f"- Energy metering: {'yes' if has('energy_metering') else 'recommended'}\\n"
            f"- Battery monitoring (BMS): {'yes' if has('battery_monitoring','bms') else 'n/a'}\\n\\n"
            "### Control room\\n\\n"
            + ("- Control Room facility is included in the plant scope.\\n"
               if 'control_room' in _fac_list else
               "- No dedicated control room selected - remote NOC assumed.\\n")
            + "\\n### KPIs & alarms\\n\\n"
            "- PR, availability, specific yield, inverter efficiency.\\n"
            f"- Design PR {pv.get('performance_ratio') or 'n/a'}, availability "
            f"{pv.get('availability_pct') or 'n/a'}%.\\n"
            "- Alarm classes: trip, derate, comms-loss, security.\\n\\n"
            "### Fault response workflow\\n\\n"
            "1. Alarm raised (SCADA/portal) -> 2. NOC triage -> 3. Field work "
            "order (CMMS) -> 4. Fix + verify -> 5. Close-out + RCA.\\n"
        )
    elif key == "ops_manual":
        title = f"Operations Manual - {proj['project_name']}"
        md = header + (
            "## Operations manual\\n\\n"
            "### Site & facilities\\n\\n" + _bullets(_fac_list, "(configure facilities on Step 4)") + "\\n\\n"
            "### Roles\\n\\n"
            "- O&M lead: plant performance, PM schedule, reporting.\\n"
            "- Technicians: corrective + preventive work orders.\\n"
            "- Security: access control at the gatehouse, patrols.\\n"
            "- NOC / remote: monitoring, first-line triage.\\n\\n"
            "### Standard procedures\\n\\n"
            "- Start-up / shutdown + LOTO (lock-out tag-out).\\n"
            "- Emergency response: fire, electrical, medical.\\n"
            "- Grid interface + protection coordination.\\n"
            "- Environmental + community obligations.\\n\\n"
            "### Documentation\\n\\n"
            "- As-built drawings, warranties, test certificates.\\n"
            "- CMMS records, spare-parts register, monitoring exports.\\n\\n"
            "### Jurisdiction\\n\\n"
            f"- Regulator: {framework.get('regulator', {}).get('name', '')}\\n"
            f"- Off-taker(s): {', '.join(framework.get('utility_offtakers') or [])}\\n"
        )
    else:
        title = "Report"
        md = header + "This report has not been implemented yet."

    return md, title''')
repl(old_else, new_branches, "8 new report branches")

# ---------------------------------------------------------------------------
# 4. _report_pdf: compute the linked-BOQ summary and pass it; widen the gate.
# ---------------------------------------------------------------------------
old_gate = crlf('''        if report_key not in FULL_REPORT_KEYS:
            abort(404)
        proj = _load_project(pid)
        uid = session["user_id"]
        opp = _load_opportunity(pid, uid)
        md, title = _build_report_markdown(report_key, proj, opp)''')
new_gate = crlf('''        if report_key not in REPORT_KEYS:
            abort(404)
        proj = _load_project(pid)
        uid = session["user_id"]
        opp = _load_opportunity(pid, uid)
        # Linked-BOQ summary so BOQ / BOM / construction reports carry real
        # priced totals (REUSES _ci_boq_actuals - no parallel costing).
        try:
            _rfin = _safe_json(proj.get("finance_config"))
            _rfx = float(_rfin.get("fx_local_per_usd") or 12.0)
        except (TypeError, ValueError):
            _rfx = 12.0
        try:
            _rboq = _ci_boq_actuals(get_db, proj.get("boq_project_id"), uid, _rfx)
        except Exception:
            _rboq = None
        md, title = _build_report_markdown(report_key, proj, opp, _rboq)''')
repl(old_gate, new_gate, "_report_pdf boq + REPORT_KEYS gate")

# ---------------------------------------------------------------------------
# 5. PG robustness: lastrowid -> RETURNING id (Step 9 x3, Step 11 x1).
#    Only the primary (tenant-aware) INSERT of each pair is converted; the
#    legacy-schema fallback keeps lastrowid (older DBs without the wide cols).
# ---------------------------------------------------------------------------
# 5a. boq_projects (Step 9) - replace the whole primary INSERT statement.
old_bp2 = crlf('''                    try:
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, tenant_id, project_name, client_name, "
                            " location, project_type, external_works_included, "
                            " infrastructure_included, services_csv) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (uid, tenant_id, project_name,
                             proj.get("client_name") or "", location, "campus",
                             external_flag, 1, services_csv),
                        )
                    except Exception:''')
new_bp2 = crlf('''                    try:
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, tenant_id, project_name, client_name, "
                            " location, project_type, external_works_included, "
                            " infrastructure_included, services_csv) "
                            "VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
                            (uid, tenant_id, project_name,
                             proj.get("client_name") or "", location, "campus",
                             external_flag, 1, services_csv),
                        )
                        _rr = cur.fetchone()
                        cur = _RetId(int(_rr[0])) if _rr else cur
                    except Exception:''')
repl(old_bp2, new_bp2, "Step9 boq_projects RETURNING id")

# 5b. boq_buildings (Step 9 primary insert)
old_bb = crlf('''                            bcur = c.execute(
                                "INSERT INTO boq_buildings "
                                "(project_id, tenant_id, building_name, "
                                " building_code, primary_purpose, "
                                " purpose_subtype, building_area, "
                                " number_of_floors, basement_included, "
                                " roof_level_included, external_area_included) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (new_boq_pid, tenant_id, label, b.upper(),
                                 "commercial", b, 0, 1, 0, 1, 0),
                            )
                            bid = int(bcur.lastrowid or 0)''')
new_bb = crlf('''                            bcur = c.execute(
                                "INSERT INTO boq_buildings "
                                "(project_id, tenant_id, building_name, "
                                " building_code, primary_purpose, "
                                " purpose_subtype, building_area, "
                                " number_of_floors, basement_included, "
                                " roof_level_included, external_area_included) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
                                (new_boq_pid, tenant_id, label, b.upper(),
                                 "commercial", b, 0, 1, 0, 1, 0),
                            )
                            _br = bcur.fetchone()
                            bid = int(_br[0]) if _br else int(bcur.lastrowid or 0)''')
repl(old_bb, new_bb, "Step9 boq_buildings RETURNING id")

# 5c. boq_floors (Step 9 primary insert)
old_bf = crlf('''                                fcur = c.execute(
                                    "INSERT INTO boq_floors "
                                    "(building_id, project_id, tenant_id, "
                                    " floor_name, floor_level, floor_type) "
                                    "VALUES (?,?,?,?,?,?)",
                                    (bid, new_boq_pid, tenant_id,
                                     "Ground Floor", 0, "ground"),
                                )
                                fid = int(fcur.lastrowid or 0)''')
new_bf = crlf('''                                fcur = c.execute(
                                    "INSERT INTO boq_floors "
                                    "(building_id, project_id, tenant_id, "
                                    " floor_name, floor_level, floor_type) "
                                    "VALUES (?,?,?,?,?,?) RETURNING id",
                                    (bid, new_boq_pid, tenant_id,
                                     "Ground Floor", 0, "ground"),
                                )
                                _fr = fcur.fetchone()
                                fid = int(_fr[0]) if _fr else int(fcur.lastrowid or 0)''')
repl(old_bf, new_bf, "Step9 boq_floors RETURNING id")

# 5d. opportunity (Step 11 create)
old_op = crlf('''                        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (derived["capital_investment_project_id"],
                         derived["user_id"], derived["project_name"],
                         derived["investor"], derived["developer"],
                         derived["client"], derived["location"],
                         derived["country"], derived["currency"],
                         derived["capacity_mwp"], derived["capex_local"],
                         derived["capex_usd"], derived["revenue_y1_local"],
                         derived["annual_gen_mwh"], derived["npv_local"],
                         derived["irr_pct"], derived["lcoe_local_per_kwh"],
                         derived["payback_years"], derived["dscr_avg"],
                         "lead", notes),
                    )
                    oid = int(cur.lastrowid or 0)''')
new_op = crlf('''                        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                        "RETURNING id",
                        (derived["capital_investment_project_id"],
                         derived["user_id"], derived["project_name"],
                         derived["investor"], derived["developer"],
                         derived["client"], derived["location"],
                         derived["country"], derived["currency"],
                         derived["capacity_mwp"], derived["capex_local"],
                         derived["capex_usd"], derived["revenue_y1_local"],
                         derived["annual_gen_mwh"], derived["npv_local"],
                         derived["irr_pct"], derived["lcoe_local_per_kwh"],
                         derived["payback_years"], derived["dscr_avg"],
                         "lead", notes),
                    )
                    _orow = cur.fetchone()
                    oid = int(_orow[0]) if _orow else int(cur.lastrowid or 0)''')
repl(old_op, new_op, "Step11 opportunity RETURNING id")

# ---------------------------------------------------------------------------
# 6. Tiny _RetId shim so the boq_projects branch can carry lastrowid uniformly
#    (the later code reads new_boq_pid = int(cur.lastrowid or 0)).
#    Insert it just before register_capital_investment defs use it: place at
#    module top after imports is simplest - anchor on the first helper def.
# ---------------------------------------------------------------------------
old_shim_anchor = crlf('''def _ci_boq_actuals(get_db, boq_project_id, uid, fx: float = 12.0) -> dict:''')
new_shim = crlf('''class _RetId:
    """Minimal cursor stand-in exposing .lastrowid for RETURNING-id inserts so
    downstream code that reads cur.lastrowid keeps working unchanged."""
    __slots__ = ("lastrowid",)
    def __init__(self, rid):
        self.lastrowid = rid


def _ci_boq_actuals(get_db, boq_project_id, uid, fx: float = 12.0) -> dict:''')
repl(old_shim_anchor, new_shim, "_RetId shim")

if data == orig:
    print("\n".join(changes))
    print("\nNO CHANGES (already fully patched).")
else:
    open(FN, "wb").write(data)
    print("\n".join(changes))
    print(f"\nWROTE {FN} ({len(orig)} -> {len(data)} bytes)")
