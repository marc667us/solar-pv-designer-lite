#!/usr/bin/env python3
"""
patch_marketplace_high_price_corrections.py

Owner directive 2026-06-23: "check prices of products some too high".

Top-25-by-price audit against the live `/marketplace` listing surfaced
five items priced 1.3-2x over their realistic Ghana-market value
(verified against published 2025-2026 APC/Eaton/Safenergy distributor
pricing in GHS). This patch corrects the SEED in web_app.py only --
the live Postgres update is handled by the matching workflow
`Fix Marketplace High Prices` because the seed only backfills empty
categories (these categories are already populated).

Corrections:
    SRT10KXLI    165,000 -> 90,000
    SRT20KXLI    285,000 -> 160,000
    S3-15K       105,000 -> 65,000
    S3-40K       235,000 -> 175,000
    S3-50K       285,000 -> 215,000
"""

from pathlib import Path

P = Path("web_app.py")
data = P.read_bytes()

# Each tuple: (old_bytes, new_bytes, label)
# Match the exact line including the SKU + price in the seed tuple so we
# don't accidentally touch any other use of the same number.
CHANGES = [
    (
        b'"SRT10KXLI",   "APC Smart-UPS On-Line SRT 10kVA, three-phase",         "No.", 165000.00, 21, "UPS"',
        b'"SRT10KXLI",   "APC Smart-UPS On-Line SRT 10kVA, three-phase",         "No.",  90000.00, 21, "UPS"',
        "SRT10KXLI 165000 -> 90000",
    ),
    (
        b'"SRT20KXLI",   "APC Smart-UPS On-Line SRT 20kVA, three-phase",         "No.", 285000.00, 21, "UPS"',
        b'"SRT20KXLI",   "APC Smart-UPS On-Line SRT 20kVA, three-phase",         "No.", 160000.00, 21, "UPS"',
        "SRT20KXLI 285000 -> 160000",
    ),
    (
        b'"S3-15K"  "15 kVA online UPS three-phase                  No. 105000.00 21 UPS',
        b'"S3-15K"  "15 kVA online UPS three-phase                  No.  65000.00 21 UPS',
        "S3-15K 105000 -> 65000 (placeholder; will retry by SKU)",
    ),
]

# Plus: do the Safenergy S3-15K / S3-40K / S3-50K via a looser SKU match
# because the source line spacing in web_app.py uses dynamic whitespace.
import re
src_text = data.decode("utf-8", errors="replace")

def fix_one(text, sku, old_price, new_price, label):
    # Match the line containing "SKU" and the old price float literal.
    # We constrain by the SKU + the literal numeric value to be safe.
    pattern = re.compile(
        r'("' + re.escape(sku) + r'"[^\n]*?, +)' +
        re.escape(f"{old_price:.2f}") +
        r'(, +\d+, +"UPS"\))'
    )
    new_text, n = pattern.subn(
        lambda m: m.group(1) + f"{new_price:.2f}" + m.group(2),
        text,
    )
    if n == 1:
        print(f"  [ok]   {label}")
        return new_text
    if n == 0:
        # Try without the "UPS" classifier (Safenergy lines don't end with it)
        pattern2 = re.compile(
            r'("' + re.escape(sku) + r'"[^\n]*?, +)' +
            re.escape(f"{old_price:.2f}") +
            r'(, +\d+, +"[^"]+"\))'
        )
        new_text, n = pattern2.subn(
            lambda m: m.group(1) + f"{new_price:.2f}" + m.group(2),
            text,
        )
        if n == 1:
            print(f"  [ok]   {label} (alt pattern)")
            return new_text
        print(f"  [skip] {label} -- no match")
        return text
    raise SystemExit(f"[fail] {label}: matched {n} times (ambiguous)")

corrections = [
    ("SRT10KXLI", 165000, 90000),
    ("SRT20KXLI", 285000, 160000),
    ("S3-15K",    105000, 65000),
    ("S3-40K",    235000, 175000),
    ("S3-50K",    285000, 215000),
]

for sku, old_v, new_v in corrections:
    src_text = fix_one(src_text, sku, old_v, new_v, f"{sku}: {old_v:,} -> {new_v:,}")

new_data = src_text.encode("utf-8")
if new_data == data:
    print("[noop] no changes -- already patched or SKUs not found")
else:
    P.write_bytes(new_data)
    print(f"[done] web_app.py: {len(data)} -> {len(new_data)} bytes ({len(new_data)-len(data):+d})")
