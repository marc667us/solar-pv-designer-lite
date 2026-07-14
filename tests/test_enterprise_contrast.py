"""The enterprise pages must stay READABLE. Contrast is measured, not eyeballed.

OWNER, 2026-07-13: "colours are making visibility bad in the enterprise pages" and
"some magenta colour make it difficult to read" and "select the colours taking into
consideration to visibility".

Two real defects, both measurable:

1. THE GOLD CHIPS WERE INVISIBLE. base.html maps `.ent-page .text-dark` onto the app's LIGHT
   body colour -- correct for the surfaces that block darkens (bg-white and bg-light become
   dark panels, so their ink must go light), but `bg-warning` is not one of those. It stays a
   bright amber, and it carries `text-dark` on badges, the questions-panel header and the
   selected-activity counter. The rule was painting #e2e2f0 onto #ffc107: 1.27:1. Not "hard
   to read" -- invisible.

2. THE MAGENTA WAS BOOTSTRAP'S <code>. `--bs-code-color` defaults to --bs-pink (#d63384), and
   these pages use <code> to name roles and permissions (`report.generate`, `tenant.admin`)
   sixteen times across ten templates. On the card surface that is 4.20:1 -- under the AA
   floor, and visibly magenta against a navy-and-gold page.

WCAG AA: 4.5:1 for body text, 3:1 for large text and UI components. These assert the real
numbers against the real values parsed out of base.html, so a future edit that reintroduces a
low-contrast colour fails here rather than in the owner's eyes.
"""

from __future__ import annotations

import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "templates" / "base.html"
_RAW = BASE.read_text(encoding="utf-8", errors="replace")

# Comments are stripped before anything is measured. The block documents the colours it is
# REPLACING -- naming #d63384 as the bootstrap pink it overrides -- and a guard that cannot
# tell a declaration from the prose explaining it would fail on its own documentation.
CSS = re.sub(r"/\*.*?\*/", "", _RAW, flags=re.S)

# The dark theme's own tokens, read from base.html rather than copied here -- a test that
# hardcodes the palette stops testing the palette the moment somebody changes it.
CARD_BG = re.search(r"--sp-card-bg:\s*(#[0-9a-fA-F]{6})", CSS).group(1)
BODY_TEXT = re.search(r"--sp-text:\s*(#[0-9a-fA-F]{6})", CSS).group(1)

BOOTSTRAP_WARNING = "#ffc107"      # what .bg-warning actually paints
AA_BODY = 4.5


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
                for c in channels]
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _ent_rule_colour(selector_fragment: str) -> str:
    """The `color:` a `.ent-page` rule sets, found by a fragment of its selector."""
    m = re.search(
        rf"\.ent-page[^{{}}]*{re.escape(selector_fragment)}[^{{}}]*\{{[^}}]*?color:\s*(#[0-9a-fA-F]{{6}})",
        CSS,
    )
    assert m, f"no .ent-page rule setting a colour was found for {selector_fragment!r}"
    return m.group(1)


def test_the_sanity_of_the_measure_itself():
    """A contrast function that says everything passes is worse than none."""
    assert contrast("#000000", "#ffffff") == 21.0
    assert contrast("#ffffff", "#ffffff") == 1.0
    # ...and it reproduces the two failures the owner actually reported.
    assert contrast(BODY_TEXT, BOOTSTRAP_WARNING) < 2, (
        "light body text on a gold chip should measure as unreadable -- if it does not, this "
        "file is not measuring what it claims to"
    )
    assert contrast("#d63384", CARD_BG) < AA_BODY      # bootstrap's magenta <code>


def test_text_on_a_gold_chip_is_readable():
    """`badge bg-warning text-dark` must keep DARK ink. It stays a light surface."""
    ink = _ent_rule_colour(".bg-warning.text-dark")
    ratio = contrast(ink, BOOTSTRAP_WARNING)
    assert ratio >= AA_BODY, (
        f"text on .bg-warning measures {ratio:.2f}:1 against {BOOTSTRAP_WARNING} -- below the "
        f"{AA_BODY}:1 AA floor. This is the badge/counter/panel-header colour the owner "
        f"reported as unreadable."
    )


def test_inline_code_is_not_bootstrap_magenta():
    """<code> names roles and permissions on these pages. It has to be legible."""
    assert "#d63384" not in CSS, "bootstrap's pink code colour is back"

    ink = _ent_rule_colour("code")
    ratio = contrast(ink, CARD_BG)
    assert ratio >= AA_BODY, (
        f"inline <code> measures {ratio:.2f}:1 on the card surface -- below the {AA_BODY}:1 "
        f"AA floor. This is the 'magenta' the owner could not read."
    )


def test_the_body_and_secondary_text_still_clear_AA():
    """The tokens the enterprise pages lean on hardest: 152 uses of .text-muted alone."""
    sub = re.search(r"--sp-sub:\s*(#[0-9a-fA-F]{6})", CSS).group(1)
    assert contrast(BODY_TEXT, CARD_BG) >= 7.0          # AAA for body copy
    assert contrast(sub, CARD_BG) >= AA_BODY            # .text-muted is remapped to this


def test_the_accordion_chevron_is_not_inverted():
    """<html data-bs-theme="dark"> already serves a LIGHT chevron.

    Inverting it in the .ent-page block would flip it back to dark and make it vanish against
    these panels -- a fix that silently breaks the control it was meant to polish.
    """
    assert not re.search(r"\.ent-page[^{}]*accordion-button::after[^{}]*\{[^}]*invert", CSS), (
        "the accordion chevron is being inverted on top of Bootstrap's dark-theme chevron"
    )
