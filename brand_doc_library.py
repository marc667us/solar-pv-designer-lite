"""Official manufacturer documentation libraries, by brand.

WHY THIS EXISTS (2026-07-19)
----------------------------
OWNER: "ensure that the literature and data sheet on each product in the marketplace is work"
-> "fix the datasheets".

MEASURED: 37 of 553 products had a cached datasheet URL. Everything else fell through to a
Google search URL.

The obvious fix was to run the existing bulk link-finder over the catalogue. That would have
been WORSE THAN DOING NOTHING, because the finder is broken:

  * DuckDuckGo now answers the scraper with HTTP 202 and zero result anchors;
  * Bing returns ten `bing.com/ck/a?...` redirect wrappers, which the code never decodes, so
    every candidate scores 0 and is discarded -- hence "(none)" for every product;
  * and decoding them does not help. Bing's scraped results for "Jinko Tiger Neo 580W
    datasheet filetype:pdf" are PACKAGING COMPANIES. Wiring the decoder in would have
    attached confident, wrong links to hundreds of products.

Worse, a bulk run stamps `links_checked_at`, which marks a product "already searched" and
excludes it from future attempts -- so one useless sweep would have permanently locked in the
gap it was meant to close.

WHAT THIS DOES INSTEAD
----------------------
A product with no specific datasheet gets its MANUFACTURER'S OWN documentation library. That
is a true statement about where the document lives, and it is one click from the answer.

The ranking of honesty matters more than the ranking of convenience:
    1. the exact datasheet, when we actually have it   (equipment_catalog.datasheet_url)
    2. the manufacturer's documentation library        (this file)
    3. a web search                                    (last resort, unchanged)

Never a guessed PDF. A wrong datasheet on an electrical component is not a cosmetic defect --
someone could specify or install from it.

COVERAGE: the top ten brands are ~53% of the catalogue. 96 brand strings exist but many are
multi-vendor labels ("Nexans / Tropical / Elsewedy") or placeholders ("Generic"), which
deliberately resolve to nothing here rather than to a guess.

MAINTENANCE: add a brand only when its documentation URL has been opened and confirmed. An
unverified entry here is exactly the kind of confident wrongness this file was written to
avoid.
"""

# Brand (lowercased, trimmed) -> official documentation / product-support library.
# Verified 2026-07-19: each is the manufacturer's own documentation entry point.
BRAND_DOC_LIBRARY: dict[str, str] = {
    "schneider":     "https://www.se.com/ww/en/download/",
    "schneider electric": "https://www.se.com/ww/en/download/",
    "mk":            "https://www.mkelectric.com/en-gb/support/Pages/Downloads.aspx",
    "mk electric":   "https://www.mkelectric.com/en-gb/support/Pages/Downloads.aspx",
    "nexans":        "https://www.nexans.com/en/support/documentation/",
    "legrand":       "https://www.legrand.com/en/support/documentation",
    "abb":           "https://library.abb.com/",
    "prysmian":      "https://www.prysmian.com/en/documents",
    "apc":           "https://www.apc.com/us/en/download/",
    "philips":       "https://www.lighting.philips.com/support/downloads",
    "signify":       "https://www.lighting.philips.com/support/downloads",
    "furse":         "https://www.furse.com/en-gb/resources.html",
    "cummins":       "https://www.cummins.com/support/manuals",
    "siemens":       "https://support.industry.siemens.com/cs/ww/en/",
    "eaton":         "https://www.eaton.com/gb/en-gb/support/documentation.html",
    "hager":         "https://www.hager.com/en/downloads",
    "huawei":        "https://solar.huawei.com/en/download",
    "jinko":         "https://www.jinkosolar.com/en/site/download",
    "jinko solar":   "https://www.jinkosolar.com/en/site/download",
    "trina":         "https://www.trinasolar.com/en-glob/resources/downloads",
    "trina solar":   "https://www.trinasolar.com/en-glob/resources/downloads",
    "longi":         "https://www.longi.com/en/support/download/",
    "canadian solar": "https://www.canadiansolar.com/downloads/",
    "ja solar":      "https://www.jasolar.com/html/en/service/",
    "sma":           "https://www.sma.de/en/service/downloads",
    "fronius":       "https://www.fronius.com/en/solar-energy/downloads",
    "growatt":       "https://en.growatt.com/support/download",
    "victron":       "https://www.victronenergy.com/support-and-downloads/technical-information",
    "victron energy": "https://www.victronenergy.com/support-and-downloads/technical-information",
    "sungrow":       "https://en.sungrowpower.com/serviceSupport",
    "solaredge":     "https://www.solaredge.com/us/downloads",
    "pylontech":     "https://en.pylontech.com.cn/service/",
    "byd":           "https://www.bydbatterybox.com/downloads",
    "deye":          "https://www.deyeinverter.com/download/",
    "must":          "https://www.mustpower.com/download",
    "felicity":      "https://www.felicitysolar.com/download",
}

# Brand strings that must NEVER resolve to a library: placeholders and multi-vendor labels.
# Listed explicitly so the intent is visible -- a lookup miss and a deliberate refusal look
# identical at the call site otherwise.
NON_BRANDS: frozenset[str] = frozenset({
    "generic", "n/a", "na", "none", "unbranded", "anonbrand", "various", "assorted", "x",
})


def library_for(brand: str) -> str:
    """The manufacturer's documentation library for `brand`, or '' if we do not know one.

    Input:  a raw brand string from equipment_catalog.brand.
    Output: an official documentation URL, or '' -- never a guess.

    Multi-vendor strings ("Nexans / Tropical / Elsewedy") resolve to '' rather than to their
    first component: the product is one of them and we do not know which, so naming one would
    be a coin flip presented as a fact.
    """
    b = (brand or "").strip().lower()
    if not b or b in NON_BRANDS:
        return ""
    if "/" in b or "," in b:
        return ""
    return BRAND_DOC_LIBRARY.get(b, "")
