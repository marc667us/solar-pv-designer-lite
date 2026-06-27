# ─── Check My Electricity Bill — feature ─────────────────────────────────────
# Spec: Documents/pvsolar1/check my bill.txt (added 2026-06-27)
# Tariff: GHANA_PURC_TARIFFS (PURC Q2 2026, effective 2026-04-01)
#
# Lifeline note: PURC treats lifeline as a CUSTOMER CLASS, not a band. A
# household whose total monthly use is ≤ 30 kWh pays the lifeline rate on
# every unit. The moment monthly use exceeds 30 kWh, the customer moves to
# the non-lifeline class (0-300 + 301+ bands) and the lifeline rate no
# longer applies to ANY unit. The legacy "band-rate" math in the original
# spec file (lifeline_rate × 30 + standard_rate × 270 + …) overstated bills
# for non-lifeline customers and is corrected here.

def _bc_expected_purc_bill(monthly_kwh, category="Residential Standard (0-300 kWh/month)"):
    """Return {energy, service, total, bands, category} for monthly consumption."""
    monthly_kwh = max(0.0, float(monthly_kwh or 0))
    bands = []

    if "Lifeline" in category and monthly_kwh <= 30:
        info = GHANA_PURC_TARIFFS["Residential Lifeline (≤ 30 kWh/month)"]
        energy = monthly_kwh * info["rate_ghc"]
        bands.append({"label": "Lifeline (≤ 30 kWh)", "kwh": monthly_kwh,
                      "rate": info["rate_ghc"], "amount": energy})
        return {"energy": energy, "service": info["fixed_ghc"],
                "total": energy + info["fixed_ghc"], "bands": bands,
                "category": "Residential Lifeline (≤ 30 kWh/month)"}

    if "Lifeline" in category and monthly_kwh > 30:
        category = "Residential Standard (0-300 kWh/month)"

    if "Residential" in category and "Non-" not in category:
        std = GHANA_PURC_TARIFFS["Residential Standard (0-300 kWh/month)"]
        hi  = GHANA_PURC_TARIFFS["Residential High Use (>300 kWh/month)"]
        service = std["fixed_ghc"]
        if monthly_kwh <= 300:
            energy = monthly_kwh * std["rate_ghc"]
            bands.append({"label": "0-300 kWh", "kwh": monthly_kwh,
                          "rate": std["rate_ghc"], "amount": energy})
        else:
            e0 = 300 * std["rate_ghc"]
            e1 = (monthly_kwh - 300) * hi["rate_ghc"]
            energy = e0 + e1
            bands.append({"label": "0-300 kWh", "kwh": 300,
                          "rate": std["rate_ghc"], "amount": e0})
            bands.append({"label": "301+ kWh", "kwh": monthly_kwh - 300,
                          "rate": hi["rate_ghc"], "amount": e1})
        return {"energy": energy, "service": service,
                "total": energy + service, "bands": bands,
                "category": "Residential (non-lifeline)"}

    if category.startswith("Non-Residential"):
        std = GHANA_PURC_TARIFFS["Non-Residential Standard (0-300 kWh/month)"]
        hi  = GHANA_PURC_TARIFFS["Non-Residential High Use (>300 kWh/month)"]
        service = std["fixed_ghc"]
        if monthly_kwh <= 300:
            energy = monthly_kwh * std["rate_ghc"]
            bands.append({"label": "0-300 kWh", "kwh": monthly_kwh,
                          "rate": std["rate_ghc"], "amount": energy})
        else:
            e0 = 300 * std["rate_ghc"]
            e1 = (monthly_kwh - 300) * hi["rate_ghc"]
            energy = e0 + e1
            bands.append({"label": "0-300 kWh", "kwh": 300,
                          "rate": std["rate_ghc"], "amount": e0})
            bands.append({"label": "301+ kWh", "kwh": monthly_kwh - 300,
                          "rate": hi["rate_ghc"], "amount": e1})
        return {"energy": energy, "service": service,
                "total": energy + service, "bands": bands,
                "category": "Non-Residential"}

    info = GHANA_PURC_TARIFFS.get(category)
    if info:
        energy = monthly_kwh * info["rate_ghc"]
        bands.append({"label": category, "kwh": monthly_kwh,
                      "rate": info["rate_ghc"], "amount": energy})
        return {"energy": energy, "service": info["fixed_ghc"],
                "total": energy + info["fixed_ghc"], "bands": bands,
                "category": category}

    return _bc_expected_purc_bill(monthly_kwh, "Residential Standard (0-300 kWh/month)")


