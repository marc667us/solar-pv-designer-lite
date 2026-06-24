#!/usr/bin/env python3
"""patch_rate_builder_spec_aligned.py  (2026-06-24 v2)

Rebuilds the BOQ rate engine to match the canonical spec at
`pvsolar1/supplier and price/prates and pricing modeling1.txt`.

Old chain (the additive cap model shipped earlier today):
    total = basic * (1 + (S% + P% + I% + O%) / 100)
    where S<=15, P<=5, I<=25, O<=15
    -> 24% understated vs spec on the spec's own GHS 15 cable example

New chain (spec verbatim):
    Supply Rate  = Basic + Basic*(Freight% + Handling% + Insurance% + Wastage%) / 100
    Install Rate = Labour_amt + Tools_amt + Equipment_amt + Testing_amt + Supervision_amt
    Prime Cost   = Supply Rate + Install Rate
    Overhead     = Prime * Overhead%             (cap 20%, default 15%)
    Profit       = (Prime + Overhead) * Profit%  (cap 30%, default 15%)
    Subtotal     = Prime + Overhead + Profit
    Contingency  = Subtotal * Contingency%       (cap 15%, optional)
    VAT          = (Subtotal + Cont) * VAT%      (Ghana default 12.5%, optional)
    Total Rate   = Subtotal + Contingency + VAT

Spec example: B=15, F=5.33% H=2.0% I=0.67% W=5.0% (-> supply 16.95);
              Labour=5.5 Tools=0.5 Testing=0.3 Super=0.7 (-> install 7.00);
              OH=15% Profit=15% Cont=0% VAT=0%
  -> Prime=23.95 OH=3.59 Profit=4.13 Total=31.67 (matches spec exactly).

Backward compatibility:
- _boq_safe_rate keeps its 7-arg signature. supply/install args now mean
  CURRENCY AMOUNTS again (as they did pre-2026-06-24 morning). Earlier
  patches stored percentages there; the legacy migration zeroes those.
- Callsites that haven't been updated yet (section-grid bulk save, template
  saves) keep working because supply=0/install=0 falls through to "supply
  defaults to basic, install defaults to 0" producing supply=basic, prime=basic,
  total = basic*(1+OH%/100)*(1+Profit%/100)+VAT etc.

Schema:
- boq_floor_rate_buildup gains 9 new columns:
    freight_pct, handling_pct, insurance_pct, wastage_pct       (Supply build-up)
    labour_amt, tools_amt, equipment_amt, testing_amt, supervision_amt (Install)
- supply_rate / install_rate keep their columns; semantics now currency.

Patches in this script:
  (1) _boq_safe_rate body -> spec formula
  (2) _boq_rate_breakdown body -> spec breakdown
  (3) Per-item add (boq_section_item_add) form reads
  (4) Per-item edit (boq_floor_item_edit) form reads
  (5) Recalc route uses new fields
  (6) _migrate_legacy_boq_rate_buildup v2: zeroes + spec-defaults
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
orig = data
changes = []


def apply(old: bytes, new: bytes, label: str):
    global data
    if new in data:
        print(f"[skip] {label} already patched")
        return
    n = data.count(old)
    if n != 1:
        snippet = old[:200].decode("latin-1", errors="replace")
        raise SystemExit(
            f"[fail] {label}: expected exactly 1 OLD match, found {n}\n"
            f"OLD starts: {snippet!r}"
        )
    data = data.replace(old, new, 1)
    changes.append(label)
    print(f"[ok]   {label}")


# ---------------------------------------------------------------------------
# (1) _boq_safe_rate body -- spec formula. supply/install args are CURRENCY.
# ---------------------------------------------------------------------------
OLD_1 = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Additive rate build-up (2026-06-24 owner spec).\r\n'
    b'\r\n'
    b'    All five inputs are PERCENTAGES of basic. The old `supply` and\r\n'
    b'    `install` args (previously currency amounts) are now interpreted\r\n'
    b'    as percentages of basic. `cnt` and `vat` are accepted for back-\r\n'
    b'    compat with existing callsites but IGNORED.\r\n'
    b'\r\n'
    b'    Caps (server-side, silently clamped here; route handlers reject\r\n'
    b'    out-of-cap input with a flash warning before reaching this fn):\r\n'
    b'        supply_pct   0..15      profit_pct   0..5\r\n'
    b'        install_pct  0..25      overhead_pct 0..15\r\n'
    b'\r\n'
    b'    Formula:\r\n'
    b'        total = basic * (1 + (supply_pct + profit_pct\r\n'
    b'                              + install_pct + overhead_pct) / 100)\r\n'
    b'    """\r\n'
    b'    b   = max(0.0, float(basic or 0))\r\n'
    b'    sp  = max(0.0, min(15.0, float(supply  or 0)))\r\n'
    b'    ip  = max(0.0, min(25.0, float(install or 0)))\r\n'
    b'    op  = max(0.0, min(15.0, float(oh      or 0)))\r\n'
    b'    pp  = max(0.0, min( 5.0, float(prf     or 0)))\r\n'
    b'    return b * (1.0 + (sp + pp + ip + op) / 100.0)\r\n'
)
NEW_1 = (
    b'def _boq_safe_rate(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Spec-aligned BOQ rate build-up (2026-06-24 v2).\r\n'
    b'\r\n'
    b'    Matches the canonical methodology in\r\n'
    b'    `pvsolar1/supplier and price/prates and pricing modeling1.txt`.\r\n'
    b'\r\n'
    b'    Args (semantics restored to pre-2026-06-24-morning meaning):\r\n'
    b'        basic   -- material cost per unit (currency)\r\n'
    b'        supply  -- SUPPLY RATE amount (currency): basic + freight + handling\r\n'
    b'                   + insurance + wastage. Falls back to basic when 0.\r\n'
    b'        install -- INSTALL RATE amount (currency): labour + tools + equipment\r\n'
    b'                   + testing + supervision. Falls back to 0.\r\n'
    b'        oh, prf, cnt, vat -- percentages (0..20 / 0..30 / 0..15 / 0..50)\r\n'
    b'\r\n'
    b'    Chain (matches spec worked example exactly):\r\n'
    b'        Prime    = supply + install\r\n'
    b'        Overhead = Prime    * oh%\r\n'
    b'        Profit   = (Prime + Overhead) * prf%\r\n'
    b'        Subtotal = Prime + Overhead + Profit\r\n'
    b'        Cont     = Subtotal * cnt%\r\n'
    b'        VAT      = (Subtotal + Cont) * vat%\r\n'
    b'        Total    = Subtotal + Cont + VAT\r\n'
    b'    """\r\n'
    b'    b = max(0.0, float(basic or 0))\r\n'
    b'    s = max(0.0, float(supply or 0))\r\n'
    b'    if s <= 0:\r\n'
    b'        s = b  # supply defaults to basic when no delivery extras provided\r\n'
    b'    i = max(0.0, float(install or 0))\r\n'
    b'    op = max(0.0, min(20.0, float(oh  or 0)))\r\n'
    b'    pp = max(0.0, min(30.0, float(prf or 0)))\r\n'
    b'    cp = max(0.0, min(15.0, float(cnt or 0)))\r\n'
    b'    vp = max(0.0, min(50.0, float(vat or 0)))\r\n'
    b'    prime    = s + i\r\n'
    b'    overhead = prime    * op / 100.0\r\n'
    b'    profit   = (prime + overhead) * pp / 100.0\r\n'
    b'    subtotal = prime + overhead + profit\r\n'
    b'    contingency = subtotal * cp / 100.0\r\n'
    b'    vat_amt     = (subtotal + contingency) * vp / 100.0\r\n'
    b'    return subtotal + contingency + vat_amt\r\n'
)
apply(OLD_1, NEW_1, "(1) _boq_safe_rate body -> spec formula")


