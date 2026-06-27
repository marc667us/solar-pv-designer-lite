# ─── Check My Electricity Bill — funding workflow + share + email ─────────────
# Phase C (2026-06-27): reframe around the funding pitch and add export/email/
# invite routes so users can:
#   1. See clearly what slice of their current bill funds a solar loan
#   2. See proportional bill drop during and after the loan
#   3. Export PDF (anon AND project flow)
#   4. Email themselves a copy
#   5. Invite friends with a pre-filled try-it link

import base64

def _bc_funding_model(bill_check_result):
    """Augment a _bc_compute() result with a "fund solar from your bill" block.

    Returns a dict ready to merge into the result, keys under 'funding'.
    """
    r = bill_check_result
    bill          = float(r.get("actual_bill") or 0)
    loan_payment  = float(r["loan"].get("estimated_monthly_payment") or 0)
    monthly_save  = float(r["solar"].get("estimated_monthly_saving") or 0)
    target_pct    = float(r["solar"].get("target_reduction_pct") or 0)
    rec_kwp       = float(r["solar"].get("recommended_kwp") or 0)
    cost_per_kwp  = float(r["loan"].get("cost_per_kwp") or 0)
    loan_years    = float(r["loan"].get("years") or 0)
    sys_cost      = rec_kwp * cost_per_kwp

    # Slice of current bill that the loan payment represents
    portion_pct = (loan_payment / bill * 100.0) if bill > 0 else 0.0
    # During the loan: residual grid bill (what stays after solar offsets)
    residual_bill = max(0.0, bill - monthly_save)
    combined_outlay = residual_bill + loan_payment
    net_change_pct = ((combined_outlay - bill) / bill * 100.0) if bill > 0 else 0.0
    # After loan: only residual bill remains
    post_loan_drop_pct = (monthly_save / bill * 100.0) if bill > 0 else 0.0
    annual_save = monthly_save * 12
    simple_payback_years = (sys_cost / annual_save) if annual_save > 0 else 0.0
    # 25-year lifetime savings (no escalation, simple)
    lifetime_save = max(0.0, monthly_save * 12 * 25 - sys_cost)

    # Headline pitch
    if combined_outlay <= bill and loan_payment > 0:
        pitch = (f"Use about {portion_pct:.0f}% of your current monthly bill "
                 f"(~GHS {loan_payment:,.0f}) to repay a {rec_kwp:,.1f} kWp solar "
                 f"loan. During the {loan_years:.0f}-year loan you stay around "
                 f"the same monthly outlay; after the loan ends your bill drops "
                 f"by {post_loan_drop_pct:.0f}% and you save GHS "
                 f"{monthly_save:,.0f}/month for the rest of the 25-year system life.")
    elif loan_payment > 0:
        pitch = (f"A {rec_kwp:,.1f} kWp system at GHS {cost_per_kwp:,.0f}/kWp "
                 f"costs about GHS {loan_payment:,.0f}/mo on a {loan_years:.0f}-year "
                 f"loan — that's around GHS {(combined_outlay - bill):,.0f}/mo more "
                 f"than your bill today. After the loan your bill drops by "
                 f"{post_loan_drop_pct:.0f}% (GHS {monthly_save:,.0f}/month saving).")
    else:
        pitch = ("Enter your bill and loan inputs to see how much of your monthly "
                 "outlay can fund solar.")

    return {
        "headline_pitch":            pitch,
        "current_bill":              round(bill, 2),
        "monthly_loan_payment":      round(loan_payment, 2),
        "portion_of_bill_pct":       round(portion_pct, 2),
        "residual_bill_during_loan": round(residual_bill, 2),
        "combined_outlay":           round(combined_outlay, 2),
        "net_change_pct":            round(net_change_pct, 2),
        "post_loan_monthly_bill":    round(residual_bill, 2),
        "post_loan_drop_pct":        round(post_loan_drop_pct, 2),
        "monthly_saving":            round(monthly_save, 2),
        "annual_saving":             round(annual_save, 2),
        "system_cost":               round(sys_cost, 2),
        "simple_payback_years":      round(simple_payback_years, 2),
        "lifetime_saving_25yr":      round(lifetime_save, 2),
        "recommended_kwp":           rec_kwp,
        "feasible":                  bool(loan_payment > 0 and combined_outlay <= bill),
    }


