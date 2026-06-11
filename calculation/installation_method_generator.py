# calculation/installation_method_generator.py
# Generates the Installation Method Report:
#   output/installation_method_report.txt  – plain text with ASCII diagrams
#   output/installation_method_report.html – styled HTML with embedded SVG diagrams

import os
from calculation.diagram_generator import (
    system_architecture_svg,
    mounting_structure_svg,
    string_wiring_svg,
    combiner_box_svg,
    inverter_connections_svg,
    battery_bank_svg,
    earthing_system_svg,
    ac_distribution_board_svg,
)
from config.ghana_regions import REGIONS, POWER_ISSUES
import config.system_inputs as _cfg

def generate_installation_method(pv_kw, num_panels, battery_kwh, num_batteries, inverter_kw):
    """
    Build and write the Installation Method Report.

    Parameters:
        pv_kw         (float): PV array size (kWp)
        num_panels    (int):   Number of PV modules
        battery_kwh   (float): Total battery capacity (kWh)
        num_batteries (int):   Number of battery units
        inverter_kw   (float): Inverter rated output (kW)
    """
    os.makedirs("output", exist_ok=True)

    # Derive string configuration for wiring diagrams
    # Split panels into two strings as evenly as possible
    string_a = num_panels // 2
    string_b = num_panels - string_a

    L = "=" * 78
    S = "-" * 78
    s = "-" * 50

    # Pull live region data from config
    region_name  = getattr(_cfg, "SELECTED_REGION", "Greater Accra")
    region       = REGIONS.get(region_name, {})
    power        = POWER_ISSUES.get(region_name, {})
    temp_der     = getattr(_cfg, "TEMP_DERATING", 1.0)
    eff_eff      = getattr(_cfg, "SYSTEM_EFFICIENCY", 0.75) * temp_der

    lines = []

    # -----------------------------------------------------------------------
    # HEADER
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  INSTALLATION METHOD REPORT",
        "  PV Solar Off-Grid System",
        L,
        f"  Project   : PV Solar Off-Grid System",
        f"  Location  : Ghana — {region_name}  ({region.get('capital', '')})",
        f"  Standard  : BS 7671:2018 (18th Edition)",
        f"  PV Array  : {pv_kw:.2f} kWp  ({num_panels} x 400 Wp modules)",
        f"  Battery   : {battery_kwh:.2f} kWh  ({num_batteries} x 2.4 kWh units)",
        f"  Inverter  : {inverter_kw:.2f} kW Hybrid Inverter/Charger",
        f"  Date      : 2026-04-10",
        L,
        "",
        "  This report describes the method of installation for each item in",
        "  the Bill of Quantities (BoQ).  It includes installation narratives,",
        "  step-by-step procedures, tools required, and installation diagrams.",
        "  All work shall comply with BS 7671:2018 and manufacturer instructions.",
        "",
    ]

    # -----------------------------------------------------------------------
    # SECTION 0A — REGIONAL CONTEXT & SITE CONDITIONS
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  SECTION 0A — REGIONAL CONTEXT & SITE CONDITIONS",
        L,
        "",
        "  Understanding the installation site's solar resource, climate, and grid",
        "  reliability is essential for safe and optimised system installation.",
        "",
        "  ┌─────────────────────────────────────────────────────────────────────┐",
        "  │  SOLAR RESOURCE SUMMARY                                             │",
        "  ├─────────────────────────────────────────────────────────────────────┤",
        f"  │  Region              : {region_name:<46}│",
        f"  │  Capital City        : {region.get('capital','—'):<46}│",
        f"  │  Climate Zone        : {region.get('climate','—'):<46}│",
        f"  │  Peak Sun Hours      : {str(region.get('psh','—')) + ' h/day':<46}│",
        f"  │  Annual GHI          : {str(region.get('ghi_annual','—')) + ' kWh/m²/yr':<46}│",
        f"  │  Avg. Temperature    : {str(region.get('avg_temp','—')) + ' °C (annual)':<46}│",
        f"  │  Temp Derating Factor: {temp_der:.4f}  (panel loss above 25 °C STC)       │",
        f"  │  Effective Efficiency: {eff_eff:.4f}  (system eff × temp derating)       │",
        f"  │  Recommended Tilt    : {str(region.get('tilt_angle','—')) + '° fixed, face equator':<46}│",
        f"  │  Rainy Season        : {region.get('rainy_months','—'):<46}│",
        f"  │  Solar Rating        : {region.get('rating','—'):<46}│",
        "  └─────────────────────────────────────────────────────────────────────┘",
        "",
        "  ┌─────────────────────────────────────────────────────────────────────┐",
        "  │  GRID & POWER RELIABILITY                                           │",
        "  ├─────────────────────────────────────────────────────────────────────┤",
        f"  │  Distribution Utility: {power.get('ecg_zone','—'):<46}│",
        f"  │  Est. Daily Outage   : {power.get('daily_outage_hrs','—'):<46}│",
        f"  │  Grid Coverage       : {str(power.get('grid_coverage_pct','—')) + '%':<46}│",
        f"  │  Reliability Rating  : {power.get('reliability','—'):<46}│",
        "  ├─────────────────────────────────────────────────────────────────────┤",
        "  │  Key Grid Issues:                                                   │",
    ]
    for issue in power.get("main_issues", []):
        lines.append(f"  │    • {issue:<64}│")
    lines += [
        "  └─────────────────────────────────────────────────────────────────────┘",
        "",
        "  INSTALLATION NOTES FOR THIS REGION:",
        f"  {region.get('notes', '')}",
        "",
        "  The poor grid reliability above justifies an off-grid / hybrid solar",
        "  system as the primary or backup power supply for this installation.",
        "",
    ]

    # -----------------------------------------------------------------------
    # OVERALL SYSTEM DIAGRAM
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  SECTION 0 — OVERALL SYSTEM ARCHITECTURE DIAGRAM",
        L,
        "",
        "  The diagram below shows the complete power flow of the system,",
        "  from PV array through to AC loads.",
        "",
        "  ┌──────────────────────────────────────────────────────────────┐",
        "  │                    PV ARRAY ON ROOF                         │",
        "  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │",
        "  │  │ Panel 1  │  │ Panel 2  │  │ Panel 3  │  │ Panel .. │   │",
        "  │  │  400 Wp  │  │  400 Wp  │  │  400 Wp  │  │  400 Wp  │   │",
        "  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │",
        "  │       └─────────────┴──────────────┴─────────────┘         │",
        "  │                         │ DC (String cables)                │",
        "  └─────────────────────────┼──────────────────────────────────┘",
        "                            │",
        "                     ┌──────▼──────┐",
        "                     │  DC COMBINER│  ← SPD (DC side)",
        "                     │  STRING BOX │",
        "                     └──────┬──────┘",
        "                            │ DC Cable 6mm²",
        "                     ┌──────▼──────────────────┐",
        "                     │   HYBRID INVERTER        │",
        "                     │   CHARGER / MPPT         │◄─── Battery Bank",
        "                     │   {:.2f} kW              │     ({} units)".format(inverter_kw, num_batteries),
        "                     └──────┬──────────────────┘",
        "                            │ AC Cable 10mm²",
        "                     ┌──────▼──────┐",
        "                     │  AC MCB +   │  ← SPD (AC side)",
        "                     │  RCCB BOARD │",
        "                     └──────┬──────┘",
        "                            │",
        "                  ┌─────────┴──────────┐",
        "                  │                    │",
        "           ┌──────▼──────┐    ┌────────▼────────┐",
        "           │  LIGHTING   │    │  SOCKET OUTLETS │",
        "           │   CIRCUIT   │    │    CIRCUIT      │",
        "           └─────────────┘    └─────────────────┘",
        "",
        "  NOTE: Earth conductor runs from earth rod to all metalwork,",
        "        module frames, inverter chassis, battery rack, and DB board.",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 4 — MOUNTING STRUCTURE  (install first — panels need mounts)
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 4 — PV MOUNTING STRUCTURE",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  Aluminium mounting rails and brackets are fixed to the roof structure",
        "  to carry the PV modules.  The structure must be designed for Ghana's",
        "  wind and rain loads, pitched at the optimal tilt angle (10°–15° for",
        "  Ghana's latitude of ~6°N) to maximise irradiance and self-cleaning.",
        "  All fixings shall be stainless steel or hot-dip galvanised to prevent",
        "  corrosion in the tropical climate.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Tape measure and chalk line",
        "    • Spirit level (600 mm minimum)",
        "    • Drill with 10 mm and 12 mm masonry/metal bits",
        "    • Angle grinder (for rail cutting)",
        "    • Spanner set and socket set (M8, M10, M12)",
        "    • Torque wrench (set to manufacturer spec, typically 12–16 Nm)",
        "    • Safety harness and fall-arrest lanyard",
        "    • Roof anchor point or scaffold",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Carry out a roof survey.  Check rafter/purlin spacing,",
        "           roofing material, load-bearing capacity, and slope.",
        "",
        "  Step 2.  Mark the panel layout on the roof using a chalk line.",
        "           Maintain a minimum 300 mm clearance from roof edges.",
        "",
        "  Step 3.  Locate and mark roof fixing points directly above rafters",
        "           or purlins.  Space rail brackets at ≤ 1,200 mm centres.",
        "",
        "  Step 4.  Drill pilot holes.  Fit roof hooks or L-feet brackets with",
        "           EPDM gaskets or sealant to prevent water ingress.",
        "",
        "  Step 5.  Bolt the aluminium rails onto the brackets.  Level each",
        "           rail with a spirit level.  Torque all bolts to spec.",
        "",
        "  Step 6.  Fit end-clamps and mid-clamps loosely along the rail,",
        "           ready to receive the panel frames.",
        "",
        "  Step 7.  Attach the earth bonding lug to each rail section.",
        "           Run the continuous earth conductor through the lugs.",
        "",
        "  Step 8.  Inspect all fixings before placing panels.",
        "",
        "  MOUNTING STRUCTURE DIAGRAM",
        "  " + s,
        "",
        "         ROOF SLOPE (10°–15° tilt toward south / equator)",
        "         ───────────────────────────────────────────────►",
        "",
        "         ┌──────────────────────────────────────────────┐  ← Rail (Al extrusion)",
        "         │  [Clamp]──[Panel Frame]──[Clamp]──[Panel]   │",
        "         │     │                      │                 │",
        "         │  [Bracket]            [Bracket]             │",
        "         │     │                      │                 │",
        "  ───────┼─────┼──────────────────────┼─────────────────┼── ROOF SURFACE",
        "         │  [Rafter]            [Rafter]                │",
        "",
        "  CROSS-SECTION (single bracket):",
        "",
        "       Panel frame",
        "         │",
        "    ─────┤ Mid-clamp",
        "         ├──── Al Rail ─────────────────",
        "         │",
        "         └── L-foot bracket",
        "               │",
        "        ───────┼──────  Roof surface",
        "               │  EPDM seal",
        "               └── Bolt into rafter",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 1 — PV SOLAR MODULES
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 1 — PV SOLAR MODULES (400 Wp EACH)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        f"  {num_panels} monocrystalline PV modules, each rated at 400 Wp, are mounted",
        "  on the pre-installed aluminium rail system.  Modules are connected in",
        "  strings using MC4 connectors and UV-resistant 6mm² solar cable.",
        f"  The {num_panels} modules are arranged in two strings: String A ({string_a} panels)",
        f"  and String B ({string_b} panels) connected in series to raise the string",
        "  voltage into the MPPT inverter's operating window (~80–160 V DC).",
        "  All modules must face true south (azimuth 180°) for Ghana's location.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Insulated gloves (voltage-rated)",
        "    • MC4 assembly tool / MC4 crimping tool",
        "    • MC4 spanner (spanners for locking MC4 connectors)",
        "    • Digital multimeter (DC voltage and current measurement)",
        "    • Clamp meter (for string current measurement)",
        "    • Torque wrench (for module clamp bolts)",
        "    • Rubber mallet",
        "    • Cable ties and UV-resistant labels",
        "    • Permanent marker for labelling polarity",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Before handling any module, confirm all DC isolators and",
        "           the inverter are switched OFF.",
        "",
        "  Step 2.  Lift module onto the rail.  NEVER step on the glass face.",
        "           Use two persons for each module on the roof.",
        "",
        "  Step 3.  Slide end-clamps onto the outer module frame edge and",
        "           mid-clamps between adjacent modules.  Hand-tighten only.",
        "",
        "  Step 4.  Check all modules are level and correctly aligned.",
        "           Torque all clamp bolts to manufacturer specification",
        "           (typically 10–14 Nm).  Do not over-torque.",
        "",
        "  Step 5.  Connect module MC4 leads in series within each string:",
        "           (+) of Module N connects to (−) of Module N+1.",
        "           Leave the open ends of each string disconnected.",
        "",
        "  Step 6.  Measure open-circuit voltage (Voc) of each string",
        "           with a multimeter before connecting to the combiner.",
        f"           Expected Voc per string: ~{string_a * 48:.0f}–{string_a * 50:.0f} V (String A),",
        f"           ~{string_b * 48:.0f}–{string_b * 50:.0f} V (String B).",
        "           If Voc reads 0 V or reversed, recheck polarity.",
        "",
        "  Step 7.  Route string cables neatly in cable trunking along the",
        "           rail or down the roof edge to the combiner box.",
        "           Secure cables every 400 mm with UV-resistant cable ties.",
        "",
        "  Step 8.  Label each string cable at both ends: 'STRING A (+)',",
        "           'STRING A (−)', 'STRING B (+)', 'STRING B (−)'.",
        "",
        "  PANEL STRING WIRING DIAGRAM",
        "  " + s,
        "",
        "  STRING A ({} panels in series):".format(string_a),
        "",
        "   [+]──┐                                             ┌──[−]",
        "   P1   │  [+]──┐              ┌──[−]  P{}   │".format(string_a),
        "  ──────┤  P2   ├── ... ───── ─┤  P{}  ├──────".format(string_a),
        "        └──[−]  │              │  [+]──┘",
        "                └──[−]  [+]───┘",
        "         │                                             │",
        "        (+) to Combiner Box                    (−) to Combiner Box",
        "",
        "  STRING B ({} panels in series):".format(string_b),
        "",
        "   [+]──┐                                             ┌──[−]",
        "   P1   │  [+]──┐              ┌──[−]  P{}   │".format(string_b),
        "  ──────┤  P2   ├── ... ────── ┤  P{}  ├──────".format(string_b),
        "        └──[−]  │              │  [+]──┘",
        "                └──[−]  [+]───┘",
        "         │                                             │",
        "        (+) to Combiner Box                    (−) to Combiner Box",
        "",
        "  MC4 CONNECTOR DETAIL:",
        "",
        "    Male MC4   ──────●═══════════●──────  Female MC4",
        "                     ↑           ↑",
        "               (+) locking    (−) locking",
        "                 connector     connector",
        "    Lock with MC4 spanner after seating (audible click).",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 5 — DC COMBINER / STRING BOX
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 5 — DC COMBINER / STRING BOX",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  The DC combiner box aggregates the two PV strings into a single",
        "  DC output fed to the inverter.  It contains string fuses (one per",
        "  string) and a DC surge protection device (SPD) to protect against",
        "  lightning-induced voltage transients.  It is mounted at the base",
        "  of the roof, at the transition from rooftop to indoor wiring,",
        "  in a weatherproof (IP65) enclosure.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Screwdrivers (flathead and Pozidriv)",
        "    • Wire strippers and crimping tool",
        "    • Multimeter (DC voltage)",
        "    • Drill with 20–25 mm knockout punch or hole saw",
        "    • Cable gland spanner",
        "    • Insulated terminal screwdriver",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Select a mounting position sheltered from direct rain",
        "           at the roof base or on an exterior wall, shaded if possible.",
        "",
        "  Step 2.  Fix the enclosure to the wall with stainless steel rawl-bolts.",
        "           Ensure the enclosure door faces downward or sideways",
        "           (never upward) to prevent water pooling at the seal.",
        "",
        "  Step 3.  Knock out cable entry holes.  Fit cable glands for each",
        "           incoming string cable and the outgoing DC main cable.",
        "",
        "  Step 4.  Mount the busbar, string fuses (15A, BS 88), and SPD",
        "           inside the enclosure per the manufacturer's diagram.",
        "",
        "  Step 5.  All DC wiring still disconnected — verify with multimeter.",
        "           Connect String A (+) and String B (+) to the fuse inputs.",
        "           Connect String A (−) and String B (−) to the negative busbar.",
        "",
        "  Step 6.  Connect the fuse outputs to the positive busbar.",
        "           Connect the SPD between the positive busbar and earth.",
        "",
        "  Step 7.  Run the DC main cable (6mm²) from the output busbars",
        "           through trunking to the inverter DC input.",
        "           Leave inverter end disconnected until inverter is installed.",
        "",
        "  Step 8.  Close the enclosure.  Label: 'DC COMBINER BOX –",
        "           DANGER: HIGH DC VOLTAGE. DO NOT OPEN UNDER LOAD.'",
        "",
        "  DC COMBINER BOX INTERNAL WIRING DIAGRAM",
        "  " + s,
        "",
        "  ┌─────────────────────────────────────────────────────────┐",
        "  │           DC COMBINER BOX (IP65 Enclosure)              │",
        "  │                                                         │",
        "  │  STRING A (+) ──── [Fuse 15A] ──┐                      │",
        "  │                                  ├── (+) Busbar ────────┼──► To Inverter (+)",
        "  │  STRING B (+) ──── [Fuse 15A] ──┘                      │",
        "  │                                        │                │",
        "  │                                      [SPD]              │",
        "  │                                        │                │",
        "  │  STRING A (−) ──────────────────────── (−) Busbar ─────┼──► To Inverter (−)",
        "  │  STRING B (−) ──────────────────────────────────────────┤",
        "  │                                        │                │",
        "  │                                      [Earth] ───────────┼──► Earth bar",
        "  └─────────────────────────────────────────────────────────┘",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 6 — DC CABLE 6mm²
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 6 — DC CABLE 6mm² (UV-RESISTANT)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  UV-resistant, double-insulated 6mm² DC solar cable (rated 1000 V DC,",
        "  XLPE insulation, tinned copper conductors) is used for all DC wiring",
        "  from module MC4 leads to the combiner box, and from the combiner box",
        "  to the inverter DC input.  Red/positive and black/negative cores are",
        "  kept segregated and clearly labelled throughout.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Cable reel stand",
        "    • Cable cutters",
        "    • Wire strippers (for 6mm²)",
        "    • MC4 crimping tool and MC4 contacts",
        "    • Cable trunking/conduit bending spring or bender",
        "    • Drill and fish tape (for threading through walls)",
        "    • UV-resistant cable tie gun",
        "    • Permanent marker and cable labels",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Measure and cut cable runs for each string, allowing",
        "           200–300 mm extra at each end for terminations.",
        "",
        "  Step 2.  Route cables inside UV-resistant trunking or conduit",
        "           on the roof surface.  Fix trunking every 600 mm.",
        "",
        "  Step 3.  Where cables pass through roof or wall penetrations,",
        "           use fire-rated conduit sleeves.  Seal with fire mastic.",
        "",
        "  Step 4.  Strip 12 mm of insulation at the MC4 connector end.",
        "           Crimp the MC4 contact onto the conductor.",
        "           Insert into the MC4 housing and click until locked.",
        "",
        "  Step 5.  Strip 15 mm of insulation at the combiner box end.",
        "           Insert into correct terminal and torque to spec.",
        "",
        "  Step 6.  Label each cable run at both ends with polarity (+/−)",
        "           and circuit identifier (e.g. 'STR-A POS').",
        "",
        "  Step 7.  Perform continuity check and insulation resistance test",
        "           (≥ 1 MOhm at 500 V DC) before energising.",
        "",
        "  DC CABLE ROUTING DIAGRAM",
        "  " + s,
        "",
        "   ROOF SURFACE",
        "   ─────────────────────────────────────────────────────────────",
        "   [Panel] ─── MC4 ─── [Trunking on rail] ─── MC4 ─── [Panel]",
        "                            │",
        "                     (string cables drop)",
        "                            │",
        "   WALL / SOFFIT ───────────┼─────────────────────────────────",
        "                            │ (conduit sleeve through roof/wall)",
        "                            │",
        "                     [Combiner Box]",
        "                            │",
        "                    (6mm² DC main cable)",
        "                            │",
        "                     [Inverter DC Input]",
        "",
        "  CABLE INSTALLATION CROSS-SECTION:",
        "",
        "      ┌──────────────────────┐",
        "      │   UV Trunking Lid    │",
        "      ├──────────────────────┤",
        "      │ (+) RED 6mm² cable  │",
        "      │ (−) BLK 6mm² cable  │",
        "      └──────────────────────┘",
        "              │",
        "       Fixed to rail or",
        "       roof surface",
        "       every 600 mm",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 12 — BATTERY ENCLOSURE / RACK
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 12 — BATTERY ENCLOSURE / RACK",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  The battery rack houses all LiFePO4 battery units in a ventilated",
        "  enclosure in a cool, dry indoor location — ideally a dedicated utility",
        "  room or shaded corner away from direct sunlight.  Batteries must be",
        "  positioned below the inverter for short, low-resistance cabling.",
        "  The rack must be secured to the wall or floor to prevent tipping.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Drill with rawl-plug bit",
        "    • Spirit level",
        "    • Spanner set",
        "    • Wall fixings (M8 stainless bolts / rawl bolts)",
        "    • Measuring tape",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Choose a location with natural or forced ventilation.",
        "           Minimum 300 mm clearance on all sides of the rack.",
        "           The location must be accessible for maintenance.",
        "",
        "  Step 2.  Mark fixing hole positions on the wall/floor.",
        "           Check with a spirit level that the base plate is level.",
        "",
        "  Step 3.  Drill and fit rawl bolts.  Secure the rack firmly.",
        "           Shake the empty rack to confirm it is stable.",
        "",
        "  Step 4.  Fit the battery units into the rack following the",
        "           manufacturer's stacking order (heaviest at the bottom).",
        "           Do NOT connect battery terminals yet.",
        "",
        "  Step 5.  Install inter-battery bus bars or cable links as supplied",
        "           by the manufacturer for the intended series/parallel config.",
        "",
        "  Step 6.  Apply ventilation grilles or drill vent holes at top and",
        "           bottom of the enclosure for convective airflow.",
        "",
        "  BATTERY RACK LAYOUT DIAGRAM",
        "  " + s,
        "",
        "       ┌──────────────────────────────┐",
        "       │      BATTERY ENCLOSURE       │",
        "       │  ┌────────────────────────┐  │◄── Vent (top)",
        "       │  │  Battery Unit {}        │  │".format(num_batteries),
        "       │  ├────────────────────────┤  │",
        "       │  │      ...               │  │",
        "       │  ├────────────────────────┤  │",
        "       │  │  Battery Unit 2        │  │",
        "       │  ├────────────────────────┤  │",
        "       │  │  Battery Unit 1        │  │◄── Vent (bottom)",
        "       │  └────────────────────────┘  │",
        "       │   (+)────────────── (−)       │",
        "       │    │                  │        │",
        "       └────┼──────────────────┼────────┘",
        "            │                  │",
        "     To Inverter (+)     To Inverter (−)",
        "     (16mm² red)         (16mm² black)",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 3 — BATTERIES
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 3 — BATTERY UNITS (2.4 kWh LIFEPO4 EACH)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        f"  {num_batteries} LiFePO4 battery units (each 2.4 kWh, 48V nominal) are",
        "  installed in the battery rack and wired in parallel to give a combined",
        f"  capacity of {battery_kwh:.2f} kWh at 48V DC.  Each unit has an integrated",
        "  Battery Management System (BMS) that provides over-charge, over-discharge,",
        "  short-circuit, and temperature protection.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Insulated screwdrivers and spanners",
        "    • Insulated gloves (rated ≥ 1000V)",
        "    • Multimeter (DC voltage measurement)",
        "    • Torque wrench (for terminal bolts)",
        "    • Anti-static wrist strap",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Confirm the inverter battery switch is OFF and no DC",
        "           circuit breaker is closed.  Verify with multimeter.",
        "",
        "  Step 2.  Check each battery unit's state of charge (SOC) with the",
        "           built-in indicator or BMS display.  All units should be",
        "           at the same SOC (±5%) before parallel connection.",
        "",
        "  Step 3.  Place Battery Unit 1 in the rack (bottom position).",
        "           Connect the BMS communication cable (CAN/RS485) if used.",
        "",
        "  Step 4.  Repeat for remaining units.  Stack in order per mfr spec.",
        "",
        "  Step 5.  Connect inter-unit busbars: (+) rail to (+) rail,",
        "           (−) rail to (−) rail (parallel configuration).",
        "           Torque terminal bolts to manufacturer spec (typically 8–12 Nm).",
        "",
        "  Step 6.  Connect the main battery cable: 16mm² red from battery (+)",
        "           bank to inverter battery (+); 16mm² black from battery (−)",
        "           to inverter battery (−).  CONNECT (−) FIRST, (+) LAST.",
        "",
        "  Step 7.  Measure total bank voltage with multimeter.",
        f"           Expected: 48–54 V DC for {num_batteries} units in parallel.",
        "",
        "  Step 8.  Do not close the inverter battery breaker until the",
        "           inverter is fully installed and configured.",
        "",
        "  BATTERY PARALLEL WIRING DIAGRAM",
        "  " + s,
        "",
        "  48V DC BUS BAR",
        "",
        "  (+) ────┬────────┬────────┬────── ... ────┬──── To Inverter (+)",
        "          │        │        │               │",
        "       [Bat 1]  [Bat 2]  [Bat 3]  ...  [Bat {}]".format(num_batteries),
        "          │        │        │               │",
        "  (−) ────┴────────┴────────┴────── ... ────┴──── To Inverter (−)",
        "",
        "  Each battery unit = 2.4 kWh / 48V LiFePO4 with integrated BMS.",
        f"  Total bank = {battery_kwh:.2f} kWh at 48V DC.",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 2 — HYBRID INVERTER
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 2 — HYBRID INVERTER / CHARGER",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        f"  The {inverter_kw:.2f} kW hybrid inverter/charger is the heart of the system.",
        "  It houses an MPPT charge controller (accepting PV DC input), a",
        "  battery charger, and a DC-to-AC inverter, all in one unit.  It",
        "  is wall-mounted indoors near the battery bank (≤ 1.5 m battery",
        "  cable run) in a ventilated location.  The inverter must be mounted",
        "  vertically on a solid wall that can bear ≥ 25 kg.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Drill (with M8 masonry bit)",
        "    • Spirit level",
        "    • Rawl plugs and M8 bolts (stainless)",
        "    • Insulated screwdrivers and spanner set",
        "    • Multimeter",
        "    • Torque wrench",
        "    • Laptop or smartphone with inverter configuration software",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Mark wall fixing positions from the mounting template",
        "           supplied with the inverter.  Ensure the unit will be",
        "           ≥ 500 mm from the floor and ≥ 300 mm from any obstruction.",
        "",
        "  Step 2.  Drill holes, fit rawl plugs, and mount the inverter",
        "           bracket/back-plate.  Verify level.  Hang the inverter unit.",
        "",
        "  Step 3.  Connect DC PV INPUT terminals:  (+) from combiner box",
        "           positive output; (−) from combiner box negative output.",
        "           Tighten to terminal torque spec.  Check polarity with meter.",
        "",
        "  Step 4.  Connect BATTERY terminals: (+) red 16mm², (−) black 16mm²",
        "           from battery bank.  Connect (−) first, then (+).",
        "           Tighten to spec.  Measure battery voltage on display.",
        "",
        "  Step 5.  Connect AC OUTPUT terminals: L (line), N (neutral), PE (earth)",
        "           using 10mm² cable to the AC distribution board.",
        "           Tighten to spec.",
        "",
        "  Step 6.  If a grid-input (GRID IN) port is present, connect the",
        "           utility supply line for auto-charging backup (optional).",
        "",
        "  Step 7.  Power on the inverter.  Navigate the settings menu:",
        "           a) Set battery type to LiFePO4 (Li-Fe).",
        f"          b) Set battery capacity to {battery_kwh:.1f} kWh.",
        "           c) Set charge voltage to 58.4 V (LiFePO4 full charge).",
        "           d) Set low-battery cut-off to 44 V (80% DoD).",
        "           e) Set AC output frequency to 50 Hz, voltage 230 V.",
        "           f) Set MPPT voltage window per PV string Voc readings.",
        "",
        "  Step 8.  Monitor display for correct PV charging current and",
        "           battery voltage.  Confirm AC output on voltmeter.",
        "",
        "  INVERTER CONNECTION DIAGRAM",
        "  " + s,
        "",
        "                        ┌───────────────────────────────┐",
        "   PV (+) ─────────────►│  PV INPUT (+)                 │",
        "   PV (−) ─────────────►│  PV INPUT (−)    MPPT         │",
        "                        │                  CHARGER       │",
        "   BAT (+) ◄────────────│  BAT (+)                      │",
        "   BAT (−) ◄────────────│  BAT (−)         BATTERY      │",
        "                        │                  CHARGER       │",
        "   AC-OUT (L) ─────────►│  AC OUT (L)                   │",
        "   AC-OUT (N) ─────────►│  AC OUT (N)      DC/AC        │",
        "   AC-OUT (PE)─────────►│  AC OUT (PE)     INVERTER     │",
        "                        │                               │",
        "   [Optional]           │  AC IN (grid)                 │",
        "   GRID ───────────────►│  AC IN (L/N/PE)               │",
        "                        └───────────────────────────────┘",
        "                                   │",
        "                              LCD Display",
        "                              & Settings",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 7 — AC CABLE 10mm²
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 7 — AC CABLE 10mm²",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  10mm² single-core copper XLPE-insulated cable (BS 5467 / BS 6724)",
        "  is used for all AC wiring between the inverter AC output terminals",
        "  and the AC distribution board (MCB/RCCB board).  Three conductors",
        "  are required: Line (brown), Neutral (blue), Protective Earth (green/",
        "  yellow).  The cable must be routed in metal trunking or conduit,",
        "  segregated from DC wiring.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Cable cutters",
        "    • Wire strippers (for 10mm²)",
        "    • Conduit bender or metal trunking",
        "    • Fish tape",
        "    • Screwdrivers and insulated terminal screwdriver",
        "    • Cable identification sleeves (brown, blue, green/yellow)",
        "    • Multimeter",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Confirm inverter AC output is isolated (OFF).",
        "",
        "  Step 2.  Measure the cable run from inverter to distribution board.",
        "           Cut three 10mm² single cores (L, N, PE) to length plus",
        "           300 mm each end for terminations.",
        "",
        "  Step 3.  Sleeve cable ends with correct colour identification",
        "           sleeves: brown (L), blue (N), green/yellow (PE).",
        "",
        "  Step 4.  Route cable in metal trunking or conduit, physically",
        "           separated from DC cable runs by at least 50 mm.",
        "",
        "  Step 5.  Strip 15 mm insulation and fit bootlace ferrules before",
        "           inserting into inverter AC terminals.  Torque to spec.",
        "",
        "  Step 6.  Run cable to the distribution board.  Terminate in the",
        "           correct MCB and neutral/earth bars.  Torque to spec.",
        "",
        "  Step 7.  Insulation resistance test: ≥ 1 MOhm between conductors",
        "           and earth at 500 V before energising.",
        "",
        "  AC CABLE ROUTING DIAGRAM",
        "  " + s,
        "",
        "   [Inverter AC Out]",
        "        │ L (brown)  ──────────────────────────────►",
        "        │ N (blue)   ──────────────────────────────►  [AC MCB",
        "        │ PE (grn/yel)─────────────────────────────►   Board]",
        "        │",
        "        └─ All 3 cores in metal trunking / conduit",
        "           Minimum 50 mm separation from DC runs",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 8 — DC CIRCUIT BREAKERS
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 8 — DC CIRCUIT BREAKERS (BS EN 60947-2)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  DC-rated miniature circuit breakers (MCBs) are installed to provide",
        "  overcurrent and short-circuit protection on the DC side.  Two are",
        "  fitted at the combiner box output (one on each string, if not already",
        "  fused), and two at the inverter DC input to allow safe isolation for",
        "  maintenance.  DC MCBs must be rated for DC voltage (not AC MCBs,",
        "  which cannot safely interrupt DC arc).",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Flathead screwdriver",
        "    • DIN rail cutter",
        "    • Wire strippers and crimping tool",
        "    • Insulated terminal screwdriver",
        "    • Multimeter",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Confirm all DC sources (PV strings, battery) are isolated.",
        "",
        "  Step 2.  Cut DIN rail to length and fix inside the enclosure.",
        "",
        "  Step 3.  Snap the DC MCBs onto the DIN rail.",
        "           Verify the voltage and current rating label on each MCB:",
        "           minimum 500 V DC, current rated ≥ 1.25 × string Isc.",
        "",
        "  Step 4.  Wire the incoming DC cable into the MCB input (top)",
        "           and the outgoing cable from the MCB output (bottom).",
        "           Torque terminals to 2.5–3.5 Nm.",
        "",
        "  Step 5.  Label each MCB: 'STRING A DC', 'STRING B DC', etc.",
        "",
        "  Step 6.  Test operation: switch MCB off and verify no voltage",
        "           passes downstream with multimeter.",
        "",
        "  DC CIRCUIT BREAKER DIAGRAM",
        "  " + s,
        "",
        "   String (+) ────[DC MCB]──── To Inverter PV(+)",
        "   String (−) ─────────────── To Inverter PV(−)",
        "                   │",
        "               DIN Rail in",
        "              IP65 Enclosure",
        "",
        "   MCB must be DC-rated (marked with ─── not ∿)",
        "   AC MCBs MUST NOT be used in DC circuits.",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 9 — AC MCB + RCCB
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 9 — AC MCB + RCCB (BS EN 60898 / BS EN 61008)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  The AC distribution board contains a Type B MCB (for overcurrent",
        "  protection) and a 30mA RCCB (Residual Current Circuit Breaker, for",
        "  earth leakage/shock protection).  These are mounted in a consumer",
        "  unit / distribution board downstream of the inverter AC output.",
        "  The RCCB protects the entire AC installation against earth fault.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Flathead screwdriver and Pozidriv screwdriver",
        "    • Insulated terminal screwdriver",
        "    • Wire strippers",
        "    • Drill (for DB board wall fixing)",
        "    • Multimeter and RCD tester",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Mount the distribution board (DB) on the wall at ≥ 1.5 m",
        "           height from the finished floor level.  Use spirit level.",
        "",
        "  Step 2.  Snap RCCB and MCB(s) onto DIN rail in the DB.",
        "           RCCB goes first (incoming side), MCBs on outgoing circuits.",
        "",
        "  Step 3.  Connect incoming AC 10mm² cable (L, N, PE) from inverter:",
        "           L ─► RCCB Line input",
        "           N ─► Neutral bar",
        "           PE ─► Earth bar",
        "",
        "  Step 4.  Link RCCB output L to MCB input.",
        "           Connect MCB outputs to final circuit cables (lighting, sockets).",
        "",
        "  Step 5.  Fit the board cover and labels.",
        "",
        "  Step 6.  Energise the board and test the RCCB with the TEST button.",
        "           RCCB must trip within 300 ms.  Reset and verify it holds.",
        "           Use an RCD tester to verify trip at 30mA, 50mA, 100mA.",
        "",
        "  AC DISTRIBUTION BOARD DIAGRAM",
        "  " + s,
        "",
        "   FROM INVERTER",
        "       │ L ──────────────────────────────────────────────────┐",
        "       │                                                      │",
        "       ├─ L ──► [RCCB 30mA] ──► [MCB 1 - Lighting]  ──► L1  │",
        "       │                    └──► [MCB 2 - Sockets]   ──► L2  │",
        "       │                    └──► [MCB 3 - spare]             │",
        "       │                                                      │",
        "       ├─ N ──► Neutral Bar ──────────────────────────────── N│",
        "       │                                                      │",
        "       └─ PE ─► Earth Bar ───────────────────────────────── PE│",
        "                                                       (to earth rod)",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 10 — SURGE PROTECTION DEVICE (SPD)
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 10 — SURGE PROTECTION DEVICE (SPD) (BS EN 61643)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  Two SPDs are installed: one Type II SPD on the DC side (inside the",
        "  combiner box) and one Type II SPD on the AC side (inside the DB board).",
        "  SPDs protect against transient over-voltages caused by lightning",
        "  strikes or switching surges on the PV array and AC distribution.",
        "  Ghana has a high lightning occurrence rate; SPD installation is",
        "  mandatory for system protection.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Flathead screwdriver",
        "    • Insulated terminal screwdriver",
        "    • Multimeter",
        "    • DIN rail snap-in tool",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Snap the SPD module onto the DIN rail inside the enclosure.",
        "",
        "  Step 2.  DC SPD wiring (combiner box):",
        "           Connect SPD terminal L+ to positive busbar.",
        "           Connect SPD terminal L− to negative busbar.",
        "           Connect SPD earth terminal to enclosure earth bar.",
        "",
        "  Step 3.  AC SPD wiring (DB board):",
        "           Connect SPD terminal L to the AC line busbar.",
        "           Connect SPD terminal N to neutral bar.",
        "           Connect SPD earth terminal to earth bar.",
        "",
        "  Step 4.  Inspect the SPD status indicator window.  Green = healthy.",
        "           Red or absent window = SPD has operated and must be replaced.",
        "",
        "  Step 5.  Label SPD: 'SURGE PROTECTION — DO NOT REMOVE UNDER LOAD.'",
        "",
        "  SPD CONNECTION DIAGRAM",
        "  " + s,
        "",
        "  DC SIDE (in Combiner Box):         AC SIDE (in DB Board):",
        "",
        "  (+) Bus ─────┐                     AC Line ─────┐",
        "               ├──[SPD]──┐                        ├──[SPD]──┐",
        "  (−) Bus ─────┘         │           Neutral ──────┘         │",
        "                         │                                    │",
        "                       [Earth]                              [Earth]",
        "                         │                                    │",
        "                    Earth Bar                            Earth Bar",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 11 — EARTHING ROD & BONDING CABLE
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 11 — EARTHING ROD & BONDING CABLE (BS 7430)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  A copper-clad steel earth electrode (minimum 1.2 m long, 14 mm dia.)",
        "  is driven into the ground outside the building to provide a low-",
        "  resistance earth path.  A 10mm² green/yellow copper bonding cable",
        "  connects the earth rod to the main earth bar in the DB board, and",
        "  to all metalwork: inverter chassis, battery rack, module frames,",
        "  combiner box, and cable trunking.  Ghana's soil conductivity is",
        "  generally good; target earth resistance ≤ 5 Ohms.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Earth rod driving tool or sledgehammer and driving head",
        "    • Hacksaw or angle grinder (for rod length trimming)",
        "    • Earth rod clamp / compression connector",
        "    • Spade or bar (for excavation trench to rod)",
        "    • Earth resistance tester (Megger or similar)",
        "    • Crimping tool (for cable lugs)",
        "    • Insulated screwdrivers",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Select a location ≥ 1 m from the building foundation,",
        "           in moist soil if possible (shaded area, near drain run-off).",
        "",
        "  Step 2.  Drive the earth rod vertically into the ground to its",
        "           full depth using the driving tool.  If the rod meets rock,",
        "           install at a 45° angle (max) or use multiple rods.",
        "",
        "  Step 3.  Expose the top of the rod (300 mm above ground or in a",
        "           buried inspection pit / earth test point box).",
        "",
        "  Step 4.  Fit the earth rod clamp onto the rod head.",
        "           Crimp a cable lug onto the 10mm² bonding cable and bolt",
        "           it to the rod clamp.  Torque to clamp manufacturer spec.",
        "",
        "  Step 5.  Route the bonding cable into the building via a sealed",
        "           conduit sleeve.  Terminate on the main earth bar in the DB.",
        "",
        "  Step 6.  Run bonding conductors from the earth bar to:",
        "           − Inverter chassis earth terminal",
        "           − Battery rack frame",
        "           − DC combiner box enclosure",
        "           − All PV module frames (via rail earth lug)",
        "           − Cable trunking / conduit runs",
        "",
        "  Step 7.  Measure earth electrode resistance with an earth resistance",
        "           tester (fall-of-potential method, BS 7430).",
        "           If > 5 Ohms: drive a second rod 3 m away and link in parallel.",
        "",
        "  EARTHING SYSTEM DIAGRAM",
        "  " + s,
        "",
        "   PV FRAMES ─── Earth Lug ─── Rail ─────────────────────────┐",
        "                                                               │",
        "   Combiner Box ──── Earth terminal ───────────────────────── ┤",
        "                                                               │",
        "   Battery Rack ──── Frame bond ────────────────────────────  ┤",
        "                                                               │",
        "   Inverter Chassis ─ Earth terminal ──────────────────────── ┤",
        "                                                               │",
        "                                                         Main Earth Bar",
        "                                                               │",
        "                                                          (in DB Board)",
        "                                                               │",
        "                                                     10mm² green/yellow",
        "                                                               │",
        "                                             ┌─────────────────┘",
        "                                             │",
        "   GROUND LEVEL ─────────────────────────────┼─────────────────",
        "                                             │",
        "                                          [Earth Rod]",
        "                                          (≥1.2 m deep)",
        "                                          Cu-clad steel",
        "                                          14mm dia.",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 13 — CABLE TRUNKING & CONDUIT
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 13 — CABLE TRUNKING & CONDUIT (BS EN 61386)",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  PVC or metal cable trunking and conduit is installed throughout to",
        "  mechanically protect all cables, to maintain segregation between",
        "  DC and AC wiring, and to present a neat, professional installation.",
        "  On the roof, UV-resistant trunking is used.  Indoors, standard PVC",
        "  mini-trunking or galvanised steel trunking is acceptable.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Hacksaw or trunking cutters",
        "    • Mitre box (for neat corner cuts)",
        "    • Drill and rawl plugs",
        "    • Spirit level and chalk line",
        "    • Screwdrivers",
        "    • Cable pulling fish tape",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  Plan the trunking routes on paper before cutting any material.",
        "           Mark the route on the wall with a chalk line.",
        "",
        "  Step 2.  Fix trunking base/back at 600 mm intervals with screws",
        "           into rawl-plugged holes.  Keep trunking level and plumb.",
        "",
        "  Step 3.  Cut trunking to length with a hacksaw or cutters.",
        "           Use a mitre box for 45° and 90° internal/external corners.",
        "",
        "  Step 4.  DC trunking and AC trunking must be in separate runs.",
        "           Minimum 50 mm separation between DC and AC trunking.",
        "           Label each trunking run: 'DC ONLY' or 'AC ONLY'.",
        "",
        "  Step 5.  Lay cables in trunking before fitting the lid.",
        "           Do not exceed 40% fill capacity of the trunking section.",
        "",
        "  Step 6.  Clip the trunking lid onto the base.  Ensure all lids",
        "           are seated and clipped at every joint.",
        "",
        "  TRUNKING SEGREGATION DIAGRAM",
        "  " + s,
        "",
        "   WALL SURFACE",
        "   │",
        "   ├── [DC TRUNKING] ─── red 6mm² (+), black 6mm² (−), earth",
        "   │    (label: DC ONLY — DANGER LIVE DC VOLTAGE)",
        "   │",
        "   │    (minimum 50 mm gap)",
        "   │",
        "   └── [AC TRUNKING] ─── brown 10mm² (L), blue 10mm² (N), grn/yel (PE)",
        "        (label: AC ONLY — 230V AC)",
        "",
    ]

    # -----------------------------------------------------------------------
    # ITEM 14 — MISCELLANEOUS FIXINGS & HARDWARE
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  ITEM 14 — MISCELLANEOUS FIXINGS & HARDWARE",
        L,
        "",
        "  NARRATIVE",
        "  " + s,
        "  This item covers all minor fixings, connectors, and consumables",
        "  required to complete the installation to a professional standard.",
        "  These include cable labels, cable ties, ferrules, wall plugs,",
        "  warning labels, wire markers, conduit fittings, and touch-up paint.",
        "",
        "  TOOLS REQUIRED",
        "  " + s,
        "    • Cable tie gun",
        "    • Label printer or permanent markers",
        "    • Crimping tool (for ferrules)",
        "",
        "  STEP-BY-STEP INSTALLATION",
        "  " + s,
        "  Step 1.  After all primary installations are complete, conduct a",
        "           walk-through to identify any unsecured cables or open entries.",
        "",
        "  Step 2.  Secure all cables in trunking with cable ties every 300 mm",
        "           in vertical runs and every 600 mm in horizontal runs.",
        "",
        "  Step 3.  Fit bootlace ferrules to all stranded conductors entering",
        "           screw terminals to prevent strand splaying.",
        "",
        "  Step 4.  Apply warning labels at all hazardous points:",
        "           − 'DANGER: HIGH DC VOLTAGE — DO NOT TOUCH' at combiner box",
        "           − 'CAUTION: DUAL SUPPLY' at the inverter",
        "           − 'BATTERY ROOM — NO NAKED FLAMES' near battery rack",
        "           − Circuit identification labels on every MCB in the DB",
        "",
        "  Step 5.  Seal all wall/roof penetrations with fire-rated mastic.",
        "",
        "  Step 6.  Apply touch-up paint to any drill holes or cut metalwork",
        "           to prevent corrosion.",
        "",
    ]

    # -----------------------------------------------------------------------
    # COMMISSIONING SEQUENCE
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  SECTION 15 — COMMISSIONING SEQUENCE",
        L,
        "",
        "  Follow this sequence after all hardware is installed.",
        "  Do NOT skip steps or reverse the order.",
        "",
        "  ┌─────────────────────────────────────────────────────────────────┐",
        "  │  COMMISSIONING CHECKLIST                                        │",
        "  ├──────┬──────────────────────────────────────────────────────────┤",
        "  │  1.  │ Visual inspection — all fixings, labels, polarity marks   │",
        "  │  2.  │ Insulation resistance test (IR): all DC circuits ≥ 1 MOhm│",
        "  │  3.  │ Insulation resistance test (IR): all AC circuits ≥ 1 MOhm│",
        "  │  4.  │ Earth continuity: all bonded metalwork ≤ 0.1 Ohm         │",
        "  │  5.  │ Earth electrode resistance ≤ 5 Ohms                      │",
        "  │  6.  │ Polarity check: verify (+)/(−) on all DC terminals        │",
        "  │  7.  │ Measure PV string Voc before connecting to combiner       │",
        "  │  8.  │ Connect battery to inverter — verify inverter powers up   │",
        "  │  9.  │ Connect PV strings — verify MPPT charging begins          │",
        "  │ 10.  │ Measure AC output voltage (target: 230 V ± 2%)           │",
        "  │ 11.  │ Test RCCB operation with TEST button and RCD tester       │",
        "  │ 12.  │ Load test: connect a known load, verify stable AC output  │",
        "  │ 13.  │ Run system for 1 hour under load — check all temperatures │",
        "  │ 14.  │ Record all test results in the commissioning logbook      │",
        "  │ 15.  │ Issue test certificate and hand over O&M manual to client │",
        "  └──────┴──────────────────────────────────────────────────────────┘",
        "",
    ]

    # -----------------------------------------------------------------------
    # FOOTER
    # -----------------------------------------------------------------------
    lines += [
        L,
        "  HEALTH & SAFETY NOTES",
        L,
        "",
        "  • PV modules produce voltage in daylight even when disconnected.",
        "    Always treat module leads as LIVE.  Use insulated gloves.",
        "",
        "  • Batteries store large amounts of energy and can deliver very",
        "    high short-circuit currents.  Never short battery terminals.",
        "    Remove jewellery, watches, and rings before working on batteries.",
        "",
        "  • Work on the roof requires a competent roofer/electrician with",
        "    appropriate fall-arrest equipment and a trained second person.",
        "",
        "  • All electrical work must be carried out by a qualified electrician",
        "    and inspected before energising.",
        "",
        "  • Comply with Ghana's Electrical Wiring Regulations (LI 1816) and",
        "    BS 7671:2018 (18th Edition IET Wiring Regulations).",
        "",
        L,
        "  End of Installation Method Report",
        L,
    ]

    content = "\n".join(lines)

    with open("output/installation_method_report.txt", "w", encoding="utf-8") as f:
        f.write(content)

    print("  Installation method report saved to output/installation_method_report.txt")

    # ── HTML report with embedded SVG diagrams ────────────────────────────────
    _generate_html_report(pv_kw, num_panels, battery_kwh, num_batteries,
                          inverter_kw, string_a, string_b)


