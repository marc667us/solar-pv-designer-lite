"""Enterprise Solar Programme Management -- routes (REBUILD, slice 3).

This file keeps the SEAM and replaces the internals. `register_enterprise_programme` has
the same name and signature it always had, because wsgi.py imports and calls it
(wsgi.py:29, wsgi.py:32) inside a try/except whose whole purpose is that a broken
enterprise module degrades to "feature missing", never to "site down". Changing the
signature would break that contract; changing what happens inside it is the rebuild.

web_app.py is NEVER edited. The four dependencies it owns are injected, exactly as
new_capital_investment_routes does it.

SECURITY SHAPE OF EVERY ROUTE
-----------------------------
    login_required        -- no anonymous access
    _require_module()     -- feature flag; 404 (not 403) while dark, so a disabled module
                             is indistinguishable from one that was never deployed
    _tenant()             -- the ACTIVE tenant is RESOLVED from the caller's membership.
                             A tenant id in a URL or a form is hostile input until proven,
                             and resolve_active_tenant() proves it (slice 1).
    csrf_protect()        -- on every POST
    every service call re-scopes by tenant_id in its WHERE clause (control C13)

WHERE THE RULES LIVE
--------------------
Not here. Routes marshal input and render output; every decision that could be wrong in a
damaging way -- may this user approve this gate, may this programme advance, is this
transition legal -- is made by app/enterprise_programme/{workflows,gates,rbac}.py, which
the background worker and any future API also call. A guard that lives in a route is a
guard the queue drainer skips.
"""

from __future__ import annotations

from flask import (
    Response, abort, flash, redirect, render_template, request, session, url_for
)
from werkzeug.utils import secure_filename

from app.enterprise_programme import (
    beneficiaries, constants, documents, dropdowns, flags, gates, imports, members,
    rbac, rollout, site_qualification, tenancy, workflows,
)
from app.enterprise_programme.documents import DocumentError
from app.enterprise_programme.engines import EngineError
from app.enterprise_programme.members import MemberError
from app.enterprise_programme.rollout import RolloutError
# `templates` is the template ENGINE, not Jinja. Aliased so that nothing in this file can
# be misread as touching Flask's template loader.
from app.enterprise_programme import templates as template_engine
from app.enterprise_programme.gates import EnterpriseGateError
from app.enterprise_programme.rbac import EnterprisePermissionError

# The session key holding the tenant the user is currently acting in. It is a HINT, never
# an authority: resolve_active_tenant() re-checks membership on every request and falls
# back to the caller's personal tenant if they are not a member of the one they ask for.
_ACTIVE_TENANT_KEY = "enterprise_active_tenant"


