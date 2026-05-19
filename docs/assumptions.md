# Design Assumptions

Default engineering assumptions for the Intelligent Global PV Solar System Design platform.
The platform is globally deployable — these are defaults only and shall be configurable
per project, region, and standard (BS 7671 / IEC / NEC).

## Location & Solar Resource
- **Location:** Configurable per project — not restricted to any region.
- **Peak Sun Hours:** Configurable per site. Default placeholder 5 h/day pending
  site-specific irradiance data (e.g. from a solar resource database or utility API).
- **Climate:** Derived from project location.

## System Performance
- **System Efficiency Factor:** 0.75 (75%) default
  - Accounts for wiring losses, inverter inefficiency, soiling, and temperature derating.
  - Configurable per project.

## Battery Storage
- **Depth of Discharge (DoD):** 80% default (assumes LiFePO4 chemistry; configurable).
- **Autonomy:** 1 day default — configurable per design.

## PV Modules
- **Module Rating:** 400 Wp default (configurable from the appliance/component library).
- **Type:** Monocrystalline Silicon default.

## Inverter
- **Peak Demand Estimate:** 25% of daily load (kW) default.
- **Safety Factor:** 1.25 applied to inverter sizing default.

## System Voltage
- **DC Bus Voltage:** Selectable — 12V / 24V / 48V / 96V (see SPEC.md §4.6).
- **AC System:** Single-phase or three-phase, selectable.

## Load Profile
- Loads defined per the Load Collection Form (SPEC.md §4.3): type, name, voltage,
  wattage, quantity, hours of use.
- Diversity / demand factors to be applied in the Load Analysis and Distribution
  Design modules.

## Standards
Calculations and component selection shall follow the standard selected for the
project: UK (BS 7671, MCS), Europe (IEC, EN), or USA (NEC, IEEE).
