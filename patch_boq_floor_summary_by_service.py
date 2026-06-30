"""Floor summary grouped by service (2026-06-30 owner directive).

User spec:
  Floor summary preparation is auto-made as section subtotals get done.
  For each service: list the section subtotals and total them. Place
  after the existing per-section table. After all services, establish
  the floor cost carried to the Building Summary.

Adds:
  * web_app.py boq_floor_summary handler: a third query that groups by
    service_code + section_letter + section, plus building the
    services_breakdown nested structure with per-service totals.
  * templates/boq_floor_summary.html: new 'Per-service breakdown' card
    rendered AFTER the existing Per-section breakdown card. Each
    service shows its sections listed with subtotals + a service total
    row. The final floor total + carried-to-Building-Summary row sits
    inside this card.

Idempotent: each replace checks the post-patch shape first.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d, old, new, label, *, crlf_target):
    if crlf_target:
        old_c, new_c = crlf(old), crlf(new)
    else:
        old_c, new_c = old, new
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# 1. web_app.py handler -- add per_service query + services_breakdown
# ============================================================
WEB = REPO / "web_app.py"
web = WEB.read_bytes()

W_OLD = b'''        per_section = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(section_letter,'') AS section_letter, "
            "       COALESCE(section,'') AS section_title, "
            "       COALESCE(SUM(total_amount),0) AS subtotal, "
            "       COUNT(*) AS row_count "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name, section_letter, section "
            "ORDER BY bill_no, section_letter",
            (fid,),
        ).fetchall()'''

W_NEW = b'''        per_section = c.execute(
            "SELECT COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(section_letter,'') AS section_letter, "
            "       COALESCE(section,'') AS section_title, "
            "       COALESCE(SUM(total_amount),0) AS subtotal, "
            "       COUNT(*) AS row_count "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY bill_no, bill_name, section_letter, section "
            "ORDER BY bill_no, section_letter",
            (fid,),
        ).fetchall()
        per_service = c.execute(
            "SELECT COALESCE(service_code,'') AS service_code, "
            "       COALESCE(bill_no,0) AS bill_no, "
            "       COALESCE(bill_name,'') AS bill_name, "
            "       COALESCE(section_letter,'') AS section_letter, "
            "       COALESCE(section,'') AS section_title, "
            "       COALESCE(SUM(total_amount),0) AS subtotal, "
            "       COUNT(*) AS row_count "
            "FROM boq_floor_items "
            "WHERE floor_id=? "
            "GROUP BY service_code, bill_no, bill_name, section_letter, section "
            "ORDER BY service_code, bill_no, section_letter",
            (fid,),
        ).fetchall()'''

web = replace_once(web, W_OLD, W_NEW, "1a: add per_service query", crlf_target=True)


# Now extend the bills/sections processing to ALSO build services_breakdown.
W_OLD2 = b'''    sections = [
        {
            "bill_no":        int(r["bill_no"] or 0),
            "bill_name":      (r["bill_name"]   or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "section_letter": (r["section_letter"] or "").upper(),
            "section_title":  (r["section_title"]  or ""),
            "subtotal":       float(r["subtotal"]  or 0),
            "row_count":      int(r["row_count"] or 0),
        }
        for r in per_section
    ]
    cont_pct = float((floor["contingency_pct"] if "contingency_pct" in floor.keys() else 10) or 10)
    contingency = subtotal * cont_pct / 100.0
    carried = subtotal + contingency
    return render_template(
        "boq_floor_summary.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=bills, sections=sections, subtotal=subtotal,
        contingency_pct=cont_pct, contingency=contingency,
        carried=carried,
    )'''

W_NEW2 = b'''    sections = [
        {
            "bill_no":        int(r["bill_no"] or 0),
            "bill_name":      (r["bill_name"]   or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "section_letter": (r["section_letter"] or "").upper(),
            "section_title":  (r["section_title"]  or ""),
            "subtotal":       float(r["subtotal"]  or 0),
            "row_count":      int(r["row_count"] or 0),
        }
        for r in per_section
    ]

    # Service-grouped breakdown (2026-06-30 owner directive). Items
    # without a service_code roll into an "Uncategorised" bucket so
    # legacy rows still appear.
    _svc_buckets = {}
    for r in per_service:
        code = (r["service_code"] or "").strip().lower()
        label = _BOQ_SERVICE_LABEL.get(code, code.replace("_", " ").title() if code else "Uncategorised")
        bucket = _svc_buckets.setdefault(code or "_uncategorised", {
            "code": code or "_uncategorised",
            "label": label,
            "sections": [],
            "service_total": 0.0,
        })
        sub = float(r["subtotal"] or 0)
        bucket["sections"].append({
            "bill_no":        int(r["bill_no"] or 0),
            "bill_name":      (r["bill_name"]   or _boq_lookup_bill_name(int(r["bill_no"] or 0)) or "OTHER"),
            "section_letter": (r["section_letter"] or "").upper(),
            "section_title":  (r["section_title"]  or ""),
            "subtotal":       sub,
            "row_count":      int(r["row_count"] or 0),
        })
        bucket["service_total"] += sub
    services_breakdown = list(_svc_buckets.values())
    services_breakdown.sort(key=lambda b: (b["code"] == "_uncategorised", -b["service_total"]))

    cont_pct = float((floor["contingency_pct"] if "contingency_pct" in floor.keys() else 10) or 10)
    contingency = subtotal * cont_pct / 100.0
    carried = subtotal + contingency
    return render_template(
        "boq_floor_summary.html",
        user=current_user(),
        project=project, building=building, floor=floor,
        bills=bills, sections=sections, services_breakdown=services_breakdown,
        subtotal=subtotal,
        contingency_pct=cont_pct, contingency=contingency,
        carried=carried,
    )'''

web = replace_once(web, W_OLD2, W_NEW2, "1b: build services_breakdown + pass to template", crlf_target=True)

WEB.write_bytes(web)


# ============================================================
# 2. templates/boq_floor_summary.html -- append service-grouped card
# ============================================================
FS = REPO / "templates" / "boq_floor_summary.html"
fs = FS.read_bytes()  # CRLF

# Append the new card AFTER the per-section card. Anchor on the closing
# `</div>` of the per-section card (the `{% endif %}` follows).
FS_OLD = b'''      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td colspan="4" class="text-end fw-black">FLOOR SUB TOTAL</td>
        <td class="text-end fw-black text-warning">{{ (subtotal)|money }}</td>
        <td class="text-end fw-black text-warning">100.0%</td>
      </tr>
    </tbody>
  </table>
</div>
{% endif %}'''

FS_NEW = b'''      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td colspan="4" class="text-end fw-black">FLOOR SUB TOTAL</td>
        <td class="text-end fw-black text-warning">{{ (subtotal)|money }}</td>
        <td class="text-end fw-black text-warning">100.0%</td>
      </tr>
    </tbody>
  </table>
</div>
{% endif %}

{% if services_breakdown %}
<div class="solar-card p-4 mt-3">
  <h6 class="fw-bold mb-3"><i class="bi bi-diagram-3 text-warning me-1"></i>Per-service breakdown (auto from section subtotals)</h6>

  {% for svc in services_breakdown %}
  <div class="mb-4" style="border-left:3px solid var(--solar-gold,#f59e0b);padding-left:12px">
    <div class="text-warning fw-bold mb-2" style="text-transform:uppercase;letter-spacing:.5px;font-size:13px">
      {{ svc.label }}
    </div>
    <table class="table table-sm align-middle mb-0" style="color:#e0e0f0;font-size:13px">
      <thead style="color:#9090c0;font-size:10px;text-transform:uppercase;letter-spacing:.5px">
        <tr>
          <th style="width:80px">Bill</th>
          <th style="width:60px">Section</th>
          <th>Title</th>
          <th class="text-end" style="width:70px">Rows</th>
          <th class="text-end">Subtotal</th>
          <th class="text-end" style="width:120px">% of Floor</th>
        </tr>
      </thead>
      <tbody>
        {% for s in svc.sections %}
        <tr>
          <td class="text-secondary small">{{ s.bill_no }}</td>
          <td class="fw-bold text-warning">{{ s.section_letter }}</td>
          <td class="small">{{ s.section_title }}</td>
          <td class="text-end small text-secondary">{{ s.row_count }}</td>
          <td class="text-end fw-bold">{{ (s.subtotal)|money }}</td>
          <td class="text-end text-secondary">{% if subtotal > 0 %}{{ '%.1f'|format(s.subtotal * 100 / subtotal) }}%{% else %}\xe2\x80\x94{% endif %}</td>
        </tr>
        {% endfor %}
        <tr style="background:rgba(245,158,11,.10);border-top:1px solid #1e1e3a">
          <td colspan="4" class="text-end fw-bold text-warning small" style="text-transform:uppercase;letter-spacing:.5px">
            {{ svc.label }} \xe2\x80\x94 Service Total
          </td>
          <td class="text-end fw-black text-warning">{{ (svc.service_total)|money }}</td>
          <td class="text-end fw-bold text-warning">{% if subtotal > 0 %}{{ '%.1f'|format(svc.service_total * 100 / subtotal) }}%{% else %}\xe2\x80\x94{% endif %}</td>
        </tr>
      </tbody>
    </table>
  </div>
  {% endfor %}

  <table class="table align-middle mb-0 mt-2" style="color:#e0e0f0;font-size:14px">
    <tbody>
      <tr style="background:rgba(245,158,11,.15);border-top:2px solid var(--solar-gold,#f59e0b)">
        <td class="fw-black" style="font-size:15px">FLOOR COST (sum of all service totals)</td>
        <td class="text-end fw-black text-warning" style="font-size:17px;width:160px">{{ (subtotal)|money }}</td>
        <td class="text-end fw-black text-warning" style="width:120px">100.0%</td>
      </tr>
      <tr style="background:rgba(245,158,11,.10);border-top:2px solid #1e1e3a">
        <td class="fw-black" style="font-size:15px">
          <a href="{{ url_for('boq_building_summary', pid=project.id, bid=building.id) }}" class="text-warning text-decoration-none">
            Carried to Building Summary <i class="bi bi-arrow-right-circle"></i>
          </a>
        </td>
        <td class="text-end fw-black text-warning" style="font-size:17px">{{ (carried)|fmt }}</td>
        <td class="text-end fw-black text-warning">{{ '%.1f'|format(100 + contingency_pct) }}%</td>
      </tr>
    </tbody>
  </table>
</div>
{% endif %}'''

fs = replace_once(fs, FS_OLD, FS_NEW, "2: append per-service breakdown card", crlf_target=True)
FS.write_bytes(fs)

print("done.")
