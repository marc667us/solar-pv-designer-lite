"""Keep tutorials in step with the app: generate missing ones, detect stale ones.

The rule (owner): *if a feature is added or changed, the engine must create or
update its tutorial.* A tutorial that is merely "authored once" rots silently --
a renamed route orphans it, a redesigned page leaves its steps pointing at
controls that no longer exist, and a brand-new page ships with no tutorial at all.

This script closes that loop. It renders each user-facing page with Flask's test
client, parses the real DOM, and reports three classes of problem:

  MISSING   a user-facing feature page has no scenario at all
  DEAD      a scenario step targets a selector that no longer matches anything
  ORPHANED  a scenario is keyed to an endpoint that no longer exists

Modes
  --check   report and exit non-zero if anything is MISSING/DEAD/ORPHANED (CI gate)
  --write   additionally emit a DRAFT scenario for every MISSING page, generated
            by scanning that page's interactive controls (buttons, links, inputs)
            and laying down a cursor step for each. Drafts are marked
            {"draft": true} and carry generated narration for a human to edit --
            the spec's "AI scans components -> generates tutorial -> developer
            edits narration -> publish" loop, minus any paid model.

Usage
  python scripts/sync_tutorials.py --check
  python scripts/sync_tutorials.py --write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCEN = os.path.join(ROOT, "static", "tutorial", "scenarios")
sys.path.insert(0, ROOT)

# Endpoints that are not "features" a user runs: APIs, assets, webhooks, health,
# auth plumbing, ops probes, exports, and anything that is not a plain GET page.
SKIP_PREFIX = ("api_", "static", "auth_", "admin_ops_", "paystack", "stripe",
               "keycloak", "csp_", "metrics", "health", "guides_", "support_asset")
SKIP_SUBSTR = ("_pdf", "_xlsx", ".rss", "_json", "webhook", "_delete", "_clear",
               "_reset", "_revoke", "logout", "download", "export", "_email",
               "_refresh", "_ping", "_run", "_save", "_record", "_activate",
               "_redeem", "_checkout", "_callback", "_template", "_batch",
               "diag", "_probe")

# Machine endpoints and static content: real URLs, but nothing a user "runs".
# A tutorial for /robots.txt or /terms would be noise, not help.
SKIP_EXACT = {
    "robots_txt", "sitemap_xml", "news_rss", "opportunities_rss", "three_test",
    "terms", "privacy", "data_protection", "login", "register", "landing_page2",
    "forgot_password", "reset_password", "verify_email", "logout",
    "boq_catalog_categories",          # returns JSON, not a page
    "prometheus_metrics", "_metrics",  # scrape endpoints
    "oidc.auth_login", "oidc.auth_register",
    # Actions/redirects, not screens a user reads.
    "marketplace_action_gate", "marketplace_product_doc_redirect",
    "folder_zip", "inspection_upload_serve", "referral_capture",
    "boq_floor_build_all", "boq_project_sync_from_bom",
    "project_from_assessment", "bill_check_design_continue",
    "boms_recheck_prices_review",
    "monitor_status", "monitor_alerts_list",   # JSON monitors, no UI
}
# A rule serving a file/feed is not a page.
SKIP_RULE_SUFFIX = (".rss", ".xml", ".txt", ".json", ".pdf", ".xlsx", ".png", ".ico")

# The admin screens that represent the "Administration", "CRM" and "Sales
# Pipeline" modules. The rest of /admin/* are internal tools, not user features.
ADMIN_FEATURES = {"admin_users", "admin_sales", "admin_pipeline"}


class Controls(HTMLParser):
    """Collect the interactive controls of a page so a draft tour can point at them.

    out: .found = [(kind, selector, label)] in document order
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, str, str]] = []
        self._grab: str | None = None
        self._buf: list[str] = []
        self._pending: tuple[str, str] | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href", "").startswith("/") and "logout" not in a["href"]:
            self._pending = ("link", f'a[href="{a["href"]}"]')
            self._grab = tag
            self._buf = []
        elif tag == "button" and "print" not in (a.get("onclick") or ""):
            # Prefer an id; then the button's own type; then a distinguishing
            # class. Assuming type="submit" is wrong -- most templates rely on
            # the implicit submit type -- and would emit a selector that matches
            # nothing (a dead step the moment it is drafted).
            if a.get("id"):
                sel = f'#{a["id"]}'
            elif a.get("type"):
                sel = f'button[type="{a["type"]}"]'
            elif a.get("class"):
                first = a["class"].split()[0]
                sel = f"button.{first}"
            else:
                sel = "button"
            self._pending = ("button", sel)
            self._grab = tag
            self._buf = []
        elif tag == "input" and a.get("type") not in ("hidden", "csrf", "submit"):
            name = a.get("name") or a.get("id")
            if name and name != "_csrf":
                self.found.append(("input", f'input[name="{name}"]', name.replace("_", " ")))
        elif tag == "select":
            name = a.get("name") or a.get("id")
            if name:
                self.found.append(("select", f'select[name="{name}"]', name.replace("_", " ")))

    def handle_data(self, data):
        if self._grab:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._grab == tag and self._pending:
            label = re.sub(r"\s+", " ", "".join(self._buf)).strip()[:60]
            if label:
                self.found.append((self._pending[0], self._pending[1], label))
            self._pending = None
            self._grab = None


