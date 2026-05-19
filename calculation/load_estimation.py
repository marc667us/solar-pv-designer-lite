# calculation/load_estimation.py
# Calculates total daily energy load from user-supplied load categories

def estimate_load(lighting_kwh, socket_kwh, ac_kwh):
    """
    Sum up the three load categories and return total daily load.

    Parameters:
        lighting_kwh (float): Daily energy from lighting loads (kWh/day)
        socket_kwh   (float): Daily energy from socket/plug loads (kWh/day)
        ac_kwh       (float): Daily energy from air conditioning loads (kWh/day)

    Returns:
        total_kwh (float): Total daily energy demand (kWh/day)
    """
    total_kwh = lighting_kwh + socket_kwh + ac_kwh

    print("\n--- Load Summary ---")
    print(f"  Lighting Load : {lighting_kwh:.2f} kWh/day")
    print(f"  Socket Load   : {socket_kwh:.2f} kWh/day")
    print(f"  AC Load       : {ac_kwh:.2f} kWh/day")
    print(f"  Total Load    : {total_kwh:.2f} kWh/day")

    return total_kwh
