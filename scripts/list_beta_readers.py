"""List the beta invitees who opened the launch email.

Queries Brevo /v3/smtp/statistics/events for `event=opened` over a
configurable window (default 14 days), cross-references against the
invitee JSON files in data/beta_outreach/, and writes the result to
data/beta_outreach/readers_to_follow_up.json.

Output schema:
  {
    "generated_at": "<UTC ISO8601>",
    "window_days": <int>,
    "total_opened_events": <int>,
    "unique_openers_total": <int>,
    "unique_openers_among_invitees": <int>,
    "openers": [
      {
        "email": "<addr>",
        "first_open": "<UTC ISO8601>",
        "open_count": <int>,
        "in_invitee_list": true/false,
        "invitee_name": "<from invitee JSON if matched>",
        "invitee_country": "<from invitee JSON if matched>"
      }, ...
    ]
  }

Env:
  BREVO_API_KEY  required
  READER_WINDOW_DAYS  default 14
  READER_OUTPUT_PATH  default data/beta_outreach/readers_to_follow_up.json
"""
from __future__ import annotations
import datetime as dt, json, os, sys, urllib.parse, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVITEE_DIR = ROOT / "data" / "beta_outreach"

BREVO = os.environ.get("BREVO_API_KEY")
if not BREVO:
    sys.exit("BREVO_API_KEY env var required")

WINDOW = int(os.environ.get("READER_WINDOW_DAYS", "14"))
OUT_PATH = Path(os.environ.get(
    "READER_OUTPUT_PATH",
    INVITEE_DIR / "readers_to_follow_up.json"
))


def load_invitees() -> dict[str, dict]:
    """Build {email: {name, country}} from per-country invitee JSON files."""
    invitees: dict[str, dict] = {}
    for p in sorted(INVITEE_DIR.glob("*_beta_invitees.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"  warn: skipping {p.name}: {e}", file=sys.stderr)
            continue
        country = doc.get("country", p.stem)
        for e in doc.get("entities", []):
            email = (e.get("email") or "").strip().lower()
            if email:
                invitees[email] = {"name": e.get("name", "?"), "country": country}
    # owner-preview list has a different shape; try to fold it in too
    op = INVITEE_DIR / "owner_preview_beta_invitees.json"
    if op.exists():
        try:
            doc = json.loads(op.read_text(encoding="utf-8"))
            for e in (doc if isinstance(doc, list) else doc.get("entities", [])):
                email = (e.get("email") or "").strip().lower()
                if email:
                    invitees[email] = {
                        "name": e.get("name", e.get("label", "?")),
                        "country": "Owner Preview",
                    }
        except Exception as e:
            print(f"  warn: skipping owner_preview: {e}", file=sys.stderr)
    return invitees


def fetch_opens(window_days: int) -> list[dict]:
    """Paginate Brevo events for the window. Filter to opened-type only."""
    events: list[dict] = []
    offset = 0
    batch = 100
    while True:
        params = {"limit": batch, "offset": offset, "days": window_days,
                  "sort": "desc", "event": "opened"}
        url = ("https://api.brevo.com/v3/smtp/statistics/events?"
               + urllib.parse.urlencode(params))
        req = urllib.request.Request(
            url,
            headers={"api-key": BREVO, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            sys.exit(f"Brevo events HTTP {e.code}: {body[:300]}")
        except Exception as e:
            sys.exit(f"Brevo events fetch failed: {e}")
        batch_events = data.get("events", [])
        events.extend(batch_events)
        if len(batch_events) < batch or len(events) >= 1000:
            break
        offset += batch
    return events


def main() -> int:
    print(f"Window: {WINDOW} days. Output: {OUT_PATH}")
    invitees = load_invitees()
    print(f"  loaded {len(invitees)} invitee emails from {INVITEE_DIR.name}/")

    events = fetch_opens(WINDOW)
    print(f"  pulled {len(events)} 'opened' events from Brevo")

    # Aggregate per email — first open time, count.
    agg: dict[str, dict] = {}
    for ev in events:
        email = (ev.get("email") or "").strip().lower()
        if not email:
            continue
        ts = ev.get("date") or ev.get("ts") or ev.get("eventTime") or ""
        rec = agg.setdefault(email, {"email": email, "first_open": ts,
                                     "open_count": 0})
        rec["open_count"] += 1
        # events come desc — so the last one we see is earliest
        if ts and ts < rec["first_open"]:
            rec["first_open"] = ts

    # Annotate with invitee match
    for rec in agg.values():
        match = invitees.get(rec["email"])
        rec["in_invitee_list"] = bool(match)
        if match:
            rec["invitee_name"] = match["name"]
            rec["invitee_country"] = match["country"]

    # Sort: invitees first, then by open_count desc
    ordered = sorted(
        agg.values(),
        key=lambda r: (not r["in_invitee_list"], -r["open_count"], r["email"]),
    )

    out = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_days": WINDOW,
        "total_opened_events": len(events),
        "unique_openers_total": len(agg),
        "unique_openers_among_invitees": sum(
            1 for r in agg.values() if r["in_invitee_list"]
        ),
        "openers": ordered,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"  wrote {OUT_PATH}")
    print(f"  unique openers: total={out['unique_openers_total']} "
          f"among_invitees={out['unique_openers_among_invitees']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
