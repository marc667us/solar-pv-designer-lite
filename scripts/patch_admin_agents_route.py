"""
Surface the 5 autonomous-monitor crons inside the in-app admin UI.

Adds a new @admin_required route /admin/agents that reads the state
JSON files from data/ and renders templates/admin_agents.html with one
card per agent. Each card links to the matching GH Actions workflow
page so the operator can trigger on demand without leaving the admin.

Byte-patch (web_app.py CRLF + mojibake constraint per CLAUDE.md).
Anchor is the closing of the existing /admin/agent route family — we
insert right before /admin/feedback.
"""
from __future__ import annotations
import os, sys

ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web_app.py")

# Same anchor the JSON-endpoints patch used. Insert sits before it.
ANCHOR = (
    b'# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 Tier 2-4 agent-triage JSON API'
)

NEW_ROUTE = (
    b'# \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80 Autonomous Agents dashboard \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\r\n'
    b'# In-app read-out for the 5 cron workflows (beta-monitor, agent-triage,\r\n'
    b'# synthetic-health, email-delivery-check, daily-digest). All execution\r\n'
    b'# happens in GH Actions; this page is just the admin-facing surface so\r\n'
    b'# the operator does not need to leave the app to know what they did.\r\n'
    b'\r\n'
    b'_GH_REPO = "marc667us/solar-pv-designer-lite"\r\n'
    b'\r\n'
    b'_AGENT_SPECS = [\r\n'
    b'    {\r\n'
    b'        "key":         "beta-monitor",\r\n'
    b'        "name":        "Beta Monitor",\r\n'
    b'        "cadence":     "every 30 min",\r\n'
    b'        "icon":        "bi-broadcast-pin",\r\n'
    b'        "color":       "#22c55e",\r\n'
    b'        "purpose":     "Polls /admin/feedback + /admin/tickets + /admin/beta plus three security probes; alerts on any new aggregate-count change.",\r\n'
    b'        "state_file":  "data/response_state.json",\r\n'
    b'        "workflow":    "beta-monitor.yml",\r\n'
    b'    },\r\n'
    b'    {\r\n'
    b'        "key":         "agent-triage",\r\n'
    b'        "name":        "Agent Triage",\r\n'
    b'        "cadence":     "hourly HH:23",\r\n'
    b'        "icon":        "bi-robot",\r\n'
    b'        "color":       "#fbbf24",\r\n'
    b'        "purpose":     "Per-item: LLM classify -> Brevo ACK -> GH issue create if severity high+. Tier 2-4 of the autonomous stack.",\r\n'
    b'        "state_file":  "data/agent_state.json",\r\n'
    b'        "workflow":    "agent-triage.yml",\r\n'
    b'    },\r\n'
    b'    {\r\n'
    b'        "key":         "synthetic-health",\r\n'
    b'        "name":        "Synthetic Health",\r\n'
    b'        "cadence":     "hourly HH:17",\r\n'
    b'        "icon":        "bi-heart-pulse",\r\n'
    b'        "color":       "#0ea5e9",\r\n'
    b'        "purpose":     "End-to-end critical-user-path walk: landing -> admin login -> create project -> design engine -> proposal PDF. Red on any step failure.",\r\n'
    b'        "state_file":  None,\r\n'
    b'        "workflow":    "synthetic-health.yml",\r\n'
    b'    },\r\n'
    b'    {\r\n'
    b'        "key":         "email-delivery-check",\r\n'
    b'        "name":        "Email Delivery Check",\r\n'
    b'        "cadence":     "every 2h HH:37",\r\n'
    b'        "icon":        "bi-envelope-check",\r\n'
    b'        "color":       "#a855f7",\r\n'
    b'        "purpose":     "Polls Brevo events API for bounces / blocks / spam complaints / deferrals against the SolarPro sender domain.",\r\n'
    b'        "state_file":  "data/email_delivery_state.json",\r\n'
    b'        "workflow":    "email-delivery-check.yml",\r\n'
    b'    },\r\n'
    b'    {\r\n'
    b'        "key":         "daily-digest",\r\n'
    b'        "name":        "Daily Digest",\r\n'
    b'        "cadence":     "09:00 UTC daily",\r\n'
    b'        "icon":        "bi-calendar-week",\r\n'
    b'        "color":       "#f43f5e",\r\n'
    b'        "purpose":     "One-shot owner summary of last-24h response volumes, rating averages, security pulse, and synthetic-health conclusions.",\r\n'
    b'        "state_file":  None,\r\n'
    b'        "workflow":    "daily-digest.yml",\r\n'
    b'    },\r\n'
    b']\r\n'
    b'\r\n'
    b'\r\n'
    b'def _agent_state_rows(state_dict):\r\n'
    b'    """Flatten the state dict into [(label, value)] for table render.\r\n'
    b'    Skips the long human-prose `note` and the bulky alerted_event_keys\r\n'
    b'    list (which is just dedup history, not operator-visible signal)."""\r\n'
    b'    if not isinstance(state_dict, dict):\r\n'
    b'        return []\r\n'
    b'    skip = {"note", "alerted_event_keys", "actions_this_run",\r\n'
    b'            "alerts_this_poll"}\r\n'
    b'    rows = []\r\n'
    b'    for k, v in state_dict.items():\r\n'
    b'        if k in skip: continue\r\n'
    b'        if isinstance(v, dict):\r\n'
    b'            # Flatten one level so security_audit + totals etc. show inline\r\n'
    b'            small = ", ".join(f"{k2}={v2}" for k2, v2 in v.items()\r\n'
    b'                                  if not isinstance(v2, (dict, list)))[:200]\r\n'
    b'            rows.append((k, small or "(nested)"))\r\n'
    b'        elif isinstance(v, list):\r\n'
    b'            rows.append((k, f"list ({len(v)} entries)"))\r\n'
    b'        else:\r\n'
    b'            rows.append((k, str(v)[:200]))\r\n'
    b'    return rows\r\n'
    b'\r\n'
    b'\r\n'
    b'@app.route("/admin/agents")\r\n'
    b'@admin_required\r\n'
    b'def admin_agents():\r\n'
    b'    """Read each cron\'s state file from disk and render the dashboard."""\r\n'
    b'    import json as _json\r\n'
    b'    root = os.path.dirname(os.path.abspath(__file__))\r\n'
    b'    agents = []\r\n'
    b'    for spec in _AGENT_SPECS:\r\n'
    b'        state = None\r\n'
    b'        if spec["state_file"]:\r\n'
    b'            sp = os.path.join(root, spec["state_file"])\r\n'
    b'            if os.path.exists(sp):\r\n'
    b'                try:\r\n'
    b'                    state = _json.load(open(sp, "r", encoding="utf-8"))\r\n'
    b'                except Exception:\r\n'
    b'                    state = None\r\n'
    b'        agents.append({\r\n'
    b'            "key":          spec["key"],\r\n'
    b'            "name":         spec["name"],\r\n'
    b'            "cadence":      spec["cadence"],\r\n'
    b'            "icon":         spec["icon"],\r\n'
    b'            "color":        spec["color"],\r\n'
    b'            "purpose":      spec["purpose"],\r\n'
    b'            "state":        state,\r\n'
    b'            "state_rows":   _agent_state_rows(state) if state else [],\r\n'
    b'            "runs_url":\r\n'
    b'                f"https://github.com/{_GH_REPO}/actions/workflows/"\r\n'
    b'                f"{spec[\'workflow\']}",\r\n'
    b'            "dispatch_url":\r\n'
    b'                f"https://github.com/{_GH_REPO}/actions/workflows/"\r\n'
    b'                f"{spec[\'workflow\']}",\r\n'
    b'            "file_url":\r\n'
    b'                f"https://github.com/{_GH_REPO}/blob/master/.github/"\r\n'
    b'                f"workflows/{spec[\'workflow\']}",\r\n'
    b'        })\r\n'
    b'    return render_template("admin_agents.html", agents=agents)\r\n'
    b'\r\n'
    b'\r\n'
)


def main() -> int:
    data = open(TARGET, "rb").read()
    n = data.count(ANCHOR)
    if n != 1:
        print(f"ERROR: anchor matched {n}x (expected 1)", file=sys.stderr)
        return 2
    if b'@app.route("/admin/agents")' in data:
        print("WARN: /admin/agents already present - bailing idempotently")
        return 0
    data = data.replace(ANCHOR, NEW_ROUTE + ANCHOR, 1)
    open(TARGET, "wb").write(data)
    print(f"OK wrote {len(data):,} bytes to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
