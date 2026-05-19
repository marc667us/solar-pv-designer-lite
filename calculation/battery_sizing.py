# calculation/battery_sizing.py
# Sizes the battery bank based on total daily load

from config.system_inputs import BATTERY_DOD, AUTONOMY_DAYS, BATTERY_UNIT_KWH
import math

def size_battery(total_load_kwh):
    """
    Calculate required battery storage capacity.

    Formula:
        Battery (kWh) = Total Load x Autonomy Days / DoD

    Parameters:
        total_load_kwh (float): Total daily energy demand (kWh/day)

    Returns:
        battery_kwh  (float): Required usable battery capacity (kWh)
        num_batteries (int):  Number of battery units required
    """
    battery_kwh = (total_load_kwh * AUTONOMY_DAYS) / BATTERY_DOD
    num_batteries = math.ceil(battery_kwh / BATTERY_UNIT_KWH)

    print("\n--- Battery Sizing ---")
    print(f"  Total Load          : {total_load_kwh:.2f} kWh/day")
    print(f"  Autonomy            : {AUTONOMY_DAYS} day(s)")
    print(f"  Depth of Discharge  : {int(BATTERY_DOD * 100)}%")
    print(f"  Required Capacity   : {battery_kwh:.2f} kWh")
    print(f"  Battery Unit Size   : {BATTERY_UNIT_KWH} kWh")
    print(f"  No. of Batteries    : {num_batteries} units")

    return battery_kwh, num_batteries