def _generate_html_report(pv_kw, num_panels, battery_kwh, num_batteries,
                           inverter_kw, string_a, string_b):
    """Generate output/installation_method_report.html with inline SVG diagrams."""

    # Pull live region & power data
    region_name = getattr(_cfg, "SELECTED_REGION", "Greater Accra")
    region      = REGIONS.get(region_name, {})
    power       = POWER_ISSUES.get(region_name, {})
    temp_der    = getattr(_cfg, "TEMP_DERATING", 1.0)
    eff_eff     = getattr(_cfg, "SYSTEM_EFFICIENCY", 0.75) * temp_der

    svg_arch  = system_architecture_svg(pv_kw, num_panels, battery_kwh,
                                        num_batteries, inverter_kw)
    svg_mount = mounting_structure_svg()
    svg_str   = string_wiring_svg(num_panels, string_a, string_b)
    svg_comb  = combiner_box_svg()
    svg_inv   = inverter_connections_svg(inverter_kw)
    svg_bat   = battery_bank_svg(num_batteries, battery_kwh)
    svg_earth = earthing_system_svg()
    svg_acb   = ac_distribution_board_svg()

    CSS = """
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #12121f; color: #dde3ec;
      font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px;
      line-height: 1.65; padding: 0 0 60px;
    }
    header {
      background: #f5a623; color: #1a1000; padding: 22px 40px;
      display: flex; justify-content: space-between; align-items: center;
    }
    header h1 { font-size: 22px; font-weight: 700; }
    header .meta { font-size: 12px; text-align: right; opacity: .75; }
    nav {
      background: #1c1c30; padding: 14px 40px;
      border-bottom: 1px solid #3a3a5c; position: sticky; top: 0; z-index: 10;
    }
    nav ul { list-style: none; display: flex; flex-wrap: wrap; gap: 6px 18px; }
    nav a { color: #4fc3f7; text-decoration: none; font-size: 12px; }
    nav a:hover { color: #f5a623; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
    section { margin-bottom: 52px; }
    h2 {
      font-size: 17px; font-weight: 700; color: #f5a623;
      border-left: 4px solid #f5a623; padding-left: 12px;
      margin-bottom: 18px;
    }
    h3 { font-size: 13px; font-weight: 700; color: #4fc3f7;
         margin: 18px 0 8px; text-transform: uppercase; letter-spacing: .05em; }
    p { margin-bottom: 10px; color: #b0bec5; }
    .tools ul { margin-left: 22px; }
    .tools li { color: #90a4ae; margin-bottom: 4px; font-size: 13px; }
    .steps ol { margin-left: 22px; }
    .steps li { color: #b0bec5; margin-bottom: 8px; font-size: 13px;
                border-left: 2px solid #3a3a5c; padding-left: 10px; }
    .steps li strong { color: #dde3ec; }
    .diagram {
      background: #12121f; border: 1px solid #3a3a5c; border-radius: 8px;
      padding: 16px; margin: 20px 0; overflow-x: auto;
    }
    .diagram figcaption {
      text-align: center; font-size: 11px; color: #607585;
      margin-top: 8px; font-style: italic;
    }
    .warn {
      background: #1a1000; border-left: 4px solid #f5a623;
      padding: 12px 16px; border-radius: 4px; margin-bottom: 12px;
    }
    .warn p { color: #ffd54f; margin: 0; font-size: 13px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 16px; }
    th { background: #1c1c30; color: #f5a623; padding: 8px 12px;
         text-align: left; font-size: 12px; border: 1px solid #3a3a5c; }
    td { padding: 8px 12px; font-size: 12px; border: 1px solid #2a2a42;
         color: #b0bec5; }
    tr:nth-child(even) td { background: #1a1a2e; }
    .tag {
      display: inline-block; padding: 2px 8px; border-radius: 10px;
      font-size: 10px; font-weight: 700; margin-right: 4px;
    }
    .tag-dc  { background: #2a1800; color: #f5a623; border: 1px solid #f5a623; }
    .tag-ac  { background: #082030; color: #4fc3f7; border: 1px solid #4fc3f7; }
    .tag-pe  { background: #082010; color: #66bb6a; border: 1px solid #66bb6a; }
    .tag-bat { background: #082028; color: #4db6ac; border: 1px solid #4db6ac; }
    footer {
      text-align: center; color: #505075; font-size: 11px; padding-top: 24px;
      border-top: 1px solid #2a2a42;
    }
    .region-grid {
      display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px;
    }
    .region-card {
      background: #1c1c30; border: 1px solid #3a3a5c; border-radius: 8px;
      padding: 16px 20px;
    }
    .region-card h3 { margin-bottom: 10px; }
    .region-card table { margin: 0; }
    .region-card td { border: none; padding: 4px 10px 4px 0; font-size: 12px; }
    .region-card td:first-child { color: #607585; white-space: nowrap; }
    .region-card td:last-child  { color: #dde3ec; font-weight: 600; }
    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 10px;
      font-size: 11px; font-weight: 700;
    }
    .badge-poor     { background: #3a1010; color: #ef5350; border: 1px solid #ef5350; }
    .badge-verypoor { background: #2a0808; color: #ff1744; border: 1px solid #ff1744; }
    .badge-fair     { background: #2a2200; color: #ffd54f; border: 1px solid #ffd54f; }
    .badge-good     { background: #0a2a0a; color: #66bb6a; border: 1px solid #66bb6a; }
    .issue-list { list-style: none; margin: 6px 0 0; padding: 0; }
    .issue-list li { color: #ef5350; font-size: 12px; padding: 3px 0;
                     border-bottom: 1px solid #2a2a42; }
    .issue-list li::before { content: "• "; color: #ef5350; }
    """

    def section(id_, title, narrative, tools, steps, diagram_svg=None, caption=""):
        tool_items = "".join(f"<li>{t}</li>" for t in tools)
        step_items = "".join(f"<li>{s}</li>" for s in steps)
        diag = ""
        if diagram_svg:
            diag = f'<figure class="diagram">{diagram_svg}<figcaption>{caption}</figcaption></figure>'
        return f"""
<section id="{id_}">
  <h2>{title}</h2>
  <h3>Narrative</h3>
  <p>{narrative}</p>
  {diag}
  <div class="tools"><h3>Tools Required</h3><ul>{tool_items}</ul></div>
  <div class="steps"><h3>Step-by-Step Procedure</h3><ol>{step_items}</ol></div>
</section>"""

    overview_section = f"""
<section id="overview">
  <h2>Section 0 — Overall System Architecture</h2>
  <p>The diagram below shows the complete power flow of the
  <strong>{pv_kw:.2f} kWp</strong> off-grid pv solar system — from the PV array
  through the DC combiner box and hybrid inverter to the battery bank and AC
  distribution board.  All wiring shall comply with
  <strong>BS&nbsp;7671:2018</strong> (18th&nbsp;Edition).</p>
  <figure class="diagram">
    {svg_arch}
    <figcaption>Fig 0 — System power-flow block diagram
    (<span class="tag tag-dc">DC+</span>
     <span class="tag tag-ac">AC</span>
     <span class="tag tag-bat">Battery</span>
     <span class="tag tag-pe">Earth PE</span>)</figcaption>
  </figure>
</section>"""

    sec4 = section(
        "item4", "Item 4 — PV Mounting Structure",
        f"Aluminium mounting rails and stainless-steel brackets are fixed to the roof "
        f"to carry the {num_panels} PV modules.  The structure is pitched at 10°–15° "
        f"(optimal for Ghana's ~6°N latitude) for maximum irradiance and self-cleaning.  "
        f"All fixings shall be stainless steel or hot-dip galvanised.",
        ["Tape measure and chalk line", "Spirit level (600 mm min.)",
         "Drill with 10 mm and 12 mm masonry/metal bits", "Angle grinder (rail cutting)",
         "Spanner/socket set (M8, M10, M12)", "Torque wrench (12–16 Nm)",
         "Safety harness and fall-arrest lanyard"],
        [f"<strong>Roof survey.</strong> Check rafter/purlin spacing, roofing material and load-bearing capacity.",
         f"<strong>Mark layout.</strong> Use chalk line.  Maintain ≥ 300 mm clearance from roof edges.",
         f"<strong>Locate fixing points</strong> directly above rafters.  Space brackets at ≤ 1 200 mm centres.",
         f"<strong>Drill pilot holes.</strong> Fit roof hooks or L-feet with EPDM gaskets.  Seal against water ingress.",
         f"<strong>Mount aluminium rails.</strong> Level with spirit level.  Torque all bolts to spec.",
         f"<strong>Fit clamps</strong> (end and mid) loosely along rail, ready for panels.",
         f"<strong>Attach earth bonding lug</strong> to each rail section.  Run continuous earth conductor."],
        svg_mount,
        "Fig 4 — Mounting structure roof cross-section"
    )

    sec1 = section(
        "item1", f"Item 1 — PV Solar Modules ({num_panels} × 400 Wp)",
        f"{num_panels} monocrystalline 400 Wp modules are mounted on the pre-installed "
        f"aluminium rail system and connected in two series strings: "
        f"String A ({string_a} panels) and String B ({string_b} panels). "
        f"All modules face true south (azimuth 180°) for Ghana's latitude.",
        ["Insulated gloves (voltage-rated)", "MC4 assembly and crimping tool",
         "MC4 spanner", "Digital multimeter (DC V and A)", "Clamp meter",
         "Torque wrench", "UV-resistant cable ties and labels"],
        [f"<strong>Isolate all DC sources</strong> before handling modules.",
         f"<strong>Lift module onto rail</strong> using two persons.  Never stand on the glass face.",
         f"<strong>Slide end-clamps and mid-clamps</strong> onto module frames.  Hand-tighten.",
         f"<strong>Check level and alignment.</strong> Torque clamp bolts to 10–14 Nm.",
         f"<strong>Connect MC4 leads in series</strong> within each string: (+) of Module N → (−) of Module N+1.",
         f"<strong>Measure Voc of each string</strong> before connecting to combiner.  "
         f"Expected: String A ≈ {string_a*48:.0f}–{string_a*50:.0f} V,  "
         f"String B ≈ {string_b*48:.0f}–{string_b*50:.0f} V.",
         f"<strong>Route string cables</strong> in UV-resistant trunking along rail.  Secure every 400 mm.",
         f"<strong>Label cables</strong> at both ends: STRING A (+/−), STRING B (+/−)."],
        svg_str,
        f"Fig 1 — PV string wiring ({num_panels} modules in 2 series strings)"
    )

    sec5 = section(
        "item5", "Item 5 — DC Combiner / String Box",
        "The DC combiner box aggregates the two PV strings into a single DC output to "
        "the inverter.  It contains string fuses (15 A per string), a DC SPD, and DC MCBs "
        "in an IP65 weatherproof enclosure mounted at the base of the roof.",
        ["Screwdrivers (flathead and Pozidriv)", "Wire strippers and crimping tool",
         "Multimeter (DC voltage)", "Drill with 20–25 mm knockout punch",
         "Cable gland spanner", "Insulated terminal screwdriver"],
        [f"<strong>Select mounting position</strong> sheltered from direct rain at the roof base.",
         f"<strong>Fix enclosure</strong> to wall with stainless rawl-bolts.  Door faces down or sideways.",
         f"<strong>Knock out cable entry holes.</strong> Fit cable glands for each string and DC output cable.",
         f"<strong>Mount busbar, fuses, SPD, and MCBs</strong> on DIN rail per manufacturer diagram.",
         f"<strong>Verify all DC sources are isolated.</strong>  Connect String A (+) and B (+) to fuse inputs.  "
         f"Connect String A (−) and B (−) to negative busbar.",
         f"<strong>Connect SPD</strong> between positive busbar and earth.",
         f"<strong>Run DC main 6mm² cable</strong> from output busbars through trunking to inverter DC input.",
         f"<strong>Label enclosure:</strong> 'DANGER: HIGH DC VOLTAGE — DO NOT OPEN UNDER LOAD'."],
        svg_comb,
        "Fig 5 — DC combiner box internal wiring schematic"
    )

    sec2 = section(
        "item2", f"Item 2 — Hybrid Inverter / Charger ({inverter_kw:.2f} kW)",
        f"The {inverter_kw:.2f} kW hybrid inverter/charger is wall-mounted indoors near the "
        f"battery bank (≤ 1.5 m battery cable run) on a solid wall rated to carry ≥ 25 kg.  "
        f"It contains an MPPT controller, battery charger, DC/AC inverter, and auto-transfer switch.",
        ["Drill (M8 masonry bit)", "Spirit level", "Rawl plugs and M8 stainless bolts",
         "Insulated screwdrivers and spanner set", "Multimeter",
         "Torque wrench", "Laptop / smartphone for inverter configuration software"],
        [f"<strong>Mark wall fixing positions</strong> from the mounting template.  "
         f"Minimum 500 mm from floor, 300 mm from any obstruction.",
         f"<strong>Drill, fit rawl plugs, mount bracket/back-plate.</strong>  Verify level.  Hang inverter.",
         f"<strong>Connect PV DC input terminals:</strong> (+) from combiner (+) output; (−) from combiner (−).  "
         f"Check polarity with multimeter.",
         f"<strong>Connect battery terminals:</strong> (+) red 16mm², (−) black 16mm².  Connect (−) first, then (+).",
         f"<strong>Connect AC output (L, N, PE)</strong> using 10mm² cable to the AC distribution board.",
         f"<strong>Power on and configure:</strong> Battery type = LiFePO4; Capacity = {battery_kwh:.1f} kWh; "
         f"Charge V = 58.4 V; Low cut-off = 44 V; AC = 230 V 50 Hz.",
         f"<strong>Monitor display</strong> for correct PV charging current and battery voltage."],
        svg_inv,
        "Fig 2 — Hybrid inverter terminal connection diagram"
    )

    sec3 = section(
        "item3", f"Item 3 — Battery Units ({num_batteries} × 2.4 kWh LiFePO4)",
        f"{num_batteries} LiFePO4 battery units (each 2.4 kWh, 48 V) are installed in the "
        f"battery rack and wired in parallel to give {battery_kwh:.2f} kWh total.  Each unit "
        f"has an integrated BMS for over-charge, over-discharge, short-circuit and temperature protection.",
        ["Insulated screwdrivers and spanners", "Insulated gloves (≥ 1000 V rated)",
         "Multimeter (DC voltage)", "Torque wrench (8–12 Nm for terminal bolts)",
         "Anti-static wrist strap"],
        [f"<strong>Confirm inverter battery switch is OFF.</strong>  Verify with multimeter.",
         f"<strong>Check SOC</strong> of each unit.  All units must be within ±5% SOC before linking.",
         f"<strong>Place Battery Unit 1</strong> (bottom position).  Connect BMS CAN/RS485 cable if required.",
         f"<strong>Stack remaining units</strong> per manufacturer stacking order.",
         f"<strong>Connect inter-unit busbars:</strong> (+) rail to (+) rail, (−) rail to (−) rail (parallel).  "
         f"Torque to 8–12 Nm.",
         f"<strong>Connect main battery cable:</strong> 16mm² red BAT(+) → inverter; "
         f"16mm² black BAT(−) → inverter.  Connect (−) FIRST, (+) LAST.",
         f"<strong>Measure total bank voltage.</strong>  Expected: 48–54 V DC."],
        svg_bat,
        f"Fig 3 — Battery bank parallel wiring ({num_batteries} units)"
    )

    sec11 = section(
        "item11", "Item 11 — Earthing Rod & Bonding Cable (BS 7430)",
        "A copper-clad steel earth electrode (≥ 1.2 m × 14 mm dia.) is driven into the ground "
        "outside the building.  A 10mm² green/yellow copper bonding cable connects the earth rod "
        "to the main earth bar, and from there to all metalwork — inverter, battery rack, module "
        "frames, combiner box, and cable trunking.  Target: earth resistance ≤ 5 Ω.",
        ["Earth rod driving tool or sledgehammer", "Earth rod clamp / compression connector",
         "Spade (for excavation)", "Earth resistance tester (Megger fall-of-potential)",
         "Crimping tool (for cable lugs)", "Insulated screwdrivers"],
        [f"<strong>Select location</strong> ≥ 1 m from building foundation, in moist shaded soil if possible.",
         f"<strong>Drive earth rod</strong> vertically to full depth.  If rock is met, angle at max 45°.",
         f"<strong>Expose rod top</strong> 300 mm above ground or install in a buried inspection pit.",
         f"<strong>Fit earth rod clamp</strong> and crimp cable lug onto 10mm² bonding cable.",
         f"<strong>Route bonding cable</strong> into building via sealed conduit sleeve.  "
         f"Terminate on main earth bar in DB.",
         f"<strong>Run bonding conductors</strong> from earth bar to: inverter chassis, battery rack frame, "
         f"DC combiner box, PV module frames (via rail lug), cable trunking.",
         f"<strong>Measure earth resistance</strong> (fall-of-potential, BS 7430).  "
         f"If &gt; 5 Ω, drive a second rod 3 m away and link in parallel."],
        svg_earth,
        "Fig 11 — Earthing and bonding system (BS 7430 / BS 7671)"
    )

    sec9 = section(
        "item9", "Item 9 — AC MCB + RCCB (BS EN 60898 / BS EN 61008)",
        "The AC distribution board contains a Type B MCB (overcurrent protection) and a 30 mA RCCB "
        "(earth leakage / shock protection) downstream of the inverter AC output.  The RCCB protects "
        "the entire AC installation against earth fault.",
        ["Flathead and Pozidriv screwdrivers", "Insulated terminal screwdriver",
         "Wire strippers", "Drill (for DB wall fixing)", "Multimeter and RCD tester"],
        [f"<strong>Mount DB board</strong> on wall at ≥ 1.5 m from finished floor level.  Use spirit level.",
         f"<strong>Snap RCCB and MCBs</strong> onto DIN rail.  RCCB goes first (incoming side).",
         f"<strong>Connect incoming AC cable</strong> (L, N, PE) from inverter: L → RCCB line input; "
         f"N → neutral bar; PE → earth bar.",
         f"<strong>Link RCCB output L to MCB input.</strong>  Connect MCB outputs to final circuit cables.",
         f"<strong>Fit board cover and labels.</strong>",
         f"<strong>Energise and test RCCB</strong> with TEST button.  Must trip within 300 ms.  "
         f"Use RCD tester to verify trip at 30 mA, 50 mA, 100 mA."],
        svg_acb,
        "Fig 9 — AC distribution board internal layout"
    )

    commissioning_table = """
<section id="commission">
  <h2>Section 15 — Commissioning Sequence</h2>
  <p>Follow this sequence strictly after all hardware is installed.
  Do <strong>not</strong> skip steps or reverse the order.</p>
  <table>
    <tr><th>#</th><th>Test / Action</th><th>Pass Criterion</th></tr>
    <tr><td>1</td><td>Visual inspection — fixings, labels, polarity marks</td><td>All secure, correctly labelled</td></tr>
    <tr><td>2</td><td>IR test — DC circuits (500 V megger)</td><td>≥ 1 MΩ</td></tr>
    <tr><td>3</td><td>IR test — AC circuits (500 V megger)</td><td>≥ 1 MΩ</td></tr>
    <tr><td>4</td><td>Earth continuity — all bonded metalwork</td><td>≤ 0.1 Ω</td></tr>
    <tr><td>5</td><td>Earth electrode resistance</td><td>≤ 5 Ω</td></tr>
    <tr><td>6</td><td>Polarity check — all DC terminals</td><td>Correct (+/−)</td></tr>
    <tr><td>7</td><td>Measure PV string Voc before connecting combiner</td><td>Within ±10% of calc. value</td></tr>
    <tr><td>8</td><td>Connect battery to inverter — verify powers up</td><td>Display active, no fault</td></tr>
    <tr><td>9</td><td>Connect PV strings — verify MPPT charging starts</td><td>Positive charge current shown</td></tr>
    <tr><td>10</td><td>Measure AC output voltage</td><td>230 V ± 2%</td></tr>
    <tr><td>11</td><td>Test RCCB with TEST button and RCD tester</td><td>Trips &lt; 300 ms at 30 mA</td></tr>
    <tr><td>12</td><td>Load test (connect known load)</td><td>Stable AC output, no tripping</td></tr>
    <tr><td>13</td><td>1-hour loaded run — monitor all temperatures</td><td>No over-temperature alarms</td></tr>
    <tr><td>14</td><td>Record all test results in commissioning logbook</td><td>Signed and dated</td></tr>
    <tr><td>15</td><td>Issue test certificate and O&amp;M manual to client</td><td>Handed over</td></tr>
  </table>
</section>"""

    safety_section = f"""
<section id="safety">
  <h2>Health &amp; Safety</h2>
  <div class="warn"><p>⚡ PV modules produce voltage in daylight even when disconnected.
  Always treat module leads as <strong>LIVE</strong>.  Use insulated gloves.</p></div>
  <div class="warn"><p>🔋 Batteries can deliver very high short-circuit currents.
  <strong>Never short battery terminals.</strong>  Remove jewellery before working on batteries.</p></div>
  <div class="warn"><p>🏗️ Roof work requires fall-arrest equipment and a trained second person.</p></div>
  <div class="warn"><p>📋 All electrical work must be carried out by a qualified electrician and
  inspected before energising.  Comply with Ghana LI 1816 and BS 7671:2018.</p></div>
</section>"""

    # Build reliability badge HTML
    _rel = power.get("reliability", "—")
    _rel_badge_cls = {
        "Very Poor": "badge-verypoor",
        "Poor":      "badge-poor",
        "Fair":      "badge-fair",
        "Good":      "badge-good",
    }.get(_rel, "badge-poor")
    _issues_html = "".join(
        f"<li>{i}</li>" for i in power.get("main_issues", [])
    )

    region_section = f"""
<section id="region">
  <h2>Section 0A — Regional Context &amp; Site Conditions</h2>
  <p>The following solar resource and grid reliability data informed the system
  design for <strong>{region_name}</strong>.  The grid reliability figures
  justify the selection of an off-grid / hybrid pv solar system as the primary
  power source for this installation.</p>
  <div class="region-grid">
    <div class="region-card">
      <h3>Solar Resource</h3>
      <table><tbody>
        <tr><td>Region</td><td>{region_name}</td></tr>
        <tr><td>Capital</td><td>{region.get('capital','—')}</td></tr>
        <tr><td>Climate</td><td>{region.get('climate','—')}</td></tr>
        <tr><td>Peak Sun Hours</td><td>{region.get('psh','—')} h/day</td></tr>
        <tr><td>Annual GHI</td><td>{region.get('ghi_annual','—')} kWh/m²/yr</td></tr>
        <tr><td>Avg. Temperature</td><td>{region.get('avg_temp','—')} °C</td></tr>
        <tr><td>Temp Derating</td><td>{temp_der:.4f}</td></tr>
        <tr><td>Eff. Efficiency</td><td>{eff_eff:.4f}</td></tr>
        <tr><td>Rec. Tilt Angle</td><td>{region.get('tilt_angle','—')}° (fixed)</td></tr>
        <tr><td>Solar Rating</td><td>{region.get('rating','—')}</td></tr>
      </tbody></table>
    </div>
    <div class="region-card">
      <h3>Grid &amp; Power Reliability</h3>
      <table><tbody>
        <tr><td>Utility</td><td>{power.get('ecg_zone','—')}</td></tr>
        <tr><td>Daily Outage</td><td>{power.get('daily_outage_hrs','—')}</td></tr>
        <tr><td>Grid Coverage</td><td>{power.get('grid_coverage_pct','—')}%</td></tr>
        <tr><td>Reliability</td><td><span class="badge {_rel_badge_cls}">{_rel}</span></td></tr>
      </tbody></table>
      <h3 style="margin-top:12px;">Key Issues</h3>
      <ul class="issue-list">{_issues_html}</ul>
    </div>
  </div>
  <div class="warn">
    <p>&#9888;&#65039; Site Note: {region.get('notes','')}</p>
  </div>
</section>"""

    nav_links = "\n".join(
        f'<li><a href="#{i}">{l}</a></li>' for i, l in [
            ("region",   "0A — Regional Context"),
            ("overview", "0 — System Architecture"),
            ("item4",    "4 — Mounting Structure"),
            ("item1",    "1 — PV Modules"),
            ("item5",    "5 — DC Combiner Box"),
            ("item2",    "2 — Hybrid Inverter"),
            ("item3",    "3 — Battery Bank"),
            ("item11",   "11 — Earthing"),
            ("item9",    "9 — AC Board"),
            ("commission","15 — Commissioning"),
            ("safety",   "H&S Notes"),
        ]
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Installation Method Report — PV Solar Off-Grid System</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>&#9728; Installation Method Report</h1>
  <div class="meta">
    PV Solar Off-Grid System &nbsp;|&nbsp; {region_name}, Ghana<br>
    {pv_kw:.2f} kWp &nbsp;/&nbsp; {battery_kwh:.2f} kWh &nbsp;/&nbsp; {inverter_kw:.2f} kW<br>
    BS 7671:2018 (18th Edition) &nbsp;|&nbsp; 2026-04-10
  </div>
</header>
<nav><ul>{nav_links}</ul></nav>
<main>
{region_section}
{overview_section}
{sec4}
{sec1}
{sec5}
{sec2}
{sec3}
{sec11}
{sec9}
{commissioning_table}
{safety_section}
</main>
<footer>
  <p>Generated by SolarPro Global — PV Solar Designer Lite &nbsp;·&nbsp; Ghana Off-Grid System &nbsp;·&nbsp; BS 7671:2018</p>
</footer>
</body>
</html>"""

    with open("output/installation_method_report.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("  Installation method HTML report saved to output/installation_method_report.html")