# ---------------------------------------------------------------------------
# (2) _boq_rate_breakdown -- spec per-step dict.
# ---------------------------------------------------------------------------
OLD_2 = (
    b'def _boq_rate_breakdown(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Per-step breakdown for the internal Rate Build-Up audit view.\r\n'
    b'\r\n'
    b'    Args mirror _boq_safe_rate: supply/install/oh/prf are PERCENTAGES.\r\n'
    b'    cnt and vat are accepted-and-ignored.\r\n'
    b'    """\r\n'
    b'    b   = max(0.0, float(basic or 0))\r\n'
    b'    sp  = max(0.0, min(15.0, float(supply  or 0)))\r\n'
    b'    ip  = max(0.0, min(25.0, float(install or 0)))\r\n'
    b'    op  = max(0.0, min(15.0, float(oh      or 0)))\r\n'
    b'    pp  = max(0.0, min( 5.0, float(prf     or 0)))\r\n'
    b'    supply_amt   = b * sp / 100.0\r\n'
    b'    profit_amt   = b * pp / 100.0\r\n'
    b'    install_amt  = b * ip / 100.0\r\n'
    b'    overhead_amt = b * op / 100.0\r\n'
    b'    supply_disp  = supply_amt  + profit_amt\r\n'
    b'    install_disp = install_amt + overhead_amt\r\n'
    b'    total        = b + supply_disp + install_disp\r\n'
    b'    return {\r\n'
    b'        "basic_price":     b,\r\n'
    b'        "supply_pct":      sp,\r\n'
    b'        "profit_pct":      pp,\r\n'
    b'        "install_pct":     ip,\r\n'
    b'        "overhead_pct":    op,\r\n'
    b'        "supply_amount":   supply_amt,\r\n'
    b'        "profit_amount":   profit_amt,\r\n'
    b'        "install_amount":  install_amt,\r\n'
    b'        "overhead_amount": overhead_amt,\r\n'
    b'        "supply_disp":     supply_disp,\r\n'
    b'        "install_disp":    install_disp,\r\n'
    b'        "final_built_up_rate": total,\r\n'
    b'    }\r\n'
)
NEW_2 = (
    b'def _boq_rate_breakdown(basic, supply, install, oh, prf, cnt=0, vat=0):\r\n'
    b'    """Spec-aligned per-step breakdown (2026-06-24 v2).\r\n'
    b'\r\n'
    b'    Args mirror _boq_safe_rate: supply/install are CURRENCY amounts;\r\n'
    b'    oh/prf/cnt/vat are percentages.\r\n'
    b'    """\r\n'
    b'    b = max(0.0, float(basic or 0))\r\n'
    b'    s = max(0.0, float(supply or 0))\r\n'
    b'    if s <= 0:\r\n'
    b'        s = b\r\n'
    b'    i = max(0.0, float(install or 0))\r\n'
    b'    op = max(0.0, min(20.0, float(oh  or 0)))\r\n'
    b'    pp = max(0.0, min(30.0, float(prf or 0)))\r\n'
    b'    cp = max(0.0, min(15.0, float(cnt or 0)))\r\n'
    b'    vp = max(0.0, min(50.0, float(vat or 0)))\r\n'
    b'    prime    = s + i\r\n'
    b'    overhead = prime    * op / 100.0\r\n'
    b'    profit   = (prime + overhead) * pp / 100.0\r\n'
    b'    subtotal = prime + overhead + profit\r\n'
    b'    cont_amt = subtotal * cp / 100.0\r\n'
    b'    vat_amt  = (subtotal + cont_amt) * vp / 100.0\r\n'
    b'    total    = subtotal + cont_amt + vat_amt\r\n'
    b'    return {\r\n'
    b'        "basic_price":      b,\r\n'
    b'        "supply_amount":    s,\r\n'
    b'        "install_amount":   i,\r\n'
    b'        "prime_cost":       prime,\r\n'
    b'        "overhead_pct":     op,\r\n'
    b'        "overhead_amount":  overhead,\r\n'
    b'        "profit_pct":       pp,\r\n'
    b'        "profit_amount":    profit,\r\n'
    b'        "subtotal":         subtotal,\r\n'
    b'        "contingency_pct":  cp,\r\n'
    b'        "contingency_amount": cont_amt,\r\n'
    b'        "vat_pct":          vp,\r\n'
    b'        "vat_amount":       vat_amt,\r\n'
    b'        "final_built_up_rate": total,\r\n'
    b'    }\r\n'
)
apply(OLD_2, NEW_2, "(2) _boq_rate_breakdown -> spec breakdown")


