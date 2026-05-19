# config/system_inputs.py
# System design constants and assumptions

LOCATION          = "Ghana"
SELECTED_REGION   = "Greater Accra"   # one of the 16 Ghana regions
PEAK_SUN_HOURS    = 4.8    # hours/day — updated by region selection
SYSTEM_EFFICIENCY = 0.75   # accounts for wiring, inverter, soiling, temperature
TEMP_DERATING     = 1.0    # panel temperature derating factor (updated by region)
BATTERY_DOD       = 0.80   # depth of discharge (80%)
AUTONOMY_DAYS     = 1      # days of battery autonomy
SYSTEM_VOLTAGE    = 48     # DC bus voltage (V)
PANEL_WP          = 400    # watt-peak per PV module
BATTERY_UNIT_KWH  = 2.4    # kWh capacity per battery unit