def _bc_confidence(completeness_flag):
    return {"yes": "high", "no": "low", "unsure": "medium"}.get(
        (completeness_flag or "").lower(), "medium")


def _bc_confidence_message(level):
    return {
        "high":   "Your load schedule appears complete. The bill comparison is suitable for checking whether your actual bill is reasonable.",
        "medium": "Some loads may be missing. Please confirm refrigerators, pumps, water heaters, external loads, and auxiliary buildings before relying on the result.",
        "low":    "This result is only a rough estimate because important active loads may be missing. Add all active loads before concluding that you are overcharged.",
    }.get(level, "")


def _bc_status(diff_pct):
    if diff_pct is None:
        return ("Insufficient data to compare.", "secondary")
    if abs(diff_pct) <= 10:
        return ("Bill is within ±10% of the expected PURC energy charge.", "success")
    if diff_pct > 10:
        return ("Potential billing difference detected — your actual bill exceeds the calculated PURC energy charge. Check ECG receipt for deductions, arrears, levies, tariff classification, or missing loads.", "warning")
    return ("Your actual bill is lower than the calculated PURC energy charge. Verify with meter reading.", "info")


def _bc_compute(payload, loads=None):
    actual_bill = float(payload.get("actual_bill") or 0)
    actual_kwh  = payload.get("actual_kwh")
    actual_kwh  = float(actual_kwh) if actual_kwh not in (None, "") else None
    category    = payload.get("category") or "Residential Standard (0-300 kWh/month)"
    meter_type  = (payload.get("meter_type") or "postpaid").lower()
    completeness= (payload.get("completeness") or "unsure").lower()
    target_pct  = float(payload.get("target_reduction_pct") or 50)
    psh         = float(payload.get("peak_sun_hours") or 5.0)
    sys_eff     = float(payload.get("system_efficiency") or 0.80)
    cost_per_kwp= float(payload.get("system_cost_per_kwp") or 8000)
    loan_years  = float(payload.get("loan_years") or 5)
    loan_rate   = float(payload.get("loan_interest_pct") or 22) / 100.0

    daily_kwh = 0.0
    monthly_kwh = 0.0
    source = "none"
    if loads:
        try:
            daily_kwh = float(calc_loads(loads) or 0)
            monthly_kwh = daily_kwh * 30.0
            source = "load_schedule"
        except Exception:
            pass
    if actual_kwh is not None and actual_kwh > 0:
        monthly_kwh = actual_kwh
        daily_kwh = actual_kwh / 30.0
        source = "user_provided_kwh"
    if monthly_kwh <= 0 and actual_bill > 0:
        std_rate = GHANA_PURC_TARIFFS["Residential Standard (0-300 kWh/month)"]["rate_ghc"]
        monthly_kwh = max(1.0, actual_bill / std_rate)
        daily_kwh = monthly_kwh / 30.0
        source = "derived_from_bill"

    expected = _bc_expected_purc_bill(monthly_kwh, category)

    effective_tariff = None
    if monthly_kwh > 0 and actual_bill > 0:
        effective_tariff = actual_bill / monthly_kwh

    difference = (actual_bill - expected["total"]) if actual_bill > 0 else None
    diff_pct = None
    if difference is not None and expected["total"] > 0:
        diff_pct = (difference / expected["total"]) * 100.0
    status_label, status_css = _bc_status(diff_pct)

    confidence = _bc_confidence(completeness)
    confidence_msg = _bc_confidence_message(confidence)

    target_kwh_offset = monthly_kwh * (target_pct / 100.0)
    daily_kwh_offset  = target_kwh_offset / 30.0
    solar_kwp = 0.0
    if psh > 0 and sys_eff > 0:
        solar_kwp = daily_kwh_offset / psh / sys_eff
    rec_kwp = round(solar_kwp * 2 + 0.499) / 2.0 if solar_kwp > 0 else 0

    if actual_bill > 0:
        monthly_saving = actual_bill * (target_pct / 100.0)
    elif effective_tariff:
        monthly_saving = target_kwh_offset * effective_tariff
    elif monthly_kwh > 0:
        monthly_saving = target_kwh_offset * (expected["total"] / monthly_kwh)
    else:
        monthly_saving = 0.0

    loan_payment = 0.0
    loan_supported = None
    if rec_kwp > 0 and loan_years > 0:
        system_cost = rec_kwp * cost_per_kwp
        months = loan_years * 12
        if loan_rate > 0:
            r = loan_rate / 12.0
            try:
                loan_payment = system_cost * r / (1 - (1 + r) ** -months)
            except Exception:
                loan_payment = system_cost / months
        else:
            loan_payment = system_cost / months
        loan_supported = monthly_saving >= loan_payment

    return {
        "inputs": {
            "actual_bill": actual_bill,
            "actual_kwh":  actual_kwh,
            "category":    category,
            "meter_type":  meter_type,
            "completeness": completeness,
        },
        "energy": {
            "daily_kwh":   round(daily_kwh, 2),
            "monthly_kwh": round(monthly_kwh, 2),
            "source":      source,
        },
        "expected": {
            "energy":  round(expected["energy"], 2),
            "service": round(expected["service"], 2),
            "total":   round(expected["total"], 2),
            "bands": [
                {"label": b["label"],
                 "kwh":    round(b["kwh"], 2),
                 "rate":   round(b["rate"], 4),
                 "amount": round(b["amount"], 2)}
                for b in expected["bands"]
            ],
            "category_applied": expected["category"],
        },
        "actual_bill":      actual_bill,
        "difference":       round(difference, 2) if difference is not None else None,
        "difference_pct":   round(diff_pct, 2) if diff_pct is not None else None,
        "effective_tariff": round(effective_tariff, 4) if effective_tariff is not None else None,
        "status_label":     status_label,
        "status_css":       status_css,
        "confidence":       confidence,
        "confidence_message": confidence_msg,
        "solar": {
            "target_reduction_pct":   target_pct,
            "target_kwh_offset":      round(target_kwh_offset, 2),
            "daily_kwh_offset":       round(daily_kwh_offset, 2),
            "computed_kwp":           round(solar_kwp, 2),
            "recommended_kwp":        rec_kwp,
            "peak_sun_hours":         psh,
            "system_efficiency":      sys_eff,
            "estimated_monthly_saving": round(monthly_saving, 2),
        },
        "loan": {
            "years":                     loan_years,
            "interest_pct":              round(loan_rate * 100.0, 2),
            "cost_per_kwp":              cost_per_kwp,
            "system_cost":               round(rec_kwp * cost_per_kwp, 2),
            "estimated_monthly_payment": round(loan_payment, 2),
            "supported":                 loan_supported,
            "message": (
                "Your estimated monthly saving can support this solar loan." if loan_supported
                else "Savings may not fully cover the loan. Consider a smaller system, higher deposit, or a longer repayment period." if loan_supported is False
                else "Loan support not evaluated."
            ),
        },
        "tariff_meta": GHANA_PURC_TARIFF_META,
    }


