"""Live per-section subtotal on Build-all (2026-06-30 owner directive).

User wants the amount in each cell of a section to total up into a
visible subtotal at the bottom of THAT section's table, in real time,
so they can quality-check the math as they enter data.

Changes:
  1. templates/_boq_section_grid_inline.html: add a <tfoot> row to the
     editable table with a `data-section-live-total="<sid>"` span.
  2. templates/boq_floor_build_all.html: extend the existing recalcAll
     function so it accumulates per-section amounts AND updates each
     section's live span (in addition to the existing floor-wide
     total). Only ticked rows contribute (consistent with how
     recalcRow returns 0 for unticked rows).

Re-runnable. Pure UI change. No backend, no schema, no data.
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
CRLF = b"\r\n"

def crlf(s: bytes) -> bytes:
    return s.replace(b"\r\n", b"\n").replace(b"\n", CRLF)

def replace_once(d, old, new, label):
    old_c, new_c = crlf(old), crlf(new)
    if new_c in d:
        print(f"  {label}: already patched, skipping")
        return d
    n = d.count(old_c)
    if n != 1:
        sys.exit(f"  {label}: expected 1 OLD match, found {n}")
    print(f"  {label}: patched")
    return d.replace(old_c, new_c, 1)


# ============================================================
# 1. Grid template -- add tfoot live subtotal row
# ============================================================
G = REPO / "templates" / "_boq_section_grid_inline.html"
g = G.read_bytes()

G_OLD = b'''        {% endfor %}
        {% if not catalog %}
        <tr><td colspan="12" class="text-secondary text-center small fst-italic py-2">No catalog items for this section yet. Use "Open standalone editor" to add custom items.</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>'''

G_NEW = b'''        {% endfor %}
        {% if not catalog %}
        <tr><td colspan="12" class="text-secondary text-center small fst-italic py-2">No catalog items for this section yet. Use "Open standalone editor" to add custom items.</td></tr>
        {% endif %}
      </tbody>
      <tfoot>
        <tr style="background:rgba(245,158,11,.08);border-top:2px solid var(--solar-gold,#f59e0b)">
          <td colspan="11" class="text-end fw-bold text-warning" style="text-transform:uppercase;letter-spacing:.5px;font-size:11px">
            Section {{ section_letter }} subtotal &mdash; ticked rows, live
          </td>
          <td class="text-end fw-black text-warning" style="font-size:15px">
            <span data-section-live-total="{{ sid }}">0</span>
          </td>
        </tr>
      </tfoot>
    </table>
  </div>'''

g = replace_once(g, G_OLD, G_NEW, "1: add tfoot live subtotal row")
G.write_bytes(g)


# ============================================================
# 2. Build-all template -- extend recalcAll to update per-section
# ============================================================
B = REPO / "templates" / "boq_floor_build_all.html"
b = B.read_bytes()

B_OLD = b'''    function recalcAll() {
      var sum = 0;
      document.querySelectorAll('tr.boq-row').forEach(function(tr){
        sum += recalcRow(tr);
      });
      var nf = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
      var el = fId('floor_total_live');
      if (el) el.textContent = nf.format(Math.round(sum));
    }'''

B_NEW = b'''    function recalcAll() {
      var sum = 0;
      // Per-section accumulator. Keyed by data-sid; only TICKED row
      // amounts contribute (recalcRow returns 0 for unticked rows).
      var perSection = {};
      document.querySelectorAll('tr.boq-row').forEach(function(tr){
        var amt = recalcRow(tr);
        sum += amt;
        var sid = tr.dataset && tr.dataset.sid;
        if (sid) {
          perSection[sid] = (perSection[sid] || 0) + amt;
        }
      });
      var nf = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});
      // Update each section's live subtotal span.
      Object.keys(perSection).forEach(function(sid){
        var el = document.querySelector('[data-section-live-total="' + sid + '"]');
        if (el) el.textContent = nf.format(Math.round(perSection[sid]));
      });
      // Sections that have NO ticked rows still need to reset to 0.
      document.querySelectorAll('[data-section-live-total]').forEach(function(el){
        var sid = el.dataset.sectionLiveTotal;
        if (sid && perSection[sid] === undefined) {
          el.textContent = '0';
        }
      });
      var el = fId('floor_total_live');
      if (el) el.textContent = nf.format(Math.round(sum));
    }'''

b = replace_once(b, B_OLD, B_NEW, "2: recalcAll per-section accumulator")
B.write_bytes(b)

print("done.")