def scenario_files() -> dict[str, dict]:
    """Load every scenario keyed by pageId. out: {pageId: doc}"""
    out = {}
    if not os.path.isdir(SCEN):
        return out
    for n in os.listdir(SCEN):
        if n.endswith(".json") and n != "index.json":
            with open(os.path.join(SCEN, n), encoding="utf-8") as f:
                out[n[:-5]] = json.load(f)
    return out


def feature_endpoints(app) -> dict[str, str]:
    """User-facing GET pages that deserve a tutorial. out: {endpoint: rule}"""
    feats = {}
    for r in app.url_map.iter_rules():
        ep, rule = r.endpoint, str(r)
        if "GET" not in (r.methods or set()):
            continue
        if rule.startswith(("/api/", "/static/", "/admin/ops")):
            continue
        if ep in SKIP_EXACT or rule.endswith(SKIP_RULE_SUFFIX):
            continue
        if rule.startswith("/admin/api"):
            continue
        # "Administration" is ONE module in the tutorial catalogue (spec S13), not
        # sixty screens. The admin pages that carry a tutorial are curated.
        if ep.startswith("admin") and ep not in ADMIN_FEATURES:
            continue
        if any(ep.startswith(p) for p in SKIP_PREFIX):
            continue
        if any(s in ep for s in SKIP_SUBSTR):
            continue
        feats[ep] = rule
    return feats


def render(client, rule: str, sample: dict[str, str]) -> str | None:
    """Render a page, substituting sample ids for path params. out: html or None"""
    path = rule
    for m in re.findall(r"<[^>]+>", rule):
        name = m.strip("<>").split(":")[-1]
        val = sample.get(name)
        if not val:
            return None
        path = path.replace(m, val)
    try:
        r = client.get(path)
    except Exception:
        return None
    return r.data.decode("utf-8", "replace") if r.status_code == 200 else None


def dead_selectors(doc: dict, html: str) -> list[str]:
    """Which of a scenario's ENTRY-SCREEN selectors no longer appear in the page?

    A multi-screen tour's later steps target controls on pages we have not
    rendered, so only the steps up to (and including) the first `navigate` step
    can be validated here. Checking past that point would flag every downstream
    control as dead.

    Deliberately coarse: we probe for the *anchor token* of each selector (id,
    class, tag) rather than running a full CSS engine. That catches the real
    failure -- a control renamed or removed -- without flagging every valid but
    compound selector.
    out: list of selectors judged dead
    """
    dead = []
    for s in doc.get("steps", []):
        sel = (s.get("targetSelector") or "").strip()
        if s.get("dynamic"):
            sel = ""                   # injected by client JS; not in server HTML
        if sel and not any(_token_present(alt.strip(), html) for alt in sel.split(",")):
            dead.append(sel)
        if s.get("action") == "navigate":
            break                      # everything after this lives on another screen
    return dead