@app.route("/api/bill-check", methods=["POST"])
@limiter.limit("60 per minute")
def api_bill_check():
    """Bill-check calculator. Anon-friendly; CSRF required."""
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    loads = None
    pid = payload.get("project_id")
    if pid and session.get("user_id"):
        try:
            proj = get_project(int(pid))
            if proj:
                loads = (proj.get("data") or {}).get("loads") or []
        except Exception:
            loads = None
    if not loads and isinstance(payload.get("loads"), list):
        loads = payload["loads"]
    try:
        result = _bc_compute(payload, loads=loads)
    except Exception as e:
        return jsonify({"error": "computation failed", "detail": str(e)}), 400
    try:
        _log_marketplace_action(
            "bill_check_calculated", "project",
            int(pid) if pid and str(pid).isdigit() else 0,
            f"cat={result['inputs']['category']} "
            f"kwh={result['energy']['monthly_kwh']} "
            f"bill={result['actual_bill']}"
        )
    except Exception:
        pass
    return jsonify(result)


@app.route("/project/<int:pid>/bill-check/save", methods=["POST"])
@login_required
def bill_check_save(pid):
    """Persist a bill-check snapshot into data['bill_check']."""
    csrf_protect()
    proj = get_project(pid)
    if not proj:
        abort(404)
    payload = request.get_json(force=True, silent=True) or {}
    loads = (proj.get("data") or {}).get("loads") or []
    try:
        result = _bc_compute(payload, loads=loads)
    except Exception as e:
        return jsonify({"error": "computation failed", "detail": str(e)}), 400
    data = proj.get("data", {}) or {}
    history = data.setdefault("bill_check_history", [])
    history.append({"saved_at": datetime.now().isoformat(timespec="seconds"), **result})
    data["bill_check_history"] = history[-20:]
    data["bill_check"] = result
    save_project_data(pid, data)
    try:
        _log_marketplace_action(
            "bill_check_saved", "project", pid,
            f"diff_pct={result.get('difference_pct')} "
            f"kwp={result['solar']['recommended_kwp']}"
        )
    except Exception:
        pass
    return jsonify({"ok": True, "snapshot": result})


