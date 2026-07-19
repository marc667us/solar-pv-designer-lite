"""Backfill datasheet / literature URLs across the whole product catalogue.

OWNER, 2026-07-19: "ensure that the literature and data sheet on each product in the
marketplace is work" -> "fix the datasheets".

THE MEASURED PROBLEM: 37 of 553 products (6.7%) have a cached datasheet_url. The other ~516
have none, so opening their datasheet falls through to a Google search URL. For an ANONYMOUS
visitor that is the end of the road -- the on-demand crawl in
`_resolve_and_cache_doc_url` deliberately runs for signed-in users only (anti-abuse), so the
catalogue never self-heals from public traffic.

WHY A SCRIPT AND NOT THE EXISTING ADMIN BUTTON.
`POST /admin/agent/find-product-links` already does this, but:
  * it is capped at LIMIT = 20 per click, so clearing 516 products is 26 manual clicks;
  * it runs SYNCHRONOUSLY inside a web request, doing up to 20 live web searches -- the exact
    shape of the bug fixed this morning, where a long AI call outlived its gunicorn worker
    and was killed with no error page;
  * it needs an admin session + CSRF, so it cannot be driven from CI.

WHAT THIS DOES NOT DO: reimplement the finder. It imports `web_app` and calls the SAME
`_find_links_for` the app uses. A second copy of the search/scoring logic would drift from the
first -- which is precisely the failure mode that produced four separate faults on 2026-07-19
(a health check reading a variable nothing sets, a diagnostic carrying its own stale model
list, and so on). One implementation, called from two places.

DRY-RUN BY DEFAULT (workflow dry-run gate). Writes only with --apply.

  python scripts/backfill_product_doc_links.py --limit 50            # dry run
  python scripts/backfill_product_doc_links.py --limit 50 --apply    # writes
"""
import argparse
import os
import sys
import time

# Run from anywhere: this lives in scripts/, but web_app.py is at the repo root. Prepending
# rather than appending so a same-named module elsewhere on the path cannot shadow the app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25,
                    help="max products to process this run (batching keeps runs bounded)")
    ap.add_argument("--apply", action="store_true",
                    help="write results; without it nothing is written")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="seconds between products -- politeness to the search engine, and "
                         "the thing that stops a bulk run looking like scraping")
    ap.add_argument("--retry-checked", action="store_true",
                    help="also retry products already stamped links_checked_at (use after a "
                         "run that failed for transient reasons)")
    args = ap.parse_args()

    # Importing web_app gives us the PRODUCTION finder plus get_db, already wired to whatever
    # DATABASE_URL points at. Heavy, but correctness beats a lighter wrong copy.
    import web_app

    find = getattr(web_app, "_find_links_for", None)
    get_db = getattr(web_app, "get_db", None)
    if find is None or get_db is None:
        print("ERROR: web_app does not expose _find_links_for/get_db", file=sys.stderr)
        return 2

    # Products still missing EITHER link. links_checked_at is respected by default so repeat
    # runs move forward instead of re-searching the same failures for ever.
    where = "(COALESCE(literature_url,'')='' OR COALESCE(datasheet_url,'')='')"
    if not args.retry_checked:
        where += " AND links_checked_at IS NULL"

    with get_db() as c:
        total_missing = c.execute(
            f"SELECT COUNT(*) AS n FROM equipment_catalog WHERE {where}").fetchone()["n"]
        rows = [dict(r) for r in c.execute(
            f"SELECT id, name, brand, model FROM equipment_catalog WHERE {where} "
            f"ORDER BY id LIMIT ?", (args.limit,)).fetchall()]

    print(f"  products still missing a link : {total_missing}")
    print(f"  processing this run           : {len(rows)}")
    print(f"  mode                          : {'APPLY' if args.apply else 'DRY-RUN'}")
    print()

    found_ds = found_lit = failed = 0
    for i, r in enumerate(rows, 1):
        label = f"{(r.get('brand') or '')} {(r.get('model') or r.get('name') or '')}".strip()
        try:
            ds, lit = find(r.get("name") or "", r.get("brand") or "", r.get("model") or "")
            crawl_ok = True
        except Exception as e:
            ds, lit, crawl_ok = "", "", False
            failed += 1
            print(f"  [{i}/{len(rows)}] SEARCH FAILED  {label[:52]}  ({e})")

        if crawl_ok:
            if ds:
                found_ds += 1
            if lit:
                found_lit += 1
            mark = ("ds+lit" if (ds and lit) else "ds" if ds else "lit" if lit else "none")
            print(f"  [{i}/{len(rows)}] {mark:<7} {label[:52]}")

        # ONLY stamp links_checked_at when the search actually RAN. The admin route stamps it
        # unconditionally, so one transient network failure marks a product "checked" and it is
        # never retried -- a permanent gap caused by a temporary problem. A product that could
        # not be searched must stay eligible.
        if args.apply and crawl_ok:
            try:
                with get_db() as c:
                    c.execute(
                        "UPDATE equipment_catalog SET "
                        "literature_url = CASE WHEN COALESCE(literature_url,'')='' AND ? != '' "
                        "                      THEN ? ELSE literature_url END, "
                        "datasheet_url  = CASE WHEN COALESCE(datasheet_url,'')='' AND ? != '' "
                        "                      THEN ? ELSE datasheet_url END, "
                        "links_checked_at = CURRENT_TIMESTAMP WHERE id=?",
                        (lit, lit, ds, ds, r["id"]))
            except Exception as e:
                failed += 1
                print(f"      WRITE FAILED for id={r['id']}: {e}")

        if args.sleep and i < len(rows):
            time.sleep(args.sleep)

    print()
    print(f"  datasheets found : {found_ds}")
    print(f"  literature found : {found_lit}")
    print(f"  failures         : {failed}")
    if not args.apply:
        print("\n  DRY-RUN -- nothing was written. Re-run with --apply to persist.")
    else:
        with get_db() as c:
            n = c.execute(
                "SELECT COUNT(*) AS n FROM equipment_catalog "
                "WHERE COALESCE(datasheet_url,'')<>''").fetchone()["n"]
        print(f"\n  products WITH a datasheet_url now: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
