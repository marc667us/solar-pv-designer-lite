"""
Global solar resource data for PV system design.
PSH = Peak Sun Hours (h/day, annual average), avg_temp = annual ambient °C.
Tariff in local currency/kWh, cost_usd_kwp = all-in installed cost USD/kWp.
Rates reviewed and corrected May 2026 against published utility tariffs.
"""

# Sources:
#   Ghana   — PURC July 2024 tariff revision
#   Nigeria — NERC 2024 multi-band tariff (Band A–E weighted average for C&I solar)
#   S.Africa— Eskom Homelight 2024/25 approved tariff
#   Kenya   — KPLC 2024 domestic tariff schedule (DC30 band)
#   Egypt   — EETC 2024 commercial schedule (post-2024 devaluation)
#   UAE     — ADDC/DEWA 2024 blended residential/commercial
#   KSA     — SEC 2024 commercial tariff schedule
#   UK      — Ofgem 2024 Q4 price cap (p/kWh)
#   Germany — BDEW average household price 2024
#   Spain   — PVPC/regulated tariff average 2024
#   USA     — EIA national average residential 2024
#   Brazil  — ANEEL average including taxes 2024
#   India   — Average across states for commercial consumers 2024
#   Pakistan— NEPRA average 2024 (post-IMF revision)
#   Australia— AER national average 2024/25
#   Tanzania— TANESCO Tariff Schedule 2024 (T1 residential)
#   Ethiopia— EEP revised tariff 2024
#   Zambia  — ZESCO tariff schedule 2024 (R2 residential)
#   Senegal — SENELEC tariff 2024 (tranche B blended)

