# calculation/specification_generator.py
# Generates the PV Master Technical Specification

import os

def generate_specification(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
    """
    Build and write the PV Master Technical Specification.

    Parameters:
        pv_kw         (float): PV array size (kWp)
        num_panels    (int):   Number of PV modules
        battery_kwh   (float): Total battery capacity (kWh)
        num_batteries (int):   Number of battery units
        inverter_kw   (float): Inverter rated output (kW)
    """
    os.makedirs("output", exist_ok=True)

    lines = [
        "PV MASTER TECHNICAL SPECIFICATION",
        "=" * 60,
        "Project  : PV Solar Off-Grid System",
        "Location : Ghana",
        "Date     : 2026-04-10",
        "Prepared : SolarPro Global — PV Solar Designer Lite",
        "=" * 60,
        "",
        "1. PV MODULES",
        "-" * 50,
        "  1.1 Type               : Monocrystalline Silicon",
        f"  1.2 Rated Power        : 400 Wp per module",
        f"  1.3 Quantity           : {num_panels} modules",
        f"  1.4 Total Array Size   : {pv_kw:.2f} kWp",
        "  1.5 Open Circuit Volt. : ≥ 40V (typical)",
        "  1.6 Short Circuit Curr.: ≥ 10A (typical)",
        "  1.7 Temperature Coeff. : ≤ -0.40%/°C (Pmax)",
        "  1.8 Mounting           : Fixed-tilt, roof or ground",
        "  1.9 Warranty           : 25-year linear power output",
        "  1.10 Certification     : BS EN 61215, BS EN 61730",
        "",
        "2. INVERTER / CHARGER",
        "-" * 50,
        "  2.1 Type               : Hybrid Inverter/Charger",
        f"  2.2 Rated AC Output    : {inverter_kw:.2f} kW",
        "  2.3 AC Output Voltage  : 415/230V AC, 3-phase/single-phase, 50 Hz",
        "  2.4 DC Input Voltage   : 48V DC nominal",
        "  2.5 Efficiency         : ≥ 95%",
        "  2.6 Protection Class   : IP65 or better",
        "  2.7 Features           : MPPT charge controller, auto transfer switch",
        "  2.8 Certification      : BS EN 62109, BS 7671 compliant",
        "",
        "3. BATTERY STORAGE",
        "-" * 50,
        "  3.1 Chemistry          : Lithium Iron Phosphate (LiFePO4)",
        f"  3.2 Total Capacity     : {battery_kwh:.2f} kWh",
        f"  3.3 Number of Units    : {num_batteries} units (2.4 kWh each)",
        "  3.4 Nominal Voltage    : 48V DC",
        "  3.5 Depth of Discharge : 80%",
        "  3.6 Cycle Life         : ≥ 2000 cycles at 80% DoD",
        "  3.7 BMS                : Integrated Battery Management System",
        "  3.8 Operating Temp.    : 0°C to 45°C",
        "  3.9 Certification      : BS EN 62619, UN38.3",
        "",
        "4. CABLING",
        "-" * 50,
        "  4.1 DC Array Cable     : 6mm² twin-core, UV-resistant, copper, XLPE — BS 7671",
        "  4.2 DC Battery Cable   : 16mm² flexible copper, rated ≥ 100A — BS 6724",
        "  4.3 AC Output Cable    : 10mm² single-core copper, XLPE — BS 5467",
        "  4.4 Earthing Cable     : 10mm² green/yellow copper — BS 7671",
        "  4.5 Cable Routing      : PVC conduit or metal trunking — BS EN 61386",
        "  4.6 Voltage Drop       : DC ≤ 1%, AC ≤ 3% (per BS 7671)",
        "",
        "5. PROTECTION DEVICES",
        "-" * 50,
        "  5.1 DC String Fuses    : 15A per string, in combiner box — BS 88",
        "  5.2 DC Circuit Breaker : Rated for DC, upstream of inverter — BS EN 60947-2",
        "  5.3 AC MCB             : 32A, Type B, on AC output — BS EN 60898",
        "  5.4 RCCB               : 30mA sensitivity, on AC distribution — BS EN 61008",
        "  5.5 Surge Protection   : Type II SPD on DC and AC sides — BS EN 61643",
        "  5.6 Isolation Switch   : Lockable DC isolator at array — BS EN 60947-3",
        "",
        "6. EARTHING & BONDING",
        "-" * 50,
        "  6.1 Earthing System    : TN-S arrangement — BS 7671 Part 5",
        "  6.2 Earth Electrode    : Copper-clad rod, ≥ 1.2m depth — BS 7430",
        "  6.3 Earth Resistance   : ≤ 5 Ohms",
        "  6.4 Bonding            : All metalwork bonded to main earth bar — BS 7671",
        "  6.5 PV Frame Bonding   : Continuous earth conductor across all frames",
        "",
        "7. TESTING & COMMISSIONING",
        "-" * 50,
        "  7.1 Insulation Test    : ≥ 1 MOhm (DC wiring, 500V megger) — BS 7671",
        "  7.2 Earth Continuity   : ≤ 0.1 Ohm between earth points — BS 7671",
        "  7.3 Polarity Check     : All DC circuits verified before connection",
        "  7.4 Functional Test    : Full system loaded operation for minimum 1 hour",
        "  7.5 Battery Test       : Charge/discharge cycle verified",
        "  7.6 Documentation      : As-built drawings, test certificates, O&M manual",
        "  7.7 Applicable Code    : BS 7671:2018 (18th Edition Wiring Regulations)",
        "",
        "=" * 60,
        "End of PV Master Technical Specification",
    ]

    content = "\n".join(lines)

    with open("output/pv_master_technical_specification.txt", "w", encoding="utf-8") as f:
        f.write(content)

    print("  Specification saved to output/pv_master_technical_specification.txt")
