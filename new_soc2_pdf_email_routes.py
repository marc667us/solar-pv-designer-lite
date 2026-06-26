# ─── SOC 2 readiness report — PDF + email + AICPA markdown ──────────────────
# Added 2026-06-25 alongside the SOC 2 batch RLS work. Layers three things on
# top of the existing /admin/soc2/report HTML page:
#
#   1. _soc2_make_aicpa_markdown(report) -> str
#      Builds a full AICPA-SSAE-18-style markdown document with the six
#      canonical sections (Cover, Management's Assertion, System
#      Description, Trust Services Criteria, Description of Controls +
#      Test Results, Other Information).
#
#   2. GET /admin/soc2/report.pdf
#      Renders the markdown via the existing _render_pdf helper and
#      returns it as an attachment.
#
#   3. POST /admin/soc2/report/email
#      Renders the PDF to bytes and sends via the existing _send_email
#      Brevo->SMTP chain with the PDF attached.
#
# All three are admin-only + audit-logged.


def _soc2_make_aicpa_markdown(report):
    """Format the SOC 2 readiness report dict as AICPA SSAE-18 style markdown.

    Layout follows the six canonical sections of a SOC 2 report so the
    output is recognizable to an external SSAE 18 auditor:
      I.   Cover Page
      II.  Management's Assertion
      III. Description of the Service Organization's System
      IV.  Trust Services Categories
      V.   Description of Controls + Test Results
      VI.  Other Information

    Returns a markdown string ready for _render_pdf().
    """
    generated_at = report.get("generated_at", "")
    score        = report.get("score", 0.0)
    counts       = report.get("counts", {})
    findings     = report.get("findings", [])
    version      = report.get("version", "1.0")

    # Map each finding label to one or more Trust Services Criteria so the
    # report can show TSC coverage. Best-effort heuristic — extend as more
    # checks land.
    TSC_MAP = {
        "M1.1": "CC6.1 Logical access controls",
        "M1.2": "CC6.6 Multi-factor authentication",
        "M1.3": "CC6.7 Authentication credentials managed",
        "M1.4": "CC6.3 Role-based access",
        "M1.5": "CC3.2 Data inventory",
        "M1.6": "CC6.1 Logical access; CC6.7 Data restricted by policy",
        "M1.7": "CC7.2 System monitoring",
        "M1.8": "CC6.2 Authentication session managed",
        "M1.9": "CC2.1 Information for risk assessment",
        "M2.6": "CC6.1 Logical access controls",
        "M2.7": "CC6.7 Data protection (CSRF)",
        "M3.1": "CC7.2 Monitoring of events; CC6.7 Data restricted",
        "M3.3": "CC7.2 System monitoring",
        "M3.5": "CC7.3 Evaluation of security events",
        "M3.7": "CC7.1 Vulnerability scanning",
        "M3.10": "CC4.1 Monitoring activities (testing)",
        "M4.1": "A1.2 Data backup and recovery",
        "M4.5": "CC2.2 Internal communication of policies",
        "M4.6": "CC4.1 Monitoring activities (evidence)",
    }

    def tsc_for(label):
        for prefix, tsc in TSC_MAP.items():
            if label.lstrip().startswith(prefix):
                return tsc
        return "Mapped to control objectives (general)"

    score_band = "Excellent" if score >= 90 else \
                 "Good"      if score >= 75 else \
                 "Acceptable" if score >= 60 else \
                 "Marginal"  if score >= 40 else "Below threshold"

    md  = ""
    md += "# SOC 2 READINESS REPORT\n\n"
    md += "## SolarPro Global Platform\n\n"
    md += f"**Report Type:** Internal Readiness Assessment (Pre-Audit)\n\n"
    md += f"**Reporting Period:** Point-in-time assessment as of {generated_at}\n\n"
    md += f"**Trust Services Categories Covered:** Security (CC), Availability (A1), Confidentiality (C1)\n\n"
    md += f"**Audit Engine Version:** {version}\n\n"
    md += "**Prepared by:** Internal SOC 2 Compliance Function (self-assessment)\n\n"
    md += "---\n\n"
    md += "**Important Notice.** This is an internal readiness report produced by automated controls introspection of the live application and database. It is NOT an SSAE 18 audited report; an external Service Auditor is required to issue an attestation. This report is intended for management review and pre-audit gap remediation.\n\n"
    md += "---\n\n"
    md += f"### Executive summary\n\n"
    md += f"- Overall readiness score: **{score:.1f}%** ({score_band})\n"
    md += f"- Controls passing: **{counts.get('pass', 0)}**\n"
    md += f"- Controls with warnings: **{counts.get('warn', 0)}**\n"
    md += f"- Controls failing: **{counts.get('fail', 0)}**\n"
    md += f"- Total controls tested: **{len(findings)}**\n\n"

    # ─── Section I: Management's Assertion ─────────────────────────────
    md += "# I. Management's Assertion\n\n"
    md += "Management of SolarPro Global is responsible for:\n\n"
    md += "1. **Designing, implementing, and operating** the controls described in this report to provide reasonable assurance that the service commitments to user entities and the applicable Trust Services Criteria are met.\n\n"
    md += "2. **Maintaining the security, availability, and confidentiality** of the customer data processed by the SolarPro Global platform.\n\n"
    md += "3. **Selecting the Trust Services Criteria** that are the basis for management's assertion. The criteria selected are the AICPA Trust Services Criteria for Security, Availability, and Confidentiality (2017, with revisions effective for periods ending on or after December 15, 2018).\n\n"
    md += "Based on the controls described and tested in Sections IV and V of this report, management asserts that the controls were **suitably designed** as of the reporting date. The effectiveness of operation over a reporting period of 6+ months will be established by an external Service Auditor in a future Type II engagement.\n\n"

    # ─── Section II: System Description ────────────────────────────────
    md += "# II. Description of the Service Organization's System\n\n"
    md += "## A. Services Provided\n\n"
    md += "SolarPro Global is a Software-as-a-Service platform that supports:\n\n"
    md += "- Engineering design of residential, commercial, and industrial photovoltaic (PV) solar power systems\n"
    md += "- Bills of Materials (BOM) and Bills of Quantities (BOQ) generation with hierarchical project/building/floor structures\n"
    md += "- Multi-vendor Marketplace for equipment procurement, including Requests for Quotation (RFQ) and price-sheet management\n"
    md += "- Multi-tenant project workspace with role-based access (admin, owner, technical, sales, supplier, procurement specialist)\n"
    md += "- Automated proposal generation and customer-facing collateral export (PDF, Excel)\n\n"
    md += "## B. Principal Service Commitments and System Requirements\n\n"
    md += "1. **Confidentiality** of customer designs, BOMs, BOQs, and pricing intelligence within the tenant boundary.\n"
    md += "2. **Availability** of the SaaS platform to enable engineering workflows during reasonable business hours.\n"
    md += "3. **Integrity** of engineering calculations, financial computations (BOM rate buildups), and audit trails.\n"
    md += "4. **Compliance** with applicable contractual data-protection obligations toward user entities.\n\n"
    md += "## C. Components of the System\n\n"
    md += "### Infrastructure\n\n"
    md += "- **Compute:** Render PaaS (production), shared with Cloudflared local-development tunnel.\n"
    md += "- **Database:** Render-managed PostgreSQL (production); SQLite (developer workstations only).\n"
    md += "- **Identity Provider:** Keycloak (auth.aiappinvent.com) — single source of truth for authentication and role assignment.\n"
    md += "- **CDN / Tunneling:** Cloudflare DNS + tunnel for developer environments.\n"
    md += "- **Object Storage:** None today; designs are stored as JSON blobs in the database.\n\n"
    md += "### Software\n\n"
    md += "- **Application:** Python 3.12 + Flask + Waitress (dev) / Gunicorn (prod).\n"
    md += "- **Authentication library:** Authlib OIDC client; PyJWT for token validation; JWKS cached.\n"
    md += "- **Data layer:** psycopg2 (Postgres) and sqlite3 (dev); Row Level Security policies on tenant-owned tables.\n"
    md += "- **Document generation:** markdown-pdf (Python) for proposals, BOMs, BOQs, this report.\n"
    md += "- **Email:** Brevo HTTPS API (primary) -> SMTP (last resort).\n"
    md += "- **CI/CD:** GitHub Actions (semgrep + pip-audit + bandit + gitleaks security CI; gated migration workflows).\n\n"
    md += "### People\n\n"
    md += "- Service Organization Owner (founder; CEO equivalent) — accountable for security, availability, and confidentiality.\n"
    md += "- Software Engineering function — implements features, fixes defects, runs change management.\n"
    md += "- Internal SOC 2 Compliance function — owns this report, the implementation plan, and policy maintenance.\n"
    md += "- (No on-call rotation today — paging cadence is best-effort; documented in `docs/policies/` as a known gap pending external audit.)\n\n"
    md += "### Procedures\n\n"
    md += "- **Change management:** All code changes flow through Git pull requests on the master branch with GitHub Actions security CI; production database migrations are gated workflows requiring explicit confirm tokens (e.g. `BATCH5_RLS_APPLY`).\n"
    md += "- **Access management:** Identity proofing via Keycloak; role assignment via 20+ realm roles; periodic access review is documented as a control objective pending operationalization.\n"
    md += "- **Incident response:** Documented in `docs/policies/incident_response.md`; live error tracker at `/admin/errors`.\n"
    md += "- **Backup and recovery:** Nightly Postgres pg_dump via `backup-postgres.yml` GitHub Actions workflow (03:00 UTC).\n"
    md += "- **Evidence collection:** Nightly SOC 2 evidence collector via `soc2-evidence.yml` (03:30 UTC).\n\n"
    md += "### Data\n\n"
    md += "- **Customer data:** Project specifications, location data, energy load profiles, equipment selections, BOMs, BOQs, RFQs, supplier responses, proposals, financial calculations.\n"
    md += "- **Operational data:** Audit logs, error logs, security logs (login failures, denial events), tenant-context observability.\n"
    md += "- **Reference data:** Equipment catalog, supplier directory, product taxonomy, appliance library — system-wide (multi-tenant readable).\n\n"
    md += "## D. Boundaries of the System\n\n"
    md += "The SOC 2 reporting boundary includes:\n\n"
    md += "- The SolarPro Global Flask web application running on Render.\n"
    md += "- The Render-managed PostgreSQL database (`solarpro-postgres`).\n"
    md += "- The Keycloak identity provider running on Render (`solarpro-keycloak`).\n"
    md += "- The GitHub repository (`marc667us/solar-pv-designer-lite`) and its automated workflows.\n\n"
    md += "Excluded from the boundary (subservice organizations — carved out):\n\n"
    md += "- **Render PaaS** (infrastructure host).\n"
    md += "- **Brevo** (transactional email sender).\n"
    md += "- **Paystack** and **Stripe** (payment processors).\n"
    md += "- **Cloudflare** (DNS, tunneling).\n"
    md += "- **OpenRouter / Ollama / GitHub Models** (AI inference providers).\n\n"
    md += "User entities are responsible for: managing their own Keycloak credentials, exercising their tenant role permissions appropriately, and notifying SolarPro of any suspected security incident impacting their account.\n\n"
    md += "## E. Identified Risks and Mitigations\n\n"
    md += "| Risk | Mitigation |\n"
    md += "|---|---|\n"
    md += "| Unauthorized cross-tenant data access | Postgres Row Level Security policies; `tenant_id` columns on tenant-owned tables; tenant context request hooks (M1.7). |\n"
    md += "| Authentication compromise | Keycloak OIDC + PKCE S256; 14-day rollback window via the `Rollback From Keycloak` workflow; MFA proposal (M1.2) drafted. |\n"
    md += "| Data integrity / orphan rows | FOREIGN KEY constraints across owned-child and user-owned chains (migration 013, 2026-06-25). |\n"
    md += "| Data loss | Nightly pg_dump backup (M4.1); 30-day artefact retention. |\n"
    md += "| Vendor compromise | Security CI scans (semgrep + pip-audit + bandit + gitleaks) on every push; dependency review pre-release. |\n"
    md += "| Service outage | Render PaaS auto-restart; health endpoints at `/api/health/*` enabling external uptime monitoring. |\n\n"
    md += "## F. Complementary User Entity Controls\n\n"
    md += "To enable SolarPro Global's controls to function as intended, user entities are expected to:\n\n"
    md += "1. Establish strong-password and MFA practices on their Keycloak account.\n"
    md += "2. Review and recertify role assignments for their organization periodically.\n"
    md += "3. Promptly notify SolarPro support of any suspected unauthorized access.\n"
    md += "4. Logically separate their production and test workspaces.\n\n"

    # ─── Section III: Trust Services Categories Covered ────────────────
    md += "# III. Trust Services Categories Covered\n\n"
    md += "This readiness assessment maps controls to the following Trust Services Categories:\n\n"
    md += "| Category | Symbol | In Scope | Notes |\n"
    md += "|---|---|---|---|\n"
    md += "| Security (Common Criteria) | CC1-CC9 | YES | Primary focus — all CC criteria mapped. |\n"
    md += "| Availability | A1.1-A1.3 | YES (partial) | A1.2 backups + recovery covered; A1.3 capacity planning pending. |\n"
    md += "| Confidentiality | C1.1-C1.2 | YES | Tenant isolation via RLS; data classification proposed. |\n"
    md += "| Processing Integrity | PI1.1-PI1.5 | NO | Deferred to a future scope. |\n"
    md += "| Privacy | P1-P8 | NO | Deferred to a future scope. |\n\n"

    # ─── Section IV: Description of Controls + Test Results ────────────
    md += "# IV. Description of Controls and Test Results\n\n"
    md += "The following table enumerates each control tested in this readiness assessment, the responsible Trust Services Criterion, and the result of the most recent introspection.\n\n"
    md += "| # | Control | TSC Criterion | Result | Detail |\n"
    md += "|---|---|---|---|---|\n"
    for idx, f in enumerate(findings, 1):
        status = f.get("status", "?").upper()
        label  = (f.get("label", "") or "").replace("|", "\\|")
        detail = (f.get("detail", "") or "").replace("|", "\\|").replace("\n", " ")
        if len(detail) > 110:
            detail = detail[:107] + "..."
        criterion = tsc_for(label).replace("|", "\\|")
        md += f"| {idx} | {label} | {criterion} | **{status}** | {detail} |\n"
    md += "\n"

    md += "## Control activities not yet tested by this engine\n\n"
    md += "The following control activities are documented in the SOC 2 implementation plan but are not yet machine-checkable. They are tracked manually in `docs/SOC2_IMPLEMENTATION_PLAN.md`:\n\n"
    md += "- M2.1 Field-level encryption at rest\n"
    md += "- M2.2 Object storage migration to R2 / S3-compatible\n"
    md += "- M2.3 Upload pipeline with anti-malware scanning (ClamAV)\n"
    md += "- M2.4 Redis-backed distributed rate limiting\n"
    md += "- M3.2 Immutable audit log with cryptographic chain\n"
    md += "- M3.4 Centralized observability (Grafana / Loki / Prometheus)\n"
    md += "- M4.2 Tested restore workflow (game-day)\n"
    md += "- M4.3 Documented DR + BCP plan\n"
    md += "- M4.8 Blue/green deployment\n"
    md += "- M4.9 External penetration test\n"
    md += "- M4.11 External SOC 2 Type I / Type II audit\n\n"

    # ─── Section V: Other Information ──────────────────────────────────
    md += "# V. Other Information Provided by Management\n\n"
    md += "## Known limitations of this report\n\n"
    md += "1. **Self-assessment only.** This report is generated by automated introspection. An external Service Auditor independent of management is required for an SSAE 18 attestation. Engagement target: Q1 2027 (Type I) followed by Q3 2027 (Type II with a six-month observation window).\n"
    md += "2. **Point-in-time view.** This report describes the state of controls at the moment of generation, not a period of operation. SOC 2 Type II attestation requires demonstrated operating effectiveness over a 6-12 month period.\n"
    md += "3. **Parallel-run RLS.** The Row Level Security policies in production currently include a `tenant_id IS NULL` escape clause to permit gradual rollout. A future Phase 7 cutover migration will tighten policies to FORCE ROW LEVEL SECURITY, after operational monitoring confirms no functional regressions.\n"
    md += "4. **Subservice organization carve-out.** This report excludes the controls operated by Render, Brevo, Paystack, Stripe, and Cloudflare. User entities relying on those subservices should review the corresponding SOC 2 reports issued by those providers directly.\n\n"
    md += "## Engagement contact\n\n"
    md += "Questions about this report or the underlying SOC 2 implementation plan should be directed to:\n\n"
    md += "- **Management contact:** support@aiappinvent.com\n"
    md += "- **Security incident reporting:** support@aiappinvent.com (subject prefix: `SECURITY`)\n\n"
    md += "---\n\n"
    md += f"*Report generated {generated_at} by `/admin/soc2/report` (audit engine v{version}).*\n"

    return md


