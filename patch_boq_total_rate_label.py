# patch_boq_total_rate_label.py
# Rename the BOQ column header "Rate" -> "Total Rate" in the spliced
# Excel + PDF export bodies inside web_app.py to match the auditorium sample.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

did = []
for old, new in [
    (b'headers = ["Item", "Description", "Qty", "Unit", "Basic Rate", "Rate", "Amount"]',
     b'headers = ["Item", "Description", "Qty", "Unit", "Basic Rate", "Total Rate", "Amount"]'),
    (b'md.append("| Item | Description | Qty | Unit | Basic Rate | Rate | Amount |")',
     b'md.append("| Item | Description | Qty | Unit | Basic Rate | Total Rate | Amount |")'),
]:
    n = data.count(old)
    if n == 0:
        did.append(f"skip (already patched or anchor missing) for: {old[:60]!r}")
        continue
    if n != 1:
        did.append(f"WARN multi-match ({n}) for: {old[:60]!r}")
        continue
    data = data.replace(old, new)
    did.append(f"patched: {old[:60]!r}")

TARGET.write_bytes(data)
for line in did:
    print(line)
