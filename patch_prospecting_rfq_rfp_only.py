# patch_prospecting_rfq_rfp_only.py
# Owner directive 2026-06-21: "as for the prospecting agent it has never
# work well, all we want is that its out put is e request to quote for
# solare systems or requets for proposal, any othe other must be submitted
# please fix".
#
# Translation: the prospecting agent must ONLY output:
#   - RFQ (Request for Quote) for solar systems
#   - RFP (Request for Proposal) for solar systems
# Anything else (news, grants, EOI without a deliverable, completed
# projects, country overviews, non-solar work) must be dropped.
#
# Two changes to web_app.py:
#
# 1. The prompt's `type` enumeration goes from
#       "RFP / Tender / EOI / ITB / Contract Notice / Grant / Installation Job"
#    to:
#       "RFQ (Request for Quote) for solar OR RFP (Request for Proposal) for solar"
#    plus explicit SKIP rules so the LLM filters server-side.
#
# 2. Post-filter on `data["prospects"]` AFTER JSON parse: drop anything
#    whose `type` isn't RFQ or RFP, AND drop anything where neither the
#    pitch nor work_description nor project_category mentions solar / PV /
#    photovoltaic / off-grid / on-grid / hybrid / mini-grid / inverter /
#    battery (broad keyword set so legitimate solar work isn't lost).
#
# Re-runnable; bails if either anchor already includes the rewritten text.

from pathlib import Path

TARGET = Path(__file__).with_name("web_app.py")
data = TARGET.read_bytes()

# ---- 1. Prompt rewrite ----------------------------------------------------

OLD_PROMPT_TYPE = b'"type": "RFP / Tender / EOI / ITB / Contract Notice / Grant / Installation Job",\r\n'
NEW_PROMPT_TYPE = (
    b'"type": "MUST be exactly \\"RFQ\\" (Request for Quote) or \\"RFP\\" '
    b'(Request for Proposal). NOTHING ELSE -- do NOT emit Tender, EOI, ITB, '
    b'Grant, Contract Notice, Installation Job, news, project completion, '
    b'or any other type. If the result is not asking for a quote or a '
    b'proposal for a SOLAR system, OMIT IT entirely.",\r\n'
)
if OLD_PROMPT_TYPE in data:
    data = data.replace(OLD_PROMPT_TYPE, NEW_PROMPT_TYPE)
    print("OK  prompt type enum constrained to RFQ/RFP only")
elif b'MUST be exactly \\"RFQ\\"' in data:
    print("Already patched (prompt type)")
else:
    print("WARN  prompt-type anchor not found")

# Inject the explicit SKIP rule at the head of the LLM instructions.
OLD_INSTRUCTIONS_HEAD = (
    b'INSTRUCTIONS \xe2\x80\x94 read each result\'s CONTENT carefully before deciding:\r\n'
    b'1. READ the full content provided. If it does not clearly confirm an open, active procurement for solar works IN {loc_label}, SKIP IT entirely.\r\n'
)
NEW_INSTRUCTIONS_HEAD = (
    b'INSTRUCTIONS \xe2\x80\x94 read each result\'s CONTENT carefully before deciding:\r\n'
    b'0. **HARD RULE**: only emit results where the buyer is asking the market for a\r\n'
    b'   QUOTE (RFQ) or PROPOSAL (RFP) for a SOLAR PV / PHOTOVOLTAIC / HYBRID / OFF-GRID /\r\n'
    b'   MINI-GRID / ROOFTOP / GROUND-MOUNT / BATTERY / INVERTER system or solar-related\r\n'
    b'   EPC works. Anything else MUST be omitted -- including: news articles, project\r\n'
    b'   completion announcements, grants without a deliverable, EOIs that ask for\r\n'
    b'   nothing, country overviews, generic tender directories. If you are unsure, OMIT.\r\n'
    b'1. READ the full content provided. If it does not clearly confirm an open, active procurement for solar works IN {loc_label}, SKIP IT entirely.\r\n'
)
if OLD_INSTRUCTIONS_HEAD in data:
    data = data.replace(OLD_INSTRUCTIONS_HEAD, NEW_INSTRUCTIONS_HEAD)
    print("OK  instructions head now starts with the RFQ/RFP HARD RULE")
