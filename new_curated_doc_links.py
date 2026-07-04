# new_curated_doc_links.py
# Owner 2026-07-04: "fix the links for datasheet and literature of the product
# on the cards" + "new products will be added in future so ensure this dont
# happen again".
#
# Context: the on-demand link crawler (_find_links_for -> _search_engine) is
# broken (stale DuckDuckGo selectors + Bing ck/a redirect wrappers that score 0
# + occasional junk/adult results), so card links never deep-linked to a real
# datasheet -- they always fell through to the Google filetype:pdf fallback.
# See memory project-solar-pv-doc-link-crawler-broken.
#
# Fix (Option 2, owner-approved): curate VERIFIED official-manufacturer
# datasheet + literature URLs for the high-value single-brand solar-equipment
# products and seed them deterministically onto the catalogue. No crawling, no
# junk risk. Matched by (brand, model) so a reseed / newly added product with
# the same identity picks the URL back up automatically.

# (brand, model, datasheet_url, literature_url)
# Every URL is an official manufacturer domain and was verified to resolve.
# Where a model number is a marketplace placeholder, the URL points at the
# manufacturer's product-FAMILY datasheet/product page (accurate + stable).
_CURATED_DOC_LINKS = [
    # --- PV modules ---
    ("JinkoSolar", "JKM-550", "https://www.jinkosolar.com/uploads/619f40ec/JKM550-570N-72HL4-BDV-F1-EN.pdf", "https://www.jinkosolar.com/en/site/tigerneo"),
    ("JinkoSolar", "JKM-480-B", "https://www.jinkosolar.com/uploads/JKM460-480N-60HL4-(V)-F1-EN.pdf", "https://www.jinkosolar.com/en/site/tigerneo"),
    # jasolar.com PDF paths 403 to non-browser clients; use the verified-200
    # jasolar.eu DeepBlue 3.0 official product page for both fields instead.
    ("JA Solar", "JAM72S30-550", "https://www.jasolar.eu/en/products/deep-blue-30", "https://www.jasolar.eu/en/products/deep-blue-30"),
    ("JA Solar", "JAM-500", "https://www.jasolar.eu/en/products/deep-blue-30", "https://www.jasolar.eu/en/products/deep-blue-30"),
    ("JA Solar", "JAM-620", "https://www.jasolar.eu/fileadmin/data/products/4.0/JAM72D42_LB.pdf", "https://www.jasolar.eu/en/products/deep-blue-40"),
    ("Trina", "JKM-440", "https://static.trinasolar.com/sites/default/files/VertexS+_NEG9RC.27_EN_2023_APAC_B_web_0.pdf", "https://pages.trinasolar.com/NEG9R.28.html"),
    ("Trina", "TRI-660", "https://static.trinasolar.com/sites/default/files/Datasheet_Vertex_NEG21C.20_EN_2023_A_web.pdf", "https://www.trinasolar.com/en-apac/NEG21C.20/"),
    ("Canadian Solar", "CS-460", "https://static.csisolar.com/wp-content/uploads/2020/06/30145858/CS-Datasheet-HiKu6_CS6L-MS_v1.2_EN.pdf", "https://www.canadiansolar.com/hiku6/"),
    # --- String / hybrid inverters ---
    ("Huawei", "SUN2000-50K", "https://solar.huawei.com/-/media/Solar/attachment/pdf/eu/datasheet/SUN2000-50kTL-M3-Datasheet.pdf", "https://solar.huawei.com/en/products/sun2000-50ktl-m3/"),
    ("Huawei", "SUN2000-80K", "https://solar.huawei.com/admin/asset/v1/pro/view/2c96bf796f074d8c9b1c8593351451bc.pdf", "https://solar.huawei.com/en/products/SUN2000-150K-MG0/"),
    ("Sungrow", "SG-100K", "https://info-support.sungrowpower.com/application/pdf/2022/12/15/DS_20221214_SG110CX-P2_%20Datasheet_V1_EN(AU).pdf", "https://www.sungrowpower.com/bra/pt/products/string-inverter/sg110cx-p2"),
    ("Sungrow", "SG-200K", "https://info-support.sungrowpower.com/application/pdf/2024/03/22/DS_20240311_%20SG200HX-US_Datasheet_V5_EN.pdf", "https://en.sungrowpower.com/productDetail/6037/string-inverter-sg200hx-us"),
    ("Sungrow", "SUN30K-3P", "https://info-support.sungrowpower.com/application/pdf/2024/03/29/DS_20240328_SH15_20_25T_Datasheet_V3_EN(AU).pdf", "https://www.sungrowpower.com/en/products/residential-energy-storage-system/sht-15-20-25"),
    ("Deye", "SUN-10K-3P", "https://www.deyeinverter.com/deyeinverter/2024/04/16/datasheet_sun-5-12k-sg04lp3_240416_en.pdf", "https://www.deyeinverter.com/product/three-phase-hybrid-inverter-1/sun5-6-8-10-12ksg04lp3.html"),
    ("Deye", "SUN-15K-3P", "https://www.deyeinverter.com/deyeinverter/2023/07/24/datasheet_sun-(5-25)k-sg01hp3-eu_230724_en.pdf", "https://www.deyeinverter.com/product/three-phase-high-voltage-hybrid-inverter/sun5-6-8-10-12-15-20ksg01hp3euam2-520kw-three-phase-2-mppt-hybrid-inverter-high-voltage-battery.html"),
    ("Deye", "SUN-5K-SP", "https://www.deyeinverter.com/deyeinverter/2024/04/16/datasheet_sun-3.6-8k-sg05lp1-eu-sm2_240416_en.pdf", "https://www.deyeinverter.com/product/single-phase-low-voltage-hybrid-inverter/sun3-6-5-6-7-6-8ksg05lp1eu-3-68kw-single-phase-2-mppt-hybrid-inverter-lv-battery-supported-336.html"),
    ("Deye", "SUN-7K-SP", "https://www.deyeinverter.com/deyeinverter/2024/04/16/datasheet_sun-3.6-8k-sg05lp1-eu-sm2_240416_en.pdf", "https://www.deyeinverter.com/product/single-phase-low-voltage-hybrid-inverter/sun3-6-5-6-7-6-8ksg05lp1eu-3-68kw-single-phase-2-mppt-hybrid-inverter-lv-battery-supported-336.html"),
    ("Solis", "SOL-20K-3P", "https://www.solisinverters.com/dataFile/2c9fafbf8c1001a6018c157d3118021b", "https://www.solisinverters.com/global/energy_storage_inverters18/S6-EH3P(12-20)K-H_gl.html"),
    ("GoodWe", "ES-3K", "https://en.goodwe.com/Ftp/EN/Downloads/Datasheet/GW_ES%20G2_Datasheet-EN.pdf", "https://en.goodwe.com/es-g2"),
    # --- Batteries (BESS) ---
    ("Pylontech", "US5000", "https://en.pylontech.com.cn/products/us5000", "https://en.pylontech.com.cn/products/us5000"),
    ("Pylontech", "BAT-10K", "https://en.pylontech.com.cn/products/forcel2", "https://en.pylontech.com.cn/products/forcel2"),
    ("Pylontech", "BAT-2.5K", "https://en.pylontech.com.cn/products/c23/114.html", "https://en.pylontech.com.cn/products/c23/114.html"),
    ("BYD", "BAT-5K", "https://bydbatterybox.com/uploads/downloads/BYD%20Battery-Box%20Premium_Datasheet_HV-AU%20V1.2%20EN-5eec6422498ad.pdf", "https://bydbatterybox.com/#anchor1"),
    ("BYD", "BAT-15K", "https://www.bydbatterybox.com/uploads/downloads/201013_Premium_Datasheet_LVS%20V2.1%20EN-5fa4baa72098c.pdf", "https://bydbatterybox.com/#anchor2"),
    ("BYD", "BAT-25K-RACK", "https://bydbatterybox.com/uploads/downloads/Premium_Datasheet_LVL%20V1.1%20EN-5ebcbeddb3624.pdf", "https://bydbatterybox.com/#anchor3"),
    ("BYD", "BAT-RACK-100", "https://bydbatterybox.com/uploads/downloads/Premium_Datasheet_LVL%20V1.1%20EN-5ebcbeddb3624.pdf", "https://bydbatterybox.com/#anchor3"),
    ("Dyness", "BAT-7K", "https://www.dyness.com/Public/Uploads/uploadfile/files/20250318/DynessTowerdatasheet20240103EN.pdf", "https://dyness.com/tower-high-voltage-storage-battery-for-household-use"),
    # --- Charge controllers ---
    ("Victron", "MPPT-100A", "https://www.victronenergy.com/upload/documents/Datasheet-SmartSolar-charge-controller-MPPT-250-70-up-to-250-100-VE.Can-EN.pdf", "https://www.victronenergy.com/solar-charge-controllers/smartsolar-mppt-ve.can"),
    ("Victron", "MPPT-60A", "https://www.victronenergy.com/upload/documents/Datasheet-SmartSolar-charge-controller-MPPT-150-60-&-150-70-EN.pdf", "https://www.victronenergy.com/solar-charge-controllers/smartsolar-250-85-250-100"),
    # --- Inverter/charger ---
    ("Victron", "PMP482505010", "https://www.victronenergy.com/upload/documents/Datasheet-MultiPlus-II-inverter-charger-EN-.pdf", "https://www.victronenergy.com/inverters-chargers/multiplus-ii"),
    # --- Mounting ---
    ("K2 Systems", "END-35", "https://catalog.k2-systems.com/media/75/8f/b0/4000197-DS-US.pdf", "https://k2-systems.com/en-us/product-solutions/k2-end-clamp/"),
    ("K2 Systems", "MID-35", "https://catalog.k2-systems.com/media/2d/53/2d/4000229-DS-US.pdf", "https://k2-systems.com/en-us/product-solutions/k2-mid-clamp/"),
    ("K2 Systems", "RAIL-K2", "https://catalog.k2-systems.com/media/73/5e/10/CrossRail-TS-US.pdf", "https://k2-systems.com/en-us/product-solutions/crossrail-system/"),
    ("K2 Systems", "ROOF-HOOK", "https://catalogue.k2-systems.com/media/1b/b1/a1/K2-pitched-roof-systems-en.pdf", "https://catalogue.k2-systems.com/en/roof-hook-singlehook-2/2003175"),
    ("Schletter", "GM-FRAME", "https://www.schletter-group.com/strapi/uploads/Schletter_Product_Catalog_2023_4_Web_NA_b0b9d2c7fa.pdf", "https://www.schletter-group.com/mounting-systems/fixed-tilt-systems/"),
    # --- MC4 connectors ---
    ("Staubli", "MC4-PAIR", "https://www.staubli.com/content/dam/ecs/catalogs-brochures/RE/SOL-MC4-11014112-en.pdf", "https://www.staubli.com/global/en/electrical-connectors/industries/renewable-energy/the-original-mc4.html"),
    # --- Monitoring ---
    ("Huawei", "SMARTLOG-1000", "https://solar.huawei.com/-/media/Solar/attachment/pdf/eu/datasheet/SmartLogger3000A.pdf", "https://solar.huawei.com/-/media/Solar/attachment/pdf/eu/datasheet/SmartLogger3000B.pdf"),
    # --- UPS ---
    ("Huawei", "UPS5000-100", "https://digitalpower.huawei.com/admin/asset/v1/pro/view/9adf7e7ca6c24bf1a0e530514448a97c.pdf", "https://digitalpower.huawei.com/en/data-center-facility/ups5000e"),
    ("Huawei", "UPS5000-200", "https://digitalpower.huawei.com/admin/asset/v1/pro/view/efed821b5f4d419f951a2c13c2e42d0b.pdf", "https://digitalpower.huawei.com/en/data-center-facility/ups5000e"),
    # --- Street light ---
    ("Felicity Solar", "SSL-60", "https://africa.felicitysolar.com/wp-content/uploads/2025/05/358-010020-08%E8%BD%AC%E6%9B%B2.pdf", "https://africa.felicitysolar.com/product/a3-60w-p/"),
]


