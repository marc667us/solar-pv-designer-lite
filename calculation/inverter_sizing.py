# calculation/inverter_sizing.py
# Sizes the inverter based on peak demand

def size_inverter(total_load_kwh):
    """
    Calculate required inverter size.

    Assumptions:
        - Peak demand is estimated at 30% of total daily load
        - Safety factor of 1.25 is applied

    Parameters:
        total_load_kwh (float): Total daily energy demand (kWh/day)

    Returns:
        inverter_kw (float): Required inverter rated output (kW)
    """
    peak_demand_kw = total_load_kwh * 0.30
    inverter_kw = round(peak_demand_kw * 1.25, 2)

    print("\n--- Inverter Sizing ---")
    print(f"  Total Load        : {total_load_kwh:.2f} kWh/day")
    print(f"  Est. Peak Demand  : {peak_demand_kw:.2f} kW")
    print(f"  Safety Factor     : 1.25")
    print(f"  Inverter Size     : {inverter_kw:.2f} kW")

    return inverter_kw