elif b"**HARD RULE**" in data and b"QUOTE (RFQ) or PROPOSAL (RFP)" in data:
    print("Already patched (instructions head)")
else:
    print("WARN  instructions-head anchor not found")

# ---- 2. Post-filter on parsed JSON ---------------------------------------

# Anchor: the line right after `data = json.loads(raw)`. We inject a
# small filter block before the AI_BUDGET_LEDGER_MARKER_AGENT comment.

OLD_AFTER_PARSE = (
    b'            data = json.loads(raw)\r\n'
    b'            # AI_BUDGET_LEDGER_MARKER_AGENT - record one ledger row per\r\n'
)
NEW_AFTER_PARSE = (
    b'            data = json.loads(raw)\r\n'
    b'            # Owner directive 2026-06-21: prospecting agent MUST output only\r\n'
    b'            # RFQ / RFP for solar systems. Drop anything else even if the LLM\r\n'
    b'            # let it through.\r\n'
    b'            try:\r\n'
    b'                _SOLAR_KEYS = ("solar", "photovoltaic", " pv ", "pv ", " pv,", "pv,",\r\n'
    b'                               "off-grid", "off grid", "on-grid", "on grid",\r\n'
    b'                               "hybrid", "mini-grid", "mini grid",\r\n'
    b'                               "rooftop", "ground-mount", "ground mount",\r\n'
    b'                               "inverter", "battery", "epc")\r\n'
    b'                _OK_TYPES = {"rfq", "rfp"}\r\n'
    b'                _kept = []\r\n'
    b'                _dropped_type = 0\r\n'
    b'                _dropped_topic = 0\r\n'
    b'                for _p in (data.get("prospects") or []):\r\n'
    b'                    _t = (str(_p.get("type", "")).strip().lower())\r\n'
    b'                    # Normalise common LLM variants -> rfq / rfp.\r\n'
    b'                    if _t.startswith("rfq") or "request for quot" in _t:\r\n'
    b'                        _t = "rfq"\r\n'
    b'                    elif _t.startswith("rfp") or "request for propos" in _t:\r\n'
    b'                        _t = "rfp"\r\n'
    b'                    if _t not in _OK_TYPES:\r\n'
    b'                        _dropped_type += 1\r\n'
    b'                        continue\r\n'
    b'                    _blob = " ".join([\r\n'
    b'                        str(_p.get("pitch", "")), str(_p.get("work_description", "")),\r\n'
    b'                        str(_p.get("project_category", "")), str(_p.get("tor", "")),\r\n'
    b'                        str(_p.get("company_name", "")), str(_p.get("source_title", "")),\r\n'
    b'                    ]).lower()\r\n'
    b'                    if not any(k in _blob for k in _SOLAR_KEYS):\r\n'
    b'                        _dropped_topic += 1\r\n'
    b'                        continue\r\n'
    b'                    _p["type"] = _t.upper()  # RFQ / RFP -- consistent UI label\r\n'
    b'                    _kept.append(_p)\r\n'
    b'                data["prospects"] = _kept\r\n'
    b'                data["_filter_dropped"] = {\r\n'
    b'                    "wrong_type": _dropped_type, "non_solar": _dropped_topic\r\n'
    b'                }\r\n'
    b'            except Exception as _filt_err:\r\n'
    b'                try: app.logger.warning("prospect filter failed: %s", _filt_err)\r\n'
    b'                except Exception: pass\r\n'
    b'            # AI_BUDGET_LEDGER_MARKER_AGENT - record one ledger row per\r\n'
)

if OLD_AFTER_PARSE in data:
    data = data.replace(OLD_AFTER_PARSE, NEW_AFTER_PARSE)
    print("OK  post-filter on prospects[] -- RFQ/RFP + solar keyword gate")
elif b'_dropped_type' in data and b'_dropped_topic' in data:
    print("Already patched (post-filter)")
else:
    print("WARN  post-parse anchor not found")

TARGET.write_bytes(data)
print("OK")
