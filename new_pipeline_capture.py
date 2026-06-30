# new_pipeline_capture.py
# 2026-06-30 — single source of truth for "a public form just captured a lead".
#
# Every public lead-capture surface (assessment popup, /assess full form,
# /bill-check explicit form, /bill-check email-the-pdf, /bill-check invite,
# contact / demo / quote / RFQ etc.) routes through ONE function so the
# /admin/pipeline Kanban + /admin/leads CRM + /admin/assessments + /admin/sales
# always see EVERY lead in the same shape.
#
# Why mirror into both `leads` AND `assessment_requests`:
#   - /admin/pipeline reads UNION of both -- the Kanban needs the row in
#     either table to render a card on the "assessment_submitted" lane.
#   - /admin/leads only reads `leads`. /admin/assessments only reads
#     `assessment_requests`. Writing both keeps both screens populated.
#
# Returns the assessment_ref (e.g. "PL-AB12CD") on success, "" on failure.
# The function NEVER raises -- callers can ignore the return value.


def _capture_pipeline_lead(
    *,
    name="",
    email="",
    phone="",
    country="",
    region="",
    system_type="residential",
    company="",
    interest="",
    message="",
    source="unknown",
    pipeline_stage="assessment_submitted",
    extra=None,
):
    """Unified pipeline capture used by every public lead-capture form.

    Args (all keyword-only):
      name, email, phone, country, region : contact + locale
      system_type    : 'residential' / 'commercial' / 'industrial' / 'hybrid'
      company        : optional employer / org name
      interest       : human label for sales ('residential', 'bill-check', ...)
      message        : free-text note for sales (context, what they asked for)
      source         : short code identifying which form -- e.g.
                       'landing_popup', 'bill_check_lead',
                       'bill_check_emailed', 'bill_check_invite',
                       'contact', 'demo_request', 'quote_request'.
      pipeline_stage : initial stage ('assessment_submitted' by default).
      extra          : optional dict with building_desc / building_size /
                       num_floors / building_type for the assessment record.

    Returns:
      assessment_ref (str) on success, "" on any DB failure. Does NOT raise.
    """
    import random
    import string as _str
    extra = extra or {}
    ref = "PL-" + "".join(random.choices(_str.ascii_uppercase + _str.digits, k=6))
    location_desc = (f"{region}, {country}".strip(", ")) if region else (country or "")
    # _qualify_lead is defined elsewhere in web_app.py -- look it up at call
    # time so the helper is resilient to import order during splice-in.
    try:
        score, grade, notes = _qualify_lead(  # noqa: F821 -- resolved in web_app.py module scope
            name, company, phone, system_type, "0", "", message)
    except Exception:
        score, grade, notes = 0, "D", ""
    bldg_desc = (extra.get("building_desc") or "")[:500]
    bldg_size = (extra.get("building_size") or "")[:80]
    try:
        num_floors_i = int(extra.get("num_floors") or 1)
    except (TypeError, ValueError):
        num_floors_i = 1
    bldg_type = (extra.get("building_type") or system_type or "")[:80]
    interest = (interest or system_type or "residential")[:80]
    try:
        with get_db() as c:  # noqa: F821 -- resolved in web_app.py module scope
            c.execute(
                "INSERT INTO assessment_requests "
                "(name,email,phone,country,region,system_type,location_desc,message,"
                " ai_score,ai_grade,ai_notes,source,status,pipeline_stage,"
                " assessment_ref,building_desc,building_size,num_floors,building_type) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name[:120], email[:200], phone[:80], country[:80], region[:80],
                 (system_type or "residential")[:40], location_desc[:200], message[:2000],
                 int(score), grade, notes[:2000], source[:80], "open",
                 pipeline_stage[:80], ref,
                 bldg_desc, bldg_size, num_floors_i, bldg_type))
            c.execute(
                "INSERT INTO leads "
                "(name,email,phone,company,country,interest,message,source,"
                " system_type,ai_score,ai_grade,ai_notes,pipeline_stage) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (name[:120], email[:200], phone[:80], (company or "")[:120], country[:80],
                 interest, message[:2000], source[:80],
                 (system_type or "residential")[:40],
                 int(score), grade, notes[:2000], pipeline_stage[:80]))
        return ref
    except Exception as e:
        try:
            app.logger.warning(  # noqa: F821 -- resolved in web_app.py module scope
                "pipeline_capture failed src=%s email=%s err=%s", source, email, e)
        except Exception:
            pass
        return ""