GLOBAL_DATA = {
    # ── Africa ────────────────────────────────────────────────────────────────
    "Ghana": {
        "currency": "GHS", "symbol": "GH₵",
        "tariff": 1.70,          # GHS/kWh — PURC 2024 blended residential (prev. 2.00 was commercial peak)
        "utility": "Electricity Company of Ghana (ECG) / NEDCo",
        "tariff_ref": "PURC Tariff Order, July 2024 — Blended Residential Rate",
        "cost_usd_kwp": 850,     # USD/kWp all-in — Ghana 2026 (was 980; reduced reflecting import-premium easing 2024-2026)
        "fx_usd": 12.0,          # GHS/USD (2026-06-09 — owner-corrected from 16.0)
        "momo": "MTN MoMo · AirtelTigo Money · Vodafone Cash",
        "regions": {
            "Greater Accra":  {"psh": 4.8, "temp": 27.8, "lat":  5.6, "lon":  -0.2},
            "Ashanti":        {"psh": 5.0, "temp": 25.8, "lat":  6.7, "lon":  -1.6},
            "Northern":       {"psh": 5.8, "temp": 29.0, "lat":  9.5, "lon":  -1.2},
            "Volta":          {"psh": 5.2, "temp": 27.0, "lat":  6.8, "lon":   0.3},
            "Western":        {"psh": 4.7, "temp": 26.5, "lat":  5.0, "lon":  -2.1},
            "Central":        {"psh": 4.8, "temp": 27.2, "lat":  5.5, "lon":  -1.2},
            "Eastern":        {"psh": 5.1, "temp": 25.5, "lat":  6.5, "lon":  -0.5},
            "Bono East":      {"psh": 5.5, "temp": 28.0, "lat":  7.8, "lon":  -1.5},
            "Upper East":     {"psh": 6.2, "temp": 31.0, "lat": 10.9, "lon":  -1.0},
            "Upper West":     {"psh": 6.0, "temp": 30.0, "lat": 10.3, "lon":  -2.3},
            "North East":     {"psh": 6.0, "temp": 30.5, "lat": 10.5, "lon":  -0.5},
            "Savannah":       {"psh": 5.9, "temp": 30.0, "lat":  9.0, "lon":  -1.6},
            "Ahafo":          {"psh": 5.2, "temp": 26.5, "lat":  6.8, "lon":  -2.5},
            "Bono":           {"psh": 5.4, "temp": 27.5, "lat":  7.8, "lon":  -2.5},
            "Oti":            {"psh": 5.5, "temp": 28.5, "lat":  8.0, "lon":   0.3},
            "Western North":  {"psh": 5.0, "temp": 26.0, "lat":  6.5, "lon":  -2.8},
        },
    },
    "Nigeria": {
        "currency": "NGN", "symbol": "₦",
        "tariff": 180.0,         # NGN/kWh — NERC 2024 weighted avg Band A–C (prev. 100 was outdated)
        "utility": "Electricity Distribution Companies (DisCos)",
        "tariff_ref": "NERC Multi-Year Tariff Order (MYTO) 2024 — Bands A–C Weighted Average",
        "cost_usd_kwp": 1000,    # USD/kWp — import duty + logistics premium
        "fx_usd": 1600.0,        # NGN/USD (May 2026 — parallel/official converged)
        "momo": "MTN MoMo Nigeria · Airtel Money · OPay",
        "regions": {
            "Lagos (Southwest)":          {"psh": 4.2, "temp": 27.0, "lat":  6.5, "lon":  3.4},
            "Abuja (Northcentral)":       {"psh": 5.5, "temp": 28.0, "lat":  9.1, "lon":  7.2},
            "Kano (Northwest)":           {"psh": 6.0, "temp": 32.0, "lat": 12.0, "lon":  8.5},
            "Maiduguri (Northeast)":      {"psh": 6.2, "temp": 33.0, "lat": 11.8, "lon": 13.2},
            "Enugu (Southeast)":          {"psh": 4.5, "temp": 26.0, "lat":  6.5, "lon":  7.5},
            "Port Harcourt (South-South)":{"psh": 3.8, "temp": 27.0, "lat":  4.8, "lon":  7.0},
            "Ibadan (Oyo)":              {"psh": 4.5, "temp": 28.0, "lat":  7.4, "lon":  3.9},
            "Benin City (Edo)":          {"psh": 4.0, "temp": 27.5, "lat":  6.3, "lon":  5.6},
        },
    },
    "South Africa": {
        "currency": "ZAR", "symbol": "R",
        "tariff": 3.80,          # ZAR/kWh — Eskom Homelight 2024/25 (prev. 3.50 pre-12.7% increase)
        "utility": "Eskom Holdings",
        "tariff_ref": "Eskom Homelight Tariff Schedule 2024/25 (12.7% NERSA-approved increase)",
        "cost_usd_kwp": 950,
        "fx_usd": 19.0,          # ZAR/USD (May 2026)
        "regions": {
            "Gauteng (Johannesburg)":  {"psh": 5.5, "temp": 18.0, "lat": -26.2, "lon": 28.0},
            "Western Cape (Cape Town)":{"psh": 5.8, "temp": 17.0, "lat": -33.9, "lon": 18.4},
            "Northern Cape (Upington)":{"psh": 6.5, "temp": 22.0, "lat": -28.5, "lon": 21.2},
            "KwaZulu-Natal (Durban)":  {"psh": 5.0, "temp": 22.0, "lat": -29.9, "lon": 31.0},
            "Eastern Cape":            {"psh": 5.2, "temp": 19.0, "lat": -32.0, "lon": 26.5},
            "Limpopo":                 {"psh": 5.8, "temp": 22.0, "lat": -23.9, "lon": 29.5},
            "Mpumalanga":              {"psh": 5.5, "temp": 20.0, "lat": -25.5, "lon": 30.5},
        },
    },
    "Kenya": {
        "currency": "KES", "symbol": "KSh",
        "tariff": 22.0,          # KES/kWh — KPLC DC30 blended incl. FCA (prev. 25 was high-band)
        "utility": "Kenya Power and Lighting Company (KPLC)",
        "tariff_ref": "KPLC Domestic Tariff DC30 incl. Fuel Cost Adjustment (FCA), 2024",
        "cost_usd_kwp": 1000,
        "fx_usd": 132.0,         # KES/USD (May 2026)
        "regions": {
            "Nairobi":         {"psh": 5.5, "temp": 19.0, "lat": -1.3, "lon": 36.8},
            "Mombasa (Coast)": {"psh": 5.8, "temp": 28.0, "lat": -4.1, "lon": 39.7},
            "Kisumu (West)":   {"psh": 5.2, "temp": 22.0, "lat": -0.1, "lon": 34.8},
            "North Kenya":     {"psh": 6.0, "temp": 25.0, "lat":  1.5, "lon": 37.5},
            "Eldoret (Rift Valley)": {"psh": 5.5, "temp": 18.0, "lat":  0.5, "lon": 35.3},
            "Nakuru":          {"psh": 5.5, "temp": 18.0, "lat": -0.3, "lon": 36.1},
        },
    },
    "Tanzania": {
        "currency": "TZS", "symbol": "TSh",
        "tariff": 400.0,         # TZS/kWh — TANESCO T1 residential 2024
        "utility": "Tanzania Electric Supply Company (TANESCO)",
        "tariff_ref": "TANESCO Tariff Schedule 2024 — T1 Residential",
        "cost_usd_kwp": 1100,    # Higher due to limited local supply chain
        "fx_usd": 2700.0,        # TZS/USD (May 2026)
        "regions": {
            "Dar es Salaam":   {"psh": 5.5, "temp": 26.0, "lat": -6.8, "lon": 39.3},
            "Dodoma":          {"psh": 5.8, "temp": 24.0, "lat": -6.2, "lon": 35.7},
            "Mwanza":          {"psh": 5.5, "temp": 23.0, "lat": -2.5, "lon": 32.9},
            "Arusha":          {"psh": 5.6, "temp": 20.0, "lat": -3.4, "lon": 36.7},
            "Moshi":           {"psh": 5.6, "temp": 21.0, "lat": -3.3, "lon": 37.3},
            "Zanzibar Island": {"psh": 5.8, "temp": 28.0, "lat": -6.2, "lon": 39.2},
            "Mbeya (Highlands)":{"psh": 5.4, "temp": 20.0, "lat": -8.9, "lon": 33.5},
        },
    },
    "Ethiopia": {
        "currency": "ETB", "symbol": "Br",
        "tariff": 2.00,          # ETB/kWh — EEP 2024 revised blended rate
        "utility": "Ethiopian Electric Power (EEP) / Ethiopian Electric Utility (EEU)",
        "tariff_ref": "EEP/EEU Revised Tariff Schedule 2024",
        "cost_usd_kwp": 1050,
        "fx_usd": 120.0,         # ETB/USD (May 2026 — post-2024 devaluation)
        "regions": {
            "Addis Ababa":     {"psh": 5.5, "temp": 17.0, "lat":  9.0, "lon": 38.7},
            "Dire Dawa":       {"psh": 6.0, "temp": 26.0, "lat":  9.6, "lon": 41.9},
            "Mekelle (Tigray)":{"psh": 6.0, "temp": 22.0, "lat": 13.5, "lon": 39.5},
            "Hawassa":         {"psh": 5.8, "temp": 22.0, "lat":  7.1, "lon": 38.5},
            "Bahir Dar":       {"psh": 5.8, "temp": 21.0, "lat": 11.6, "lon": 37.4},
            "Adama (Nazret)":  {"psh": 5.8, "temp": 22.0, "lat":  8.5, "lon": 39.3},
        },
    },
    "Zambia": {
        "currency": "ZMW", "symbol": "ZK",
        "tariff": 3.00,          # ZMW/kWh — ZESCO R2 residential 2024
        "utility": "ZESCO Limited",
        "tariff_ref": "ZESCO Tariff Schedule 2024 — R2 Residential",
        "cost_usd_kwp": 1050,
        "fx_usd": 27.0,          # ZMW/USD (May 2026)
        "regions": {
            "Lusaka":          {"psh": 5.8, "temp": 22.0, "lat": -15.4, "lon": 28.3},
            "Livingstone":     {"psh": 6.0, "temp": 23.0, "lat": -17.9, "lon": 25.9},
            "Ndola (Copperbelt)":{"psh": 5.5, "temp": 22.0, "lat": -13.0, "lon": 28.6},
            "Kitwe":           {"psh": 5.5, "temp": 22.0, "lat": -12.8, "lon": 28.2},
            "Kabwe":           {"psh": 5.7, "temp": 22.0, "lat": -14.4, "lon": 28.5},
        },
    },
    "Senegal": {
        "currency": "XOF", "symbol": "CFA",
        "tariff": 110.0,         # XOF/kWh — SENELEC tranche B blended 2024
        "utility": "SENELEC (Société Nationale d'Électricité du Sénégal)",
        "tariff_ref": "SENELEC Tariff Schedule 2024 — Tranche B Blended Rate",
        "cost_usd_kwp": 1050,
        "fx_usd": 620.0,         # XOF/USD (CFA franc pegged to EUR at 655.957 XOF/EUR)
        "momo": "Orange Money · Wave · Free Money",
        "regions": {
            "Dakar":           {"psh": 5.5, "temp": 25.0, "lat": 14.7, "lon": -17.4},
            "Thies":           {"psh": 5.6, "temp": 25.0, "lat": 14.8, "lon": -16.9},
            "Touba":           {"psh": 5.8, "temp": 28.0, "lat": 14.9, "lon": -15.9},
            "Ziguinchor":      {"psh": 5.2, "temp": 27.0, "lat": 12.6, "lon": -16.3},
            "Saint-Louis":     {"psh": 6.0, "temp": 26.0, "lat": 16.0, "lon": -16.5},
            "Tambacounda":     {"psh": 6.2, "temp": 30.0, "lat": 13.8, "lon": -13.7},
        },
    },
    "Gambia": {
        "currency": "GMD", "symbol": "D",
        "tariff": 9.0,           # GMD/kWh — NAWEC residential blended 2024
        "utility": "NAWEC (National Water and Electricity Company)",
        "tariff_ref": "NAWEC Residential Electricity Tariff 2024",
        "cost_usd_kwp": 1100,
        "fx_usd": 71.0,          # GMD/USD (May 2026)
        "momo": "Africell Money · QMoney (Trust Bank)",
        "regions": {
            "Banjul / Kombo":  {"psh": 5.5, "temp": 27.0, "lat": 13.5, "lon": -16.6},
            "Brikama":         {"psh": 5.6, "temp": 27.5, "lat": 13.3, "lon": -16.7},
            "Farafenni":       {"psh": 5.8, "temp": 30.0, "lat": 13.6, "lon": -15.6},
            "Basse Santa Su":  {"psh": 6.0, "temp": 31.0, "lat": 13.3, "lon": -14.2},
            "Janjanbureh":     {"psh": 5.9, "temp": 30.5, "lat": 13.5, "lon": -14.8},
        },
    },
    "Liberia": {
        "currency": "LRD", "symbol": "L$",
        "tariff": 54.0,          # LRD/kWh — LEC residential (~$0.27/kWh at LRD 200/USD)
        "utility": "Liberia Electricity Corporation (LEC)",
        "tariff_ref": "LEC Residential Tariff Schedule 2024",
        "cost_usd_kwp": 1100,
        "fx_usd": 200.0,         # LRD/USD (May 2026)
        "momo": "MTN MoMo · Orange Money",
        "regions": {
            "Monrovia":        {"psh": 4.5, "temp": 26.0, "lat":  6.3, "lon": -10.8},
            "Gbarnga":         {"psh": 5.0, "temp": 25.0, "lat":  7.0, "lon":  -9.5},
            "Buchanan":        {"psh": 4.8, "temp": 27.0, "lat":  5.9, "lon":  -9.9},
            "Zwedru":          {"psh": 5.0, "temp": 25.0, "lat":  6.1, "lon":  -8.1},
            "Voinjama":        {"psh": 5.2, "temp": 24.0, "lat":  8.4, "lon": -10.0},
        },
    },
    "Cameroon": {
        "currency": "XAF", "symbol": "FCFA",
        "tariff": 90.0,          # XAF/kWh — ENEO blended residential/commercial 2024
        "utility": "ENEO Cameroun S.A.",
        "tariff_ref": "ENEO Blended Residential/Commercial Tariff 2024 (ARSEL regulated)",
        "cost_usd_kwp": 1100,
        "fx_usd": 615.0,         # XAF/USD (Central African CFA pegged to EUR; 1 USD ≈ XAF 615)
        "momo": "MTN MoMo · Orange Money Cameroon",
        "regions": {
            "Yaounde":         {"psh": 4.5, "temp": 23.0, "lat":  3.9, "lon": 11.5},
            "Douala":          {"psh": 4.0, "temp": 27.0, "lat":  4.1, "lon":  9.7},
            "Garoua":          {"psh": 6.5, "temp": 32.0, "lat":  9.3, "lon": 13.4},
            "Bamenda":         {"psh": 4.8, "temp": 22.0, "lat":  5.9, "lon": 10.2},
            "Maroua":          {"psh": 6.5, "temp": 32.0, "lat": 10.6, "lon": 14.3},
            "Bafoussam":       {"psh": 4.8, "temp": 22.0, "lat":  5.5, "lon": 10.4},
            "Ngaoundere":      {"psh": 5.5, "temp": 24.0, "lat":  7.3, "lon": 13.6},
        },
    },
    "Egypt": {
        "currency": "EGP", "symbol": "E£",
        "tariff": 1.80,          # EGP/kWh — EETC 2024 commercial (prev. 1.50 pre-devaluation)
        "utility": "Egyptian Electricity Transmission Company (EETC) / DISCOs",
        "tariff_ref": "EETC Commercial Schedule 2024 — post-EGP float revision",
        "cost_usd_kwp": 850,
        "fx_usd": 50.0,          # EGP/USD (May 2026 — post-March 2024 float)
        "regions": {
            "Cairo":        {"psh": 6.3, "temp": 22.0, "lat": 30.1, "lon": 31.4},
            "Aswan":        {"psh": 7.5, "temp": 30.0, "lat": 24.1, "lon": 32.9},
            "Alexandria":   {"psh": 5.8, "temp": 20.0, "lat": 31.2, "lon": 29.9},
            "Luxor":        {"psh": 7.2, "temp": 28.0, "lat": 25.7, "lon": 32.6},
            "Hurghada":     {"psh": 7.0, "temp": 27.0, "lat": 27.3, "lon": 33.8},
        },
    },
    # ── Middle East ───────────────────────────────────────────────────────────
    "UAE": {
        "currency": "AED", "symbol": "AED",
        "tariff": 0.29,          # AED/kWh — ADDC/DEWA 2024 blended residential (prev. 0.38 overshot)
        "utility": "DEWA (Dubai) / ADDC (Abu Dhabi) / SEWA (Sharjah)",
        "tariff_ref": "ADDC/DEWA Blended Residential Tariff 2024",
        "cost_usd_kwp": 800,
        "fx_usd": 3.67,          # AED pegged to USD
        "regions": {
            "Abu Dhabi": {"psh": 6.5, "temp": 28.0, "lat": 24.5, "lon": 54.4},
            "Dubai":     {"psh": 6.0, "temp": 27.0, "lat": 25.2, "lon": 55.3},
            "Sharjah":   {"psh": 6.0, "temp": 27.5, "lat": 25.4, "lon": 55.4},
            "Ras Al Khaimah": {"psh": 6.0, "temp": 27.0, "lat": 25.8, "lon": 55.9},
        },
    },
    "Saudi Arabia": {
        "currency": "SAR", "symbol": "SAR",
        "tariff": 0.26,          # SAR/kWh — SEC 2024 commercial schedule (prev. 0.18 was residential subsidy)
        "utility": "Saudi Electricity Company (SEC)",
        "tariff_ref": "SEC Commercial Tariff Schedule 2024 (ECRA regulated)",
        "cost_usd_kwp": 780,
        "fx_usd": 3.75,          # SAR pegged to USD
        "regions": {
            "Riyadh":  {"psh": 7.0, "temp": 26.0, "lat": 24.7, "lon": 46.7},
            "Jeddah":  {"psh": 6.5, "temp": 28.0, "lat": 21.5, "lon": 39.2},
            "Dammam":  {"psh": 6.2, "temp": 26.0, "lat": 26.4, "lon": 50.1},
            "Tabuk":   {"psh": 7.2, "temp": 24.0, "lat": 28.4, "lon": 36.6},
        },
    },
    # ── Europe ────────────────────────────────────────────────────────────────
    "United Kingdom": {
        "currency": "GBP", "symbol": "£",
        "tariff": 0.245,         # GBP/kWh — Ofgem Q4 2024 price cap (prev. 0.29 was 2023 crisis peak)
        "utility": "Various licensed suppliers (Ofgem regulated)",
        "tariff_ref": "Ofgem Default Tariff Price Cap Q4 2024 — Unit Rate",
        "cost_usd_kwp": 1600,    # USD/kWp — UK labor + scaffolding + compliance premium
        "fx_usd": 0.79,          # GBP/USD (May 2026)
        "regions": {
            "England — South": {"psh": 3.2, "temp": 12.0, "lat": 51.5, "lon":  -0.1},
            "England — North": {"psh": 2.8, "temp": 10.0, "lat": 53.5, "lon":  -2.2},
            "Scotland":        {"psh": 2.5, "temp":  8.0, "lat": 56.5, "lon":  -4.0},
            "Wales":           {"psh": 2.7, "temp": 10.0, "lat": 52.1, "lon":  -3.8},
            "Northern Ireland":{"psh": 2.5, "temp":  9.0, "lat": 54.6, "lon":  -6.7},
        },
    },
    "Germany": {
        "currency": "EUR", "symbol": "€",
        "tariff": 0.32,          # EUR/kWh — BDEW household average 2024
        "utility": "Various licensed suppliers (Bundesnetzagentur regulated)",
        "tariff_ref": "BDEW Average Household Electricity Price 2024 (incl. taxes & levies)",
        "cost_usd_kwp": 1200,
        "fx_usd": 0.91,          # EUR/USD (May 2026 — prev. 0.92 slightly off)
        "regions": {
            "Bavaria (South)": {"psh": 3.8, "temp": 10.0, "lat": 48.1, "lon": 11.6},
            "NRW (West)":      {"psh": 3.2, "temp": 10.0, "lat": 51.2, "lon":  6.8},
            "Berlin (North)":  {"psh": 3.0, "temp":  9.0, "lat": 52.5, "lon": 13.4},
            "Hamburg":         {"psh": 2.9, "temp":  9.5, "lat": 53.6, "lon":  9.9},
            "Baden-Württemberg":{"psh": 3.6, "temp": 11.0, "lat": 48.7, "lon":  9.2},
        },
    },
    "Spain": {
        "currency": "EUR", "symbol": "€",
        "tariff": 0.25,          # EUR/kWh — PVPC regulated average 2024
        "utility": "Red Eléctrica de España (REE) / Various retailers",
        "tariff_ref": "PVPC (Precio Voluntario al Pequeño Consumidor) Regulated Average 2024",
        "cost_usd_kwp": 1050,
        "fx_usd": 0.91,
        "regions": {
            "Andalusia":  {"psh": 5.5, "temp": 18.0, "lat": 37.4, "lon":  -6.0},
            "Madrid":     {"psh": 5.0, "temp": 15.0, "lat": 40.4, "lon":  -3.7},
            "Catalonia":  {"psh": 4.8, "temp": 16.0, "lat": 41.4, "lon":   2.2},
            "Murcia":     {"psh": 5.8, "temp": 18.5, "lat": 37.9, "lon":  -1.1},
            "Valencia":   {"psh": 5.3, "temp": 17.0, "lat": 39.5, "lon":  -0.4},
            "Canary Islands":{"psh": 6.0, "temp": 22.0, "lat": 28.1, "lon":-15.4},
        },
    },
    # ── Americas ──────────────────────────────────────────────────────────────
    "USA": {
        "currency": "USD", "symbol": "$",
        "tariff": 0.16,          # USD/kWh — EIA national residential average 2024
        "utility": "Various (state-regulated IOUs, co-ops, and municipal utilities)",
        "tariff_ref": "EIA National Average Residential Retail Rate 2024 (Form EIA-861)",
        "cost_usd_kwp": 2500,    # USD/kWp gross (before 30% ITC credit)
        "fx_usd": 1.0,
        "regions": {
            "Arizona":    {"psh": 6.5, "temp": 22.0, "lat": 33.4, "lon": -112.1},
            "California": {"psh": 5.8, "temp": 17.0, "lat": 36.8, "lon": -119.4},
            "Texas":      {"psh": 5.5, "temp": 20.0, "lat": 31.0, "lon":  -99.0},
            "Florida":    {"psh": 5.0, "temp": 23.0, "lat": 27.7, "lon":  -82.5},
            "New York":   {"psh": 4.0, "temp": 12.0, "lat": 40.7, "lon":  -74.0},
            "Colorado":   {"psh": 5.5, "temp": 10.0, "lat": 39.7, "lon": -104.9},
            "Nevada":     {"psh": 6.3, "temp": 20.0, "lat": 36.2, "lon": -115.1},
        },
    },
    "Brazil": {
        "currency": "BRL", "symbol": "R$",
        "tariff": 0.85,          # BRL/kWh — ANEEL average incl. taxes 2024 (prev. 0.70 was pre-inflation)
        "utility": "Various DISCOs (ANEEL regulated)",
        "tariff_ref": "ANEEL National Average Tariff 2024 — incl. ICMS, PIS/COFINS taxes",
        "cost_usd_kwp": 900,
        "fx_usd": 5.8,           # BRL/USD (May 2026 — prev. 5.1 was outdated)
        "regions": {
            "Bahia (Northeast)":     {"psh": 5.5, "temp": 24.0, "lat": -12.9, "lon": -38.5},
            "São Paulo (Southeast)": {"psh": 4.8, "temp": 19.0, "lat": -23.5, "lon": -46.6},
            "Minas Gerais":          {"psh": 5.2, "temp": 20.0, "lat": -19.9, "lon": -43.9},
            "Amazon (North)":        {"psh": 4.0, "temp": 26.0, "lat":  -3.1, "lon": -60.0},
            "Rio Grande do Sul":     {"psh": 4.5, "temp": 18.0, "lat": -30.0, "lon": -51.2},
            "Ceará":                 {"psh": 5.8, "temp": 26.0, "lat":  -3.7, "lon": -38.5},
        },
    },
    # ── Asia / Pacific ────────────────────────────────────────────────────────
    "India": {
        "currency": "INR", "symbol": "₹",
        "tariff": 8.0,           # INR/kWh — average commercial across states 2024
        "utility": "State DISCOMs (CERC / SERC regulated)",
        "tariff_ref": "CERC / State SERC Average Commercial Tariff 2024 — Weighted across states",
        "cost_usd_kwp": 700,     # USD/kWp — with battery (prev. 600 was grid-tied only, too low)
        "fx_usd": 84.0,          # INR/USD (May 2026)
        "regions": {
            "Rajasthan":              {"psh": 6.5, "temp": 28.0, "lat": 26.9, "lon":  75.8},
            "Gujarat":                {"psh": 6.0, "temp": 27.0, "lat": 22.3, "lon":  72.6},
            "Maharashtra (Mumbai)":   {"psh": 5.0, "temp": 27.0, "lat": 19.1, "lon":  72.9},
            "Karnataka (Bangalore)":  {"psh": 5.5, "temp": 23.0, "lat": 12.9, "lon":  77.6},
            "Tamil Nadu":             {"psh": 5.5, "temp": 28.0, "lat": 13.1, "lon":  80.3},
            "Delhi":                  {"psh": 5.5, "temp": 25.0, "lat": 28.6, "lon":  77.2},
            "Telangana (Hyderabad)":  {"psh": 5.5, "temp": 27.0, "lat": 17.4, "lon":  78.5},
        },
    },
    "Pakistan": {
        "currency": "PKR", "symbol": "Rs",
        "tariff": 60.0,          # PKR/kWh — NEPRA post-IMF revision average 2024 (prev. 50 was outdated)
        "utility": "DISCOs — LESCO, PESCO, IESCO, HESCO, MEPCO (NEPRA regulated)",
        "tariff_ref": "NEPRA Average Consumer Tariff 2024 — Post-IMF Revision",
        "cost_usd_kwp": 750,     # USD/kWp (prev. 700 was too low for battery systems)
        "fx_usd": 280.0,         # PKR/USD (May 2026)
        "regions": {
            "Punjab (Lahore)":  {"psh": 5.5, "temp": 25.0, "lat": 31.5, "lon": 74.4},
            "Sindh (Karachi)":  {"psh": 6.0, "temp": 27.0, "lat": 24.9, "lon": 67.0},
            "Balochistan":      {"psh": 6.5, "temp": 25.0, "lat": 28.0, "lon": 65.0},
            "KPK (Peshawar)":   {"psh": 5.0, "temp": 22.0, "lat": 34.0, "lon": 71.6},
            "Islamabad":        {"psh": 5.2, "temp": 22.0, "lat": 33.7, "lon": 73.1},
        },
    },
    "Australia": {
        "currency": "AUD", "symbol": "A$",
        "tariff": 0.34,          # AUD/kWh — AER national average 2024/25 (prev. 0.30 was understated)
        "utility": "Various retailers (AER / state regulator regulated)",
        "tariff_ref": "AER National Average Residential Flat Rate 2024/25",
        "cost_usd_kwp": 1100,
        "fx_usd": 1.5625,        # AUD per USD (May 2026: A$1=USD0.64 → 1 USD=A$1.5625)
        "regions": {
            "Queensland (Brisbane)":       {"psh": 5.8, "temp": 22.0, "lat": -27.5, "lon": 153.0},
            "New South Wales (Sydney)":    {"psh": 5.2, "temp": 18.0, "lat": -33.9, "lon": 151.2},
            "Victoria (Melbourne)":        {"psh": 4.5, "temp": 15.0, "lat": -37.8, "lon": 145.0},
            "Western Australia (Perth)":   {"psh": 5.8, "temp": 19.0, "lat": -31.9, "lon": 115.9},
            "South Australia (Adelaide)":  {"psh": 5.5, "temp": 17.0, "lat": -34.9, "lon": 138.6},
            "Northern Territory (Darwin)": {"psh": 6.0, "temp": 29.0, "lat": -12.5, "lon": 130.8},
        },
    },
}


