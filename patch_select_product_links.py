# patch_select_product_links.py
# Add ec.literature_url + ec.datasheet_url to the two product-listing
# SELECT queries (marketplace browse + procurement center) so the
# templates can display them.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# Marketplace browse (around line 14173)
OLD1 = b'               "       ec.price_usd, ec.lead_time_days, ec.subcategory, "\r\n'
NEW1 = (
    b'               "       ec.price_usd, ec.lead_time_days, ec.subcategory, "\r\n'
    b'               "       ec.literature_url, ec.datasheet_url, "\r\n'
)

# Procurement center (around line 17732)
OLD2 = b'            "       ec.price_usd, ec.lead_time_days, ec.category_id, "\r\n'
NEW2 = (
    b'            "       ec.price_usd, ec.lead_time_days, ec.category_id, "\r\n'
    b'            "       ec.literature_url, ec.datasheet_url, "\r\n'
)

did = []
for OLD, NEW, label in [(OLD1, NEW1, "marketplace"), (OLD2, NEW2, "procurement-center")]:
    if NEW.split(b'\r\n', 1)[0] in data and b"literature_url" in data:
        # Already patched (best-effort detection)
        pass
    n = data.count(OLD)
    if n == 0:
        did.append(f"skip {label} (anchor missing or already patched)")
        continue
    if n != 1:
        did.append(f"WARN {label}: multi-anchor count={n}")
        continue
    # Check we haven't already patched this specific spot
    around = data[data.find(OLD): data.find(OLD) + len(OLD) + 100]
    if b"ec.literature_url" in around:
        did.append(f"{label} already patched")
        continue
    data = data.replace(OLD, NEW)
    did.append(f"patched {label}")

TARGET.write_bytes(data)
for line in did:
    print(line)
