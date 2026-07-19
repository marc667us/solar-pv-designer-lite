"""Manufacturer documentation tier for product datasheets.

Context: 37 of 553 products had a cached datasheet URL; the rest fell through to a Google
search. The automated finder cannot close that gap -- DuckDuckGo answers the scraper with
HTTP 202 and Bing returns redirect wrappers whose decoded targets are unrelated ads -- so a
product with no exact datasheet is now offered its MANUFACTURER'S documentation library.

The invariant these tests protect is honesty, not coverage: never emit a link we cannot
stand behind. A wrong datasheet on an electrical component is something a person could
specify or install from.

Run: python -m pytest test_brand_doc_library.py -q
"""
import pytest

from brand_doc_library import BRAND_DOC_LIBRARY, NON_BRANDS, library_for


def test_known_manufacturers_resolve():
    assert library_for("Schneider").startswith("https://")
    assert library_for("ABB").startswith("https://")
    assert library_for("Prysmian").startswith("https://")


def test_lookup_is_case_and_whitespace_insensitive():
    """Catalogue brand strings are hand-entered; 'ABB', ' abb ' and 'Abb' are one brand."""
    assert library_for("  ABB  ") == library_for("abb") == library_for("Abb")


def test_multi_vendor_strings_resolve_to_nothing():
    """'Nexans / Tropical / Elsewedy' is three possible manufacturers.

    Returning the first would be a coin flip presented as a fact. The product is one of them
    and we do not know which.
    """
    assert library_for("Nexans / Tropical / Elsewedy") == ""
    assert library_for("Schneider / ABB / Siemens") == ""
    assert library_for("Sollatek, ServoMax") == ""


def test_placeholder_brands_resolve_to_nothing():
    for b in ("Generic", "generic", "N/A", "none", "Unbranded", "AnonBrand"):
        assert library_for(b) == "", b


def test_unknown_brand_returns_empty_not_a_guess():
    """The whole point: a miss must fall through to search, never to an invented URL."""
    assert library_for("Totally Made Up Brand Ltd") == ""


def test_empty_and_none_are_safe():
    assert library_for("") == ""
    assert library_for(None) == ""


def test_every_entry_is_a_plausible_official_url():
    """Guards against a typo'd or relative entry silently shipping as a redirect target."""
    for brand, url in BRAND_DOC_LIBRARY.items():
        assert url.startswith("https://"), f"{brand} must be https"
        assert " " not in url, f"{brand} has whitespace in its URL"
        assert brand == brand.strip().lower(), f"{brand} key must be trimmed+lowercased"


def test_non_brands_never_appear_as_real_entries():
    """A placeholder must not be both refused and defined -- that ambiguity is a future bug."""
    assert not (set(BRAND_DOC_LIBRARY) & NON_BRANDS)


@pytest.mark.parametrize("brand", ["Schneider", "MK", "ABB", "Prysmian", "APC", "Philips"])
def test_top_catalogue_brands_are_covered(brand):
    """The measured top brands still carrying a VERIFIED documentation URL.

    Nexans and Legrand were removed on 2026-07-19: their documented URLs returned 404, so 53
    products were being redirected to dead pages -- worse than the search fallback they
    replaced. They come back only when someone confirms a working documentation URL.
    """
    assert library_for(brand), f"{brand} lost its documentation library"


@pytest.mark.parametrize("brand", ["Nexans", "Legrand", "Jinko", "Trina", "Hager", "Sungrow"])
def test_brands_with_no_verified_doc_page_fall_back_to_search(brand):
    """Deliberately absent -- do not "restore" these without verifying the URL first.

    Each 404'd when audited, or resolved only to a corporate homepage. A homepage is not a
    documentation library, and a search for "<brand> <model> datasheet" gets the user closer
    than a front page does. An entry here must be a page that actually serves documents.
    """
    assert library_for(brand) == ""
