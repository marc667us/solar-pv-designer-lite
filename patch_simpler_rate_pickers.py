#!/usr/bin/env python3
"""patch_simpler_rate_pickers.py -- 2026-06-24 v5

Replace the detailed Supply/Install build-up sub-field reads on both
route handlers with simple Supply%/Install% pickers (matching the new
dropdown UI). The engine receives derived amounts:
    supply  = basic * (1 + supply_pct / 100)
    install = basic * install_pct / 100
"""
from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()
changes = []


def apply(old, new, label):
    global data
    if new in data:
        print(f"[skip] {label}")
        return
    n = data.count(old)
    if n != 1:
        raise SystemExit(f"[fail] {label}: matches={n}")
    data = data.replace(old, new, 1)
    changes.append(label)
    print(f"[ok] {label}")


# (1) boq_section_item_add -- replace sub-field block.
OLD_ADD = (
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
NEW_ADD = (
    b'    # 2026-06-24 v5: simple Supply%/Install% pickers replace the detailed\r\n'
    b'    # build-up sub-fields. Each dropdown is range-capped on the client;\r\n'
    b'    # server clamps to the same range for safety.\r\n'
    b'    def _pick(name, lo, hi, default):\r\n'
    b'        raw = (f.get(name) or "").strip()\r\n'
    b'        if not raw:\r\n'
    b'            return float(default)\r\n'
    b'        try:\r\n'
    b'            return max(float(lo), min(float(hi), float(raw)))\r\n'
    b'        except (TypeError, ValueError):\r\n'
    b'            return float(default)\r\n'
    b'    supply_pct  = _pick("supply_pct",      0.0, 15.0, 10.0)\r\n'
    b'    install_pct = _pick("install_pct",     0.0, 25.0, 15.0)\r\n'
    b'    oh          = _pick("overhead_pct",    0.0, 20.0, 15.0)\r\n'
    b'    prf         = _pick("profit_pct",      0.0, 30.0, 15.0)\r\n'
    b'    cnt         = _pick("contingency_pct", 0.0, 15.0,  0.0)\r\n'
    b'    vat         = _pick("vat_pct",         0.0, 50.0,  0.0)\r\n'
    b'    # Sub-field vars kept zero (no longer collected from form).\r\n'
    b'    fr_pct = hd_pct = ins_pct = ws_pct = 0.0\r\n'
    b'    lab_amt = tools_amt = eq_amt = test_amt = sup_amt = 0.0\r\n'
    b'    supply  = basic * (1.0 + supply_pct  / 100.0)\r\n'
    b'    install = basic * (install_pct / 100.0)\r\n'
    b'    final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply(OLD_ADD, NEW_ADD, "(1) section_item_add -- simple pickers")


# (2) boq_floor_item_edit -- same.
OLD_EDIT = (
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
NEW_EDIT = (
    b'        # 2026-06-24 v5: simple Supply%/Install% pickers.\r\n'
    b'        def _pick(name, lo, hi, default):\r\n'
    b'            raw = (f.get(name) or "").strip()\r\n'
    b'            if not raw:\r\n'
    b'                return float(default)\r\n'
    b'            try:\r\n'
    b'                return max(float(lo), min(float(hi), float(raw)))\r\n'
    b'            except (TypeError, ValueError):\r\n'
    b'                return float(default)\r\n'
    b'        supply_pct  = _pick("supply_pct",      0.0, 15.0, 10.0)\r\n'
    b'        install_pct = _pick("install_pct",     0.0, 25.0, 15.0)\r\n'
    b'        oh          = _pick("overhead_pct",    0.0, 20.0, 15.0)\r\n'
    b'        prf         = _pick("profit_pct",      0.0, 30.0, 15.0)\r\n'
    b'        cnt         = _pick("contingency_pct", 0.0, 15.0,  0.0)\r\n'
    b'        vat         = _pick("vat_pct",         0.0, 50.0,  0.0)\r\n'
    b'        fr_pct = hd_pct = ins_pct = ws_pct = 0.0\r\n'
    b'        lab_amt = tools_amt = eq_amt = test_amt = sup_amt = 0.0\r\n'
    b'        if not desc or qty <= 0 or basic <= 0:\r\n'
    b'            flash("Description, qty and basic price are all required.", "warning")\r\n'
    b'            return redirect(url_for("boq_floor_item_edit", pid=pid, bid=bid, fid=fid, iid=iid))\r\n'
    b'        supply  = basic * (1.0 + supply_pct  / 100.0)\r\n'
    b'        install = basic * (install_pct / 100.0)\r\n'
    b'        final_rate = _boq_safe_rate(basic, supply, install, oh, prf, cnt, vat)\r\n'
)
apply(OLD_EDIT, NEW_EDIT, "(2) floor_item_edit -- simple pickers")


P.write_bytes(data)
print(f"[done] {len(changes)} change(s)")
