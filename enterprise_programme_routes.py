"""Enterprise Solar Programme Management -- routes (Phase 1).

Registered from wsgi.py via register_enterprise_programme(app, ...), following
the dependency-injection pattern already proven by
new_capital_investment_routes.register_capital_investment (web_app.py:1034).
web_app.py is NEVER edited -- it is CRLF+mojibake and a byte-splice is not
needed here because this module is imported, not spliced.

SECURITY SHAPE OF EVERY ROUTE
-----------------------------
    login_required                  -- no anonymous access
    _require_module()               -- feature flag; 404 when dark
    _require_membership()           -- caller must belong to an organisation
    org_id comes from the MEMBERSHIP, never from the URL or the form
    csrf_protect() on every POST
    every repository call re-scopes by org_id in its WHERE clause

An id in a URL is untrusted input. `programme_id` alone never identifies a row.
"""

from __future__ import annotations

from flask import (
    abort, flash, redirect, render_template, request, session, url_for, jsonify
)

import enterprise_programme_jobs as jobs
import enterprise_programme_repository as repo
import enterprise_programme_services as svc


def register_enterprise_programme(app, *, get_db, login_required, csrf_protect,
                                  current_user):
    """Attach the enterprise module to an existing Flask app.

    Input:  the app plus the four dependencies it needs from web_app (injected
            to avoid a circular import, exactly as the capital-investment module
            does).
    Output: none. Registers routes + a context processor.
    """

    # Registration itself must stay SIDE-EFFECT FREE -- no DB touch here.
    # Two reasons, both real:
    #   1. Flask forbids adding routes / context processors once the app has
    #      served its first request, so registration has to happen at import.
    #      At that moment DB_PATH may still point at the developer's real
    #      solar.db, and creating tables in it would be an unpleasant surprise.
    #   2. On Postgres the schema is migration 024 (applied deliberately through
    #      the gated workflow, because it carries the RLS policies).
    # So the SQLite schema is ensured LAZILY, on the first enterprise request.
    _schema_ready: dict[str, bool] = {"done": False}

    def _ensure_schema_once() -> None:
        if _schema_ready["done"]:
            return
        repo.ensure_enterprise_schema(get_db)   # no-op on Postgres
        _schema_ready["done"] = True

    # ---- guards ----------------------------------------------------------

    def _uid() -> int | None:
        """The session's users.id, or None."""
        return session.get("user_id")

    def _require_module() -> None:
        """404 the whole module while the feature flag is dark.

        A 404 (not a 403) so a disabled module is indistinguishable from one
        that was never deployed.
        """
        _ensure_schema_once()
        if not repo.module_enabled(get_db):
            abort(404)

    def _require_membership() -> dict:
        """The caller's organisation membership, or bounce them to bootstrap.

        This is the PRIMARY tenant boundary in Phase 1 (RLS is ENABLE-not-FORCE
        and therefore defence in depth only -- see migration 024's header).
        """
        uid = _uid()
        if not uid:
            abort(401)
        membership = repo.get_active_membership(get_db, uid)
        if not membership:
            abort(redirect(url_for("enterprise_home")))  # pragma: no cover
        return membership

    # ---- nav flag --------------------------------------------------------

    @app.context_processor
    def _inject_enterprise_flag():
        """Expose the flag to every template so base.html can hide the nav link
        without this module having to edit base.html at all."""
        try:
            return {"enterprise_programme_enabled": repo.module_enabled(get_db)}
        except Exception:
            return {"enterprise_programme_enabled": False}

    # ---- home / bootstrap ------------------------------------------------

    @app.route("/enterprise")
    @login_required
    def enterprise_home():
        """Portfolio dashboard, or the bootstrap prompt for a user with no org."""
        _require_module()
        uid = _uid()
        membership = repo.get_active_membership(get_db, uid)

        if not membership:
            user = current_user()
            return render_template(
                "enterprise_programme/bootstrap.html",
                suggested_name=svc.default_org_name(user),
            )

        org_id = membership["organisation_id"]
        return render_template(
            "enterprise_programme/dashboard.html",
            membership=membership,
            stats=svc.org_dashboard(get_db, org_id, uid),
            programmes=repo.list_programmes(get_db, org_id, uid, limit=10)[0],
            audit=repo.list_audit(get_db, org_id, uid, limit=10),
        )

    @app.route("/enterprise/bootstrap", methods=["POST"])
    @login_required
    def enterprise_bootstrap():
        """Create the organisation + owner membership. Idempotent."""
        _require_module()
        csrf_protect()
        uid = _uid()

        legal_name = (request.form.get("legal_name") or "").strip()
        if not legal_name:
            flash("Organisation name is required.", "error")
            return redirect(url_for("enterprise_home"))

        repo.bootstrap_organisation(
            get_db, uid, legal_name,
            org_type=request.form.get("organisation_type") or "corporate_enterprise",
            country=request.form.get("country") or "",
            currency=request.form.get("default_currency") or "USD",
            keycloak_sub=str(session.get("kc_sub") or ""),
        )
        flash(f"Enterprise workspace created for {legal_name}.", "success")
        return redirect(url_for("enterprise_home"))

    # ---- programmes ------------------------------------------------------

    @app.route("/enterprise/programmes")
    @login_required
    def enterprise_programmes():
        """Paginated programme registry."""
        _require_module()
        m = _require_membership()
        uid = _uid()

        page = max(1, int(request.args.get("page") or 1))
        per_page = 25
        rows, total = repo.list_programmes(
            get_db, m["organisation_id"], uid,
            limit=per_page, offset=(page - 1) * per_page,
        )
        return render_template(
            "enterprise_programme/programmes_list.html",
            membership=m, programmes=rows, total=total, page=page,
            per_page=per_page,
            pages=max(1, (total + per_page - 1) // per_page),
        )

    @app.route("/enterprise/programmes/new", methods=["GET", "POST"])
    @login_required
    def enterprise_programme_new():
        """Create a programme."""
        _require_module()
        m = _require_membership()
        uid = _uid()
        org_id = m["organisation_id"]

        if request.method == "POST":
            csrf_protect()
            data = _programme_form(request.form)
            errors = svc.validate_programme(data)
            if errors:
                for e in errors:
                    flash(e, "error")
                return render_template(
                    "enterprise_programme/programme_form.html",
                    membership=m, form=data, mode="new",
                    programme_types=svc.PROGRAMME_TYPES,
                    design_strategies=svc.DESIGN_STRATEGIES,
                    statuses=svc.PROGRAMME_STATUSES,
                )
            pid = repo.create_programme(get_db, org_id, uid, data)
            flash("Programme created.", "success")
            return redirect(url_for("enterprise_programme_detail", programme_id=pid))

        return render_template(
            "enterprise_programme/programme_form.html",
            membership=m, mode="new",
            form={
                "programme_code": repo.next_programme_code(get_db, org_id, uid),
                "currency": m.get("default_currency") or "USD",
                "design_strategy": "standard",
                "status": "draft",
            },
            programme_types=svc.PROGRAMME_TYPES,
            design_strategies=svc.DESIGN_STRATEGIES,
            statuses=svc.PROGRAMME_STATUSES,
        )

    @app.route("/enterprise/programmes/<int:programme_id>")
    @login_required
    def enterprise_programme_detail(programme_id: int):
        """Programme dashboard: real KPIs, phases, beneficiaries, linked projects."""
        _require_module()
        m = _require_membership()
        uid = _uid()

        view = svc.programme_dashboard(get_db, m["organisation_id"], uid, programme_id)
        if not view:
            abort(404)  # not this organisation's programme

        return render_template(
            "enterprise_programme/programme_detail.html",
            membership=m, **view,
        )

    @app.route("/enterprise/programmes/<int:programme_id>/edit", methods=["GET", "POST"])
    @login_required
    def enterprise_programme_edit(programme_id: int):
        """Edit a programme."""
        _require_module()
        m = _require_membership()
        uid = _uid()
        org_id = m["organisation_id"]

        programme = repo.get_programme(get_db, org_id, uid, programme_id)
        if not programme:
            abort(404)

        if request.method == "POST":
            csrf_protect()
            data = _programme_form(request.form)
            data["programme_code"] = programme["programme_code"]  # code is immutable
            errors = svc.validate_programme(data)
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                repo.update_programme(get_db, org_id, uid, programme_id, data)
                flash("Programme updated.", "success")
                return redirect(
                    url_for("enterprise_programme_detail", programme_id=programme_id)
                )

        return render_template(
            "enterprise_programme/programme_form.html",
            membership=m, mode="edit", programme=programme, form=programme,
            programme_types=svc.PROGRAMME_TYPES,
            design_strategies=svc.DESIGN_STRATEGIES,
            statuses=svc.PROGRAMME_STATUSES,
        )

    # ---- phases ----------------------------------------------------------

    @app.route("/enterprise/programmes/<int:programme_id>/phases", methods=["POST"])
    @login_required
    def enterprise_phase_add(programme_id: int):
        """Add an implementation phase."""
        _require_module()
        m = _require_membership()
        csrf_protect()
        uid = _uid()

        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Phase name is required.", "error")
            return redirect(url_for("enterprise_programme_detail",
                                    programme_id=programme_id))

        ok = repo.add_phase(get_db, m["organisation_id"], uid, programme_id, {
            "name": name,
            "sequence_no": request.form.get("sequence_no") or 1,
            "start_date": request.form.get("start_date") or "",
            "target_completion_date": request.form.get("target_completion_date") or "",
            "target_beneficiaries": request.form.get("target_beneficiaries") or 0,
            "target_capacity_kwp": request.form.get("target_capacity_kwp") or 0,
            "status": request.form.get("status") or "planned",
        })
        if ok is None:
            abort(404)
        flash("Phase added.", "success")
        return redirect(url_for("enterprise_programme_detail", programme_id=programme_id))

    # ---- beneficiaries ---------------------------------------------------

    @app.route("/enterprise/programmes/<int:programme_id>/beneficiaries")
    @login_required
    def enterprise_beneficiaries(programme_id: int):
        """Paginated beneficiary register."""
        _require_module()
        m = _require_membership()
        uid = _uid()
        org_id = m["organisation_id"]

        programme = repo.get_programme(get_db, org_id, uid, programme_id)
        if not programme:
            abort(404)

        page = max(1, int(request.args.get("page") or 1))
        per_page = 50
        rows, total = repo.list_beneficiaries(
            get_db, org_id, uid, programme_id,
            limit=per_page, offset=(page - 1) * per_page,
        )
        return render_template(
            "enterprise_programme/beneficiaries.html",
            membership=m, programme=programme, beneficiaries=rows, total=total,
            page=page, per_page=per_page,
            pages=max(1, (total + per_page - 1) // per_page),
            beneficiary_types=svc.BENEFICIARY_TYPES,
            phases=repo.list_phases(get_db, org_id, uid, programme_id),
        )

    @app.route("/enterprise/programmes/<int:programme_id>/beneficiaries/new",
               methods=["POST"])
    @login_required
    def enterprise_beneficiary_new(programme_id: int):
        """Register one beneficiary manually. (Bulk import is Phase 2.)"""
        _require_module()
        m = _require_membership()
        csrf_protect()
        uid = _uid()

        data = {
            "name": (request.form.get("name") or "").strip(),
            "beneficiary_type": request.form.get("beneficiary_type") or "household",
            "phase_id": request.form.get("phase_id") or None,
            "region": request.form.get("region") or "",
            "district": request.form.get("district") or "",
            "community": request.form.get("community") or "",
            "address": request.form.get("address") or "",
            "latitude": request.form.get("latitude") or None,
            "longitude": request.form.get("longitude") or None,
            "contact_name": request.form.get("contact_name") or "",
            "contact_email": request.form.get("contact_email") or "",
            "contact_phone": request.form.get("contact_phone") or "",
            "load_kwh_day": request.form.get("load_kwh_day") or 0,
            "target_capacity_kwp": request.form.get("target_capacity_kwp") or 0,
            "priority_score": request.form.get("priority_score") or 0,
        }
        errors = svc.validate_beneficiary(data)
        if errors:
            for e in errors:
                flash(e, "error")
        elif repo.add_beneficiary(get_db, m["organisation_id"], uid, programme_id,
                                  data) is None:
            abort(404)
        else:
            flash(f"Beneficiary '{data['name']}' registered.", "success")

        return redirect(url_for("enterprise_beneficiaries", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/beneficiaries/"
               "<int:beneficiary_id>/status", methods=["POST"])
    @login_required
    def enterprise_beneficiary_status(programme_id: int, beneficiary_id: int):
        """Approve / reject / archive a beneficiary."""
        _require_module()
        m = _require_membership()
        csrf_protect()
        uid = _uid()

        status = request.form.get("status") or ""
        if not repo.set_beneficiary_status(get_db, m["organisation_id"], uid,
                                           programme_id, beneficiary_id, status):
            abort(404)
        flash(f"Beneficiary marked {status}.", "success")
        return redirect(url_for("enterprise_beneficiaries", programme_id=programme_id))

    # ---- project links ---------------------------------------------------

    @app.route("/enterprise/programmes/<int:programme_id>/projects")
    @login_required
    def enterprise_project_links(programme_id: int):
        """Link existing SolarPro projects into the programme.

        The picker only ever offers projects THIS user owns.
        """
        _require_module()
        m = _require_membership()
        uid = _uid()
        org_id = m["organisation_id"]

        programme = repo.get_programme(get_db, org_id, uid, programme_id)
        if not programme:
            abort(404)

        return render_template(
            "enterprise_programme/project_links.html",
            membership=m, programme=programme,
            links=repo.list_links(get_db, org_id, uid, programme_id),
            candidates=repo.list_linkable_projects(get_db, uid),
            beneficiaries=repo.list_beneficiaries(
                get_db, org_id, uid, programme_id, limit=200
            )[0],
        )

    @app.route("/enterprise/programmes/<int:programme_id>/projects/link",
               methods=["POST"])
    @login_required
    def enterprise_project_link(programme_id: int):
        """Link one project. Refuses any project the caller does not own."""
        _require_module()
        m = _require_membership()
        csrf_protect()
        uid = _uid()

        kind = request.form.get("project_kind") or ""
        try:
            project_id = int(request.form.get("project_id") or 0)
        except (TypeError, ValueError):
            project_id = 0

        # A malformed beneficiary_id must be a clean rejection, not a 500
        # (Codex gate 1 re-review, non-blocking).
        raw_beneficiary = request.form.get("beneficiary_id") or ""
        try:
            beneficiary_id = int(raw_beneficiary) if raw_beneficiary else None
        except (TypeError, ValueError):
            flash("Unknown beneficiary for this programme.", "error")
            return redirect(url_for("enterprise_project_links",
                                    programme_id=programme_id))

        ok, message = repo.link_project(
            get_db, m["organisation_id"], uid, programme_id, kind, project_id,
            beneficiary_id,
        )
        flash(message, "success" if ok else "error")
        return redirect(url_for("enterprise_project_links", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/projects/<int:link_id>/unlink",
               methods=["POST"])
    @login_required
    def enterprise_project_unlink(programme_id: int, link_id: int):
        """Remove a link. The project itself is never touched."""
        _require_module()
        m = _require_membership()
        csrf_protect()
        uid = _uid()

        if not repo.unlink_project(get_db, m["organisation_id"], uid, programme_id,
                                   link_id):
            abort(404)
        flash("Project unlinked.", "success")
        return redirect(url_for("enterprise_project_links", programme_id=programme_id))

    # ---- jobs (foundation; nothing is enqueued in Phase 1) ---------------

    @app.route("/enterprise/jobs")
    @login_required
    def enterprise_jobs():
        """Job list, as JSON, for UI polling."""
        _require_module()
        m = _require_membership()
        return jsonify(jobs=jobs.list_jobs(get_db, m["organisation_id"], _uid()))

    @app.route("/enterprise/jobs/<int:job_id>")
    @login_required
    def enterprise_job_status(job_id: int):
        """Poll one job's progress."""
        _require_module()
        m = _require_membership()
        job = jobs.get_job(get_db, m["organisation_id"], _uid(), job_id)
        if not job:
            abort(404)
        return jsonify(job=job)

    @app.route("/enterprise/jobs/tick", methods=["POST"])
    @login_required
    def enterprise_job_tick():
        """Process one chunk of one job.

        Behind its OWN flag as well as the module flag -- nothing may process in
        the background until the owner explicitly turns the queue on.
        """
        _require_module()
        m = _require_membership()
        csrf_protect()
        if str(repo.read_flag(get_db, repo.FLAG_JOBS, "0")).strip() != "1":
            abort(404)
        return jsonify(jobs.tick(get_db, m["organisation_id"], _uid()))

    return app


def _programme_form(form) -> dict:
    """Normalise a programme form POST into the service/repository shape."""
    return {
        "programme_code": (form.get("programme_code") or "").strip(),
        "name": (form.get("name") or "").strip(),
        "programme_type": form.get("programme_type") or "residential",
        "description": form.get("description") or "",
        "countries": [c.strip() for c in (form.get("countries") or "").split(",") if c.strip()],
        "regions": [r.strip() for r in (form.get("regions") or "").split(",") if r.strip()],
        "target_beneficiaries": form.get("target_beneficiaries") or 0,
        "target_capacity_kwp": form.get("target_capacity_kwp") or 0,
        "target_battery_kwh": form.get("target_battery_kwh") or 0,
        "budget_amount": form.get("budget_amount") or 0,
        "currency": form.get("currency") or "USD",
        "delivery_model": form.get("delivery_model") or "",
        "procurement_strategy": form.get("procurement_strategy") or "",
        "design_strategy": form.get("design_strategy") or "standard",
        "status": form.get("status") or "draft",
    }
