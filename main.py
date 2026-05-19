# main.py
# Solar PV Designer Lite - Entry Point
# Asks user for load inputs, sizes the system, and generates output documents.

import os
from calculation.load_estimation import estimate_load
from calculation.pv_sizing import size_pv
from calculation.battery_sizing import size_battery
from calculation.inverter_sizing import size_inverter
from calculation.boq_generator import generate_boq
from calculation.specification_generator import generate_specification
from calculation.installation_method_generator import generate_installation_method


def get_float(prompt):
    """Prompt user for a positive float value."""
    while True:
        try:
            value = float(input(prompt))
            if value < 0:
                print("  Please enter a value of 0 or greater.")
            else:
                return value
        except ValueError:
            print("  Invalid input. Please enter a number.")


def generate_report(lighting, sockets, ac, total_load,
                    pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
    """Write a summary design report to output/report.txt."""
    os.makedirs("output", exist_ok=True)

    lines = [
        "SOLAR PV SYSTEM DESIGN REPORT",
        "=" * 60,
        "Project  : Solar PV Off-Grid System",
        "Location : Ghana",
        "Date     : 2026-04-10",
        "Tool     : Solar PV Designer Lite",
        "=" * 60,
        "",
        "1. LOAD SUMMARY",
        "-" * 40,
        f"  Lighting Load : {lighting:.2f} kWh/day",
        f"  Socket Load   : {sockets:.2f} kWh/day",
        f"  AC Load       : {ac:.2f} kWh/day",
        f"  Total Load    : {total_load:.2f} kWh/day",
        "",
        "2. DESIGN ASSUMPTIONS",
        "-" * 40,
        "  Location              : Ghana",
        "  Peak Sun Hours        : 5 h/day",
        "  System Efficiency     : 0.75 (75%)",
        "  Battery DoD           : 80%",
        "  Autonomy              : 1 day",
        "  DC System Voltage     : 48V",
        "",
        "3. SIZING RESULTS",
        "-" * 40,
        f"  PV Array Size         : {pv_kw:.2f} kWp",
        f"  No. of PV Modules     : {num_panels} x 400 Wp modules",
        f"  Battery Capacity      : {battery_kwh:.2f} kWh",
        f"  No. of Battery Units  : {num_batteries} x 2.4 kWh units",
        f"  Inverter Size         : {inverter_kw:.2f} kW",
        "",
        "4. OUTPUT FILES",
        "-" * 40,
        "  output/report.txt",
        "  output/boq.txt",
        "  output/pv_master_technical_specification.txt",
        "  output/installation_method_report.txt",
        "",
        "=" * 60,
        "End of Report",
    ]

    content = "\n".join(lines)

    with open("output/report.txt", "w") as f:
        f.write(content)

    print("  Report saved to output/report.txt")


def main():
    print("=" * 60)
    print("   SOLAR PV DESIGNER LITE")
    print("   Off-Grid System Sizing Tool")
    print("=" * 60)
    print("\nEnter daily energy consumption for each load category.")
    print("(Enter 0 if a category does not apply)\n")

    # Step 1: Collect load inputs from user
    lighting = get_float("  Lighting Load  (kWh/day): ")
    sockets  = get_float("  Socket Load    (kWh/day): ")
    ac       = get_float("  AC/HVAC Load   (kWh/day): ")

    # Step 2: Calculate total load
    total_load = estimate_load(lighting, sockets, ac)

    if total_load == 0:
        print("\n  Total load is 0 kWh/day. Please enter at least one load value.")
        return

    # Step 3: Size PV array
    pv_kw, num_panels = size_pv(total_load)

    # Step 4: Size battery storage
    battery_kwh, num_batteries = size_battery(total_load)

    # Step 5: Size inverter
    inverter_kw = size_inverter(total_load)

    # Step 6: Generate output documents
    print("\n--- Generating Output Files ---")
    generate_report(lighting, sockets, ac, total_load,
                    pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw)

    generate_boq(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw)

    generate_specification(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw)

    generate_installation_method(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw)

    print("\n" + "=" * 60)
    print("  Design complete. Check the output/ folder for results.")
    print("=" * 60)


if __name__ == "__main__":
    main()
