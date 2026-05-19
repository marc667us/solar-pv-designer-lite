# calculation/pv_sizing.py
# Sizes the PV array based on total daily load

from config.system_inputs import PEAK_SUN_HOURS, SYSTEM_EFFICIENCY, TEMP_DERATING, PANEL_WP
import math

def size_pv(total_load_kwh):
    """
    Calculate required PV array size, incorporating region-specific peak sun hours
    and panel temperature derating factor.

    Formula:
        Effective Efficiency = System Efficiency × Temperature Derating
        PV (kWp) = Total Load (kWh/day) / (Peak Sun Hours × Effective Efficiency)

    Parameters:
        total_load_kwh (float): Total daily energy demand (kWh/day)

    Returns:
        pv_kw      (float): Required PV array size (kWp)
        num_panels (int):   Number of panels required
    """
    effective_eff = SYSTEM_EFFICIENCY * TEMP_DERATING
    pv_kw = total_load_kwh / (PEAK_SUN_HOURS * effective_eff)
    num_panels = math.ceil((pv_kw * 1000) / PANEL_WP)

    print("\n--- PV Array Sizing ---")
    print(f"  Total Load           : {total_load_kwh:.2f} kWh/day")
    print(f"  Peak Sun Hours       : {PEAK_SUN_HOURS} h/day")
    print(f"  System Efficiency    : {SYSTEM_EFFICIENCY}")
    print(f"  Temp Derating Factor : {TEMP_DERATING:.4f}")
    print(f"  Effective Efficiency : {effective_eff:.4f}")
    print(f"  PV Array Size        : {pv_kw:.2f} kWp")
    print(f"  Panel Rating         : {PANEL_WP} Wp")
    print(f"  No. of Panels        : {num_panels} modules")

    return pv_kw, num_panels
