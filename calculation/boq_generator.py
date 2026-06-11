# calculation/boq_generator.py
# Generates the Bill of Quantities and saves to output/boq.txt

import os

def generate_boq(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
    """
    Build and write the Bill of Quantities with rate and amount columns.

    Parameters:
        pv_kw         (float): PV array size (kWp)
        num_panels    (int):   Number of PV modules
        battery_kwh   (float): Total battery capacity (kWh)
        num_batteries (int):   Number of battery units
        inverter_kw   (float): Inverter rated output (kW)
    """
    os.makedirs("output", exist_ok=True)

    # Column widths
    W_NO   = 4
    W_DESC = 36
    W_QTY  = 5
    W_UNIT = 5
    W_RATE = 12
    W_TRATE= 12
    W_AMT  = 14

    TOTAL_WIDTH = W_NO + W_DESC + W_QTY + W_UNIT + W_RATE + W_TRATE + W_AMT + 14

    def row(no, desc, qty, unit, basic_rate="", total_rate="", amount=""):
        return (
            f"{str(no):<{W_NO}} "
            f"{desc:<{W_DESC}} "
            f"{str(qty):>{W_QTY}} "
            f"{unit:<{W_UNIT}} "
            f"{basic_rate:>{W_RATE}} "
            f"{total_rate:>{W_TRATE}} "
            f"{amount:>{W_AMT}}"
        )

    header = row("No.", "Description", "Qty", "Unit", "Basic Rate", "Total Rate", "Amount (GHS)")
    divider = "-" * len(header)

    # Overhead / profit uplift factor applied to basic rates (20%)
    UPLIFT = 1.20

    def fmt(val):
        """Format a number as GHS currency string with commas."""
        return f"{val:,.2f}"

    # Inverter basic rate scales with output kW (reviewed April 2026)
    if   inverter_kw <= 3: inv_basic = 4_500.00   # e.g. Growatt SPF 3000 / Goodwe 3 kW
    elif inverter_kw <= 5: inv_basic = 5_800.00   # e.g. Growatt SPF 5000 / Goodwe 5 kW
    elif inverter_kw <= 8: inv_basic = 8_500.00   # e.g. Victron Multiplus 5000 class
    else:                  inv_basic = 12_000.00  # 10+ kW three-phase / larger hybrid

    # Item data: (no, description, qty, unit, basic_rate_GHS)
    # Basic rates — Ghana market research April 2026 (landed price incl. duty + VAT):
    #   Panels   : 1,600 GHS per 400 Wp quality brand (Jinko/JA Solar/LONGi class)
    #              at USD/GHS ~16, FOB ~$65 + duty 12.5% + VAT 21.9% + margin
    #   Inverter : Scaled by kW — 4,500–12,000 GHS (Growatt / Goodwe / Victron class)
    #   Battery  : 3,800 GHS per 2.4 kWh LiFePO4 (Pylontech US2000 class)
    #   Mounting : 280 GHS per panel (galvanised rail + clamps, local fabrication)
    #   Combiner : 700 GHS per string box (4-string, with fuses)
    #   DC cable : 18 GHS/m for 6mm² UV-resistant solar cable (Supply Master GH)
    #   AC cable : 19 GHS/m for 10mm² armoured cable (Supply Master GH)
    #   Breakers : 55 GHS per DC MCB (Schneider / ABB class, Jiji.com.gh)
    #   MCB+RCCB : 220 GHS per AC protection set (Apt Ghana / Jiji.com.gh)
    #   SPD      : 350 GHS per device (DC + AC pair, Type 2, local market)
    #   Earthing : 450 GHS per set (rod + bonding cable, Supply Master GH)
    #   Bat rack : 750 GHS per enclosure (local fabrication, powder-coat steel)
    #   Trunking : 900 GHS per lot (PVC trunking + conduit, BS EN 61386)
    #   Misc     : 600 GHS allowance (connectors, MC4, labels, cable ties)
    items = [
        (1,  f"PV Solar Modules (400 Wp each)",                  num_panels,    "No.", 1_600.00),
        (2,  f"Hybrid Inverter ({inverter_kw:.1f}kW, 415/230V)", 1,             "No.", inv_basic),
        (3,  "Battery Units (2.4 kWh LiFePO4 each)",             num_batteries, "No.", 3_800.00),
        (4,  "PV Mounting Structure (rail + clamps)",             num_panels,    "No.",   280.00),
        (5,  "DC Combiner / String Box (4-string)",               1,             "No.",   700.00),
        (6,  "DC Cable 6mm² (UV-resistant solar cable)",         50,            "m",      18.00),
        (7,  "AC Cable 10mm²",                                   20,            "m",      19.00),
        (8,  "DC Circuit Breakers (BS EN 60947-2)",               4,             "No.",    55.00),
        (9,  "AC MCB + RCCB (BS EN 60898 / 61008)",              2,             "No.",   220.00),
        (10, "Surge Protection Device SPD (BS EN 61643)",         2,             "No.",   350.00),
        (11, "Earthing Rod & Bonding Cable (BS 7430)",            1,             "Set",   450.00),
        (12, "Battery Enclosure / Rack",                          1,             "No.",   750.00),
        (13, "Cable Trunking & Conduit (BS EN 61386)",            1,             "Lot",   900.00),
        (14, "Miscellaneous Fixings & Hardware",                  1,             "Lot",   600.00),
    ]

    grand_total = 0.0
    item_rows = []
    for no, desc, qty, unit, basic_rate in items:
        total_rate = basic_rate * UPLIFT
        amount     = qty * total_rate
        grand_total += amount
        item_rows.append(
            row(no, desc, qty, unit,
                fmt(basic_rate), fmt(total_rate), fmt(amount))
        )

    lines = [
        "BILL OF QUANTITIES (BoQ)",
        "=" * len(header),
        "Project  : PV Solar Off-Grid System",
        "Location : Ghana",
        "Standard : BS 7671:2018 (18th Edition)",
        "Voltage  : 415/230V AC, 50 Hz",
        "Date     : 2026-04-10",
        "=" * len(header),
        "",
        "Currency : GHS (Ghanaian Cedi)",
        "Rates    : Basic Rate = market supply cost (Ghana, April 2026)",
        "         : Total Rate = Basic Rate x 1.20 (incl. delivery,",
        "         :              handling, contractor overhead & profit)",
        "",
        header,
        divider,
        *item_rows,
        divider,
        row("", "GRAND TOTAL (GHS)", "", "", "", "", fmt(grand_total)),
        "",
        f"  Total PV Capacity : {pv_kw:.2f} kWp",
        f"  Total Battery     : {battery_kwh:.2f} kWh",
        f"  Inverter Rating   : {inverter_kw:.2f} kW",
        "",
        "Note: Basic rates from Ghana market research (April 2026).",
        "      Panel: 1,600 GHS / 400Wp (Jinko/JA/LONGi class, landed incl. duty+VAT).",
        "      Battery: 3,800 GHS / 2.4 kWh LiFePO4 (Pylontech class).",
        "      Inverter: 4,500–12,000 GHS scaled by kW rating.",
        "      Quantities subject to detailed design review.",
        "      All prices exclude site-specific VAT adjustments.",
        "      Subject to contractor quotation and site survey confirmation.",
    ]

    content = "\n".join(lines)

    with open("output/boq.txt", "w", encoding="utf-8") as f:
        f.write(content)

    print("\n  BoQ saved to output/boq.txt")