@app.route("/project/<int:pid>/bill-check/report.pdf", methods=["POST"])
@login_required
def bill_check_report(pid):
    """Render bill-check result as a PDF via existing _render_pdf helper."""
    csrf_protect()
    proj = get_project(pid)
    if not proj:
        abort(404)
    payload = request.get_json(force=True, silent=True) or {}
    loads = (proj.get("data") or {}).get("loads") or []
    r = _bc_compute(payload, loads=loads)
    sym = "GHS "
    md  = f"# Bill Check Report — Project {pid}\n\n"
    md += f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} — PURC tariff effective {r['tariff_meta']['effective_from']}*\n\n"
    md += "## Summary\n\n| Item | Value |\n|---|---|\n"
    md += f"| Customer Category | {r['expected']['category_applied']} |\n"
    md += f"| Meter Type | {r['inputs']['meter_type'].title()} |\n"
    md += f"| Load Schedule Completeness | {r['inputs']['completeness']} |\n"
    md += f"| Confidence Level | {r['confidence'].upper()} |\n"
    md += f"| Estimated Monthly kWh | {r['energy']['monthly_kwh']:,.2f} |\n"
    md += f"| Expected PURC Energy Charge | {sym}{r['expected']['energy']:,.2f} |\n"
    md += f"| Service Charge | {sym}{r['expected']['service']:,.2f} |\n"
    md += f"| Expected PURC Bill (energy + service) | {sym}{r['expected']['total']:,.2f} |\n"
    md += f"| Actual Bill | {sym}{r['actual_bill']:,.2f} |\n"
    if r.get("difference") is not None:
        md += f"| Difference (Actual − Expected) | {sym}{r['difference']:,.2f} ({r['difference_pct']:+.2f}%) |\n"
    if r.get("effective_tariff") is not None:
        md += f"| Effective Tariff | {sym}{r['effective_tariff']:.4f}/kWh |\n"
    md += "\n## Status\n\n"
    md += f"> {r['status_label']}\n\n"
    md += f"**Confidence note:** {r['confidence_message']}\n\n"
    md += "## PURC Band Breakdown\n\n"
    md += "| Band | kWh | Rate (GHS/kWh) | Amount |\n|---|---:|---:|---:|\n"
    for b in r["expected"]["bands"]:
        md += f"| {b['label']} | {b['kwh']:,.2f} | {b['rate']:.4f} | {sym}{b['amount']:,.2f} |\n"
    md += "\n## Solar Offset Recommendation\n\n| Item | Value |\n|---|---|\n"
    md += f"| Target Reduction | {r['solar']['target_reduction_pct']:.0f}% |\n"
    md += f"| Target kWh Offset / month | {r['solar']['target_kwh_offset']:,.2f} |\n"
    md += f"| Daily kWh Offset | {r['solar']['daily_kwh_offset']:,.2f} |\n"
    md += f"| Peak Sun Hours | {r['solar']['peak_sun_hours']} |\n"
    md += f"| System Efficiency | {r['solar']['system_efficiency']:.0%} |\n"
    md += f"| Computed kWp | {r['solar']['computed_kwp']:,.2f} |\n"
    md += f"| Recommended System Size | **{r['solar']['recommended_kwp']:,.1f} kWp** |\n"
    md += f"| Estimated Monthly Saving | {sym}{r['solar']['estimated_monthly_saving']:,.2f} |\n"
    md += "\n## Loan Support\n\n"
    md += f"- System cost @ {sym}{r['loan']['cost_per_kwp']:,.0f}/kWp = {sym}{r['loan']['system_cost']:,.2f}\n"
    md += f"- Loan: {r['loan']['years']:.0f} years @ {r['loan']['interest_pct']:.1f}% interest\n"
    md += f"- Estimated monthly repayment: {sym}{r['loan']['estimated_monthly_payment']:,.2f}\n"
    md += f"- {r['loan']['message']}\n\n"
    md += "## Important notes\n\n"
    md += "- The expected PURC bill is the **energy charge + service charge only**. Levies (NHIL, GETFL, VAT, street-light) typically add a further ~17.5% on top of the energy charge.\n"
    md += "- Use careful language: a difference is *potential* until the meter reading and tariff classification are verified.\n"
    md += f"- Lifeline (GHS {GHANA_PURC_TARIFFS['Residential Lifeline (≤ 30 kWh/month)']['rate_ghc']:.4f}/kWh) is a customer class, not a band — it applies only when total monthly use is at or below 30 kWh.\n"
    md += f"- Tariff source: {r['tariff_meta']['source_title']} ({r['tariff_meta']['source_url']}).\n"
    try:
        _log_marketplace_action("bill_check_report_generated", "project", pid, "pdf")
    except Exception:
        pass
    return _render_pdf("Bill Check Report", md, f"bill_check_project_{pid}.pdf")


@app.route("/api/bill-check/lead", methods=["POST"])
@limiter.limit("10 per hour")
def bill_check_lead():
    """Anon lead capture from the bill-check modal. source='Electricity Bill Check'."""
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    name    = (payload.get("name") or "").strip()
    email   = (payload.get("email") or "").strip()
    phone   = (payload.get("phone") or "").strip()
    country = (payload.get("country") or "Ghana").strip()
    message = (payload.get("message") or "Bill check completed; user requested follow-up.").strip()
    if not name or not email:
        return jsonify({"error": "name and email required"}), 400
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO leads (name,email,phone,company,country,interest,message,source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (name, email, phone, "", country, "residential", message, "Electricity Bill Check"))
        try:
            _log_marketplace_action("bill_check_lead_created", "lead", 0, f"email={email}")
        except Exception:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": "could not record lead", "detail": str(e)}), 500