def _field(row, key: str):
    """Read one column from whatever current_user() hands back.

    Input:  a sqlite3.Row, a dict, a psycopg2 row, or None; the column name.
    Output: the value, or None.

    web_app.current_user() returns a sqlite3.Row on SQLite -- which supports row["x"] but
    NOT row.get("x") -- and a dict-like elsewhere. Neither is safe to assume, and the
    difference only shows up at runtime on one backend, so it is handled once, here.
    """
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def register_enterprise_programme(app, *, get_db, login_required, csrf_protect,
                                  current_user):
    """Attach the enterprise module to an existing Flask app.

    Input:  the app plus the four dependencies it needs from web_app (injected to avoid a
            circular import).
    Output: none. Registers routes + a context processor.
    """

    # Registration must stay SIDE-EFFECT FREE -- no DB touch here. Flask forbids adding
    # routes once the app has served a request, so registration happens at import time, and
    # at that moment DB_PATH may still point at the developer's real solar.db. Creating
    # tables in it as a side effect of an import would be an unpleasant surprise. On
    # Postgres the schema is migrations 025/026, applied deliberately through the gated
    # workflow because they carry the RLS policies. So SQLite schema is ensured LAZILY.
    # Memoised PER DATABASE, not per process. A single boolean was wrong: it records a fact
    # about a database ("its tables exist"), and the process can be pointed at a different
    # one -- which is exactly what a second test module does when it swaps DB_PATH, and it
    # then finds a database whose schema was never created because a previous database had
    # already set the flag. Production has one database and would never have shown this.
    _schema_ready: set[str] = set()

    def _db_identity(c) -> str:
        """Which database is this connection actually talking to?"""
        if flags._is_postgres():
            # Never issue a PRAGMA at psycopg2: an unknown statement aborts the whole
            # transaction. Postgres owns its schema through migration 026 anyway, so
            # ensure_schema is a no-op there and one key for all of Postgres is correct.
            return "postgres"
        try:
            row = c.execute("PRAGMA database_list").fetchone()
            return str(row[2]) if row else "sqlite"
        except Exception:
            return "sqlite"

    def _ensure_schema_once(c) -> None:
        key = _db_identity(c)
        if key in _schema_ready:
            return
        tenancy.ensure_schema(c)        # no-op on Postgres
        workflows.ensure_schema(c)      # no-op on Postgres
        beneficiaries.ensure_schema(c)  # no-op on Postgres
        documents.ensure_schema(c)      # no-op on Postgres (migration 028 owns it)
        rollout.ensure_schema(c)        # no-op on Postgres (migration 029 owns it)
        _schema_ready.add(key)

    # ---- guards ----------------------------------------------------------

    def _uid() -> int:
        uid = session.get("user_id")
        if not uid:
            abort(401)
        return uid

    def _require_module() -> None:
        """404 the whole module while the flag is dark."""
        if not flags.module_enabled(get_db):
            abort(404)

    def _tenant(c, uid: int) -> str:
        """The tenant this request acts in.

        The session may CARRY a tenant id, but it never GRANTS one: resolve_active_tenant
        checks membership and silently falls back to the user's personal tenant. So a user
        who tampers with the session (or is removed from an organisation mid-session) lands
        in their own tenant, not someone else's.

        ON A FRESH SESSION, a user who belongs to exactly ONE organisation starts there
        rather than in their personal workspace. Without this they log in, find an empty
        page, and reasonably conclude their programmes have vanished -- the org is where
        their work actually is. With two or more, we cannot guess, so they land in their
        personal workspace and pick. This is a DEFAULT, not an authority: whatever it
        chooses still goes through resolve_active_tenant below.
        """
        requested = session.get(_ACTIVE_TENANT_KEY)
        if not requested:
            orgs = [t for t in tenancy.list_tenants_for_user(c, uid)
                    if not t.get("is_personal")]
            if len(orgs) == 1:
                requested = orgs[0]["id"]

        active = tenancy.resolve_active_tenant(c, uid, requested)
        session[_ACTIVE_TENANT_KEY] = active
        return active

    # ---- nav flag --------------------------------------------------------

    @app.context_processor
    def _inject_enterprise_flag():
        """Expose the flag to every template so base.html can hide the nav link without
        this module having to edit base.html at all."""
        try:
            return {"enterprise_programme_enabled": flags.module_enabled(get_db)}
        except Exception:
            return {"enterprise_programme_enabled": False}

    # ---- home ------------------------------------------------------------

    @app.route("/enterprise")
    @login_required
    def enterprise_home():
        """Portfolio view: the tenants the user belongs to, and their programmes."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            # Every user has a personal tenant. Backfilled on live by migration 025; created
            # on demand here for anyone who signed up after it ran.
            user = current_user()
            tenancy.get_or_create_personal_tenant(
                c, uid,
                _field(user, "username") or f"user-{uid}",
                _field(user, "email"),
            )
            active = _tenant(c, uid)
            programmes = _list_programmes(c, active)
            return render_template(
                "enterprise_programme/home.html",
                tenants=tenancy.list_tenants_for_user(c, uid),
                active_tenant=active,
                programmes=programmes,
                can_create=rbac.has_permission(c, active, uid, "programme.create"),
            )

    def _list_programmes(c, tenant_id: str) -> list[dict]:
        """Programmes in this tenant, newest first. Tenant-scoped in the WHERE clause."""
        rows = c.execute(
            "SELECT id, code, name, current_phase_code, status, design_strategy "
            "  FROM enterprise_programme_registry "
            " WHERE tenant_id=? ORDER BY id DESC",
            (tenant_id,),
        ).fetchall()
        phase_names = {p[0]: p[2] for p in constants.PHASES}
        return [
            {
                "id": r[0], "code": r[1], "name": r[2],
                "phase_code": r[3], "phase_name": phase_names.get(r[3], r[3]),
                "status": r[4], "design_strategy": r[5],
            }
            for r in rows
        ]

    # ---- switch organisation ---------------------------------------------

    @app.route("/enterprise/switch-tenant", methods=["POST"])
    @login_required
    def enterprise_switch_tenant():
        """Change which organisation the user is acting in.

        The posted id is a REQUEST, not a grant -- _tenant() re-resolves it against real
        membership on this and every later request.
        """
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            requested = (request.form.get("tenant_id") or "").strip()
            session[_ACTIVE_TENANT_KEY] = tenancy.resolve_active_tenant(c, uid, requested)
        return redirect(url_for("enterprise_home"))

    # ---- organisation onboarding -----------------------------------------

    @app.route("/enterprise/onboarding", methods=["GET", "POST"])
    @login_required
    def enterprise_onboarding():
        """Create a real multi-user organisation (a tenant that is not personal)."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)

            if request.method == "POST":
                csrf_protect()
                try:
                    tenant_id = tenancy.create_organisation(
                        c, uid,
                        (request.form.get("legal_name") or "").strip(),
                        (request.form.get("organisation_type") or "").strip(),
                        (request.form.get("country") or "").strip() or None,
                    )
                except ValueError as e:
                    flash(str(e), "error")
                    return redirect(url_for("enterprise_onboarding"))
                session[_ACTIVE_TENANT_KEY] = tenant_id
                flash("Organisation created. You are its Enterprise Owner.", "success")
                return redirect(url_for("enterprise_home"))

            return render_template(
                "enterprise_programme/onboarding.html",
                organisation_types=dropdowns.organisation_types(),
                countries=dropdowns.countries(),
            )

    # ---- create a programme ----------------------------------------------

    @app.route("/enterprise/programmes/new", methods=["GET", "POST"])
    @login_required
    def enterprise_programme_new():
        """Register a programme. It is born at Phase 1 / Concept with all 16 phases and 14
        gates already seeded -- see workflows.create_programme."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            # Checked on the GET too, not only on submit. create_programme is still the
            # boundary -- but without this a user who cannot create a programme is handed
            # the whole form and only finds out when they press Register.
            if not rbac.has_permission(c, active, uid, "programme.create"):
                abort(403)

            if request.method == "POST":
                csrf_protect()
                sponsor = (request.form.get("sponsor_user_id") or "").strip()
                try:
                    pid = workflows.create_programme(
                        c, active, uid,
                        code=(request.form.get("code") or "").strip(),
                        name=(request.form.get("name") or "").strip(),
                        design_strategy=(request.form.get("design_strategy")
                                         or "standard").strip(),
                        sponsor_user_id=int(sponsor) if sponsor else None,
                        country=(request.form.get("country") or "").strip() or None,
                        description=(request.form.get("description") or "").strip() or None,
                    )
                except EnterprisePermissionError:
                    abort(403)
                except (ValueError, EnterpriseGateError) as e:
                    flash(str(e), "error")
                    return redirect(url_for("enterprise_programme_new"))
                flash("Programme registered at Phase 1 (Concept).", "success")
                return redirect(url_for("enterprise_programme_detail", programme_id=pid))

            return render_template(
                "enterprise_programme/programme_new.html",
                options=dropdowns.for_programme_form(),
                members=_members(c, active),
            )

    def _members(c, tenant_id: str) -> list[dict]:
        """Active members of the tenant, for the sponsor dropdown.

        The sponsor is CHOSEN from the organisation's own members, never typed -- a sponsor
        who is not in the organisation is not a sponsor, and create_programme rejects one.
        """
        rows = c.execute(
            "SELECT m.user_id, COALESCE(u.username, 'user-' || m.user_id) "
            "  FROM enterprise_tenant_memberships m "
            "  LEFT JOIN users u ON u.id = m.user_id "
            " WHERE m.tenant_id=? AND m.status='active' "
            " ORDER BY 2",
            (tenant_id,),
        ).fetchall()
        return [{"user_id": r[0], "username": r[1]} for r in rows]

    # ---- programme detail: the lifecycle command centre --------------------

    @app.route("/enterprise/programmes/<int:programme_id>")
    @login_required
    def enterprise_programme_detail(programme_id: int):
        """One programme: where it is, what it may do next, and what is blocking it."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            try:
                state = workflows.get_programme_state(c, active, programme_id)
            except EnterpriseGateError:
                # C13: another tenant's programme and a non-existent one are the same 404.
                # Distinguishing them would leak the existence of other organisations' work.
                abort(404)

            row = c.execute(
                "SELECT code, name, description, design_strategy, country, sponsor_user_id "
                "  FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
                (active, programme_id),
            ).fetchone()

            return render_template(
                "enterprise_programme/programme_detail.html",
                programme={
                    "id": programme_id, "code": row[0], "name": row[1],
                    "description": row[2], "design_strategy": row[3],
                    "country": row[4], "sponsor_user_id": row[5],
                },
                state=state,
                phases=_phase_board(c, active, programme_id),
                gates=_gate_board(c, active, programme_id, uid),
                documents=_documents(c, active, programme_id),
                document_types=REQUIRED_DOCUMENT_TYPES,
                history=_history(c, active, programme_id),
                controls=gates.control_summary(),
                can_edit=rbac.has_permission(c, active, uid, "programme.edit",
                                             programme_id=programme_id),
            )

    def _phase_board(c, tenant_id, programme_id) -> list[dict]:
        """All 16 phases with their state -- the whole road, including what is still ahead."""
        rows = c.execute(
            "SELECT phase_code, sequence_no, status FROM enterprise_programme_phase_states "
            " WHERE tenant_id=? AND programme_id=? ORDER BY sequence_no",
            (tenant_id, programme_id),
        ).fetchall()
        names = {p[0]: p[2] for p in constants.PHASES}
        return [
            {"code": r[0], "sequence_no": r[1], "status": r[2],
             "name": names.get(r[0], r[0]),
             "gate": constants.GATE_CLOSING_PHASE.get(r[0])}
            for r in rows
        ]

    def _gate_board(c, tenant_id, programme_id, uid) -> list[dict]:
        """All 14 gates: who must sign, whether they have, and whether YOU could.

        `can_approve` only decides whether to render a button. It is not a security control
        -- approve_gate re-checks the role and the named post holder, because a hidden
        button is not a guard (the URL can still be POSTed).

        The caller's roles and the programme's named post holders are read ONCE, not once
        per gate. The obvious shape -- ask rbac and the registry inside the loop -- costs
        ~30 round trips to render one page, and on a remote Postgres every one of them is
        a network hop.
        """
        rows = c.execute(
            "SELECT gate_code, phase_code, status, approving_role, decided_by_user_id "
            "  FROM enterprise_stage_gates WHERE tenant_id=? AND programme_id=? "
            " ORDER BY gate_code",
            (tenant_id, programme_id),
        ).fetchall()

        held_roles = rbac.roles_for_user(c, tenant_id, uid, programme_id=programme_id)
        holders = _named_post_holders(c, tenant_id, programme_id)

        labels = {g[0]: g[2] for g in constants.GATES}
        out = []
        for code, phase_code, status, role, decided_by in rows:
            deferred = code in constants.GATES_DEFERRED_BEYOND_RELEASE_1
            approved = status == "Approved"
            can = (not deferred and not approved
                   and _may_sign(uid, role, held_roles, holders))
            out.append({
                "code": code, "name": labels.get(code, code), "phase_code": phase_code,
                "status": status, "approving_role": role, "decided_by": decided_by,
                "deferred": deferred, "can_approve": bool(can),
                # A deferred gate already explains itself with its own badge, and an
                # approved one is waiting for nothing -- neither needs the predicates run.
                "blocked_reason": (
                    None if (deferred or approved)
                    else _gate_blocked_reason(c, tenant_id, programme_id, code)
                ),
            })
        return out

    def _named_post_holders(c, tenant_id, programme_id) -> dict[str, int | None]:
        """The user this programme named for each gate authority: {role_code: user_id|None}.

        Mirrors workflows._require_named_post_holder, which is still the enforcement point.
        This is the render-time copy, read in one query instead of one per gate.
        """
        columns = list(constants.GATE_AUTHORITY_HOLDER_COLUMN.items())
        row = c.execute(
            f"SELECT {', '.join(col for _, col in columns)} "
            "  FROM enterprise_programme_registry WHERE tenant_id=? AND id=?",
            (tenant_id, programme_id),
        ).fetchone()
        if row is None:
            return {}
        return {authority: row[i] for i, (authority, _) in enumerate(columns)}

    def _may_sign(uid, role, held_roles, holders) -> bool:
        """Would approve_gate accept this user for this gate? (render-time only)

        Two conditions, exactly as the service enforces them: hold the approving role, AND
        -- when the programme has NAMED a holder for that post -- be that person. An
        unfilled post (NULL) falls back to the role check alone.
        """
        if role not in held_roles:
            return False
        named = holders.get(role)
        return named is None or int(named) == int(uid)

    def _gate_blocked_reason(c, tenant_id, programme_id, gate_code) -> str | None:
        """What the gate is still waiting for -- shown so a blocked gate explains itself
        instead of just refusing when the button is pressed."""
        try:
            gates.evaluate_gate(c, tenant_id, programme_id, gate_code)
            return None
        except EnterpriseGateError as e:
            return str(e)

    def _documents(c, tenant_id, programme_id) -> list[dict]:
        rows = c.execute(
            "SELECT doc_type, title, created_at FROM enterprise_documents "
            " WHERE tenant_id=? AND programme_id=? ORDER BY id DESC",
            (tenant_id, programme_id),
        ).fetchall()
        return [{"doc_type": r[0], "title": r[1], "created_at": r[2]} for r in rows]

    def _history(c, tenant_id, programme_id) -> list[dict]:
        """The transition ledger -- who moved this programme, when, and through which gate."""
        rows = c.execute(
            "SELECT from_phase_code, to_phase_code, gate_code, actor_user_id, note, created_at "
            "  FROM enterprise_workflow_transitions "
            " WHERE tenant_id=? AND programme_id=? ORDER BY id DESC LIMIT 50",
            (tenant_id, programme_id),
        ).fetchall()
        return [
            {"from": r[0], "to": r[1], "gate": r[2], "actor": r[3],
             "note": r[4], "at": r[5]}
            for r in rows
        ]

    # ---- lifecycle actions -------------------------------------------------

    @app.route("/enterprise/programmes/<int:programme_id>/transition", methods=["POST"])
    @login_required
    def enterprise_programme_transition(programme_id: int):
        """Move the programme. The service decides whether it may."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            target = (request.form.get("target") or "").strip()
            note = (request.form.get("note") or "").strip() or None
            try:
                if target == "RESUME":
                    workflows.resume_from_hold(c, active, programme_id, uid, comment=note)
                    flash("Programme resumed.", "success")
                else:
                    state = workflows.transition_programme_phase(
                        c, active, programme_id, target, uid, note=note
                    )
                    flash(f"Programme moved to {state['status']}.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)          # not yours; it does not exist, as far as you know
                # 409, expressed as a flash: the request was well-formed and the caller was
                # authorised -- the programme is simply not in a state where this is legal.
                flash(str(e), "error")
        return redirect(url_for("enterprise_programme_detail", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/gates/<gate_code>/approve",
               methods=["POST"])
    @login_required
    def enterprise_gate_approve(programme_id: int, gate_code: str):
        """Sign a stage gate. Only the named authority can, and the service enforces it."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                workflows.approve_gate(
                    c, active, programme_id, gate_code.upper(), uid,
                    comment=(request.form.get("comment") or "").strip() or None,
                )
                flash(f"{gate_code.upper()} approved.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_programme_detail", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/documents", methods=["POST"])
    @login_required
    def enterprise_document_add(programme_id: int):
        """Register a required document (concept note, charter, business case...).

        The doc TYPE is a dropdown, not free text: the gate predicates look for a specific
        type, so a typo would silently leave a gate un-passable with no explanation.
        """
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            doc_type = (request.form.get("doc_type") or "").strip()
            if doc_type not in REQUIRED_DOCUMENT_TYPES:
                abort(400)
            try:
                workflows.register_document(
                    c, active, uid, programme_id,
                    doc_type=doc_type,
                    title=(request.form.get("title") or doc_type).strip(),
                    uri=(request.form.get("uri") or "").strip() or None,
                )
                flash("Document registered.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_programme_detail", programme_id=programme_id))

    # ---- templates: the standard a programme repeats -----------------------
    #
    # Every write below is a thin wrapper. The rules -- who may edit, what freezes when,
    # which version may generate -- live in app/enterprise_programme/templates.py, because
    # slice 7's project generator and the queue drainer call the same services and must get
    # the same answers. A rule enforced in a route is a rule the worker does not have.

    @app.route("/enterprise/templates")
    @login_required
    def enterprise_templates():
        """Every template in the organisation, and what each could generate today."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            return render_template(
                "enterprise_programme/templates.html",
                templates=template_engine.list_templates(c, active),
                can_manage=rbac.has_permission(c, active, uid, "template.manage"),
                can_approve=rbac.has_permission(c, active, uid, "template.approve"),
            )

    @app.route("/enterprise/templates/new", methods=["GET", "POST"])
    @login_required
    def enterprise_template_new():
        """Register a template. It is born with version 1, in Draft."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            if not rbac.has_permission(c, active, uid, "template.manage"):
                abort(403)

            if request.method == "POST":
                csrf_protect()
                try:
                    template_id, _version_id = template_engine.create_template(
                        c, active, uid,
                        code=(request.form.get("code") or "").strip(),
                        name=(request.form.get("name") or "").strip(),
                        beneficiary_type=(request.form.get("beneficiary_type")
                                          or "").strip(),
                        design_strategy=(request.form.get("design_strategy")
                                         or "standard").strip(),
                    )
                except EnterprisePermissionError:
                    abort(403)
                except EnterpriseGateError as e:
                    flash(str(e), "error")
                    return redirect(url_for("enterprise_template_new"))
                flash("Template registered. Version 1 is a Draft -- fill it in, then "
                      "submit it for approval.", "success")
                return redirect(url_for("enterprise_template_detail",
                                        template_id=template_id))

            return render_template(
                "enterprise_programme/template_new.html",
                form=dropdowns.for_template_form(c),
            )

    @app.route("/enterprise/templates/<int:template_id>")
    @login_required
    def enterprise_template_detail(template_id: int):
        """One template: its versions, its editable draft (if any), and what it can do."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            try:
                tpl = template_engine.get_template(c, active, template_id)
            except EnterpriseGateError:
                abort(404)  # C13: not yours and not there are the same answer

            versions = template_engine.list_versions(c, active, template_id)
            draft = next((v for v in versions if v["editable"]), None)
            programme_id = tpl["programme_id"]
            can_manage = rbac.has_permission(c, active, uid, "template.manage",
                                             programme_id=programme_id)
            return render_template(
                "enterprise_programme/template_detail.html",
                template=tpl,
                versions=versions,
                draft=draft,
                generative=template_engine.generative_from(versions),
                # Only built when the form will actually be RENDERED -- the template gates
                # it on exactly these two conditions. Building it regardless meant every
                # read of this page (a director checking the version history, say) paid for
                # a 500-row scan of the product catalogue that was then thrown away.
                form=(dropdowns.for_template_form(c) if (draft and can_manage) else None),
                can_manage=can_manage,
                can_approve=rbac.has_permission(c, active, uid, "template.approve",
                                                programme_id=programme_id),
            )

    def _parameters_from_form(form) -> dict:
        """Read the template parameters out of a submitted form.

        Input:  the Flask request form.
        Output: a raw dict keyed by parameter field key.

        Driven by constants.TEMPLATE_PARAMETER_FIELDS -- the SAME list that renders the
        form and validates the result -- so a field cannot be posted that the validator
        does not know, and a field cannot be added to the schema without this reading it.
        `getlist` for the multi-value kinds, because a browser posts repeated keys.

        Nothing is trusted here. This only SHAPES the input; templates.validate_parameters
        decides what is legal.
        """
        out: dict = {}
        for field in constants.TEMPLATE_PARAMETER_FIELDS:
            key, kind = field["key"], field["kind"]
            if kind in ("multiselect", "number_list"):
                out[key] = form.getlist(key)
            elif kind == "bool":
                out[key] = key in form
            else:
                out[key] = form.get(key)
        return out

    @app.route("/enterprise/templates/versions/<int:version_id>/save", methods=["POST"])
    @login_required
    def enterprise_template_version_save(version_id: int):
        """Save the draft. Refused on any version that has left Draft -- see templates.py."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                version = template_engine.get_version_state(c, active, version_id)
                template_engine.save_draft_parameters(
                    c, active, uid, version_id, _parameters_from_form(request.form)
                )
                flash("Draft saved.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                # Back to the FORM, not to the index. A rejected value ("50kw" in a size
                # field) is the ordinary case, not an exceptional one, and bouncing the
                # user to the template list to read why is how a form gets abandoned.
                flash(str(e), "error")
        return redirect(url_for("enterprise_template_detail",
                                template_id=version["template_id"]))

    @app.route("/enterprise/templates/<int:template_id>/versions", methods=["POST"])
    @login_required
    def enterprise_template_version_new(template_id: int):
        """Start a new draft by copying the newest version. THIS is how a template changes."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                template_engine.create_version(c, active, uid, template_id)
                flash("New draft version created, copied from the latest.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_template_detail", template_id=template_id))

    # The version lifecycle actions, and the service each one is. Kept as a table rather
    # than five near-identical routes: they differ ONLY in which service they call, and
    # five copies of the same try/except is five chances to forget the C13 404.
    _VERSION_ACTIONS = {
        "submit":  (template_engine.submit_for_review,
                    "Submitted for approval. The parameters are now frozen."),
        "approve": (template_engine.approve_version,
                    "Version approved. It may now generate projects."),
        "reject":  (template_engine.reject_version,
                    "Sent back to Draft."),
        "publish": (template_engine.publish_version,
                    "Version published. Any previously published version is superseded."),
        "archive": (template_engine.archive_version,
                    "Version archived."),
    }

    @app.route("/enterprise/templates/versions/<int:version_id>/<action>",
               methods=["POST"])
    @login_required
    def enterprise_template_version_action(version_id: int, action: str):
        """Move a version through its lifecycle: submit, approve, reject, publish, archive."""
        _require_module()
        csrf_protect()
        uid = _uid()
        service = _VERSION_ACTIONS.get(action)
        if service is None:
            abort(404)
        run, message = service

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                version = template_engine.get_version_state(c, active, version_id)
                run(c, active, uid, version_id,
                    comment=(request.form.get("comment") or "").strip() or None)
                flash(message, "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                # Stay on the template. "Submit" refused because the draft is incomplete is
                # the most likely error here, and the fields it names are on this page.
                flash(str(e), "error")
        return redirect(url_for("enterprise_template_detail",
                                template_id=version["template_id"]))


    # ---- the beneficiary register ------------------------------------------
    #
    # Registering is not approving, and the routes do not blur that. `beneficiary.import`
    # (a District Coordinator) puts a site into the register; `beneficiary.approve` (a
    # Programme Manager) admits it to the programme. The services enforce both -- these
    # routes only decide which buttons to draw.

    @app.route("/enterprise/programmes/<int:programme_id>/beneficiaries")
    @login_required
    def enterprise_beneficiaries(programme_id: int):
        """The register for one programme, with its status counts and import history."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                state = workflows.get_programme_state(c, active, programme_id)
            except EnterpriseGateError:
                abort(404)              # C13

            status = (request.args.get("status") or "").strip() or None
            rows = beneficiaries.list_beneficiaries(
                c, active, programme_id, status=status
            )
            counts = beneficiary_counts = beneficiaries.count_by_status(
                c, active, programme_id
            )
            return render_template(
                "enterprise_programme/beneficiaries.html",
                programme_id=programme_id,
                state=state,
                beneficiaries=rows,
                counts=counts,
                total=sum(beneficiary_counts.values()),
                # The list is capped. Say so, rather than letting a 4000-site programme
                # quietly render as 500 and look complete.
                capped=len(rows) >= 500,
                status_filter=status,
                statuses=constants.BENEFICIARY_STATUSES,
                batches=imports.list_batches(c, active, programme_id),
                beneficiary_types=dropdowns.beneficiary_types(),
                import_max_rows=constants.IMPORT_MAX_ROWS,
                can_import=rbac.has_permission(c, active, uid, "beneficiary.import",
                                               programme_id=programme_id),
                can_approve=rbac.has_permission(c, active, uid, "beneficiary.approve",
                                                programme_id=programme_id),
            )

    @app.route("/enterprise/programmes/<int:programme_id>/beneficiaries/new",
               methods=["GET", "POST"])
    @login_required
    def enterprise_beneficiary_new(programme_id: int):
        """Enter one site by hand. The bulk path is the importer."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            # OWNERSHIP BEFORE AUTHORISATION (C13). Checking the permission first meant a
            # user holding tenant-wide `beneficiary.import` was handed the form for ANOTHER
            # tenant's programme id, and a user without it got a 403 -- which confirms the
            # programme exists. Not-yours and not-there must be the same answer.
            try:
                workflows.get_programme_state(c, active, programme_id)
            except EnterpriseGateError:
                abort(404)

            if not rbac.has_permission(c, active, uid, "beneficiary.import",
                                       programme_id=programme_id):
                abort(403)

            if request.method == "POST":
                csrf_protect()
                try:
                    bid = beneficiaries.create_beneficiary(
                        c, active, uid, programme_id,
                        code=(request.form.get("code") or "").strip(),
                        name=(request.form.get("name") or "").strip(),
                        beneficiary_type=(request.form.get("beneficiary_type")
                                          or "").strip(),
                        fields=_beneficiary_fields_from_form(request.form),
                    )
                except EnterprisePermissionError:
                    abort(403)
                except EnterpriseGateError as e:
                    if e.control == "C13":
                        abort(404)
                    flash(str(e), "error")
                    return redirect(url_for("enterprise_beneficiary_new",
                                            programme_id=programme_id))
                flash("Beneficiary registered. It still has to be approved into the "
                      "programme before it can be qualified.", "success")
                return redirect(url_for("enterprise_beneficiary_detail",
                                        beneficiary_id=bid))

            return render_template(
                "enterprise_programme/beneficiary_form.html",
                programme_id=programme_id,
                beneficiary=None,
                form=dropdowns.for_beneficiary_form(),
            )

    def _beneficiary_fields_from_form(form) -> dict:
        """Read the 22 attributes out of a submitted form.

        Driven by constants.BENEFICIARY_FIELD_SPEC -- the SAME list that renders the form
        and validates the result -- so a field cannot be posted that the validator does not
        know, and a field cannot be added to the schema without this reading it.
        """
        return {f["key"]: form.get(f["key"]) for f in constants.BENEFICIARY_FIELD_SPEC}

    @app.route("/enterprise/beneficiaries/<int:beneficiary_id>",
               methods=["GET", "POST"])
    @login_required
    def enterprise_beneficiary_detail(beneficiary_id: int):
        """One site: its record, its state, and what may be done to it."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            try:
                row = beneficiaries.get_beneficiary(c, active, beneficiary_id)
            except EnterpriseGateError:
                abort(404)              # C13

            if request.method == "POST":
                csrf_protect()
                try:
                    row = beneficiaries.update_beneficiary(
                        c, active, uid, beneficiary_id,
                        _beneficiary_fields_from_form(request.form),
                    )
                    flash("Beneficiary updated.", "success")
                except EnterprisePermissionError:
                    abort(403)
                except EnterpriseGateError as e:
                    if e.control == "C13":
                        abort(404)
                    flash(str(e), "error")

            programme_id = row["programme_id"]
            return render_template(
                "enterprise_programme/beneficiary_form.html",
                programme_id=programme_id,
                beneficiary=row,
                form=dropdowns.for_beneficiary_form(),
                can_edit=rbac.has_permission(c, active, uid, "beneficiary.import",
                                             programme_id=programme_id),
                can_approve=rbac.has_permission(c, active, uid, "beneficiary.approve",
                                                programme_id=programme_id),
            )

    @app.route("/enterprise/beneficiaries/<int:beneficiary_id>/transition",
               methods=["POST"])
    @login_required
    def enterprise_beneficiary_transition(beneficiary_id: int):
        """Admit a site to the programme, or turn it away."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                row = beneficiaries.get_beneficiary(c, active, beneficiary_id)
                beneficiaries.transition_beneficiary(
                    c, active, uid, beneficiary_id,
                    (request.form.get("target") or "").strip(),
                    comment=(request.form.get("comment") or "").strip() or None,
                )
                flash("Beneficiary updated.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_beneficiary_detail",
                                beneficiary_id=beneficiary_id))

    # ---- site qualification (slice 6) ---------------------------------------
    #
    # SCORING and DECIDING are two acts by two people. A surveyor with `qualification.score`
    # records what they found; a manager with `qualification.approve` decides the programme
    # will serve it. `decide` refuses a site nobody scored -- which is what control C02
    # ("no beneficiary becomes a project without qualification") actually MEANS in code.

    @app.route("/enterprise/programmes/<int:programme_id>/priority")
    @login_required
    def enterprise_priority_list(programme_id: int):
        """Doc 3's priority list: every site, best score first, unscored last."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                programme = workflows.get_programme_state(c, active, programme_id)   # C13
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                raise
            sites, capped = site_qualification.priority_list(c, active, programme_id)
            return render_template(
                "enterprise_programme/priority_list.html",
                programme=programme, programme_id=programme_id, sites=sites,
                capped=capped,
                criteria=constants.QUALIFICATION_CRITERIA,
                qualified=site_qualification.count_qualified(c, active, programme_id),
                can_score=rbac.has_permission(c, active, uid, "qualification.score",
                                              programme_id=programme_id),
            )

    @app.route("/enterprise/beneficiaries/<int:beneficiary_id>/qualify",
               methods=["GET", "POST"])
    @login_required
    def enterprise_qualify_site(beneficiary_id: int):
        """The scorecard. GET renders it; POST records the survey (it does NOT decide)."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                site = beneficiaries.get_beneficiary(c, active, beneficiary_id)      # C13
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                raise

            if request.method == "POST":
                csrf_protect()
                scores = {
                    crit["key"]: request.form.get(crit["key"])
                    for crit in constants.QUALIFICATION_CRITERIA
                    if request.form.get(crit["key"]) is not None
                }
                try:
                    site_qualification.score_site(
                        c, active, uid, beneficiary_id, scores=scores,
                        notes=(request.form.get("notes") or "").strip(),
                    )
                    flash("Site scored. It still needs a decision.", "success")
                    return redirect(url_for("enterprise_qualify_site",
                                            beneficiary_id=beneficiary_id))
                except EnterprisePermissionError:
                    abort(403)
                except EnterpriseGateError as e:
                    if e.control == "C13":
                        abort(404)
                    flash(str(e), "error")

            return render_template(
                "enterprise_programme/qualify_site.html",
                site=site,
                qualification=site_qualification.get_qualification(c, active,
                                                                   beneficiary_id),
                criteria=constants.QUALIFICATION_CRITERIA,
                score_min=constants.QUALIFICATION_SCORE_MIN,
                score_max=constants.QUALIFICATION_SCORE_MAX,
                decisions=constants.QUALIFICATION_DECISIONS,
                can_score=rbac.has_permission(c, active, uid, "qualification.score",
                                              programme_id=site["programme_id"]),
                can_decide=rbac.has_permission(c, active, uid, "qualification.approve",
                                               programme_id=site["programme_id"]),
            )

    @app.route("/enterprise/beneficiaries/<int:beneficiary_id>/qualify/decide",
               methods=["POST"])
    @login_required
    def enterprise_qualify_decide(beneficiary_id: int):
        """Qualify the site, or refuse it. The ONLY way into either status."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                site_qualification.decide(
                    c, active, uid, beneficiary_id,
                    decision=(request.form.get("decision") or "").strip(),
                    notes=(request.form.get("notes") or "").strip(),
                )
                flash("Decision recorded.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_qualify_site", beneficiary_id=beneficiary_id))

    # ---- bulk import --------------------------------------------------------
    #
    # Upload -> STAGE (nothing written to the register) -> fix the mapping as often as you
    # like -> commit. The register is only ever touched by the commit.

    @app.route("/enterprise/programmes/<int:programme_id>/import", methods=["POST"])
    @login_required
    def enterprise_import_upload(programme_id: int):
        """Parse a spreadsheet, guess its columns, and stage every row. Writes NO
        beneficiaries -- the operator sees what would happen first."""
        _require_module()
        csrf_protect()
        uid = _uid()

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            flash("Choose a CSV or XLSX file to import.", "error")
            return redirect(url_for("enterprise_beneficiaries",
                                    programme_id=programme_id))

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                # Establish "is this programme yours, and may you import into it?" BEFORE
                # decompressing and parsing the upload. The 404 was already correct, but a
                # stranger could make a single free-tier instance parse a 16 MB spreadsheet
                # for the privilege of being told no.
                workflows.get_programme_state(c, active, programme_id)      # C13
                rbac.require_permission(c, active, uid, "beneficiary.import",
                                        programme_id=programme_id)
                headers, rows = imports.parse_file(upload.filename, upload.read())
                batch_id = imports.stage_import(
                    c, active, uid, programme_id,
                    filename=upload.filename,
                    headers=headers, rows=rows,
                    mapping=imports.auto_map(headers),
                    default_type=(request.form.get("default_type") or "").strip(),
                )
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return redirect(url_for("enterprise_beneficiaries",
                                        programme_id=programme_id))
        return redirect(url_for("enterprise_import_detail", batch_id=batch_id))

    @app.route("/enterprise/imports/<int:batch_id>")
    @login_required
    def enterprise_import_detail(batch_id: int):
        """The preview: what this import WOULD do, before it does any of it."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                batch = imports.get_batch(c, active, batch_id)
            except EnterpriseGateError:
                abort(404)              # C13
            return render_template(
                "enterprise_programme/import_detail.html",
                batch=batch,
                headers=sorted({h for r in batch["rows"] for h in r["raw"]}),
                importable=imports.importable_fields(),
                beneficiary_types=dropdowns.beneficiary_types(),
                can_import=rbac.has_permission(
                    c, active, uid, "beneficiary.import",
                    programme_id=batch["programme_id"]),
            )

    @app.route("/enterprise/imports/<int:batch_id>/remap", methods=["POST"])
    @login_required
    def enterprise_import_remap(batch_id: int):
        """Re-run the staged rows through a corrected column mapping. Still writes nothing."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            mapping = {
                key[len("map__"):]: value.strip()
                for key, value in request.form.items()
                if key.startswith("map__") and value.strip()
            }
            # A form that never showed the default type must not be read as a request to
            # clear it: absent means "leave it as chosen at upload" (None), present-and-blank
            # means the operator deliberately emptied it.
            posted_default = request.form.get("default_type")
            try:
                counts = imports.restage_batch(
                    c, active, uid, batch_id, mapping=mapping,
                    default_type=(None if posted_default is None
                                  else posted_default.strip()),
                )
                flash(f"Re-checked: {counts['Valid']} valid, {counts['Error']} with "
                      f"errors, {counts['Duplicate']} duplicates.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_import_detail", batch_id=batch_id))

    @app.route("/enterprise/imports/<int:batch_id>/commit", methods=["POST"])
    @login_required
    def enterprise_import_commit(batch_id: int):
        """Create a beneficiary for every Valid row. THE ONLY thing that writes the register."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                batch = imports.get_batch(c, active, batch_id, limit=1)
                result = imports.commit_batch(
                    c, active, uid, batch_id,
                    include_duplicates=("include_duplicates" in request.form),
                )
                # Each number names a different thing the operator would do something
                # different about: duplicates they declined, rows that never validated, and
                # rows the database itself refused. Rolling them into one "skipped" sent
                # them looking in the wrong place.
                detail = ", ".join(
                    part for part in (
                        f"{result['skipped']} duplicate(s) skipped" if result["skipped"] else "",
                        f"{result['errors']} with errors" if result["errors"] else "",
                        f"{result['failed']} refused by the database" if result["failed"] else "",
                    ) if part
                )
                flash(f"Imported {result['imported']} beneficiaries"
                      + (f" ({detail})" if detail else "")
                      + ". They are registered, not yet approved into the programme.",
                      "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return redirect(url_for("enterprise_import_detail", batch_id=batch_id))
        return redirect(url_for("enterprise_beneficiaries",
                                programme_id=batch["programme_id"]))

    @app.route("/enterprise/imports/<int:batch_id>/cancel", methods=["POST"])
    @login_required
    def enterprise_import_cancel(batch_id: int):
        """Throw a staged import away. The rows stay -- what was rejected, and why, is evidence."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                batch = imports.get_batch(c, active, batch_id, limit=1)
                imports.cancel_batch(c, active, uid, batch_id)
                flash("Import cancelled. Nothing was written to the register.", "success")
            except EnterprisePermissionError:
                abort(403)
            except EnterpriseGateError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return redirect(url_for("enterprise_import_detail", batch_id=batch_id))
        return redirect(url_for("enterprise_beneficiaries",
                                programme_id=batch["programme_id"]))

    # ---- lifecycle documents (slice 6.6) ---------------------------------
    #
    # The owner's requirement, in their words: "in the life cycle activities must have
    # check box, one use select one or even multiple of the activities the app must
    # generate document" and "where user must load a document that document can be used to
    # develop life cycle document". So: tick activities -> get a document; upload a source
    # document -> it becomes the material the generated document is drawn from.

    @app.route("/enterprise/programmes/<int:programme_id>/lifecycle-documents")
    @login_required
    def enterprise_lifecycle_documents(programme_id: int):
        """The activity picker, the upload form, and the programme's document register."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            try:
                prog = documents.programme_facts(c, active, programme_id)
            except EnterpriseGateError:
                abort(404)                      # C13: not-yours and not-there are the same

            docs = documents.list_documents(c, active, programme_id)
            return render_template(
                "enterprise_programme/lifecycle_documents.html",
                programme=prog,
                programme_id=programme_id,
                stages=constants.LIFECYCLE_STAGES,
                phase_names={code: name for code, _no, name in constants.PHASES},
                phase_numbers={code: no for code, no, _name in constants.PHASES},
                phase_activities=constants.PHASE_ACTIVITIES,
                # Counted here, not in Jinja: summing a nested length across a stage's
                # phases in a template needs a filter Jinja does not have, and faking it
                # with `map('extract', ...)` silently yields nothing.
                stage_counts={
                    scode: sum(len(constants.PHASE_ACTIVITIES[p]) for p in sphases)
                    for scode, _sname, sphases in constants.LIFECYCLE_STAGES
                },
                current_phase=prog.get("phase_code"),
                current_stage=constants.STAGE_OF_PHASE.get(prog.get("phase_code")),
                documents=docs,
                sources=[d for d in docs if d["doc_kind"] == "uploaded"],
                supported=sorted(documents.SUPPORTED_UPLOADS),
                max_mb=documents.MAX_UPLOAD_BYTES // (1024 * 1024),
                questions=documents.outstanding_questions(c, active, programme_id),
                can_generate=rbac.has_permission(c, active, uid, "report.generate",
                                                 programme_id=programme_id),
                can_upload=rbac.has_permission(c, active, uid, "programme.edit",
                                               programme_id=programme_id),
            )

    @app.route("/enterprise/programmes/<int:programme_id>/lifecycle-documents/answers",
               methods=["POST"])
    @login_required
    def enterprise_lifecycle_document_answers(programme_id: int):
        """Answer the questions the app raised. The answers become the document's content."""
        _require_module()
        csrf_protect()
        uid = _uid()
        back = redirect(url_for("enterprise_lifecycle_documents",
                                programme_id=programme_id))

        # Form fields arrive as answer[P01_A02]. Only known activity codes are accepted --
        # save_answers filters again, because a service must not trust its caller.
        answers = {
            k[len("answer["):-1]: v
            for k, v in request.form.items()
            if k.startswith("answer[") and k.endswith("]")
        }

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                n = documents.save_answers(c, active, uid, programme_id, answers)
            except EnterprisePermissionError:
                abort(403)
            except DocumentError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return back

        if n:
            flash(f"{n} answer(s) saved. Regenerate the document to fold them in.",
                  "success")
        else:
            flash("No answers were provided.", "error")
        return back

    @app.route("/enterprise/programmes/<int:programme_id>/lifecycle-documents/upload",
               methods=["POST"])
    @login_required
    def enterprise_lifecycle_document_upload(programme_id: int):
        """Upload a source document. Its text becomes material for generation."""
        _require_module()
        csrf_protect()
        uid = _uid()
        back = redirect(url_for("enterprise_lifecycle_documents",
                                programme_id=programme_id))

        f = request.files.get("document")
        if not f or not f.filename:
            flash("Choose a file to upload.", "error")
            return back

        # THE CAP IS ENFORCED BEFORE THE BYTES ARE IN MEMORY (Codex slice-6.6, MED).
        # `f.read()` on its own buffers the WHOLE upload first and only then discovers it is
        # too big -- which is not a limit, it is an invitation: on a 512 MiB instance a few
        # concurrent 500 MB posts are an outage. So:
        #   1. reject on the declared Content-Length when it is already over (cheap, and
        #      catches the honest client), and
        #   2. read only MAX+1 bytes regardless, because Content-Length is the CLIENT'S
        #      claim and a hostile one will lie about it. The +1 is what tells us it was
        #      over the limit rather than exactly at it.
        # The service checks the length AGAIN -- a service must not rely on its caller.
        if (request.content_length or 0) > documents.MAX_UPLOAD_BYTES + 4096:
            flash(f"That file is larger than "
                  f"{documents.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", "error")
            return back

        data = f.stream.read(documents.MAX_UPLOAD_BYTES + 1)
        if len(data) > documents.MAX_UPLOAD_BYTES:
            flash(f"That file is larger than "
                  f"{documents.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", "error")
            return back

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                documents.upload_document(
                    c, active, uid, programme_id,
                    file_name=f.filename, data=data,
                    title=(request.form.get("title") or "").strip(),
                )
            except EnterprisePermissionError:
                abort(403)
            except DocumentError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return back
        flash("Document uploaded. It can now be used to build a lifecycle document.",
              "success")
        return back

    @app.route("/enterprise/programmes/<int:programme_id>/lifecycle-documents/generate",
               methods=["POST"])
    @login_required
    def enterprise_lifecycle_document_generate(programme_id: int):
        """Generate a document from the ticked activities. THE feature."""
        _require_module()
        csrf_protect()
        uid = _uid()
        back = redirect(url_for("enterprise_lifecycle_documents",
                                programme_id=programme_id))

        picked = request.form.getlist("activities")
        if not picked:
            flash("Tick at least one lifecycle activity.", "error")
            return back

        source_id = (request.form.get("source_document_id") or "").strip()
        source_document_id = int(source_id) if source_id.isdigit() else None

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                doc_id = documents.generate_document(
                    c, active, uid, programme_id,
                    activity_codes=picked,
                    title=(request.form.get("title") or "").strip(),
                    source_document_id=source_document_id,
                    use_ai=bool(request.form.get("use_ai")),
                )
            except EnterprisePermissionError:
                abort(403)
            except DocumentError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
                return back

        flash(f"Document generated from {len(set(picked))} activities.", "success")
        return redirect(url_for("enterprise_document_download", document_id=doc_id))

    @app.route("/enterprise/documents/<int:document_id>/download")
    @login_required
    def enterprise_document_download(document_id: int):
        """Download a document: the PDF for a generated one, the original for an upload."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                doc = documents.get_document(c, active, document_id)
            except DocumentError:
                abort(404)                      # C13 -- never 403, never "it exists but"

            if doc["doc_kind"] == "generated":
                try:
                    body = documents.render_pdf(doc["markdown"] or "", doc["title"])
                except DocumentError as e:
                    flash(str(e), "error")
                    return redirect(url_for("enterprise_lifecycle_documents",
                                            programme_id=doc["programme_id"]))
                mime, name = "application/pdf", (doc["file_name"] or "document.pdf")
            else:
                body = doc["content"]
                if body is None:
                    abort(404)                  # a register row with no file behind it
                mime = doc["mime_type"] or "application/octet-stream"
                name = doc["file_name"] or "document"

            # THE FILENAME IS USER INPUT AND IT IS GOING INTO A HEADER (Codex slice-6.6, MED).
            # It was uploaded by a person, so it can contain quotes, semicolons, CR/LF or
            # path separators -- and splicing it raw into Content-Disposition lets a quote
            # close the field early and a newline inject a header outright. `secure_filename`
            # reduces it to a safe basename; the fallback covers the case where it reduces to
            # nothing at all (a name that was entirely separators and quotes).
            safe = secure_filename(name) or "document"

            # `attachment`, never inline: a PDF or DOCX rendered INLINE from a user-supplied
            # upload is a stored-XSS surface the moment a browser sniffs it as HTML.
            # `nosniff` is what stops the sniffing.
            return Response(body, mimetype=mime, headers={
                "Content-Disposition": f'attachment; filename="{safe}"',
                "X-Content-Type-Options": "nosniff",
            })

    # ---- members and roles (slice 6.5) -----------------------------------
    #
    # The surface that was missing entirely: slice 3 shipped role CHECKING with no way to
    # GRANT a role, so an organisation could never take on a second person, and its owner
    # could not delegate. Guarded by `tenant.admin`.

    @app.route("/enterprise/members")
    @login_required
    def enterprise_members():
        """Who is in this organisation, and what each of them may do."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                view = members.overview(c, active, uid)
            except EnterprisePermissionError:
                abort(403)
            except MemberError as e:
                flash(str(e), "error")
                return redirect(url_for("enterprise_home"))

            return render_template(
                "enterprise_programme/members.html",
                members=view["members"],
                assignable_roles=view["assignable_roles"],
                is_solo=view["is_solo"],
                role_permissions=constants.ROLE_PERMISSIONS,
            )

    @app.route("/enterprise/members/add", methods=["POST"])
    @login_required
    def enterprise_member_add():
        """Invite an existing SolarPro user into this organisation with a starting role."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                user = members.invite(
                    c, active, uid,
                    (request.form.get("identifier") or "").strip(),
                    (request.form.get("role_code") or "").strip(),
                )
                flash(f"{user['username']} added to the organisation.", "success")
            except EnterprisePermissionError:
                abort(403)
            except MemberError as e:
                flash(str(e), "error")
        return redirect(url_for("enterprise_members"))

    @app.route("/enterprise/members/<int:user_id>/roles", methods=["POST"])
    @login_required
    def enterprise_member_roles(user_id: int):
        """Grant or revoke one tenant-wide role."""
        _require_module()
        csrf_protect()
        uid = _uid()
        action = (request.form.get("action") or "").strip()
        role_code = (request.form.get("role_code") or "").strip()

        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                if action == "grant":
                    members.grant(c, active, uid, user_id, role_code)
                    flash(f"Granted {role_code}.", "success")
                elif action == "revoke":
                    members.revoke(c, active, uid, user_id, role_code)
                    flash(f"Revoked {role_code}.", "success")
                else:
                    flash("Unknown action.", "error")
            except EnterprisePermissionError:
                abort(403)
            except MemberError as e:
                flash(str(e), "error")
        return redirect(url_for("enterprise_members"))

    @app.route("/enterprise/members/<int:user_id>/remove", methods=["POST"])
    @login_required
    def enterprise_member_remove(user_id: int):
        """Offboard a member. Their roles stop granting anything immediately."""
        _require_module()
        csrf_protect()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                members.remove(c, active, uid, user_id)
                flash("Member removed from the organisation.", "success")
            except EnterprisePermissionError:
                abort(403)
            except MemberError as e:
                flash(str(e), "error")
        return redirect(url_for("enterprise_members"))

    # ------------------------------------------------------------------
    # SLICE 7 -- the programme's ONE design, scaled to every site
    # ------------------------------------------------------------------
    # The owner's shape, in their words: "when you are in planning the programme must open
    # into standard or generation station design"; "the implementation must be built up from
    # the design but scaled to all programme sites"; "the BOQ and everything is the same for
    # each site". So there is ONE screen and it walks exactly that: choose the approved
    # template -> build the one design -> engineering approves it -> roll it out to every
    # qualified site -> read the programme plans. Not one screen per step; the steps ARE the
    # story, and splitting them across five pages would hide the fact that they are one.

    @app.route("/enterprise/programmes/<int:programme_id>/design")
    @login_required
    def enterprise_design(programme_id: int):
        """The programme's design and rollout screen."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)

            try:
                prog = documents.programme_facts(c, active, programme_id)
            except EnterpriseGateError:
                abort(404)              # C13: not-yours and not-there are one answer

            design = rollout.current_design(c, active, programme_id)
            stage = constants.STAGE_OF_PHASE.get(prog.get("phase_code"))
            return render_template(
                "enterprise_programme/design.html",
                programme=prog,
                programme_id=programme_id,
                stage=stage,
                stage_name=dict((sc, sn) for sc, sn, _p
                                in constants.LIFECYCLE_STAGES).get(stage, ""),
                planning_reached=stage is not None and stage != "S1_INITIATION",
                options=rollout.design_options(c, active, programme_id),
                design=design,
                scope=(rollout.rollout_scope(c, active, programme_id, design["id"])
                       if design else None),
                job=rollout.latest_job(c, active, programme_id),
                sites=rollout.site_projects(c, active, programme_id),
                funding=rollout.funding_requirement(c, active, programme_id),
                boq=rollout.scaled_boq(c, active, programme_id),
                can_design=rbac.has_permission(c, active, uid, "design.generate",
                                               programme_id=programme_id),
                can_approve=rbac.has_permission(c, active, uid, "engineering.approve",
                                                programme_id=programme_id),
                can_survey=rbac.has_permission(c, active, uid, "qualification.score",
                                               programme_id=programme_id),
            )

    @app.route("/enterprise/programmes/<int:programme_id>/design/create",
               methods=["POST"])
    @login_required
    def enterprise_design_create(programme_id: int):
        """Build the ONE design that every site in this programme will be."""
        _require_module()
        csrf_protect()
        uid = _uid()
        f = request.form
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                design = rollout.create_reference_design(
                    c, active, uid, programme_id,
                    template_version_id=int(f.get("template_version_id") or 0),
                    monthly_kwh=f.get("monthly_kwh"),
                    design_kwp=f.get("design_kwp"),
                    region=(f.get("region") or "").strip(),
                )
                flash(
                    "Reference design built ({:g} kWp). Engineering must approve it before "
                    "it can be rolled out to the programme's sites.".format(
                        design.get("kwp") or 0),
                    "success")
            except EnterprisePermissionError:
                abort(403)
            except RolloutError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
            except EngineError as e:
                # The design engine refused. That is an operator-fixable input problem (a
                # zero bill, a capacity nothing can be built at), not a server fault -- so
                # it is a flash on the form, not a 500.
                flash(str(e), "error")
        return redirect(url_for("enterprise_design", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/design/<int:design_id>/"
               "<action>", methods=["POST"])
    @login_required
    def enterprise_design_action(programme_id: int, design_id: int, action: str):
        """approve (C04) | supersede | rollout. One route, because they are one workflow."""
        _require_module()
        csrf_protect()
        uid = _uid()
        if action not in ("approve", "supersede", "rollout"):
            abort(404)
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                if action == "approve":
                    rollout.approve_reference_design(c, active, uid, design_id)
                    flash("Design approved by engineering. It can now be rolled out.",
                          "success")
                elif action == "supersede":
                    rollout.supersede_reference_design(c, active, uid, design_id)
                    flash("Design superseded. The sites already built from it keep "
                          "pointing at it -- that record is what says what each site was "
                          "actually built to.", "success")
                else:
                    job_id = rollout.queue_rollout(c, active, uid, programme_id,
                                                   design_id=design_id)
                    job = rollout.get_job(c, active, job_id)
                    flash(
                        "Rollout queued for {} site{}. It runs in the background -- the "
                        "queue is drained on a schedule, so it is not instant.".format(
                            job["total_items"], "" if job["total_items"] == 1 else "s"),
                        "success")
            except EnterprisePermissionError:
                abort(403)
            except RolloutError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_design", programme_id=programme_id))

    @app.route("/enterprise/programmes/<int:programme_id>/sites/<int:link_id>/survey",
               methods=["POST"])
    @login_required
    def enterprise_site_survey(programme_id: int, link_id: int):
        """The field assessment + shading survey for ONE location.

        RECORDED, NOT APPLIED. See rollout.record_site_variance: the reference BOQ is what
        gets built at every site, so a survey that disagrees with it raises a flag for
        engineering rather than quietly re-sizing this one site's array behind everyone's
        back.
        """
        _require_module()
        csrf_protect()
        uid = _uid()
        f = request.form
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                rollout.record_site_variance(
                    c, active, uid, programme_id, link_id,
                    shading_factor=(f.get("shading_factor") or None),
                    field_notes=(f.get("field_notes") or ""),
                )
                flash("Site survey recorded.", "success")
            except EnterprisePermissionError:
                abort(403)
            except RolloutError as e:
                if e.control == "C13":
                    abort(404)
                flash(str(e), "error")
        return redirect(url_for("enterprise_design", programme_id=programme_id))

    def _programme_plans_markdown(c, tenant_id: str, programme_id: int) -> str:
        """The programme plans, as markdown.

        Everything here is READ, never recomputed: the reference design's frozen summary,
        its frozen BOQ multiplied by the site count, the funding total. A report that
        recomputes is a report that can disagree with the thing it is reporting on -- and
        the one place that must never happen is the document the sponsor is funding from.
        """
        prog = documents.programme_facts(c, tenant_id, programme_id)
        design = rollout.current_design(c, tenant_id, programme_id)
        if design is None:
            return ("# " + str(prog["name"]) + " -- Programme Plans\n\n"
                    "This programme has no reference design yet. A programme opens into "
                    "its design at the Planning stage.\n")

        funding = rollout.funding_requirement(c, tenant_id, programme_id)
        boq = rollout.scaled_boq(c, tenant_id, programme_id)
        sites = rollout.site_projects(c, tenant_id, programme_id)
        summary = design["summary"] or {}
        cur = summary.get("currency") or ""
        path_label = dict(constants.DESIGN_PATHS).get(design["design_path"],
                                                      design["design_path"])

        out = ["# " + str(prog["name"]) + " -- Programme Plans", ""]
        out.append("**Programme code:** " + str(prog["code"]) + "  ")
        out.append("**Design path:** " + str(path_label) + "  ")
        out.append("**Sites in this programme:** " + str(funding["sites"]) + "  ")
        out.append("**Design status:** " + str(design["status"]))
        out.append("")
        out.append("## The reference design")
        out.append("")
        out.append("One design. Every site is this design -- same equipment, same bill of "
                   "quantities. Only the address changes.")
        out.append("")
        for label, key, unit in (
            ("PV array",      "pv_kw",       "kWp"),
            ("Modules",       "num_panels",  ""),
            ("Inverter",      "inverter_kw", "kW"),
            ("Battery",       "battery_kwh", "kWh"),
            ("Daily energy",  "daily_kwh",   "kWh/day"),
            ("Cost per site", "total_cost",  cur),
        ):
            value = summary.get(key)
            if value is not None:
                out.append("- **{}:** {:,.2f} {}".format(label, value, unit).rstrip())
        out.append("")
        out.append("## Scaled to the programme")
        out.append("")
        out.append("- **Sites:** " + str(funding["sites"]))
        if funding.get("kwp_total"):
            out.append("- **Total installed capacity:** "
                       "{:,.1f} kWp".format(funding["kwp_total"]))
        if funding.get("total"):
            out.append("- **Total funding required:** {} {:,.2f}".format(
                cur, funding["total"]))
            out.append("")
            out.append("Funding is sought ONCE, by the programme, for all locations -- "
                       "never per building.")
        out.append("")

        if boq["lines"]:
            out.append("## Bill of quantities -- programme total")
            out.append("")
            out.append("| Item | Unit | Per site | Total (x{}) |".format(boq["multiplier"]))
            out.append("|---|---|---|---|")
            for line in boq["lines"][:200]:
                out.append("| {} | {} | {} | {} |".format(
                    line["description"] or "",
                    line["unit"] or "",
                    "" if line["unit_qty"] is None else "{:,.2f}".format(line["unit_qty"]),
                    "" if line["total_qty"] is None
                    else "{:,.2f}".format(line["total_qty"])))
            out.append("")

        if sites:
            out.append("## Sites")
            out.append("")
            out.append("| Code | Site | Project | Survey findings |")
            out.append("|---|---|---|---|")
            for site in sites[:500]:
                out.append("| {} | {} | #{} | {} |".format(
                    site["code"] or "", site["name"] or "", site["project_id"],
                    "; ".join(site["flags"]) or "-"))
            out.append("")
        return "\n".join(out)

    @app.route("/enterprise/programmes/<int:programme_id>/plans.pdf")
    @login_required
    def enterprise_programme_plans(programme_id: int):
        """The output report: the plans of the programme, for the number of sites."""
        _require_module()
        uid = _uid()
        with get_db() as c:
            _ensure_schema_once(c)
            tenancy.apply_enterprise_guc(c, uid)
            active = _tenant(c, uid)
            try:
                rbac.require_permission(c, active, uid, "report.generate")
            except EnterprisePermissionError:
                abort(403)
            try:
                markdown = _programme_plans_markdown(c, active, programme_id)
            except EnterpriseGateError:
                abort(404)
            pdf = documents.render_pdf("Programme plans", markdown)
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={
                "Content-Disposition":
                    'attachment; filename="programme-plans-%d.pdf"' % programme_id,
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.route("/enterprise/jobs/drain", methods=["POST"])
    def enterprise_drain_jobs():
        """The worker. Called by a scheduled GitHub Action, never by a browser.

        There is no worker PROCESS and there cannot be one: Render's free tier caps this
        account at a single instance, and a second service was already refused on
        2026-07-10. So the queue is drained by an authenticated POST from a cron.

        AUTHENTICATED BY A SHARED SECRET, COMPARED IN CONSTANT TIME. A cron has no session,
        so there is nothing for @login_required to check and nothing for CSRF to protect --
        both are absent deliberately, and the bearer token is therefore the ONLY thing
        standing between a stranger and this programme's project generation. A plain `==`
        on a secret leaks its length and, given enough attempts, its bytes.

        AN UNSET SECRET IS A 404, NOT AN OPEN DOOR. If the environment variable is missing,
        this endpoint does not exist. The failure mode of a misconfiguration must never be
        "unguarded".
        """
        import hmac
        import os

        secret = os.environ.get("ENTERPRISE_JOB_TOKEN") or ""
        if not secret:
            abort(404)
        presented = request.headers.get("Authorization") or ""
        if not presented.startswith("Bearer "):
            abort(401)
        if not hmac.compare_digest(presented[7:], secret):
            abort(401)

        drained = []
        with get_db() as c:
            _ensure_schema_once(c)
            rows = c.execute(
                "SELECT id FROM enterprise_jobs "
                " WHERE status IN ('Queued','Running') AND job_type='generate_projects' "
                " ORDER BY created_at LIMIT 3"
            ).fetchall()
            for row in rows:
                try:
                    drained.append(rollout.drain_job(c, int(row[0])))
                except Exception as e:   # noqa: BLE001 -- one job must not kill the pass
                    drained.append({"job_id": int(row[0]), "status": "error",
                                    "error": str(e)[:200]})
        return {"drained": drained}, 200



# The document types the gate predicates actually look for. A form that offered anything
# else would let a user register a "business case" the gate cannot see.
REQUIRED_DOCUMENT_TYPES: dict[str, str] = {
    "concept_note":         "Concept Note (Gate 1)",
    "programme_charter":    "Programme Charter (Gate 2)",
    "beneficiary_register": "Beneficiary Register (Gate 3)",
    "business_case":        "Business Case (Gate 4)",
    "master_plan":          "Programme Master Plan (Gate 5)",
    "template_version_pack": "Template Version Pack (Gate 6)",
    "funding_strategy":     "Funding Strategy (Gate 7)",
    "signed_contract":      "Signed Contract (Gate 8)",
    "ifc_package":          "Issued-For-Construction Package (Gate 9)",
}
