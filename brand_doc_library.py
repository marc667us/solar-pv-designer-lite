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

COVERAGE: 240 of 588 products (40%). 96 brand strings exist but many are multi-vendor labels
("Nexans / Tropical / Elsewedy") or placeholders ("Generic"), which deliberately resolve to
nothing rather than to a guess.

AUDITED 2026-07-19 -- AND THE FIRST VERSION OF THIS FILE WAS WRONG.
It shipped with 30 hand-written URLs, none of which had ever been fetched. Fetching them found
13 returning 404, INCLUDING Nexans (29 products) and Legrand (24 products): 53 products were
being redirected to DEAD PAGES. That is worse than the web search this file replaced, because
a search at least finds something. Claimed coverage was 52%; real coverage was far lower, and
part of it was actively harmful.

The dead entries were REMOVED rather than repointed at a homepage. Several vendors' 404s
resolve only to a corporate front page, and a front page is not a documentation library -- a
search for "<brand> <model> datasheet" gets the user closer. An entry here must be a page that
actually serves documents.

403/406 entries are KEPT: those vendors block datacentre IPs and bot user-agents while serving
browsers normally (the doc-redirect code documents the same behaviour). A bot-block is not a
dead page.

MAINTENANCE: add a brand only when its documentation URL has been FETCHED and confirmed -- not
merely looked plausible. `.github/workflows/diag-brand-doc-links.yml` re-checks every URL
monthly and FAILS on 404/410, so this cannot rot silently again.
"""

# Brand (lowercased, trimmed) -> official documentation / product-support library.
# Verified 2026-07-19: each is the manufacturer's own documentation entry point.
BRAND_DOC_LIBRARY: dict[str, str] = {
    "schneider":     "https://www.se.com/ww/en/download/",
    "schneider electric": "https://www.se.com/ww/en/download/",
    "mk":            "https://www.mkelectric.com/en-gb/support/Pages/Downloads.aspx",
    "mk electric":   "https://www.mkelectric.com/en-gb/support/Pages/Downloads.aspx",
    "abb":           "https://library.abb.com/",
    "prysmian":      "https://www.prysmian.com/en/documents",
    "apc":           "https://www.apc.com/us/en/download/",
    "philips":       "https://www.lighting.philips.com/support",
    "signify":       "https://www.lighting.philips.com/support",
    "cummins":       "https://www.cummins.com/support/manuals",
    "longi":         "https://www.longi.com/en/download/",
    "canadian solar": "https://www.canadiansolar.com/downloads/",
    "ja solar":      "https://www.jasolar.com/html/en/service/",
    "sma":           "https://www.sma.de/en/service/downloads",
    "fronius":       "https://www.fronius.com/en/solar-energy",
    "growatt":       "https://en.growatt.com/support/download",
    "victron":       "https://www.victronenergy.com/support-and-downloads/technical-information",
    "victron energy": "https://www.victronenergy.com/support-and-downloads/technical-information",
    "solaredge":     "https://www.solaredge.com/us/downloads",
    "pylontech":     "https://en.pylontech.com.cn/service/",
    "byd":           "https://www.bydbatterybox.com/downloads",
    "deye":          "https://www.deyeinverter.com/download/",
    "felicity":      "https://www.felicitysolar.com/download",
    "commscope":      "https://www.commscope.com/resources/",
    "hikvision":      "https://www.hikvision.com/en/support/download/",
    "ubiquiti":       "https://techspecs.ui.com/",
    "panduit":        "https://www.panduit.com/en/support/download-center.html",
    "socomec":        "https://www.socomec.com/en/documentation",
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


def library_domain_for(brand: str) -> str:
    """The bare domain of `brand`'s documentation library, or ''.

    Input:  a raw brand string.  Output: e.g. "se.com", "library.abb.com", or "".
    Reuses the VERIFIED urls above rather than introducing a second per-brand table
    that could drift out of sync with them.
    Syntax notes: urlsplit().netloc gives "www.se.com"; the leading "www." is dropped
    so the site: filter also matches other hosts on the same domain.
    """
    lib = library_for(brand)
    if not lib:
        return ""
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(lib).netloc or "").strip().lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def product_doc_search_for(brand: str, model: str, kind: str = "datasheet") -> str:
    """A document search for ONE product, scoped to its manufacturer's own site.

    Input:  brand, the product model/name, and kind in {'datasheet','literature'}.
    Output: a search URL restricted to the brand's documentation domain, or ''.

    WHY THIS EXISTS (2026-07-25). The brand tier above answers with the manufacturer's
    documentation ENTRY POINT. That is honest, but it ignores both the model and the
    kind, so every Schneider product -- whichever one you clicked, and whether you asked
    for the datasheet or the literature -- landed on the SAME generic
    https://www.se.com/ww/en/download/ portal. Two differently-labelled links doing the
    identical thing, on a page with no product context, is what "the links don't work"
    means to someone looking for one specific document.

    This keeps the file's honesty rule intact -- it still never asserts that a particular
    PDF *is* the product's datasheet -- while making the destination product-specific and
    kind-aware. `site:` keeps every result on the manufacturer's OWN domain.

    Deliberately NOT `filetype:pdf` here: over-narrowing a model-specific query can return
    ZERO results, which is a worse dead end than the generic portal was. Without it the
    search lands on the product's page on the official site, which carries the documents.
    The last-resort open web search (in the caller) keeps filetype:pdf, unchanged.
    """
    domain = library_domain_for(brand)
    m = (model or "").strip()
    if not domain or not m:
        return ""
    terms = "brochure literature" if (kind or "").strip().lower() == "literature" \
        else "datasheet specification"
    try:
        from urllib.parse import quote_plus
        return "https://www.google.com/search?q=" + quote_plus(
            "site:%s %s %s" % (domain, m, terms))
    except Exception:
        return ""