def _token_present(sel: str, html: str) -> bool:
    """Cheap presence probe for one CSS alternative. out: bool"""
    if not sel:
        return False
    m = re.match(r"#([\w-]+)", sel)
    if m:
        return f'id="{m.group(1)}"' in html
    m = re.match(r"\.([\w-]+)", sel)
    if m:
        return m.group(1) in html
    m = re.match(r"(\w+)\[([\w-]+)([~^$*]?=)\"?([^\]\"]*)\"?\]", sel)
    if m:
        tag, attr, _, val = m.groups()
        return f"<{tag}" in html and (val in html if val else attr in html)
    m = re.match(r"^(\w+)$", sel)
    if m:
        return f"<{m.group(1)}" in html
    return True          # exotic selector: don't guess, don't fail the build


def draft_for(endpoint: str, rule: str, html: str) -> dict:
    """Generate a DRAFT scenario by scanning a page's controls. out: doc"""
    p = Controls()
    p.feed(html)
    seen, steps = set(), []
    for kind, sel, label in p.found:
        if sel in seen:
            continue
        seen.add(sel)
        if kind == "input":
            action, voice = "typeText", f"Enter the {label}."
        elif kind == "select":
            action, voice = "moveCursor", f"Choose the {label}."
        elif kind == "button":
            action, voice = "moveCursor", f"Then use {label}."
        else:
            action, voice = "moveCursor", f"{label} takes you to the next screen."
        steps.append({
            "stepNumber": len(steps) + 1,
            "title": label.title()[:40] or kind.title(),
            "description": f"TODO: describe what {label!r} does.",
            "voiceScript": voice,
            "captionText": voice,
            "targetSelector": sel,
            "action": action,
            "duration": 700,
            "delayBefore": 120,
            "screen": endpoint,
            "fallbackMessage": f"{label}: not visible on this screen yet.",
            **({"typeText": "example"} if kind == "input" else {}),
        })
        if len(steps) >= 8:
            break
    return {
        "tutorialId": f"tut-{endpoint}",
        "pageId": endpoint,
        "title": endpoint.replace("_", " ").title(),
        "module": "TODO",
        "description": f"TODO: what does {rule} do for the user?",
        "version": 1,
        "language": "en-US",
        "draft": True,
        "screens": [endpoint],
        "estimatedDuration": len(steps) * 2,
        "steps": steps,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="fail on missing/dead/orphaned")
    ap.add_argument("--write", action="store_true", help="write draft scenarios")
    ap.add_argument("--pid", default="65", help="sample project id for path params")
    args = ap.parse_args()

    import web_app
    app = web_app.app
    app.config["TESTING"] = True
    sample = {"pid": args.pid, "id": args.pid, "slug": "quick"}

    # The Enterprise Programme module is registered in wsgi.py, not web_app.py (web_app.py is
    # CRLF+mojibake and must never be edited), so `web_app.app` is missing ~40 live routes --
    # and a gate cannot report a page it cannot SEE. That is how an entire shipped module sat
    # with no tutorial and a backlog of zero.
    #
    # Registered onto a THROWAWAY app and merged, not onto web_app.app: registering installs
    # a context_processor, and Flask forbids setup methods once an app has served a request.
    # Not by importing wsgi either -- that runs load_dotenv() and would aim this at the LIVE
    # database.
    # NOTE ON THE DEAD-SELECTOR PASS: merging the rules below makes the enterprise pages
    # VISIBLE to the MISSING check, but this script's renderer uses a test client with NO
    # SESSION, and every /enterprise page is login-gated -- so they 302, land in the
    # "could not be rendered" bucket, and their SELECTORS are never linted here. That is not
    # fixable from this script. Their selectors and nav anchors are verified instead by
    # tests/enterprise_programme/test_enterprise_tutorial_selectors.py, which renders them as
    # a real logged-in owner of a real organisation. It found two dead selectors this script
    # could never have seen.
    extra_rules = []
    try:
        from flask import Flask
        from enterprise_programme_routes import register_enterprise_programme
        _probe = Flask("_tutorial_endpoint_probe")
        register_enterprise_programme(
            _probe,
            get_db=web_app.get_db,
            login_required=web_app.login_required,
            csrf_protect=web_app.csrf_protect,
            current_user=web_app.current_user,
        )
        extra_rules = list(_probe.url_map.iter_rules())
    except Exception as e:  # pragma: no cover - mirrors wsgi.py's boot resilience
        print(f"[warn] enterprise routes not registered ({e}); their pages are unchecked")

    class _RuleView:
        """Just enough app for feature_endpoints(): a url_map that iterates rules."""

        def __init__(self, rules):
            self.url_map = SimpleNamespace(iter_rules=lambda: list(rules))

    merged = _RuleView(list(app.url_map.iter_rules()) + extra_rules)

    scen = scenario_files()
    feats = feature_endpoints(merged)
    endpoints = {r.endpoint for r in merged.url_map.iter_rules()}

    # A page is covered when it has its own scenario, OR when a multi-screen flow
    # already walks it (declared in that scenario's `covers`). Requiring a second
    # tutorial for a screen a flow visits would be duplication, not coverage.
    covered = set(scen)
    for doc in scen.values():
        covered.update(doc.get("covers") or [])

    # backlog.json is the committed ratchet shared with the test suite: a known
    # gap is reported but does not fail the build; an UNLISTED gap does.
    backlog_path = os.path.join(ROOT, "static", "tutorial", "backlog.json")
    try:
        with open(backlog_path, encoding="utf-8") as f:
            backlog = set(json.load(f)["endpoints"])
    except Exception:
        backlog = set()

    orphaned = sorted(set(scen) - endpoints)
    missing, dead, unrendered = [], {}, []

    with app.test_client() as cl:
        with cl.session_transaction() as s:
            s["user_id"] = 1
        for ep, rule in sorted(feats.items()):
            html = render(cl, rule, sample)
            if html is None:
                # We could not render it (unusual path param, or it needs data),
                # so we cannot lint its selectors -- but coverage is still
                # enforceable. A page that is neither covered nor in the backlog
                # must NOT slip through just because we could not render it.
                unrendered.append(ep)
                if ep not in covered and ep not in backlog:
                    missing.append((ep, rule, ""))
                continue
            if ep not in covered:
                missing.append((ep, rule, html))
                continue
            if ep not in scen:
                continue                 # walked by a flow; nothing of its own to lint
            bad = dead_selectors(scen[ep], html)
            if bad:
                dead[ep] = bad

    print(f"feature pages: {len(feats)}   with tutorial: {len(set(feats) & set(scen))}"
          f"   scenarios: {len(scen)}")
    if unrendered:
        print(f"\n[skipped] {len(unrendered)} page(s) could not be rendered "
              f"(need params/permissions): {', '.join(unrendered[:8])}"
          + ("…" if len(unrendered) > 8 else ""))
    if orphaned:
        print(f"\nORPHANED ({len(orphaned)}): scenario has no such endpoint")
        for e in orphaned:
            print(f"  - {e}")
    if dead:
        print(f"\nDEAD SELECTORS ({len(dead)} page(s)): the page changed under the tutorial")
        for e, sels in dead.items():
            for s in sels:
                print(f"  - {e}: {s}")
    if missing:
        print(f"\nMISSING ({len(missing)}): feature page with no tutorial")
        for ep, rule, _ in missing:
            print(f"  - {ep:34} {rule}")

    if args.write and missing:
        os.makedirs(SCEN, exist_ok=True)
        for ep, rule, html in missing:
            doc = draft_for(ep, rule, html)
            if not doc["steps"]:
                print(f"  skipped {ep}: no interactive controls found to demonstrate")
                continue
            with open(os.path.join(SCEN, f"{ep}.json"), "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False)
            print(f"  drafted {ep}.json ({len(doc['steps'])} steps) — edit the narration")

    known = [ep for ep, _, _ in missing if ep in backlog]
    if known:
        print(f"\n[backlog] {len(known)} known gap(s) from "
              f"static/tutorial/backlog.json (reported, not fatal)")
    new_missing = [m for m in missing if m[0] not in backlog]
    problems = len(orphaned) + len(dead) + (0 if args.write else len(new_missing))
    if args.check and problems:
        print(f"\nFAIL: {problems} tutorial problem(s). "
              f"Run with --write to draft missing ones, then edit the narration.")
        return 1
    print("\nOK" if not problems else "\ndrafts written; re-run --check after editing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
