# -*- coding: utf-8 -*-
"""
patch_webapp_ci_autobuild.py
============================
Adds web_app._ci_autobuild_floor_items(): the reuse helper that lets the
Generation Station / Capital Investment Step 9 populate a floor's BOQ down to
the CELL level (boq_floor_items + boq_floor_rate_buildup) from a list of
existing _BOQ_SERVICES codes.

REUSES the platform engine end to end:
  * _services_loaded_sections()  -> sections (carrying service_code),
  * _boq_catalog_for_section() / _BOQ_SECTION_ITEM_CATALOG -> item catalog,
  * _boq_apply_overrides()       -> per-user catalog overrides,
  * boq_rate_v3()                -> the ONE BOQ rate formula.

Codex-review fixes folded in:
  * H1: writes boq_floor_items.service_code so the "remove dropped services"
        cleanup (DELETE ... WHERE service_code IN (...)) can reach these rows.
  * M4: writes tenant_id (from _kc_current_tenant_id()) on items + rate-buildup.

Catalog items are 3-tuples (desc, unit, basic); qty seeds to 1 like the
standard Build-all default. Idempotent per floor.

Byte-level, CRLF-aware (web_app.py is CRLF with mojibake - never edit as text).
Idempotent: re-running is a no-op if the helper is already present.
"""

PATH = "web_app.py"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


data = open(PATH, "rb").read()

if b"def _ci_autobuild_floor_items" in data:
    print("already patched - no-op")
    raise SystemExit(0)

ANCHOR = crlf("\r\n# === BEGIN: lv_panel_avr_seed splice ===\r\n")
assert data.count(ANCHOR) == 1, "anchor not unique/found"