def _soc2_make_pdf_bytes(report):
    """Render the SOC 2 readiness report to PDF bytes (no Flask response).

    Used by both /admin/soc2/report.pdf (returned via send_file) and
    /admin/soc2/report/email (attached to the outgoing mail).
    """
    from markdown_pdf import MarkdownPdf, Section
    import io as _io

    md = _soc2_make_aicpa_markdown(report)

    CSS = """
    @page { size: A4 portrait; margin: 14mm 12mm 14mm 12mm; }
    body{font-family:'Segoe UI',Arial,sans-serif;color:#111827;font-size:10pt;line-height:1.45;margin:0;padding:0}
    h1{color:#1e3a8a;font-size:18pt;border-bottom:3px solid #f59e0b;padding-bottom:6px;margin-bottom:14px}
    h2{color:#1e3a8a;font-size:13pt;border-bottom:1px solid #bfdbfe;padding-bottom:3px;margin-top:14px}
    h3{color:#374151;font-size:11pt;margin-top:10px}
    table{width:100%;border-collapse:collapse;margin:8px 0;font-size:8.5pt;border:1.2pt solid #000}
    th{background:#1e3a5f;color:#fff;padding:5px 7px;text-align:left;border:1px solid #000;font-size:9pt}
    td{border:1px solid #000;padding:4px 7px;vertical-align:top}
    tr:nth-child(even) td{background:#f5f7fb}
    blockquote{background:#f0fdf4;border-left:4px solid #22c55e;padding:8px 12px;margin:6px 0;border-radius:3px}
    p{margin:4px 0}
    hr{border:none;border-top:1px solid #444;margin:10px 0}
    code{background:#f3f4f6;padding:1px 4px;border-radius:3px;font-size:9pt}
    strong{color:#1e3a8a}
    """

    pdf = MarkdownPdf(toc_level=2)
    pdf.meta.update({
        "title":   "SOC 2 Readiness Report - SolarPro Global",
        "author":  "SolarPro Global Internal SOC 2 Compliance",
        "subject": "SOC 2 Type II Readiness Assessment",
    })

    # Split on top-level H1 so each numbered section starts on a fresh page.
    parts = md.split("\n# ")
    pdf.add_section(Section(parts[0], toc=False), user_css=CSS)
    for part in parts[1:]:
        pdf.add_section(Section("# " + part, toc=True), user_css=CSS)

    buf = _io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@app.route("/admin/soc2/report.pdf")
