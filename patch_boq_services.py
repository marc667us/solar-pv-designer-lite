#!/usr/bin/env python3
"""patch_boq_services.py -- 2026-06-22 (session A).

Three byte-level patches against web_app.py + an idempotent splice of
new_boq_services_engine.py:

  (1) Add `services_csv` column to boq_projects (SQLite + Postgres ALTER).
  (2) boq_projects_new POST: persist services_csv from form.
  (3) boq_projects_new GET: pass _BOQ_SERVICES catalogue to template.
  (4) boq_template_picker: enrich matched/others rows with service tags +
      project-coverage flag. Surface chosen services on the picker page.
  (5) boq_template_view: call _inject_service_bills() so any chosen service
      missing from the template is appended as a placeholder bill.
  (6) Splice the engine module (`new_boq_services_engine.py`) into web_app.py
      so its functions and registries are importable from the routes.

Each patch is gated on its needle. Re-running is safe.
"""
from __future__ import annotations
import sys

PATH = "web_app.py"
NEW  = "new_boq_services_engine.py"
BEGIN = b"# === BEGIN: boq_services_engine splice ==="
END   = b"# === END: boq_services_engine splice ==="

def main():
    with open(PATH, "rb") as fh:
        data = fh.read()
    new_block = open(NEW, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    orig_len = len(data)
    log = []

    # ---- (6) Splice engine module --------------------------------------
    if BEGIN in data and END in data:
        s = data.find(BEGIN)
        e = data.find(END, s) + len(END)
        data = data[:s] + new_block.rstrip(b"\r\n") + data[e:]
        log.append("(6) services-engine block replaced.")
    else:
        anchor = b"if __name__ == \"__main__\":"
        pos = data.rfind(anchor)
        if pos < 0:
            log.append("(6) `if __name__` anchor not found -- aborting.")
            print("\n".join(log)); sys.exit(2)
        data = data[:pos] + new_block + b"\r\n\r\n" + data[pos:]
        log.append("(6) services-engine block spliced before __main__.")

    # ---- (1) Add services_csv ALTER to boq_projects --------------------
    # Find _boq_ensure_schema or, failing that, splice next to product_categories
    # ALTERs we added earlier (those run on every BOM hit which is good enough).
    needle_alter_anchor = (
        b"        # 2026-06-22 (session A): per-category taxonomy storage for the\r\n"
        b"        # admin Manage Categories page. Idempotent on both engines.\r\n"
        b"        for _ddl in (\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN default_unit TEXT DEFAULT 'No.'\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN subcategories_csv TEXT DEFAULT ''\",\r\n"
        b"            \"ALTER TABLE product_categories ADD COLUMN spec_fields_csv TEXT DEFAULT ''\",\r\n"
        b"        ):\r\n"
        b"            try:\r\n"
        b"                with get_db() as _c:\r\n"
        b"                    _c.execute(_ddl)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
    )
    add_alter = (
        b"        # 2026-06-22 (session A): services_csv on boq_projects.\r\n"
        b"        for _ddl in (\r\n"
        b"            \"ALTER TABLE boq_projects ADD COLUMN services_csv TEXT DEFAULT ''\",\r\n"
        b"        ):\r\n"
        b"            try:\r\n"
        b"                with get_db() as _c:\r\n"
        b"                    _c.execute(_ddl)\r\n"
        b"            except Exception:\r\n"
        b"                pass\r\n"
    )
    if needle_alter_anchor in data and add_alter not in data:
        data = data.replace(needle_alter_anchor, needle_alter_anchor + add_alter, 1)
        log.append("(1) boq_projects.services_csv ALTER spliced.")
    elif add_alter in data:
        log.append("(1) boq_projects.services_csv ALTER already present.")
    else:
        log.append("(1) services_csv ALTER anchor missing -- run earlier patches first.")

    # ---- (2) boq_projects_new POST: persist services_csv ---------------
    n2 = (
        b"        ext_works = 1 if f.get(\"external_works_included\") else 0\r\n"
        b"        infra = 1 if f.get(\"infrastructure_included\") else 0\r\n"
        b"        if not name:\r\n"
        b"            flash(\"Project name is required.\", \"warning\")\r\n"
        b"            return redirect(url_for(\"boq_projects_new\"))\r\n"
        b"        with get_db() as c:\r\n"
        b"            cur = c.execute(\r\n"
        b"                \"INSERT INTO boq_projects (user_id, project_name, client_name, \"\r\n"
        b"                \"location, project_type, external_works_included, infrastructure_included) \"\r\n"
        b"                \"VALUES (?,?,?,?,?,?,?)\",\r\n"
        b"                (uid, name, client, location, ptype, ext_works, infra),\r\n"
        b"            )\r\n"
        b"            pid = int(cur.lastrowid or 0)\r\n"
    )
    r2 = (
        b"        ext_works = 1 if f.get(\"external_works_included\") else 0\r\n"
        b"        infra = 1 if f.get(\"infrastructure_included\") else 0\r\n"
        b"        # 2026-06-22 services step: persist selected codes (csv)\r\n"
        b"        _chosen_services = [c for c in (f.getlist(\"services\") or []) if c in _BOQ_SERVICE_LABEL]\r\n"
        b"        services_csv = \",\".join(_chosen_services)\r\n"
        b"        if not name:\r\n"
        b"            flash(\"Project name is required.\", \"warning\")\r\n"
        b"            return redirect(url_for(\"boq_projects_new\"))\r\n"
        b"        if not _chosen_services:\r\n"
        b"            flash(\"Select at least one service the BOQ must cover.\", \"warning\")\r\n"
        b"            return redirect(url_for(\"boq_projects_new\"))\r\n"
        b"        with get_db() as c:\r\n"
        b"            # services_csv column was ALTERed in (1); on a fresh DB it's part of the schema.\r\n"
        b"            try:\r\n"
        b"                cur = c.execute(\r\n"
        b"                    \"INSERT INTO boq_projects (user_id, project_name, client_name, \"\r\n"
        b"                    \"location, project_type, external_works_included, infrastructure_included, services_csv) \"\r\n"
        b"                    \"VALUES (?,?,?,?,?,?,?,?)\",\r\n"
        b"                    (uid, name, client, location, ptype, ext_works, infra, services_csv),\r\n"
        b"                )\r\n"
        b"            except Exception:\r\n"
        b"                cur = c.execute(\r\n"
        b"                    \"INSERT INTO boq_projects (user_id, project_name, client_name, \"\r\n"
        b"                    \"location, project_type, external_works_included, infrastructure_included) \"\r\n"
        b"                    \"VALUES (?,?,?,?,?,?,?)\",\r\n"
        b"                    (uid, name, client, location, ptype, ext_works, infra),\r\n"
        b"                )\r\n"
        b"            pid = int(cur.lastrowid or 0)\r\n"
    )
    if n2 in data:
        data = data.replace(n2, r2, 1)
        log.append("(2) boq_projects_new POST persists services_csv.")
    elif b"_chosen_services = [c for c in (f.getlist(\"services\") or [])" in data:
        log.append("(2) boq_projects_new POST already persists services_csv.")
    else:
        log.append("(2) boq_projects_new POST anchor NOT FOUND.")

    # ---- (3) boq_projects_new GET: pass services catalogue -------------
    n3 = b"    return render_template(\"boq_project_new.html\", user=current_user())\r\n"
    r3 = b"    return render_template(\"boq_project_new.html\", user=current_user(), services=_BOQ_SERVICES)\r\n"
    if n3 in data:
        data = data.replace(n3, r3, 1)
        log.append("(3) boq_projects_new GET passes services catalogue.")
    elif b"services=_BOQ_SERVICES" in data:
        log.append("(3) boq_projects_new GET already passes services.")
    else:
        log.append("(3) boq_projects_new GET anchor NOT FOUND.")

    # ---- (4) boq_template_picker: enrich rows + pass chosen services ---
    n4 = (
        b"    from new_boq_project_templates import _boq_template_list\r\n"
        b"    # Filter by building purpose where possible; show all if none match.\r\n"
        b"    purpose = (building[\"primary_purpose\"] or \"\").strip().lower()\r\n"
        b"    matched = _boq_template_list(purpose=purpose)\r\n"
        b"    others  = [t for t in _boq_template_list() if t[\"slug\"] not in {m[\"slug\"] for m in matched}]\r\n"
        b"    return render_template(\r\n"
        b"        \"boq_template_picker.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        project=project, building=building, floor=floor,\r\n"
        b"        matched=matched, others=others, purpose=purpose,\r\n"
        b"    )\r\n"
    )
    r4 = (
        b"    from new_boq_project_templates import _boq_template_list, _boq_template_get\r\n"
        b"    # Filter by building purpose where possible; show all if none match.\r\n"
        b"    purpose = (building[\"primary_purpose\"] or \"\").strip().lower()\r\n"
        b"    matched = _boq_template_list(purpose=purpose)\r\n"
        b"    others  = [t for t in _boq_template_list() if t[\"slug\"] not in {m[\"slug\"] for m in matched}]\r\n"
        b"    # 2026-06-22 services: tag every template card with the services it covers + a\r\n"
        b"    # match-count vs the project's chosen services so the UI can highlight winners.\r\n"
        b"    try:\r\n"
        b"        _services_csv = (project[\"services_csv\"] if \"services_csv\" in project.keys() else \"\") or \"\"\r\n"
        b"    except Exception:\r\n"
        b"        _services_csv = \"\"\r\n"
        b"    chosen = _services_csv_to_list(_services_csv)\r\n"
        b"    chosen_set = set(chosen)\r\n"
        b"    def _enrich(t):\r\n"
        b"        full = _boq_template_get(t[\"slug\"]) or {}\r\n"
        b"        svc = _template_services(full)\r\n"
        b"        matches = [s for s in svc if s in chosen_set]\r\n"
        b"        t[\"services\"] = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in svc]\r\n"
        b"        t[\"match_count\"] = len(matches)\r\n"
        b"        return t\r\n"
        b"    matched = [_enrich(t) for t in matched]\r\n"
        b"    others  = [_enrich(t) for t in others]\r\n"
        b"    matched.sort(key=lambda t: -t[\"match_count\"])\r\n"
        b"    others.sort(key=lambda t: -t[\"match_count\"])\r\n"
        b"    # Services chosen but no template / no skeleton covers them.\r\n"
        b"    all_template_svc = set()\r\n"
        b"    for tt in matched + others:\r\n"
        b"        for s, _, _ in tt[\"services\"]:\r\n"
        b"            all_template_svc.add(s)\r\n"
        b"    uncovered = [s for s in chosen if s not in all_template_svc]\r\n"
        b"    chosen_view = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in chosen]\r\n"
        b"    uncovered_view = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in uncovered]\r\n"
        b"    return render_template(\r\n"
        b"        \"boq_template_picker.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        project=project, building=building, floor=floor,\r\n"
        b"        matched=matched, others=others, purpose=purpose,\r\n"
        b"        chosen_services=chosen_view, uncovered_services=uncovered_view,\r\n"
        b"    )\r\n"
    )
    if n4 in data:
        data = data.replace(n4, r4, 1)
        log.append("(4) boq_template_picker now tags templates with services + sorts.")
    elif b"chosen_set = set(chosen)" in data:
        log.append("(4) boq_template_picker already enriched.")
    else:
        log.append("(4) boq_template_picker anchor NOT FOUND.")

    # ---- (5) boq_template_view: inject service bills -------------------
    n5 = (
        b"    from new_boq_project_templates import _boq_template_get\r\n"
        b"    template = _boq_template_get(slug)\r\n"
        b"    if not template:\r\n"
        b"        flash(\"Template not found.\", \"warning\")\r\n"
        b"        return redirect(url_for(\"boq_template_picker\", pid=pid, bid=bid, fid=fid))\r\n"
        b"    return render_template(\r\n"
        b"        \"boq_template_checkbox.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        project=project, building=building, floor=floor,\r\n"
        b"        template=template, slug=slug,\r\n"
        b"    )\r\n"
    )
    r5 = (
        b"    from new_boq_project_templates import _boq_template_get\r\n"
        b"    template = _boq_template_get(slug)\r\n"
        b"    if not template:\r\n"
        b"        flash(\"Template not found.\", \"warning\")\r\n"
        b"        return redirect(url_for(\"boq_template_picker\", pid=pid, bid=bid, fid=fid))\r\n"
        b"    # 2026-06-22 services: inject extra bills for any chosen service the\r\n"
        b"    # template doesn't already cover.\r\n"
        b"    try:\r\n"
        b"        _scsv = (project[\"services_csv\"] if \"services_csv\" in project.keys() else \"\") or \"\"\r\n"
        b"    except Exception:\r\n"
        b"        _scsv = \"\"\r\n"
        b"    chosen = _services_csv_to_list(_scsv)\r\n"
        b"    template = _inject_service_bills(template, chosen)\r\n"
        b"    injected = template.get(\"_services_injected\") or []\r\n"
        b"    chosen_view = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in chosen]\r\n"
        b"    injected_view = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in injected]\r\n"
        b"    return render_template(\r\n"
        b"        \"boq_template_checkbox.html\",\r\n"
        b"        user=current_user(),\r\n"
        b"        project=project, building=building, floor=floor,\r\n"
        b"        template=template, slug=slug,\r\n"
        b"        chosen_services=chosen_view, injected_services=injected_view,\r\n"
        b"    )\r\n"
    )
    if n5 in data:
        data = data.replace(n5, r5, 1)
        log.append("(5) boq_template_view injects service bills.")
    elif b"chosen_view = [(s, _BOQ_SERVICE_LABEL[s], _BOQ_SERVICE_ICON[s]) for s in chosen]" in data:
        log.append("(5) boq_template_view already injects services.")
    else:
        log.append("(5) boq_template_view anchor NOT FOUND.")

    if len(data) == orig_len and data == open(PATH, "rb").read():
        log.append("\nNo changes -- already patched.")
        print("\n".join(log))
        return
    with open(PATH, "wb") as fh:
        fh.write(data)
    log.append(f"\nwrote {PATH} ({orig_len} -> {len(data)} bytes)")
    print("\n".join(log))

if __name__ == "__main__":
    main()