HELPER = crlf('''

def _ci_autobuild_floor_items(fid, bid, pid, uid, service_codes):
    """Auto-populate one floor's BOQ line items (the CELL level) from a list of
    _BOQ_SERVICES codes, REUSING the standard section/item catalog and the
    standard rate engine (boq_rate_v3). Default rates match the standard
    Build-all (OH 10 / Profit 15 / VAT 12.5 / Supply 10 / Install 15).

    Writes service_code (so the project-edit "remove dropped services" cleanup
    can delete these rows) and tenant_id (defence-in-depth). Idempotent per
    floor: if the floor already has items, does nothing. Returns the count of
    line items inserted.
    """
    codes = [c for c in (service_codes or [])
             if c in _BOQ_SERVICE_BILL_SKELETON]
    if not codes:
        return 0
    try:
        tid = _kc_current_tenant_id()
    except Exception:
        tid = None

    # Expand each loaded section into its catalog items - the SAME catalog +
    # override path the standard Build-all page uses.
    sections = _services_loaded_sections(codes)
    _cat_dict = globals().get("_BOQ_SECTION_ITEM_CATALOG", {}) or {}
    rows = []
    for sec in sections:
        title = (sec.get("section_title") or "").strip()
        try:
            cat = _boq_catalog_for_section(title) or []
        except Exception:
            cat = []
        if not cat and title:
            tnorm = "".join(ch for ch in title.upper() if ch.isalnum())
            for k, v in _cat_dict.items():
                kn = "".join(ch for ch in str(k).upper() if ch.isalnum())
                if kn and tnorm and (kn == tnorm or kn in tnorm
                                     or tnorm in kn):
                    cat = list(v)
                    break
        try:
            cat = _boq_apply_overrides(uid, cat) if cat else cat
        except Exception:
            pass
        for item in (cat or []):
            if isinstance(item, dict):
                idesc = item.get("desc")
                iunit = item.get("unit") or "No."
                iqty = item.get("qty")
                iqty = 1.0 if iqty in (None, "", 0) else iqty
                ibasic = item.get("basic")
                ispec = item.get("spec", "")
            else:
                # catalog tuple (desc, unit, basic); qty seeds to 1.
                seq = list(item) if isinstance(item, (tuple, list)) else []
                idesc = seq[0] if len(seq) > 0 else ""
                iunit = (seq[1] if len(seq) > 1 else "No.") or "No."
                ibasic = seq[2] if len(seq) > 2 else 0
                ispec = seq[3] if len(seq) > 3 else ""
                iqty = 1.0
            rows.append({
                "bill_no":          sec.get("bill_no"),
                "bill_name":        sec.get("bill_name"),
                "section_letter":   sec.get("section_letter"),
                "section_title":    title,
                "subsection_label": sec.get("subsection", ""),
                "service_code":     sec.get("service_code", ""),
                "desc":             idesc,
                "unit":             iunit,
                "qty":              iqty,
                "basic":            ibasic,
                "spec":             ispec,
            })
    if not rows:
        return 0

    try:
        from boq_rate_v3 import boq_rate_v3
    except Exception:
        boq_rate_v3 = None

    floor_oh, floor_prf, floor_vat = 10.0, 15.0, 12.5
    floor_sp, floor_ip, floor_vinb = 10.0, 15.0, 0

    inserted = 0
    next_no_by_sec = {}
    with get_db() as c:
        # Idempotency guard: never double-populate a floor.
        try:
            existing = c.execute(
                "SELECT id FROM boq_floor_items WHERE floor_id=? LIMIT 1",
                (fid,)).fetchone()
        except Exception:
            existing = None
        if existing is not None:
            return 0

        for r in rows:
            try:
                basic = float(r.get("basic") or 0.0)
                qty = float(r.get("qty") or 0.0)
            except (TypeError, ValueError):
                continue
            desc = (r.get("desc") or "").strip()
            if not desc or qty <= 0 or basic <= 0:
                continue

            if boq_rate_v3:
                supply_amt, install_amt, total_rate = boq_rate_v3(
                    basic, floor_sp, floor_ip, floor_oh, floor_prf, floor_vat,
                    vat_in_basic=bool(floor_vinb))
            else:
                eff_vat = 0 if floor_vinb else floor_vat
                supply_amt = basic * (
                    floor_sp + floor_oh + floor_prf + eff_vat) / 100.0
                install_amt = basic * floor_ip / 100.0
                total_rate = basic + supply_amt + install_amt
            total = qty * total_rate

            bill_no = int(r.get("bill_no") or 0)
            letter = (r.get("section_letter") or "").upper()[:8]
            title = (r.get("section_title") or "").strip()[:80]
            bill_nm = (r.get("bill_name") or "").strip()[:120]
            sublbl = (r.get("subsection_label") or "").strip()[:200]
            unit = (r.get("unit") or "No.").strip()[:20] or "No."
            spec_t = (r.get("spec") or "").strip()
            svc = (r.get("service_code") or "")[:40]

            sec_key = (bill_no, letter)
            if sec_key not in next_no_by_sec:
                try:
                    next_no_by_sec[sec_key] = int(
                        _boq_next_item_no(fid, bill_no, letter))
                except Exception:
                    next_no_by_sec[sec_key] = 1
            item_no_disp = str(next_no_by_sec[sec_key])
            next_no_by_sec[sec_key] += 1

            cur = c.execute(
                "INSERT INTO boq_floor_items ("
                "  floor_id, building_id, project_id, user_id, tenant_id, "
                "  service_code, section, subsection, "
                "  bill_no, bill_name, section_letter, subsection_label, "
                "  item_no, item_no_display, "
                "  description, specification, unit, qty, "
                "  final_built_up_rate, total_amount, "
                "  source_type, approval_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fid, bid, pid, uid, tid,
                    svc, title[:80], "",
                    bill_no, bill_nm[:120], letter, sublbl[:200],
                    item_no_disp, item_no_disp,
                    desc[:500], spec_t, unit[:20], qty,
                    total_rate, total,
                    "capital_autobuild", "project_only",
                ),
            )
            new_id = int(cur.lastrowid or 0)
            inserted += 1

            try:
                c.execute(
                    "INSERT INTO boq_floor_rate_buildup ("
                    "  floor_item_id, project_id, user_id, tenant_id, "
                    "  basic_price, supply_rate, install_rate, "
                    "  overhead_pct, profit_pct, contingency_pct, vat_pct, "
                    "  supply_pct, install_pct, vat_in_basic, "
                    "  final_built_up_rate, total_amount) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        new_id, pid, uid, tid,
                        basic, supply_amt, install_amt,
                        floor_oh, floor_prf, 0.0, floor_vat,
                        floor_sp, floor_ip, floor_vinb,
                        total_rate, total,
                    ),
                )
            except Exception:
                pass

        try:
            c.execute(
                "UPDATE boq_floors SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (fid,))
        except Exception:
            pass
    return inserted

''')

data = data.replace(ANCHOR, HELPER + ANCHOR, 1)
open(PATH, "wb").write(data)
print("web_app.py patched OK - _ci_autobuild_floor_items inserted "
      "(service_code + tenant_id)")