def _bc_recommendations(r, funding):
    """Return a list of plain-language recommendation strings."""
    recs = []
    bill = r.get("actual_bill") or 0
    target_pct = r["solar"].get("target_reduction_pct") or 0
    if bill <= 0:
        recs.append("Enter your actual monthly bill amount so we can size the funding model.")
        return recs

    if funding["feasible"]:
        recs.append(
            f"Switch GHS {funding['monthly_loan_payment']:,.0f}/month of your current bill "
            f"into a solar loan repayment. Your total monthly outlay stays at about "
            f"GHS {funding['combined_outlay']:,.0f} for {r['loan']['years']:.0f} years."
        )
        recs.append(
            f"After the loan ends, your monthly bill drops to about "
            f"GHS {funding['post_loan_monthly_bill']:,.0f} — that's a "
            f"{funding['post_loan_drop_pct']:.0f}% permanent reduction worth "
            f"GHS {funding['annual_saving']:,.0f}/year for the rest of the 25-year system life."
        )
    elif funding["monthly_loan_payment"] > 0:
        recs.append(
            f"At GHS {r['loan']['cost_per_kwp']:,.0f}/kWp the loan repayment is "
            f"~GHS {funding['monthly_loan_payment']:,.0f}/mo — about GHS "
            f"{abs(funding['combined_outlay'] - bill):,.0f}/mo over your current bill during the "
            f"loan. Consider: a lower target reduction (try {max(30, int(target_pct)-20)}%), "
            f"a longer loan term, a higher deposit, or a smaller system."
        )

    if r["confidence"] == "low":
        recs.append(
            "Your load schedule looks incomplete — add active loads (AC, fridges, pumps, "
            "water heaters, external lights) so the funding model uses the right monthly kWh."
        )
    elif r["confidence"] == "medium":
        recs.append(
            "Confirm refrigerators, pumps, water heaters and external lights are in your load list "
            "so the funding model is accurate."
        )

    if r.get("difference_pct") is not None and r["difference_pct"] > 25:
        recs.append(
            "Your actual bill is materially higher than the PURC energy charge for this consumption. "
            "Check your ECG receipt for levies, arrears, tariff classification, and confirm the meter "
            "reading before assuming overcharge."
        )

    recs.append(
        "Next step: open the full solar design wizard — we'll size panels/inverter/battery for the "
        f"{funding['recommended_kwp']:,.1f} kWp target and generate the engineering pack."
    )
    return recs