@admin_required
def admin_soc2_report_pdf():
    """Download the SOC 2 readiness report as a PDF attachment."""
    report = _run_soc2_audit()
    try:
        pdf_bytes = _soc2_make_pdf_bytes(report)
    except Exception as e:
        flash(f"PDF generation failed: {str(e)[:120]}", "error")
        return redirect(url_for("admin_soc2_report"))

    try:
        log_audit(action="soc2_report_pdf",
                  user_id=session.get("user_id"),
                  status="pass",
                  details=f"score={report.get('score')}")
    except Exception:
        pass

    fname_ts = (report.get("generated_at") or "").replace(":", "").replace("-", "")[:15] or "now"
    filename = f"solarpro_soc2_readiness_{fname_ts}.pdf"
    import io as _io
    return send_file(_io.BytesIO(pdf_bytes),
                     mimetype="application/pdf",
                     as_attachment=True,
                     download_name=filename)


@app.route("/admin/soc2/report/email", methods=["POST"])
@admin_required
def admin_soc2_report_email():
    """Email the SOC 2 readiness report PDF to a chosen recipient."""
    csrf_protect()
    to_addr = (request.form.get("to") or "").strip()
    if not to_addr or "@" not in to_addr or len(to_addr) > 200:
        flash("Please provide a valid email address.", "error")
        return redirect(url_for("admin_soc2_report"))

    report = _run_soc2_audit()
    try:
        pdf_bytes = _soc2_make_pdf_bytes(report)
    except Exception as e:
        flash(f"PDF generation failed: {str(e)[:120]}", "error")
        return redirect(url_for("admin_soc2_report"))

    score = report.get("score", 0.0)
    counts = report.get("counts", {})
    subject = f"SolarPro Global - SOC 2 Readiness Report ({score:.1f}%)"
    safe_addr = to_addr.replace("<", "&lt;").replace(">", "&gt;")
    html_body = f"""
        <p>The attached PDF is the latest SolarPro Global SOC 2 readiness report.</p>
        <p><strong>Overall readiness score:</strong> {score:.1f}%<br>
           <strong>Controls passing:</strong> {counts.get('pass', 0)}<br>
           <strong>Controls with warnings:</strong> {counts.get('warn', 0)}<br>
           <strong>Controls failing:</strong> {counts.get('fail', 0)}</p>
        <p>This is an internal readiness report produced by automated introspection.
        It is NOT a substitute for an external SSAE 18 audit.</p>
        <p>Sent to: {safe_addr}</p>
    """
    fname_ts = (report.get("generated_at") or "").replace(":", "").replace("-", "")[:15] or "now"
    filename = f"solarpro_soc2_readiness_{fname_ts}.pdf"

    try:
        ok = _send_email(
            to_addr,
            subject,
            html_body,
            attachments=[(filename, pdf_bytes, "application/pdf")],
        )
    except Exception as e:
        flash(f"Email send failed: {str(e)[:120]}", "error")
        return redirect(url_for("admin_soc2_report"))

    try:
        log_audit(action="soc2_report_email",
                  user_id=session.get("user_id"),
                  status="pass" if ok else "fail",
                  details=f"to={to_addr} score={score:.1f}")
    except Exception:
        pass

    if ok:
        flash(f"SOC 2 readiness report emailed to {to_addr}.", "success")
    else:
        flash(f"Email send may have failed (provider returned no success). Check logs.", "warning")
    return redirect(url_for("admin_soc2_report"))
