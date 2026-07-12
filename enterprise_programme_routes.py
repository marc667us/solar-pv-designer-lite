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
    abort, flash, redirect, render_template, request, session, url_for
)

from app.enterprise_programme import (
    constants, dropdowns, flags, gates, rbac, tenancy, workflows,
)
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
    _schema_ready: dict[str, bool] = {"done": False}

    def _ensure_schema_once(c) -> None:
        if _schema_ready["done"]:
            return
        tenancy.ensure_schema(c)    # no-op on Postgres
        workflows.ensure_schema(c)  # no-op on Postgres
        _schema_ready["done"] = True

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