def _bc_share_payload_encode(payload):
    """Encode a sanitised bill-check payload to a URL-safe base64 string."""
    safe = {
        "actual_bill":          float(payload.get("actual_bill") or 0),
        "actual_kwh":           float(payload["actual_kwh"]) if payload.get("actual_kwh") not in (None, "") else None,
        "category":             payload.get("category") or "Residential Standard (0-300 kWh/month)",
        "meter_type":           payload.get("meter_type") or "postpaid",
        "completeness":         payload.get("completeness") or "unsure",
        "target_reduction_pct": float(payload.get("target_reduction_pct") or 50),
        "system_cost_per_kwp":  float(payload.get("system_cost_per_kwp") or 8000),
        "loan_years":           float(payload.get("loan_years") or 5),
        "loan_interest_pct":    float(payload.get("loan_interest_pct") or 22),
    }
    raw = json.dumps(safe, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _bc_share_payload_decode(token):
    """Reverse of _bc_share_payload_encode. Returns {} on failure."""
    if not token:
        return {}
    try:
        pad = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + pad).encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _bc_render_pdf_bytes(title, md_content):
    """Render markdown → PDF bytes (no Flask response). Same CSS as _render_pdf."""
    from markdown_pdf import MarkdownPdf, Section
    CSS = """
    @page { size: A4 portrait; margin: 12mm 10mm 14mm 10mm; }
    body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;font-size:10pt;line-height:1.45}
    h1{color:#b45309;font-size:16pt;border-bottom:3px solid #f59e0b;padding-bottom:6px;margin-bottom:10px}
    h2{color:#1e3a8a;font-size:12pt;border-bottom:1px solid #bfdbfe;padding-bottom:3px;margin-top:14px}
    h3{color:#374151;font-size:10.5pt;margin-top:10px}
    table{width:100%;border-collapse:collapse;margin:8px 0;font-size:9pt;border:1.2pt solid #000}
    th{background:#1e3a5f;color:#fff;padding:5px 7px;text-align:left;border:1px solid #000}
    td{border:1px solid #000;padding:4px 7px;vertical-align:top}
    tr:nth-child(even) td{background:#f5f7fb}
    blockquote{background:#fffbeb;border-left:4px solid #f59e0b;padding:8px 12px;margin:6px 0;border-radius:3px}
    p{margin:4px 0}
    hr{border:none;border-top:1px solid #444;margin:10px 0}
    """
    pdf = MarkdownPdf(toc_level=2)
    pdf.meta.update({"title": title, "author": "SolarPro Global", "subject": title})
    parts = md_content.split("\n# ")
    pdf.add_section(Section(parts[0], toc=False), user_css=CSS)
    for part in parts[1:]:
        pdf.add_section(Section("# " + part, toc=True), user_css=CSS)
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def _bc_build_report_markdown(result, share_url=None, contact_email=None):
    """Build the funding-model-led markdown report shared by PDF / email."""
    f = result.get("funding") or {}
    sym = "GHS "
    md  = "# Use Your Bill to Fund Solar — SolarPro Global Report\n\n"
    md += f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    md += f"PURC tariff effective {result['tariff_meta']['effective_from']}*\n\n"

    md += "## The Pitch\n\n"
    md += f"> {f.get('headline_pitch','') or 'Enter your bill and loan inputs to see the funding model.'}\n\n"

    md += "## Funding Model — At A Glance\n\n"
    md += "| | Today | During the loan | After the loan |\n|---|---:|---:|---:|\n"
    md += (f"| **Monthly grid bill** | {sym}{f.get('current_bill',0):,.0f} "
           f"| {sym}{f.get('residual_bill_during_loan',0):,.0f} "
           f"| {sym}{f.get('post_loan_monthly_bill',0):,.0f} |\n")
    md += (f"| **Solar loan repayment** | — "
           f"| {sym}{f.get('monthly_loan_payment',0):,.0f} | — |\n")
    md += (f"| **Total monthly outlay** | {sym}{f.get('current_bill',0):,.0f} "
           f"| {sym}{f.get('combined_outlay',0):,.0f} "
           f"| {sym}{f.get('post_loan_monthly_bill',0):,.0f} |\n")
    md += (f"| **vs today** | — | "
           f"{f.get('net_change_pct',0):+.1f}% | "
           f"−{f.get('post_loan_drop_pct',0):.1f}% |\n\n")

    md += "## What You're Funding\n\n"
    md += "| Item | Value |\n|---|---|\n"
    md += f"| Recommended system size | **{f.get('recommended_kwp',0):,.1f} kWp** |\n"
    md += f"| System cost (indicative) | {sym}{f.get('system_cost',0):,.0f} |\n"
    md += f"| Loan term | {result['loan']['years']:.0f} years @ {result['loan']['interest_pct']:.1f}% interest |\n"
    md += f"| Monthly loan repayment | {sym}{f.get('monthly_loan_payment',0):,.0f} ({f.get('portion_of_bill_pct',0):.0f}% of your current bill) |\n"
    md += f"| Monthly saving from solar offset | {sym}{f.get('monthly_saving',0):,.0f} |\n"
    md += f"| Annual saving | {sym}{f.get('annual_saving',0):,.0f} |\n"
    md += f"| Simple payback | {f.get('simple_payback_years',0):,.1f} years |\n"
    md += f"| 25-year net saving | {sym}{f.get('lifetime_saving_25yr',0):,.0f} |\n\n"

    md += "## Recommendations\n\n"
    for rec in (result.get("recommendations") or []):
        md += f"- {rec}\n"
    md += "\n"

    md += "# Bill Audit Detail\n\n"
    md += "## Summary\n\n| Item | Value |\n|---|---|\n"
    md += f"| Customer Category | {result['expected']['category_applied']} |\n"
    md += f"| Meter Type | {result['inputs']['meter_type'].title()} |\n"
    md += f"| Load Schedule Completeness | {result['inputs']['completeness']} |\n"
    md += f"| Confidence Level | {result['confidence'].upper()} |\n"
    md += f"| Estimated Monthly kWh | {result['energy']['monthly_kwh']:,.2f} |\n"
    md += f"| Expected PURC Energy Charge | {sym}{result['expected']['energy']:,.2f} |\n"
    md += f"| Service Charge | {sym}{result['expected']['service']:,.2f} |\n"
    md += f"| Expected PURC Bill (energy + service) | {sym}{result['expected']['total']:,.2f} |\n"
    md += f"| Actual Bill | {sym}{result['actual_bill']:,.2f} |\n"
    if result.get("difference") is not None:
        md += f"| Difference (Actual − Expected) | {sym}{result['difference']:,.2f} ({result['difference_pct']:+.2f}%) |\n"
    if result.get("effective_tariff") is not None:
        md += f"| Effective Tariff | {sym}{result['effective_tariff']:.4f}/kWh |\n"
    md += "\n## Status\n\n"
    md += f"> {result['status_label']}\n\n"
    md += f"**Confidence note:** {result['confidence_message']}\n\n"

    md += "## PURC Band Breakdown\n\n"
    md += "| Band | kWh | Rate (GHS/kWh) | Amount |\n|---|---:|---:|---:|\n"
    for b in result["expected"]["bands"]:
        md += f"| {b['label']} | {b['kwh']:,.2f} | {b['rate']:.4f} | {sym}{b['amount']:,.2f} |\n"

    md += "\n# Share This Result\n\n"
    if share_url:
        md += f"**Anyone can run their own check** at this prefilled link: {share_url}\n\n"
    md += ("Forward this PDF to a friend — they'll see the same comparison for their own "
           "bill in under 60 seconds. SolarPro Global is free to use; no signup required for "
           "the bill check.\n\n")

    md += "## Important Notes\n\n"
    md += ("- Expected PURC bill is the **energy charge + service charge only**. Levies "
           "(NHIL, GETFL, VAT, street-light) typically add ~17.5% on top of the energy charge.\n")
    md += ("- Lifeline (GHS 0.8690/kWh) is a customer *class*, not a band — it applies only "
           "when total monthly use is at or below 30 kWh.\n")
    md += ("- The funding model uses simple-interest amortisation and a 25-year flat-saving "
           "horizon; real savings depend on PURC tariff escalation (~8%/yr historic) and "
           "system performance (-0.5%/yr typical degradation).\n")
    md += f"- Tariff source: {result['tariff_meta']['source_title']} ({result['tariff_meta']['source_url']}).\n"
    if contact_email:
        md += f"- This report was generated for {contact_email}.\n"
    return md


