"""CONSOLIDATED patch — PURC Q3 2026 tariff refresh + Energy Coverage Analysis
(Slice 1 + Slice 2 reports), incorporating all Codex + Supervisor fixes.
Byte-level only (CLAUDE.md Pattern A/B). Run once on a pristine web_app.py."""
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()
open(PATH + ".bak_precoverage", "wb").write(data)

if b"def _bc_coverage(" in data:
    print("ALREADY PATCHED — aborting.")
    sys.exit(0)


def repl(old, new, expect):
    global data
    n = data.count(old)
    assert n == expect, f"expected {expect} of {old!r}, found {n}"
    data = data.replace(old, new)


# ── 1. PURC Q2 2026 → Q3 2026 (electricity +3.49%, effective 1 Jul 2026) ──────
repl(b'"rate_ghc":   0.8690,', b'"rate_ghc":   0.8993,', 1)   # lifeline (published)
repl(b'"rate_ghc":   1.9688,', b'"rate_ghc":   2.0375,', 1)   # res std
repl(b'"rate_ghc":   2.6015,', b'"rate_ghc":   2.6923,', 1)   # res high
repl(b'"rate_ghc":   1.7775,', b'"rate_ghc":   1.8395,', 1)   # non-res std
repl(b'"rate_ghc":   2.1649,', b'"rate_ghc":   2.2405,', 1)   # non-res high
repl(b'"rate_ghc":   2.3211,', b'"rate_ghc":   2.4021,', 1)   # SLT-LV
repl(b'"rate_ghc":   2.0160,', b'"rate_ghc":   2.0864,', 3)   # SLT-MV / Ind-LV / EV
repl(b'"rate_ghc":   1.3204,', b'"rate_ghc":   1.3665,', 1)   # SLT-MV-2
repl(b'"rate_ghc":   1.8212,', b'"rate_ghc":   1.8848,', 2)   # SLT-HV / Ind-HV
repl(b'"fixed_ghc":  2.13,',    b'"fixed_ghc":  2.2043,',  1)  # lifeline
repl(b'"fixed_ghc":  10.7309,', b'"fixed_ghc":  11.1054,', 2)  # residential
repl(b'"fixed_ghc":  12.4282,', b'"fixed_ghc":  12.8619,', 2)  # non-residential
repl(b'"fixed_ghc":  500.00,',  b'"fixed_ghc":  517.45,',  7)  # SLT / industrial / EV
repl(b'Ghana PURC Tariff Schedule (Q2 2026, effective April 1 2026)',
     b'Ghana PURC Tariff Schedule (Q3 2026, effective July 1 2026)', 1)
repl(b'# Source: PURC "2026 Second Quarter Tariff Review Decision", 13-03-2026.',
     b'# Source: PURC "2026 Third Quarter Tariff Review Decision" (+3.49% electricity, eff. 1 Jul 2026).',
     1)
repl(b'"effective_from":   "2026-04-01",', b'"effective_from":   "2026-07-01",', 1)
repl(b'"published_on":     "2026-03-13",', b'"published_on":     "2026-06-22",', 1)
repl(b'"quarter":          "Q2 2026",',    b'"quarter":          "Q3 2026",', 1)
repl(b'"source_url":       "https://www.purc.com.gh/attachment/288818-20260313090334.pdf",',
     b'"source_url":       "https://ecg.com.gh/index.php/en/services/billing-centre/current-tariff",',
     1)
repl(b'"source_title":     "PURC 2026 Second Quarter Tariff Review Decision",',
     b'"source_title":     "PURC 2026 Third Quarter Tariff Review Decision",', 1)
repl(b'"adjustment_note": "Residential -1.66% vs Q1 2026; SLT-LV -13.96%; HV -15.43%.",',
     b'"adjustment_note": "Q3 2026: electricity +3.49% flat vs Q2 (eff. 1 Jul 2026). '
     b'Lifeline 89.93 p/kWh published exact; other bands scaled +3.49% pending per-category gazette PDF.",',
     1)

# ── 2. User-facing PURC copy Q2 2026 -> Q3 2026 (math is now Q3) ──────────────
n_q = data.count(b"Q2 2026"); data = data.replace(b"Q2 2026", b"Q3 2026")
n_d = data.count(b"2026-04-01"); data = data.replace(b"2026-04-01", b"2026-07-01")
print(f"copy: {n_q} 'Q2 2026', {n_d} '2026-04-01' updated")

# ── 3. Wire coverage recompute (design save + bill-check save + results GET) ──
repl(b'            "ac_cables":    ac_cables,\r\n        }\r\n        save_project_data(pid, data)',
     b'            "ac_cables":    ac_cables,\r\n        }\r\n'
     b'        _bc_refresh_coverage(data)\r\n        save_project_data(pid, data)', 1)

repl(b'    data["bill_check"] = result\r\n    save_project_data(pid, data)',
     b'    data["bill_check"] = result\r\n    _bc_refresh_coverage(data)\r\n'
     b'    save_project_data(pid, data)', 1)

# results GET: in-memory refresh for display ONLY — no DB write on a GET.
repl(b'    recs = calc_recommendations(r["economics"], project["data"], r)\r\n'
     b'    return render_template("results.html", user=current_user(),',
     b'    recs = calc_recommendations(r["economics"], project["data"], r)\r\n'
     b'    if project["data"].get("bill_check") and not project["data"].get("coverage"):\r\n'
     b'        try:\r\n'
     b'            _bc_refresh_coverage(project["data"])  # in-memory display only\r\n'
     b'        except Exception:\r\n'
     b'            pass\r\n'
     b'    return render_template("results.html", user=current_user(),', 1)

# ── 4. Report injections next to the existing _bill_check_md sites ────────────
repl(b'{_bill_check_md(d)}\r\n# Monthly Energy Generation & Savings',
     b'{_bill_check_md(d)}\r\n{_coverage_md(d)}# Monthly Energy Generation & Savings', 1)
repl(b'    md += _bill_check_md(d)\r\n    for reason in eco["verdict_reasons"]:',
     b'    md += _bill_check_md(d)\r\n    md += _coverage_md(d)\r\n    for reason in eco["verdict_reasons"]:', 1)

# ── 5. Insert helper blocks (Pattern B) before if __name__ ───────────────────
def crlf(p):
    b = open(p, "rb").read()
    return b.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

block = crlf("_coverage_helpers.py") + b"\r\n\r\n" + crlf("_coverage_md.py") + b"\r\n\r\n"
TARGET = b'if __name__ == "__main__":'
pos = data.rfind(TARGET)
assert pos != -1
data = data[:pos] + block + data[pos:]

open(PATH, "wb").write(data)
print("PATCH OK — bytes now:", len(data))
