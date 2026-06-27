#!/usr/bin/env python3
"""Back-fill voltage_v / frequency_hz / compliance_standards on equipment_catalog
from the existing free-text spec / name columns.

Reads DATABASE_URL from env. Dry-run by default; pass --apply to commit.

Logic:
- Skip rows that already have voltage_v > 0 OR frequency_hz > 0 OR
  compliance_standards != '' (don't overwrite supplier-declared values).
- Voltage: capture kV (multiply by 1000), then plain V. First match wins.
  Handles "11/0.433 kV" by taking the first kV figure (primary side).
- Frequency: capture explicit "50 Hz" / "60 Hz".
- Standards: collect IEC/BS/EN/ISO/ANSI/UL/NEMA refs + "ECG", "PURC",
  "VRA" tokens, comma-joined, de-duped.
"""
import os
import re
import sys
from collections import OrderedDict


# Transformer "11/0.433 kV" — capture the primary (left) side first.
VOLT_RE_KV_PAIR = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*/\s*\d+(?:\.\d+)?\s*kV\b", re.IGNORECASE)
VOLT_RE_KV      = re.compile(r"\b(\d{1,3}(?:\.\d+)?)\s*kV\b", re.IGNORECASE)
VOLT_RE_V       = re.compile(r"\b(\d{2,5}(?:\.\d+)?)\s*[Vv]\b(?![Aa])")  # avoid VA/Vrms gotchas
FREQ_RE         = re.compile(r"\b(50|60)\s*Hz\b", re.IGNORECASE)

STD_PATTERNS = [
    re.compile(r"\bIEC[\s-]?\d{3,5}(?:-\d+)?\b", re.IGNORECASE),
    re.compile(r"\bBS[\s-]?EN[\s-]?\d{3,5}(?:-\d+)?\b", re.IGNORECASE),
    re.compile(r"\bEN[\s-]?\d{3,5}(?:-\d+)?\b", re.IGNORECASE),
    re.compile(r"\bISO[\s-]?\d{3,5}(?:-\d+)?\b", re.IGNORECASE),
    re.compile(r"\bANSI[\s/]?[A-Z]+\d*(?:\.\d+)?\b", re.IGNORECASE),
    re.compile(r"\bUL[\s-]?\d{3,5}\b", re.IGNORECASE),
    re.compile(r"\bNEMA[\s-]?[A-Z0-9.-]+\b", re.IGNORECASE),
]
TOKEN_STANDARDS = ("ECG", "PURC", "VRA", "EPA", "GS")


def _parse_voltage(text):
    if not text:
        return 0.0
    m = VOLT_RE_KV_PAIR.search(text)
    if m:
        try:
            return float(m.group(1)) * 1000.0
        except ValueError:
            pass
    m = VOLT_RE_KV.search(text)
    if m:
        try:
            return float(m.group(1)) * 1000.0
        except ValueError:
            pass
    m = VOLT_RE_V.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0


def _parse_frequency(text):
    if not text:
        return 0.0
    m = FREQ_RE.search(text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return 0.0


def _parse_standards(text):
    if not text:
        return ""
    found = OrderedDict()
    for pat in STD_PATTERNS:
        for m in pat.finditer(text):
            tok = re.sub(r"\s+", " ", m.group(0)).strip().upper()
            found[tok] = True
    upper = text.upper()
    for tok in TOKEN_STANDARDS:
        if re.search(rf"\b{tok}\b", upper):
            found[tok] = True
    return ", ".join(found.keys())


def main():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("FATAL: DATABASE_URL env var not set", file=sys.stderr)
        return 2
    apply = "--apply" in sys.argv
    print(f"=== back-fill marketplace grid fields — mode: {'APPLY' if apply else 'DRY-RUN'} ===")

    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT id, name, spec, voltage_v, frequency_hz, compliance_standards "
                "FROM equipment_catalog "
                "WHERE COALESCE(is_active,1)=1 "
                "ORDER BY id"
            )
            rows = cur.fetchall()
        print(f"  candidate rows in equipment_catalog: {len(rows)}")

        proposals = []
        skipped_already_set = 0
        skipped_nothing_found = 0
        for r in rows:
            cur_v   = float(r["voltage_v"] or 0)
            cur_hz  = float(r["frequency_hz"] or 0)
            cur_std = (r["compliance_standards"] or "").strip()
            if cur_v > 0 or cur_hz > 0 or cur_std:
                skipped_already_set += 1
                continue
            text = " ".join([r["name"] or "", r["spec"] or ""])
            v   = _parse_voltage(text)
            hz  = _parse_frequency(text)
            std = _parse_standards(text)
            if v == 0 and hz == 0 and not std:
                skipped_nothing_found += 1
                continue
            proposals.append((r["id"], r["name"], v, hz, std))

        print(f"  skipped (already has voltage/freq/standards): {skipped_already_set}")
        print(f"  skipped (no parseable hints in spec):          {skipped_nothing_found}")
        print(f"  proposed UPDATEs:                              {len(proposals)}")
        for pid, name, v, hz, std in proposals[:25]:
            print(f"    id={pid:>5}  V={v:>7.1f}  Hz={hz:>4.1f}  std='{std}'  name={name[:60]!r}")
        if len(proposals) > 25:
            print(f"    ... (+{len(proposals) - 25} more)")

        if not apply:
            print("DRY-RUN: no rows written. Re-run with --apply to commit.")
            return 0
        print("APPLY: committing UPDATEs ...")
        with conn.cursor() as cur:
            for pid, _name, v, hz, std in proposals:
                cur.execute(
                    "UPDATE equipment_catalog "
                    "SET voltage_v=COALESCE(NULLIF(voltage_v,0),%s), "
                    "    frequency_hz=COALESCE(NULLIF(frequency_hz,0),%s), "
                    "    compliance_standards=COALESCE(NULLIF(compliance_standards,''),%s) "
                    "WHERE id=%s",
                    (v, hz, std, pid),
                )
        conn.commit()
        print(f"OK: committed {len(proposals)} UPDATEs.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