def get_countries():
    return sorted(GLOBAL_DATA.keys())


def get_regions(country):
    return list(GLOBAL_DATA.get(country, {}).get("regions", {}).keys())


def get_solar_data(country, region):
    """Return solar data dict for a country/region, or None."""
    cd = GLOBAL_DATA.get(country)
    if not cd:
        return None
    rd = cd["regions"].get(region)
    if not rd:
        return None
    return {
        "country":      country,
        "region":       region,
        "psh":          rd["psh"],
        "avg_temp":     rd["temp"],
        "latitude":     rd["lat"],
        "longitude":    rd["lon"],
        "tariff":       cd["tariff"],
        "currency":     cd["currency"],
        "symbol":       cd["symbol"],
        "cost_usd_kwp": cd["cost_usd_kwp"],
        "fx_usd":       cd["fx_usd"],
        "momo":         cd.get("momo", ""),
        "utility":      cd.get("utility", ""),
        "tariff_ref":   cd.get("tariff_ref", ""),
    }


def get_momo_countries():
    """Return dict of country → MoMo networks for all countries that support it."""
    return {c: d["momo"] for c, d in GLOBAL_DATA.items() if d.get("momo")}


def temp_derating(avg_temp_c):
    """Panel temperature derating: 0.4%/°C above 25°C STC."""
    return max(0.88, 1.0 - max(0.0, (avg_temp_c - 25.0) * 0.004))
