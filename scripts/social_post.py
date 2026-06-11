"""Cross-channel social poster for SolarPro beta launch.

Backend: Buffer's GraphQL API (free plan: 3 channels, 10 queued, 1 API key).
Posts a single image+caption to FB + IG + LinkedIn channels in one run.

Env vars required:
  BUFFER_API_KEY                — from publish.buffer.com/settings/api
  BUFFER_CHANNEL_FB             — channel id (set after discover_channels)
  BUFFER_CHANNEL_IG             — channel id
  BUFFER_CHANNEL_LI             — channel id
  POST_IMAGE_URL_SQUARE         — public HTTPS URL of the 1080x1080 flyer
  POST_IMAGE_URL_WIDE           — public HTTPS URL of the 1200x628 flyer
  POSTED_LOG                    — local path for the posted-id idempotency log
                                 (default: ./logs/social_posted.json)

CLI:
  python scripts/social_post.py discover-channels
        — list connected channels + their ids
  python scripts/social_post.py post
        — schedule a post on all three channels for ~5 min from now
  python scripts/social_post.py post --dry-run
        — print the GraphQL mutation without sending
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = Path(os.environ.get("POSTED_LOG", ROOT / "logs" / "social_posted.json"))

BUFFER_GQL = "https://api.buffer.com"

# Captions live next to the flyer in docs/Social_Posts_v1.md so this script
# stays declarative; edit the .md to change copy.
FB_CAPTION = (
    "SolarPro Global beta is live 🌞\n\n"
    "Find live solar tenders and RFPs across 22+ countries — then auto-generate the "
    "engineering design, BOQ, and a bankable proposal in 30 minutes.\n\n"
    "Built for installers, EPCs, and consultants who want to win more contracts "
    "and stop losing weekends to spreadsheets.\n\n"
    "14 days free. No card needed.\n\n"
    "→ https://solarpro.aiappinvent.com?utm_source=facebook&utm_medium=social&utm_campaign=beta_launch\n\n"
    "#SolarPV #RenewableEnergy #SolarTenders #EPC #OffGrid #Ghana #Africa #PVDesign"
)

IG_CAPTION = (
    "SolarPro Global beta is live 🌞⚡\n\n"
    "Find live solar RFPs across 22+ countries → auto-design the system → "
    "bankable proposal in 30 minutes.\n\n"
    "Built for installers, EPCs, and consultants who want to win contracts faster.\n\n"
    "14 days free. No card. Link in bio. ☀️"
)

LI_CAPTION = (
    "SolarPro Global is now in public beta.\n\n"
    "The problem: solar installers and EPCs spend more time hunting tenders and "
    "rebuilding the same engineering math than they spend winning contracts.\n\n"
    "What we built:\n"
    "• A tender + RFP radar that watches 22+ countries for live solar opportunities\n"
    "• Auto PV / battery / inverter / cable sizing — BS 7671 & IEC 60364 compliant\n"
    "• A Bill of Quantities + financial proposal generator that produces bankable docs in 30 minutes\n\n"
    "Already used by installers across Ghana, Nigeria, Kenya, the UK, and the US "
    "in our 35-invitee preview round.\n\n"
    "14-day free trial. No credit card.\n\n"
    "We're looking for 50 more installers, EPCs, and consultants to put it through "
    "hell during beta. If you sell solar systems for a living, this is for you.\n\n"
    "→ https://solarpro.aiappinvent.com?utm_source=linkedin&utm_medium=social&utm_campaign=beta_launch\n\n"
    "#SolarEnergy #RenewableEnergy #SolarPV #EPC #SolarTenders #PVDesign #Africa #CleanTech #BetaLaunch"
)


def _gql(query: str, variables: dict | None = None) -> dict:
    """POST a Buffer GraphQL query. Returns parsed JSON or raises."""
    api_key = os.environ.get("BUFFER_API_KEY")
    if not api_key:
        sys.exit("error: BUFFER_API_KEY env var not set")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        BUFFER_GQL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"buffer http {e.code}: {e.read().decode(errors='replace')[:400]}")
    if "errors" in data:
        sys.exit(f"buffer errors: {json.dumps(data['errors'], indent=2)}")
    return data["data"]


def discover_channels() -> None:
    """Print connected channels + ids so you can populate the env vars."""
    orgs = _gql("query { account { organizations { id name } } }")
    print(json.dumps(orgs, indent=2))
    if not orgs.get("account", {}).get("organizations"):
        sys.exit("no organizations on this Buffer account — connect channels first")
    for org in orgs["account"]["organizations"]:
        print(f"\n=== org: {org['name']} ({org['id']}) ===")
        ch = _gql(
            "query($orgId: ID!) { channels(input: {organizationId: $orgId}) "
            "{ id name service } }",
            {"orgId": org["id"]},
        )
        for c in ch["channels"]:
            print(f"  {c['service']:10s}  {c['name']:30s}  id={c['id']}")


def _load_log() -> dict:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return {}


def _save_log(d: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(d, indent=2))


def _post_one(channel_id: str, text: str, image_url: str, due_at: str) -> dict:
    mutation = """
mutation Create($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}
""".strip()
    payload = {
        "input": {
            "text": text,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": "customScheduled",
            "dueAt": due_at,
            "assets": [{"image": {"url": image_url}}],
        }
    }
    return _gql(mutation, payload)


def post(dry_run: bool = False) -> None:
    fb_id = os.environ.get("BUFFER_CHANNEL_FB")
    ig_id = os.environ.get("BUFFER_CHANNEL_IG")
    li_id = os.environ.get("BUFFER_CHANNEL_LI")
    sq_url = os.environ.get("POST_IMAGE_URL_SQUARE")
    wide_url = os.environ.get("POST_IMAGE_URL_WIDE")
    missing = [k for k, v in {
        "BUFFER_CHANNEL_FB": fb_id, "BUFFER_CHANNEL_IG": ig_id,
        "BUFFER_CHANNEL_LI": li_id,
        "POST_IMAGE_URL_SQUARE": sq_url, "POST_IMAGE_URL_WIDE": wide_url,
    }.items() if not v]
    if missing:
        sys.exit(f"missing env: {', '.join(missing)}")

    due_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    jobs = [
        ("facebook",  fb_id, FB_CAPTION, sq_url),
        ("instagram", ig_id, IG_CAPTION, sq_url),
        ("linkedin",  li_id, LI_CAPTION, wide_url),
    ]
    log = _load_log()
    log_key = f"beta_launch_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')}"
    if log_key in log:
        sys.exit(f"already posted today (key={log_key}); delete {LOG_PATH} to repost")
    log[log_key] = {"started": dt.datetime.now(dt.timezone.utc).isoformat(), "results": {}}

    for service, ch_id, caption, image_url in jobs:
        print(f"\n--- {service} (channel {ch_id}) ---")
        if dry_run:
            print(f"DRY-RUN dueAt={due_at}")
            print(f"caption ({len(caption)} chars):\n{caption[:200]}{'...' if len(caption) > 200 else ''}")
            print(f"image: {image_url}")
            continue
        result = _post_one(ch_id, caption, image_url, due_at)
        log[log_key]["results"][service] = result
        print(json.dumps(result, indent=2))

    if not dry_run:
        log[log_key]["completed"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _save_log(log)
        print(f"\n✓ logged to {LOG_PATH}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover-channels")
    post_p = sub.add_parser("post")
    post_p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.cmd == "discover-channels":
        discover_channels()
    elif args.cmd == "post":
        post(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