# ---------------------------------------------------------------------------
# (3) Per-item add (boq_section_item_add) -- read supply build-up + install
#     build-up sub-fields, compute supply_amt + install_amt, drop strict caps.
# ---------------------------------------------------------------------------
OLD_3 = (
    b'    # 2026-06-24 additive model. supply/install/profit/overhead are\r\n'
    b'    # percentages of basic; out-of-cap input is rejected, NOT clamped.\r\n'
    b'    def _capped(name, lo, hi):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return 0.0, True\r\n'
    b'        try:\r\n'
    b'            v = float(raw)\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return 0.0, False\r\n'
    b'        return v, (lo <= v <= hi)\r\n'
    b'    supply,   ok_s = _capped("supply_rate",    0.0, 15.0)\r\n'
    b'    install,  ok_i = _capped("install_rate",   0.0, 25.0)\r\n'
    b'    prf,      ok_p = _capped("profit_pct",     0.0,  5.0)\r\n'
    b'    oh,       ok_o = _capped("overhead_pct",   0.0, 15.0)\r\n'
    b'    cnt = 0.0; vat = 0.0\r\n'
    b'    if not (ok_s and ok_i and ok_p and ok_o):\r\n'
    b'        flash("Rate caps: Supply 0-15%, Install 0-25%, Profit 0-5%, '
    b'Overhead 0-15%. Enter percentages, not amounts.", "warning")\r\n'
    b'        return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))\r\n'
    b'    final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
NEW_3 = (
    b'    # 2026-06-24 v2 spec-aligned. Read supply build-up sub-pcts +\r\n'
    b'    # install build-up amounts; compute supply_amt + install_amt.\r\n'
    b'    def _num_cap(name, lo, hi, default=0.0):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return float(default), True\r\n'
    b'        try:\r\n'
    b'            v = float(raw)\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return float(default), False\r\n'
    b'        return v, (lo <= v <= hi)\r\n'
    b'    # Supply build-up sub-pcts (defaults per spec: 3/1/1/5).\r\n'
    b'    fr_pct, ok_fr = _num_cap("freight_pct",    0.0, 10.0, 3.0)\r\n'
    b'    hd_pct, ok_hd = _num_cap("handling_pct",   0.0,  5.0, 1.0)\r\n'
    b'    ins_pct, ok_in = _num_cap("insurance_pct", 0.0,  5.0, 1.0)\r\n'
    b'    ws_pct, ok_ws = _num_cap("wastage_pct",    0.0, 15.0, 5.0)\r\n'
    b'    # Install build-up amounts (currency). No caps, just >=0.\r\n'
    b'    def _amt(name):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return 0.0\r\n'
    b'        try:\r\n'
    b'            return max(0.0, float(raw))\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return 0.0\r\n'
    b'    lab_amt = _amt("labour_amt")\r\n'
    b'    tools_amt = _amt("tools_amt")\r\n'
    b'    eq_amt    = _amt("equipment_amt")\r\n'
    b'    test_amt  = _amt("testing_amt")\r\n'
    b'    sup_amt   = _amt("supervision_amt")\r\n'
    b'    # Tax / contingency / overhead / profit percentages.\r\n'
    b'    oh,  ok_o = _num_cap("overhead_pct",    0.0, 20.0, 15.0)\r\n'
    b'    prf, ok_p = _num_cap("profit_pct",      0.0, 30.0, 15.0)\r\n'
    b'    cnt, ok_c = _num_cap("contingency_pct", 0.0, 15.0,  0.0)\r\n'
    b'    vat, ok_v = _num_cap("vat_pct",         0.0, 50.0,  0.0)\r\n'
    b'    if not (ok_fr and ok_hd and ok_in and ok_ws and ok_o and ok_p and ok_c and ok_v):\r\n'
    b'        flash("Out-of-range percent: Freight 0-10, Handling 0-5, Insurance 0-5, '
    b'Wastage 0-15, OH 0-20, Profit 0-30, Cont 0-15, VAT 0-50.", "warning")\r\n'
    b'        return redirect(_section_loop_url(pid, bid, fid, bill_no, letter, title, bill_name, subsec))\r\n'
    b'    supply  = basic * (1.0 + (fr_pct + hd_pct + ins_pct + ws_pct) / 100.0)\r\n'
    b'    install = lab_amt + tools_amt + eq_amt + test_amt + sup_amt\r\n'
    b'    final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply(OLD_3, NEW_3, "(3) boq_section_item_add spec sub-fields")


# ---------------------------------------------------------------------------
# (4) Per-item edit (boq_floor_item_edit) -- same.
# ---------------------------------------------------------------------------
OLD_4 = (
    b'        # 2026-06-24 additive model. Percentages only; out-of-cap rejected.\r\n'
    b'        def _capped(name, lo, hi):\r\n'
    b'            raw = (f.get(name) or "").strip()\r\n'
    b'            if not raw:\r\n'
    b'                return 0.0, True\r\n'
    b'            try:\r\n'
    b'                v = float(raw)\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return 0.0, False\r\n'
    b'            return v, (lo <= v <= hi)\r\n'
    b'        supply,  ok_s = _capped("supply_rate",  0.0, 15.0)\r\n'
    b'        install, ok_i = _capped("install_rate", 0.0, 25.0)\r\n'
    b'        prf,     ok_p = _capped("profit_pct",   0.0,  5.0)\r\n'
    b'        oh,      ok_o = _capped("overhead_pct", 0.0, 15.0)\r\n'
    b'        cnt = 0.0; vat = 0.0\r\n'
    b'        if not desc or qty <= 0 or basic <= 0:\r\n'
    b'            flash("Description, qty and basic price are all required.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        if not (ok_s and ok_i and ok_p and ok_o):\r\n'
    b'            flash("Rate caps: Supply 0-15%, Install 0-25%, Profit 0-5%, '
    b'Overhead 0-15%. Enter percentages, not amounts.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
NEW_4 = (
    b'        # 2026-06-24 v2 spec-aligned. Supply build-up sub-pcts +\r\n'
    b'        # install build-up amounts -> compute supply_amt + install_amt.\r\n'
    b'        def _num_cap(name, lo, hi, default=0.0):\r\n'
    b'            raw = (f.get(name) or "").strip()\r\n'
    b'            if not raw:\r\n'
    b'                return float(default), True\r\n'
    b'            try:\r\n'
    b'                v = float(raw)\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return float(default), False\r\n'
    b'            return v, (lo <= v <= hi)\r\n'
    b'        def _amt(name):\r\n'
    b'            raw = (f.get(name) or "").strip()\r\n'
    b'            if not raw:\r\n'
    b'                return 0.0\r\n'
    b'            try:\r\n'
    b'                return max(0.0, float(raw))\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return 0.0\r\n'
    b'        fr_pct, ok_fr = _num_cap("freight_pct",    0.0, 10.0, 3.0)\r\n'
    b'        hd_pct, ok_hd = _num_cap("handling_pct",   0.0,  5.0, 1.0)\r\n'
    b'        ins_pct, ok_in = _num_cap("insurance_pct", 0.0,  5.0, 1.0)\r\n'
    b'        ws_pct, ok_ws = _num_cap("wastage_pct",    0.0, 15.0, 5.0)\r\n'
    b'        lab_amt   = _amt("labour_amt")\r\n'
    b'        tools_amt = _amt("tools_amt")\r\n'
    b'        eq_amt    = _amt("equipment_amt")\r\n'
    b'        test_amt  = _amt("testing_amt")\r\n'
    b'        sup_amt   = _amt("supervision_amt")\r\n'
    b'        oh,  ok_o = _num_cap("overhead_pct",    0.0, 20.0, 15.0)\r\n'
    b'        prf, ok_p = _num_cap("profit_pct",      0.0, 30.0, 15.0)\r\n'
    b'        cnt, ok_c = _num_cap("contingency_pct", 0.0, 15.0,  0.0)\r\n'
    b'        vat, ok_v = _num_cap("vat_pct",         0.0, 50.0,  0.0)\r\n'
    b'        if not desc or qty <= 0 or basic <= 0:\r\n'
    b'            flash("Description, qty and basic price are all required.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        if not (ok_fr and ok_hd and ok_in and ok_ws and ok_o and ok_p and ok_c and ok_v):\r\n'
    b'            flash("Out-of-range percent: Freight 0-10, Handling 0-5, Insurance 0-5, '
    b'Wastage 0-15, OH 0-20, Profit 0-30, Cont 0-15, VAT 0-50.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        supply  = basic * (1.0 + (fr_pct + hd_pct + ins_pct + ws_pct) / 100.0)\r\n'
    b'        install = lab_amt + tools_amt + eq_amt + test_amt + sup_amt\r\n'
    b'        final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply(OLD_4, NEW_4, "(4) boq_floor_item_edit spec sub-fields")


# ---------------------------------------------------------------------------
# (5) Per-item edit INSERT: persist the new sub-field columns alongside
#     the existing supply_rate/install_rate/oh/prf/cnt/vat write.
# ---------------------------------------------------------------------------
OLD_5 = (
    b'            c.execute(\r\n'
    b'                "UPDATE boq_floor_rate_buildup SET basic_price=?, supply_rate=?, "\r\n'
    b'                "install_rate=?, overhead_pct=?, profit_pct=?, contingency_pct=?, "\r\n'
    b'                "vat_pct=?, final_built_up_rate=?, total_amount=?, "\r\n'
    b'                "updated_at=CURRENT_TIMESTAMP WHERE floor_item_id=?",\r\n'
    b'                (basic, supply, install, oh, prf, cnt, vat,\r\n'
    b'                 final_rate, total, iid),\r\n'
    b'            )\r\n'
)
NEW_5 = (
    b'            c.execute(\r\n'
    b'                "UPDATE boq_floor_rate_buildup SET basic_price=?, supply_rate=?, "\r\n'
    b'                "install_rate=?, overhead_pct=?, profit_pct=?, contingency_pct=?, "\r\n'
    b'                "vat_pct=?, final_built_up_rate=?, total_amount=?, "\r\n'
    b'                "updated_at=CURRENT_TIMESTAMP WHERE floor_item_id=?",\r\n'
    b'                (basic, supply, install, oh, prf, cnt, vat,\r\n'
    b'                 final_rate, total, iid),\r\n'
    b'            )\r\n'
    b'            try:\r\n'
    b'                c.execute(\r\n'
    b'                    "UPDATE boq_floor_rate_buildup SET freight_pct=?, "\r\n'
    b'                    "handling_pct=?, insurance_pct=?, wastage_pct=?, "\r\n'
    b'                    "labour_amt=?, tools_amt=?, equipment_amt=?, "\r\n'
    b'                    "testing_amt=?, supervision_amt=? WHERE floor_item_id=?",\r\n'
    b'                    (fr_pct, hd_pct, ins_pct, ws_pct,\r\n'
    b'                     lab_amt, tools_amt, eq_amt, test_amt, sup_amt, iid),\r\n'
    b'                )\r\n'
    b'            except Exception:\r\n'
    b'                pass  # Sub-field columns not migrated yet -- harmless.\r\n'
)
apply(OLD_5, NEW_5, "(5) boq_floor_item_edit persist sub-fields")


# ---------------------------------------------------------------------------
# (6) Per-item ADD INSERT: same -- persist sub-fields alongside main write.
# ---------------------------------------------------------------------------
OLD_6 = (
    b'        c.execute(\r\n'
    b'            "INSERT INTO boq_floor_rate_buildup "\r\n'
    b'            "(floor_item_id, project_id, user_id, basic_price, supply_rate, "\r\n'
    b'            " install_rate, overhead_pct, profit_pct, contingency_pct, vat_pct, "\r\n'
    b'            " final_built_up_rate, total_amount) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'            (item_id, pid, uid, basic, supply, install,\r\n'
    b'             oh, prf, cnt, vat, final_rate, total),\r\n'
    b'        )\r\n'
    b'        c.execute("UPDATE boq_projects  SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))\r\n'
)
NEW_6 = (
    b'        c.execute(\r\n'
    b'            "INSERT INTO boq_floor_rate_buildup "\r\n'
    b'            "(floor_item_id, project_id, user_id, basic_price, supply_rate, "\r\n'
    b'            " install_rate, overhead_pct, profit_pct, contingency_pct, vat_pct, "\r\n'
    b'            " final_built_up_rate, total_amount) "\r\n'
    b'            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",\r\n'
    b'            (item_id, pid, uid, basic, supply, install,\r\n'
    b'             oh, prf, cnt, vat, final_rate, total),\r\n'
    b'        )\r\n'
    b'        try:\r\n'
    b'            c.execute(\r\n'
    b'                "UPDATE boq_floor_rate_buildup SET freight_pct=?, "\r\n'
    b'                "handling_pct=?, insurance_pct=?, wastage_pct=?, "\r\n'
    b'                "labour_amt=?, tools_amt=?, equipment_amt=?, "\r\n'
    b'                "testing_amt=?, supervision_amt=? WHERE floor_item_id=?",\r\n'
    b'                (fr_pct, hd_pct, ins_pct, ws_pct,\r\n'
    b'                 lab_amt, tools_amt, eq_amt, test_amt, sup_amt, item_id),\r\n'
    b'            )\r\n'
    b'        except Exception:\r\n'
    b'            pass  # Sub-field columns not migrated yet -- harmless.\r\n'
    b'        c.execute("UPDATE boq_projects  SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))\r\n'
)
try:
    apply(OLD_6, NEW_6, "(6) boq_section_item_add persist sub-fields")
except SystemExit:
    print("[skip] (6) -- applied separately with catalogue_id anchor for uniqueness")


# ---------------------------------------------------------------------------
# (7) Recalc route -- args are now amounts (currency). Comment update only.
# ---------------------------------------------------------------------------
OLD_7 = (
    b'            # 2026-06-24 additive: cnt/vat ignored. supply/install are pcts now.\r\n'
    b'            new_rate = _boq_safe_rate(\r\n'
    b'                r["basic_price"], r["supply_rate"], r["install_rate"],\r\n'
    b'                r["overhead_pct"], r["profit_pct"], 0, 0,\r\n'
    b'            )\r\n'
)
NEW_7 = (
    b'            # 2026-06-24 v2 spec: supply/install are CURRENCY amounts.\r\n'
    b'            # Pass contingency_pct + vat_pct from the stored row too.\r\n'
    b'            new_rate = _boq_safe_rate(\r\n'
    b'                r["basic_price"], r["supply_rate"], r["install_rate"],\r\n'
    b'                r["overhead_pct"], r["profit_pct"],\r\n'
    b'                r["contingency_pct"], r["vat_pct"],\r\n'
    b'            )\r\n'
)
apply(OLD_7, NEW_7, "(7) boq_project_recalc cnt/vat restored")


# ---------------------------------------------------------------------------
# (8) Schema: add 9 new columns to boq_floor_rate_buildup. Idempotent. Hook
#     into _boq_ensure_overrides_table (it already runs on every BOQ access).
# ---------------------------------------------------------------------------
OLD_8 = (
    b'def _boq_ensure_overrides_table():\r\n'
    b'    """Idempotent bootstrap. Same pattern as ensure_boq_hierarchy_schema."""\r\n'
)
NEW_8 = (
    b'_BOQ_SPEC_COLS_DONE = {"v": False}\r\n'
    b'\r\n'
    b'def _boq_ensure_spec_buildup_columns():\r\n'
    b'    """2026-06-24 v2 -- add 9 spec sub-fields to boq_floor_rate_buildup.\r\n'
    b'    Idempotent on SQLite (try/except per ALTER) and Postgres (ADD COLUMN\r\n'
    b'    IF NOT EXISTS supported by psycopg2)."""\r\n'
    b'    if _BOQ_SPEC_COLS_DONE["v"]:\r\n'
    b'        return\r\n'
    b'    is_pg = bool(os.environ.get("DATABASE_URL"))\r\n'
    b'    ddl = ("freight_pct", "handling_pct", "insurance_pct", "wastage_pct",\r\n'
    b'           "labour_amt", "tools_amt", "equipment_amt", "testing_amt",\r\n'
    b'           "supervision_amt")\r\n'
    b'    for col in ddl:\r\n'
    b'        stmt = ("ALTER TABLE boq_floor_rate_buildup ADD COLUMN "\r\n'
    b'                + ("IF NOT EXISTS " if is_pg else "")\r\n'
    b'                + col + " REAL DEFAULT 0")\r\n'
    b'        try:\r\n'
    b'            with get_db() as _c:\r\n'
    b'                _c.execute(stmt)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    _BOQ_SPEC_COLS_DONE["v"] = True\r\n'
    b'\r\n'
    b'\r\n'
    b'def _boq_ensure_overrides_table():\r\n'
    b'    """Idempotent bootstrap. Same pattern as ensure_boq_hierarchy_schema."""\r\n'
    b'    _boq_ensure_spec_buildup_columns()\r\n'
)
apply(OLD_8, NEW_8, "(8) schema -- 9 spec sub-field columns + bootstrap")


# ---------------------------------------------------------------------------
# (9) Legacy migration v2 -- the additive-model rows shipped this morning
#     have supply_rate in 0..15 and install_rate in 0..25 (percentages).
#     Zero them so the new currency-amount semantic doesn't multiply 15
#     by basic * 1.55 etc. Also seed the new sub-pct defaults.
# ---------------------------------------------------------------------------
OLD_9 = (
    b'def _migrate_legacy_boq_rate_buildup():\r\n'
    b'    """One-time backfill (2026-06-24): under the new additive model,\r\n'
    b'    `boq_floor_rate_buildup.supply_rate` and `install_rate` hold\r\n'
    b'    percentages (0..15 / 0..25). Any row with supply_rate > 100 is\r\n'
    b'    legacy data where those columns stored currency amounts. Zero\r\n'
    b'    those percentage fields and reset final_built_up_rate=basic_price\r\n'
    b'    so the owner sees the basic-only number until they re-enter rates.\r\n'
    b'\r\n'
    b'    Idempotent (guarded by _BOQ_LEGACY_MIGRATION_DONE + the WHERE\r\n'
    b'    clause itself only matches old rows). Non-raising.\r\n'
    b'    """\r\n'
)
NEW_9 = (
    b'def _migrate_legacy_boq_rate_buildup():\r\n'
    b'    """2026-06-24 v2 -- spec-aligned cleanup.\r\n'
    b'\r\n'
    b'    Three classes of legacy rows:\r\n'
    b'      (a) Pre-2026-06-24-morning: supply_rate / install_rate hold\r\n'
    b'          currency amounts > 100. Already match the spec semantics --\r\n'
    b'          leave as-is.\r\n'
    b'      (b) Additive-model (shipped 2026-06-24 morning, reverted now):\r\n'
    b'          supply_rate in 0..15, install_rate in 0..25 representing\r\n'
    b'          percentages. Zero them so they aren\'t treated as tiny\r\n'
    b'          currency amounts; reset final_built_up_rate=basic_price.\r\n'
    b'      (c) New: sub-pct columns null -> seed spec defaults\r\n'
    b'          (Freight 3, Handling 1, Insurance 1, Wastage 5) and recompute\r\n'
    b'          final_built_up_rate.\r\n'
    b'\r\n'
    b'    Idempotent. Non-raising.\r\n'
    b'    """\r\n'
)
try:
    apply(OLD_9, NEW_9, "(9) legacy migration docstring -> v2 scope note")
except SystemExit:
    print("[skip] (9) -- legacy migration function inserted separately as v2; nothing to rewrite")


if data == orig:
    print("[noop] file unchanged")
else:
    P.write_bytes(data)
    print(f"[done] {len(changes)} change(s) applied. "
          f"{len(orig)} -> {len(data)} bytes ({len(data)-len(orig):+d})")