def _bc_enrich(result):
    """Add funding + recommendations to a base _bc_compute() result, in place."""
    funding = _bc_funding_model(result)
    result["funding"] = funding
    result["recommendations"] = _bc_recommendations(result, funding)
    return result


def _bc_share_url(payload):
    """Build a 'Try it yourself' URL with the payload prefilled."""
    token = _bc_share_payload_encode(payload)
    try:
        return url_for("bill_check_landing", b=token, _external=True)
    except Exception:
        return "/bill-check?b=" + token


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/bill-check")
@limiter.limit("60 per minute")
def bill_check_landing():
    """Public landing page for the bill-check tool. Accepts ?b=<token> to prefill."""
    token = request.args.get("b", "")
    prefill = _bc_share_payload_decode(token) if token else {}
    return render_template("bill_check_landing.html",
                           user=current_user(),
                           prefill=prefill,
                           prefill_token=token)


@app.route("/api/bill-check/report.pdf", methods=["POST"])
@limiter.limit("30 per hour")
def bill_check_report_anon():
    """Anon PDF download — no project required."""
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    loads = payload["loads"] if isinstance(payload.get("loads"), list) else None
    try:
        result = _bc_enrich(_bc_compute(payload, loads=loads))
    except Exception as e:
        return jsonify({"error": "computation failed", "detail": str(e)}), 400
    share = _bc_share_url(payload)
    md = _bc_build_report_markdown(result, share_url=share)
    try:
        _log_marketplace_action("bill_check_report_anon", "lead", 0, "anon PDF download")
    except Exception:
        pass
    return _render_pdf("Bill Check Report — Fund Solar From Your Bill",
                       md, "bill_check_report.pdf")


