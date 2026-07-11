# Byte-level patch: extend the spliced guides system in web_app.py so that
#   1. _guide_lookup serves portal-tutorial + sales-pitch (markdown from docs/src),
#   2. the demo_url map deep-links a live multi-screen walkthrough for those two,
#   3. guides_view passes guide_nav so guide.html can render tabs for all 5 guides.
# CRLF-safe, idempotent, asserts each anchor is unique. NEVER Edit web_app.py directly.
import sys

PATH = "web_app.py"
data = open(PATH, "rb").read()


def crlf(s: str) -> bytes:
    return s.replace("\n", "\r\n").encode("utf-8")


# ── 1 + 3: replace _guide_lookup with cache + loader + nav + 5-slug lookup ──
OLD_LOOKUP = crlf(
    'def _guide_lookup(slug):\n'
    '    return {\n'
    '        "quick":     ("Quick Start", _GUIDE_QUICK_MD),\n'
    '        "full-user": ("Full User Guide", _GUIDE_FULL_USER_MD),\n'
    '        "technical": ("Full Technical Guide", _GUIDE_FULL_TECHNICAL_MD),\n'
    '    }.get(slug)'
)

NEW_LOOKUP = crlf(
    '_GUIDE_SRC_CACHE = {}\n'
    '\n'
    '\n'
    'def _load_src_md(fname, fallback_title):\n'
    '    # Load a guide\'s markdown from docs/src/<fname> -- the SAME source the\n'
    '    # collateral PDFs render from -- so Read / Audio / PDF all draw from one\n'
    '    # file and never drift. Cached per process; safe fallback if the file is\n'
    '    # missing on a given deploy.\n'
    '    cached = _GUIDE_SRC_CACHE.get(fname)\n'
    '    if cached is not None:\n'
    '        return cached\n'
    '    try:\n'
    '        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),\n'
    '                         "docs", "src", fname)\n'
    '        with open(p, "r", encoding="utf-8") as fh:\n'
    '            md = fh.read()\n'
    '    except Exception:\n'
    '        md = "# " + fallback_title + "\\n\\n_This guide is being prepared._"\n'
    '    _GUIDE_SRC_CACHE[fname] = md\n'
    '    return md\n'
    '\n'
    '\n'
    '# Ordered nav rendered as tabs on every guide page: (slug, label, icon).\n'
    '_GUIDE_NAV = [\n'
    '    ("quick",           "3-min Quick",          "bi-lightning-charge-fill"),\n'
    '    ("full-user",       "Full User Guide",      "bi-book-half"),\n'
    '    ("technical",       "Full Technical Guide", "bi-cpu-fill"),\n'
    '    ("portal-tutorial", "Portal Tutorial",      "bi-mortarboard-fill"),\n'
    '    ("sales-pitch",     "Sales Pitch",          "bi-megaphone-fill"),\n'
    ']\n'
    '\n'
    '\n'
    'def _guide_lookup(slug):\n'
    '    return {\n'
    '        "quick":     ("Quick Start", _GUIDE_QUICK_MD),\n'
    '        "full-user": ("Full User Guide", _GUIDE_FULL_USER_MD),\n'
    '        "technical": ("Full Technical Guide", _GUIDE_FULL_TECHNICAL_MD),\n'
    '        "portal-tutorial": ("Portal Tutorial",\n'
    '                            _load_src_md("portal_tutorial.md", "Portal Tutorial")),\n'
    '        "sales-pitch": ("Sales Pitch (Inbound Call Script)",\n'
    '                        _load_src_md("sales_pitch.md", "Sales Pitch")),\n'
    '    }.get(slug)'
)

# ── 2: extend demo_url map + pass guide_nav to the template ──
OLD_DEMO = crlf(
    '    demo_url = {\n'
    '        "quick":     url_for("dashboard") + "?tutorial=auto",\n'
    '        "full-user": url_for("marketplace_public") + "?tutorial=auto",\n'
    '        "technical": url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)

NEW_DEMO = crlf(
    '    demo_url = {\n'
    '        "quick":           url_for("dashboard") + "?tutorial=auto",\n'
    '        "full-user":       url_for("marketplace_public") + "?tutorial=auto",\n'
    '        "technical":       url_for("capital_investment_landing") + "?tutorial=auto",\n'
    '        "portal-tutorial": url_for("dashboard") + "?tutorial=auto",\n'
    '        "sales-pitch":     url_for("marketplace_public") + "?tutorial=auto",\n'
    '    }.get(slug, "")'
)

OLD_RENDER = crlf(
    '        demo_url=demo_url,\n'
    '        listen_autoplay=(request.args.get("listen") == "1"),'
)
NEW_RENDER = crlf(
    '        demo_url=demo_url,\n'
    '        guide_nav=_GUIDE_NAV,\n'
    '        listen_autoplay=(request.args.get("listen") == "1"),'
)

if b'_GUIDE_NAV = [' in data:
    print("Already patched (found _GUIDE_NAV) -- no change.")
    sys.exit(0)

for label, old, new in [("lookup", OLD_LOOKUP, NEW_LOOKUP),
                        ("demo", OLD_DEMO, NEW_DEMO),
                        ("render", OLD_RENDER, NEW_RENDER)]:
    n = data.count(old)
    if n != 1:
        print(f"ABORT: anchor '{label}' found {n} times (need exactly 1)")
        sys.exit(1)
    data = data.replace(old, new)

open(PATH, "wb").write(data)
print("Patched web_app.py: 5-guide lookup + demo map + guide_nav.")
