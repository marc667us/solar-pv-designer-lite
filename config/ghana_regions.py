# config/ghana_regions.py
# Solar and climate characteristics for Ghana's 16 administrative regions.
# Data sourced from: NASA POWER, PVGIS v5, Ghana Meteorological Agency (GMet),
# and ECOWREX West Africa Solar Atlas (2023).
#
# Key parameters used in calculations:
#   psh            – Peak Sun Hours (h/day): primary PV sizing driver
#   temp_factor    – Panel temperature derating factor applied to system efficiency
#                    Formula: 1 − max(0, (avg_temp − 25) × 0.004)
#                    Accounts for panel power loss above STC temperature (25 °C)

REGIONS = {
    # ── Southern / Coastal ──────────────────────────────────────────────────
    "Greater Accra": {
        "capital":      "Accra",
        "psh":          4.8,
        "ghi_annual":   1752,    # kWh/m²/year
        "ghi_daily":    4.80,    # kWh/m²/day
        "avg_temp":     27.8,    # °C (annual average)
        "latitude":     5.6,
        "longitude":   -0.2,
        "tilt_angle":   6,       # recommended fixed-tilt (degrees)
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jul, Sep – Oct",
        "harmattan":    "Dec – Feb (mild)",
        "rating":       "Moderate",
        "rating_color": "#4fc3f7",
        "notes": (
            "Coastal humidity and low marine cloud cover reduce effective irradiance. "
            "Two rainy seasons. Good year-round sunshine between seasons."
        ),
    },
    "Central": {
        "capital":      "Cape Coast",
        "psh":          4.8,
        "ghi_annual":   1752,
        "ghi_daily":    4.80,
        "avg_temp":     27.2,
        "latitude":     5.5,
        "longitude":   -1.2,
        "tilt_angle":   6,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jul, Sep – Oct",
        "harmattan":    "Dec – Feb (mild)",
        "rating":       "Moderate",
        "rating_color": "#4fc3f7",
        "notes": (
            "Similar coastal profile to Greater Accra. "
            "Second rainy season (Sep–Oct) brings cloud cover."
        ),
    },
    "Western": {
        "capital":      "Sekondi-Takoradi",
        "psh":          4.7,
        "ghi_annual":   1715,
        "ghi_daily":    4.70,
        "avg_temp":     26.5,
        "latitude":     5.0,
        "longitude":   -2.1,
        "tilt_angle":   5,
        "climate":      "Tropical Rainforest (Af)",
        "rainy_months": "Apr – Jul, Sep – Nov",
        "harmattan":    "Weak / absent",
        "rating":       "Moderate",
        "rating_color": "#4fc3f7",
        "notes": (
            "High annual rainfall and persistent cloud cover. "
            "Lowest PSH in Ghana due to rainforest climate. "
            "System efficiency may be reduced by soiling from heavy rainfall runoff."
        ),
    },
    # ── Middle Belt ──────────────────────────────────────────────────────────
    "Ashanti": {
        "capital":      "Kumasi",
        "psh":          5.0,
        "ghi_annual":   1825,
        "ghi_daily":    5.00,
        "avg_temp":     25.8,
        "latitude":     6.7,
        "longitude":   -1.6,
        "tilt_angle":   7,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jun, Sep – Oct",
        "harmattan":    "Dec – Feb (moderate)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Ghana's most densely populated region. "
            "Mild temperatures improve panel efficiency. "
            "Well-balanced two-season solar year."
        ),
    },
    "Eastern": {
        "capital":      "Koforidua",
        "psh":          5.1,
        "ghi_annual":   1862,
        "ghi_daily":    5.10,
        "avg_temp":     25.5,
        "latitude":     6.5,
        "longitude":   -0.5,
        "tilt_angle":   7,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jun, Sep – Oct",
        "harmattan":    "Dec – Feb (moderate)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Good solar resource with lower average temperature than coastal regions. "
            "Akosombo area (Volta Lake) benefits from reflective lake surface."
        ),
    },
    "Volta": {
        "capital":      "Ho",
        "psh":          5.2,
        "ghi_annual":   1898,
        "ghi_daily":    5.20,
        "avg_temp":     27.0,
        "latitude":     6.8,
        "longitude":    0.3,
        "tilt_angle":   7,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jul, Sep – Oct",
        "harmattan":    "Dec – Jan (moderate)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Easternmost region bordered by Togo. "
            "Transitional climate. Good solar availability in dry season."
        ),
    },
    "Western North": {
        "capital":      "Sefwi Wiawso",
        "psh":          5.0,
        "ghi_annual":   1825,
        "ghi_daily":    5.00,
        "avg_temp":     26.0,
        "latitude":     6.5,
        "longitude":   -2.8,
        "tilt_angle":   7,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jul, Sep – Oct",
        "harmattan":    "Dec – Feb (moderate)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Newly created region (2019). Forested highland terrain. "
            "Solar resource similar to Ashanti."
        ),
    },
    "Ahafo": {
        "capital":      "Goaso",
        "psh":          5.2,
        "ghi_annual":   1898,
        "ghi_daily":    5.20,
        "avg_temp":     26.5,
        "latitude":     6.8,
        "longitude":   -2.5,
        "tilt_angle":   7,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jun, Sep – Oct",
        "harmattan":    "Dec – Feb (moderate)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Part of the former Brong-Ahafo region. "
            "Good solar availability; transitional zone between forest and savanna."
        ),
    },
    "Bono": {
        "capital":      "Sunyani",
        "psh":          5.4,
        "ghi_annual":   1971,
        "ghi_daily":    5.40,
        "avg_temp":     27.5,
        "latitude":     7.8,
        "longitude":   -2.5,
        "tilt_angle":   8,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jun, Aug – Sep",
        "harmattan":    "Nov – Feb (strong)",
        "rating":       "Good",
        "rating_color": "#66bb6a",
        "notes": (
            "Sunyani is one of Ghana's sunnier cities. "
            "Increasing dry savanna conditions northward. "
            "Strong harmattan (Nov–Feb) reduces irradiance slightly."
        ),
    },
    "Bono East": {
        "capital":      "Techiman",
        "psh":          5.5,
        "ghi_annual":   2008,
        "ghi_daily":    5.50,
        "avg_temp":     28.0,
        "latitude":     7.8,
        "longitude":   -1.5,
        "tilt_angle":   8,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Jun, Aug – Sep",
        "harmattan":    "Nov – Feb (strong)",
        "rating":       "Very Good",
        "rating_color": "#ffd54f",
        "notes": (
            "Higher irradiance than Bono due to lower latitude cloud cover. "
            "Techiman is a major commercial hub. "
            "Excellent for large-scale solar installations."
        ),
    },
    "Oti": {
        "capital":      "Dambai",
        "psh":          5.5,
        "ghi_annual":   2008,
        "ghi_daily":    5.50,
        "avg_temp":     28.5,
        "latitude":     8.0,
        "longitude":    0.3,
        "tilt_angle":   8,
        "climate":      "Tropical Savanna (Aw)",
        "rainy_months": "Apr – Sep",
        "harmattan":    "Nov – Feb (moderate–strong)",
        "rating":       "Very Good",
        "rating_color": "#ffd54f",
        "notes": (
            "Newly created region along the Volta River. "
            "Single long rainy season. Strong solar potential in dry season."
        ),
    },
    # ── Northern ─────────────────────────────────────────────────────────────
    "Northern": {
        "capital":      "Tamale",
        "psh":          5.8,
        "ghi_annual":   2117,
        "ghi_daily":    5.80,
        "avg_temp":     29.0,
        "latitude":     9.5,
        "longitude":   -1.2,
        "tilt_angle":  10,
        "climate":      "Sudan Savanna (BSh)",
        "rainy_months": "Apr – Sep",
        "harmattan":    "Oct – Mar (strong)",
        "rating":       "Very Good",
        "rating_color": "#ffd54f",
        "notes": (
            "Tamale has one of the highest solar irradiances among major cities. "
            "Long dry season (Oct–Mar) excellent for solar generation. "
            "Single rainy season. Temperature peaks at 40 °C in March."
        ),
    },
    "Savannah": {
        "capital":      "Damongo",
        "psh":          5.9,
        "ghi_annual":   2153,
        "ghi_daily":    5.90,
        "avg_temp":     30.0,
        "latitude":     9.0,
        "longitude":   -1.6,
        "tilt_angle":   9,
        "climate":      "Sudan Savanna (BSh)",
        "rainy_months": "May – Sep",
        "harmattan":    "Oct – Apr (strong)",
        "rating":       "Very Good",
        "rating_color": "#ffd54f",
        "notes": (
            "Extensive savanna. Very long dry season. "
            "High temperatures require attention to panel cooling and inverter ventilation. "
            "Apply temperature derating factor for accurate sizing."
        ),
    },
    "North East": {
        "capital":      "Nalerigu",
        "psh":          6.0,
        "ghi_annual":   2190,
        "ghi_daily":    6.00,
        "avg_temp":     30.5,
        "latitude":    10.5,
        "longitude":   -0.5,
        "tilt_angle":  10,
        "climate":      "Sudan Savanna (BSh)",
        "rainy_months": "May – Sep",
        "harmattan":    "Oct – Apr (very strong)",
        "rating":       "Excellent",
        "rating_color": "#f5a623",
        "notes": (
            "Among the highest solar irradiance regions in Ghana. "
            "Very long dry season. Strong harmattan winds can deposit dust on panels — "
            "schedule quarterly cleaning for optimal performance."
        ),
    },
    "Upper West": {
        "capital":      "Wa",
        "psh":          6.0,
        "ghi_annual":   2190,
        "ghi_daily":    6.00,
        "avg_temp":     30.0,
        "latitude":    10.3,
        "longitude":   -2.3,
        "tilt_angle":  10,
        "climate":      "Sudan Savanna / Sahel",
        "rainy_months": "May – Sep",
        "harmattan":    "Oct – Apr (very strong)",
        "rating":       "Excellent",
        "rating_color": "#f5a623",
        "notes": (
            "Excellent solar resource. Long dry season. "
            "High ambient temperature — apply temperature derating. "
            "Dust deposition from harmattan reduces output; monthly cleaning recommended."
        ),
    },
    "Upper East": {
        "capital":      "Bolgatanga",
        "psh":          6.2,
        "ghi_annual":   2263,
        "ghi_daily":    6.20,
        "avg_temp":     31.0,
        "latitude":    10.9,
        "longitude":   -1.0,
        "tilt_angle":  11,
        "climate":      "Sudan Savanna / Sahel",
        "rainy_months": "May – Sep",
        "harmattan":    "Oct – Apr (very strong)",
        "rating":       "Excellent",
        "rating_color": "#f5a623",
        "notes": (
            "Highest solar irradiance in Ghana. "
            "Bolgatanga receives ~6.2 peak sun hours daily on average. "
            "Very high temperatures (up to 42 °C in April) — oversizing PV array by "
            "5–8% recommended to offset thermal losses."
        ),
    },
}