@app.route("/api/bill-check/email", methods=["POST"])
@limiter.limit("10 per hour")
def bill_check_email():
    """Email the bill-check report PDF to the user. Body: {email, name, ...payload}."""
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    to_email = (payload.get("email") or "").strip()
    to_name  = (payload.get("name")  or "").strip() or "there"
    if not to_email or "@" not in to_email:
        return jsonify({"error": "valid email required"}), 400
    loads = payload["loads"] if isinstance(payload.get("loads"), list) else None
    try:
        result = _bc_enrich(_bc_compute(payload, loads=loads))
    except Exception as e:
        return jsonify({"error": "computation failed", "detail": str(e)}), 400
    share = _bc_share_url(payload)
    md = _bc_build_report_markdown(result, share_url=share, contact_email=to_email)
    try:
        pdf_bytes = _bc_render_pdf_bytes("Bill Check Report — Fund Solar From Your Bill", md)
    except Exception as e:
        return jsonify({"error": "pdf render failed", "detail": str(e)}), 500

    f = result.get("funding") or {}
    bill = f.get("current_bill", 0)
    portion = f.get("portion_of_bill_pct", 0)
    drop = f.get("post_loan_drop_pct", 0)
    kwp = f.get("recommended_kwp", 0)
    saving = f.get("monthly_saving", 0)
    subject = f"Your SolarPro report — fund a {kwp:,.1f} kWp system from your bill"
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:600px;margin:auto;color:#1a1a2e">
      <div style="background:#1e1e3a;color:#fbbf24;padding:18px 22px;border-radius:6px 6px 0 0">
        <div style="font-size:11px;letter-spacing:1.5px;font-weight:900;text-transform:uppercase">SolarPro Global</div>
        <h2 style="margin:6px 0 0;font-size:20px">Hi {to_name}, your Bill Check report is attached</h2>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:22px;border-radius:0 0 6px 6px">
        <p>Here&apos;s the short version:</p>
        <ul>
          <li><strong>Use ~{portion:.0f}% of your current monthly bill</strong> to repay a {kwp:,.1f} kWp solar loan.</li>
          <li><strong>After the loan ends, your bill drops by {drop:.0f}%</strong> — saving GHS {saving:,.0f}/month for the rest of the 25-year system life.</li>
          <li>Full numbers, PURC band breakdown, and recommendations are in the PDF.</li>
        </ul>
        <p style="margin:18px 0 6px"><strong>Want a friend to see this?</strong></p>
        <p style="margin:0">Forward this email, or send them the prefilled link:<br>
          <a href="{share}" style="color:#b45309">{share}</a>
        </p>
        <p style="margin:20px 0 6px;font-size:12px;color:#6b7280">
          The numbers in this report use PURC&apos;s Q2 2026 tariff schedule (effective 2026-04-01)
          and a simple loan amortisation. Real savings depend on tariff escalation and system performance.
        </p>
      </div>
    </div>
    """
    text_body = (
        f"Hi {to_name},\n\nYour SolarPro Bill Check report is attached.\n\n"
        f"Short version:\n"
        f"- Use about {portion:.0f}% of your current monthly bill to repay a {kwp:.1f} kWp solar loan.\n"
        f"- After the loan ends your bill drops by {drop:.0f}% (GHS {saving:,.0f}/mo saving).\n\n"
        f"Forward this report to a friend or share this prefilled link:\n{share}\n\n"
        f"— SolarPro Global · https://solarpro.aiappinvent.com\n"
    )
    try:
        ok = _send_email(
            to_email, subject, html, text_body=text_body,
            attachments=[("bill_check_report.pdf", pdf_bytes, "application/pdf")]
        )
    except Exception as e:
        return jsonify({"error": "email send failed", "detail": str(e)}), 500
    if not ok:
        return jsonify({"error": "email backend rejected the send (check SMTP/Resend config)"}), 500
    try:
        _log_marketplace_action("bill_check_emailed", "lead", 0, f"to={to_email}")
    except Exception:
        pass
    # Also drop a lead row so sales sees the engagement
    try:
        with get_db() as c:
            c.execute(
                "INSERT INTO leads (name,email,phone,company,country,interest,message,source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (to_name if to_name != "there" else "",
                 to_email, "", "", payload.get("country") or "Ghana",
                 "residential",
                 f"Bill check report emailed. Bill {bill:.0f}, kWp {kwp:.1f}, drop {drop:.0f}%.",
                 "Electricity Bill Check — emailed report"))
    except Exception:
        pass
    return jsonify({"ok": True, "share_url": share})


@app.route("/api/bill-check/invite", methods=["POST"])
@limiter.limit("5 per hour")
def bill_check_invite():
    """Viral invite: short email to up to 5 friends with a try-it-yourself link.

    Body: {sender_name, sender_email?, recipients: [..], ...bill check payload}.
    """
    csrf_protect()
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    sender_name = (payload.get("sender_name") or "").strip() or "A friend"
    sender_email= (payload.get("sender_email") or "").strip()
    raw_recips  = payload.get("recipients") or []
    if isinstance(raw_recips, str):
        raw_recips = [r.strip() for r in raw_recips.replace(",", " ").split() if r.strip()]
    recips = [r for r in raw_recips if "@" in r][:5]
    if not recips:
        return jsonify({"error": "at least one recipient email required"}), 400

    try:
        result = _bc_enrich(_bc_compute(payload, loads=None))
    except Exception:
        result = None
    share = _bc_share_url(payload)
    f = (result or {}).get("funding") or {}
    drop = f.get("post_loan_drop_pct", 0)
    kwp = f.get("recommended_kwp", 0)
    sent = []
    failed = []
    for to_email in recips:
        subject = f"{sender_name} thought you'd want to check your ECG bill (60-second tool)"
        html = f"""
        <div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:auto;color:#1a1a2e">
          <div style="background:#fbbf24;color:#1e1e3a;padding:14px 18px;border-radius:6px 6px 0 0">
            <strong>SolarPro Global · 60-second bill check</strong>
          </div>
          <div style="border:1px solid #e5e7eb;border-top:none;padding:20px;border-radius:0 0 6px 6px">
            <p>{sender_name} just checked their electricity bill against the PURC Q2 2026 tariff and figured out how much of their bill could fund a solar system.</p>
            {('<p>For their numbers: about a <strong>' + str(int(round(kwp))) + ' kWp</strong> system would drop their bill by <strong>' + str(int(round(drop))) + '%</strong> after the loan ends.</p>') if kwp and drop else ''}
            <p style="margin:18px 0"><a href="{share}" style="background:#1e1e3a;color:#fbbf24;padding:10px 18px;border-radius:4px;text-decoration:none;font-weight:700">Run it for your own bill →</a></p>
            <p style="font-size:12px;color:#6b7280">No signup needed. Free. Open in your browser:<br>{share}</p>
          </div>
        </div>
        """
        text_body = (
            f"{sender_name} just ran their ECG bill through SolarPro's 60-second bill check.\n\n"
            f"Run yours here (no signup needed):\n{share}\n\n"
            "— SolarPro Global\n"
        )
        try:
            ok = _send_email(to_email, subject, html, text_body=text_body)
            (sent if ok else failed).append(to_email)
        except Exception:
            failed.append(to_email)
    try:
        _log_marketplace_action("bill_check_invite_sent", "lead", 0,
                                f"sender={sender_email or 'anon'} sent={len(sent)} failed={len(failed)}")
    except Exception:
        pass
    # Drop a lead row for the sender too — they engaged enough to invite friends
    if sender_email and "@" in sender_email:
        try:
            with get_db() as c:
                c.execute(
                    "INSERT INTO leads (name,email,phone,company,country,interest,message,source) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (sender_name, sender_email, "", "",
                     payload.get("country") or "Ghana", "residential",
                     f"Invited {len(sent)} friend(s) via bill-check share.",
                     "Electricity Bill Check — viral invite"))
        except Exception:
            pass
    return jsonify({"ok": True, "sent": sent, "failed": failed, "share_url": share})


# Augment the existing /api/bill-check + project save/report routes by wrapping
# their compute output with the funding model. The original routes already
# call _bc_compute; we monkey-patch by aliasing the function name to a wrapper
# that runs _bc_enrich on the result. Importantly, this preserves the prior
# response shape — it only ADDS keys ('funding', 'recommendations').
_bc_compute_raw = _bc_compute  # noqa: F821 - defined in earlier block


def _bc_compute(payload, loads=None):  # noqa: F811 - intentional override
    return _bc_enrich(_bc_compute_raw(payload, loads=loads))