def _seed_curated_doc_links():
    """UPSERT curated official datasheet/literature URLs onto matching catalogue
    rows (matched case-insensitively by brand+model). Additive: only fills a URL
    column that is currently empty, so a supplier-supplied URL is never
    overwritten. Clears links_checked_at on matched rows so any product a broken
    crawl previously stamped 'checked-empty' now serves the curated URL and can
    still resolve its other (uncurated) field on demand. Idempotent; opens its
    own db connection like the sibling seeders. Safe to call on every cold
    start. Inputs: none. Output: none (writes to equipment_catalog)."""
    try:
        _ensure_product_link_columns()
    except Exception:
        pass
    try:
        with get_db() as c:
            for brand, model, ds, lit in _CURATED_DOC_LINKS:
                # CASE-guards keep this additive (never clobber an existing url);
                # links_checked_at=NULL re-enables on-demand resolve of the
                # field we did not curate. db_adapter maps ? -> %s on Postgres.
                c.execute(
                    "UPDATE equipment_catalog SET "
                    "datasheet_url = CASE WHEN COALESCE(datasheet_url,'')='' THEN ? ELSE datasheet_url END, "
                    "literature_url = CASE WHEN COALESCE(literature_url,'')='' THEN ? ELSE literature_url END, "
                    "links_checked_at = NULL "
                    "WHERE LOWER(COALESCE(brand,''))=LOWER(?) AND LOWER(COALESCE(model,''))=LOWER(?)",
                    (ds, lit, brand, model))
    except Exception as e:
        try: app.logger.warning("curated doc-link seed failed: %s", e)
        except Exception: pass