# ── Region ordering for the UI dropdown ──────────────────────────────────────
REGION_LIST = [
    # Southern
    "Greater Accra", "Central", "Western",
    # Middle belt
    "Ashanti", "Eastern", "Volta", "Western North",
    "Ahafo", "Bono", "Bono East", "Oti",
    # Northern
    "Northern", "Savannah", "North East",
    # Upper
    "Upper West", "Upper East",
]

DEFAULT_REGION = "Greater Accra"


# ── Grid & Power Reliability data per region ─────────────────────────────────
# Sources: ECG/NEDCo service reports, World Bank Ghana Energy Sector (2023),
# PURC (Public Utilities Regulatory Commission) Ghana 2022 report,
# Ghana Statistical Service 2021 Population Census (electrification rates).
#
# ECG  = Electricity Company of Ghana (serves southern/middle belt)
# NEDCo= Northern Electricity Distribution Company (serves northern belt)
POWER_ISSUES = {
    "Greater Accra": {
        "ecg_zone":          "ECG — Accra East/West Districts",
        "daily_outage_hrs":  "4–8 hrs/day",
        "grid_coverage_pct": 82,
        "reliability":       "Fair",
        "main_issues": [
            "Recurrent load shedding (dumsor)",
            "Voltage fluctuations during peak hours",
            "High commercial connection fees",
        ],
    },
    "Central": {
        "ecg_zone":          "ECG — Cape Coast District",
        "daily_outage_hrs":  "6–10 hrs/day",
        "grid_coverage_pct": 72,
        "reliability":       "Fair",
        "main_issues": [
            "Load shedding affecting fishing industry",
            "Aging coastal distribution lines",
            "High billing disputes in rural areas",
        ],
    },
    "Western": {
        "ecg_zone":          "ECG — Sekondi-Takoradi District",
        "daily_outage_hrs":  "6–10 hrs/day",
        "grid_coverage_pct": 68,
        "reliability":       "Fair",
        "main_issues": [
            "High industrial demand (oil & gas)",
            "Aging distribution infrastructure",
            "Load shedding in non-urban areas",
        ],
    },
    "Ashanti": {
        "ecg_zone":          "ECG — Kumasi District",
        "daily_outage_hrs":  "6–12 hrs/day",
        "grid_coverage_pct": 70,
        "reliability":       "Fair",
        "main_issues": [
            "High demand density — Kumasi metro",
            "Load shedding (dumsor) widespread",
            "Industrial supply shortfalls",
        ],
    },
    "Eastern": {
        "ecg_zone":          "ECG — Koforidua District",
        "daily_outage_hrs":  "8–12 hrs/day",
        "grid_coverage_pct": 60,
        "reliability":       "Poor",
        "main_issues": [
            "Frequent line faults in hilly terrain",
            "Rural coverage gaps",
            "Load shedding during dry season",
        ],
    },
    "Volta": {
        "ecg_zone":          "ECG / NEDCo — Transitional Zone",
        "daily_outage_hrs":  "8–14 hrs/day",
        "grid_coverage_pct": 55,
        "reliability":       "Poor",
        "main_issues": [
            "Flooding disrupts distribution lines",
            "Low grid coverage in lake communities",
            "Extended outages in rural east",
        ],
    },
    "Western North": {
        "ecg_zone":          "ECG — Sefwi Wiawso District",
        "daily_outage_hrs":  "8–14 hrs/day",
        "grid_coverage_pct": 45,
        "reliability":       "Poor",
        "main_issues": [
            "Low rural electrification rate",
            "Load shedding throughout region",
            "Limited grid infrastructure (new region)",
        ],
    },
    "Ahafo": {
        "ecg_zone":          "NEDCo — Goaso District",
        "daily_outage_hrs":  "8–14 hrs/day",
        "grid_coverage_pct": 48,
        "reliability":       "Poor",
        "main_issues": [
            "Unreliable supply from NEDCo grid",
            "Low rural grid coverage",
            "Load shedding affecting mining ops",
        ],
    },
    "Bono": {
        "ecg_zone":          "NEDCo — Sunyani District",
        "daily_outage_hrs":  "8–14 hrs/day",
        "grid_coverage_pct": 52,
        "reliability":       "Poor",
        "main_issues": [
            "Aging NEDCo distribution lines",
            "Rural access gaps",
            "Seasonal demand spikes",
        ],
    },
    "Bono East": {
        "ecg_zone":          "NEDCo — Techiman District",
        "daily_outage_hrs":  "10–16 hrs/day",
        "grid_coverage_pct": 42,
        "reliability":       "Poor",
        "main_issues": [
            "Extended daily outages",
            "Low grid coverage outside Techiman",
            "High solar investment potential",
        ],
    },
    "Oti": {
        "ecg_zone":          "NEDCo — Dambai District",
        "daily_outage_hrs":  "10–18 hrs/day",
        "grid_coverage_pct": 35,
        "reliability":       "Very Poor",
        "main_issues": [
            "Very low grid coverage (new region)",
            "Extended blackouts common",
            "Limited transmission infrastructure",
        ],
    },
    "Northern": {
        "ecg_zone":          "NEDCo — Tamale District",
        "daily_outage_hrs":  "10–16 hrs/day",
        "grid_coverage_pct": 45,
        "reliability":       "Poor",
        "main_issues": [
            "Extended load shedding dry season",
            "Voltage instability in peri-urban areas",
            "Rural electrification below 40%",
        ],
    },
    "Savannah": {
        "ecg_zone":          "NEDCo — Damongo District",
        "daily_outage_hrs":  "12–18 hrs/day",
        "grid_coverage_pct": 30,
        "reliability":       "Very Poor",
        "main_issues": [
            "Extended daily blackouts",
            "Very low rural coverage",
            "Grid absent in most communities",
        ],
    },
    "North East": {
        "ecg_zone":          "NEDCo — Nalerigu District",
        "daily_outage_hrs":  "12–20 hrs/day",
        "grid_coverage_pct": 28,
        "reliability":       "Very Poor",
        "main_issues": [
            "Grid access limited to district capital",
            "No electricity in most villages",
            "Strong off-grid solar business case",
        ],
    },
    "Upper West": {
        "ecg_zone":          "NEDCo — Wa District",
        "daily_outage_hrs":  "12–20 hrs/day",
        "grid_coverage_pct": 30,
        "reliability":       "Very Poor",
        "main_issues": [
            "Extended daily outages",
            "Very low rural coverage",
            "Grid confined to Wa and major towns",
        ],
    },
    "Upper East": {
        "ecg_zone":          "NEDCo — Bolgatanga District",
        "daily_outage_hrs":  "10–18 hrs/day",
        "grid_coverage_pct": 38,
        "reliability":       "Poor",
        "main_issues": [
            "Frequent outages — low generation margin",
            "Rural coverage below 35%",
            "High ambient temp degrades transformers",
        ],
    },
}


def get_region(name):
    """Return the data dict for a region, or None if not found."""
    return REGIONS.get(name)


def temp_derating_factor(avg_temp_c):
    """
    Compute panel temperature derating factor.
    Panels lose ~0.40 %/°C above STC temperature (25 °C).
    Returns a multiplier: 1.0 at 25 °C, ~0.976 at 31 °C.
    """
    return max(0.90, 1.0 - max(0.0, (avg_temp_c - 25.0) * 0.004))
