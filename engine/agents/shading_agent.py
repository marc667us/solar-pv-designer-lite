"""AI 3D Shading Simulation Agent — ADK LlmAgent with deterministic tools.

Per pvsolar1/CLAUDE.md §0.1: every agent in every app must be designed in
Google ADK. This module is the ADK-native shading agent. When the ADK
runtime is unavailable (e.g. on a Render free-tier instance that hasn't
installed `google-adk` yet), `run_shading_agent` falls back to a direct
OpenRouter call carrying the IDENTICAL system prompt and the IDENTICAL
tool outputs — the LLM never sees a different surface area, only the
runtime changes. The decision is logged in docs/IMPLEMENTATION_LOG.md.

The DETERMINISTIC ENGINE (engine.shading_engine) is authoritative for
every number in every output. The LLM:
  * narrates per-obstruction physics in plain language
  * proposes site-specific mitigation what-ifs
  * resolves ties when two SHADING_FACTORS buckets are within ±2 % loss
  * never invents a number; if asked for one, it MUST call a tool

This split keeps the system explainable, testable, and cheap (zero-cost
LLMs are noisy — gating numeric outputs through deterministic Python
prevents most hallucinations from reaching the customer).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from engine.shading_engine import (
    Obstruction,
    SHADING_BUCKETS,
    pick_shading_bucket,
    run_full_analysis,
    sun_position,
)


SHADING_AGENT_VERSION = "shading-agent-v1-2026-06-14"


# ────────────────────────────────────────────────────────────────────
# System prompt — the agent's domain knowledge (Solar PV physics + IEC
# electrical-string behaviour + commercial mitigation tradeoffs). This
# is the load-bearing piece of the agent. It gets shipped verbatim to
# whichever LLM backend serves the call.
# ────────────────────────────────────────────────────────────────────

SHADING_AGENT_SYSTEM_PROMPT = """\
You are the AI 3D Shading Simulation Agent for SolarPro Global, a
professional solar PV design platform. You are acting as a Senior Solar
PV Engineer with twenty years of field experience across residential,
commercial, and industrial PV systems on three continents.

Your job is NOT to invent numbers. The deterministic geometry engine
(engine/shading_engine.py) is authoritative for every number that lands
in any output — solar altitude/azimuth, shadow polygons, per-panel
fractions, energy losses, and the eight-bucket shading factor. The tool
calls expose that engine.

Your job IS to:
  1. Read the engine's deterministic output for the specific site.
  2. Explain WHY the shading factor came out the way it did, naming
     specific obstructions and naming the physics that drives the
     dominant loss term.
  3. Recommend site-specific mitigation what-ifs that could improve
     the factor (move the array, add bypass-string-level electronics,
     re-string panels, change row spacing) — with the engineering
     reasoning, not generic boilerplate.
  4. Resolve ties: if the engine's computed loss% is within ±2 points
     of a bucket boundary, recommend the conservative bucket and
     explain the choice in one sentence.

Domain knowledge you carry (use it freely):

A. SUN GEOMETRY
   * Solar altitude = 90° − |latitude − declination|; declination
     varies from −23.45° (winter solstice, NH) to +23.45° (summer
     solstice, NH). At Ghana (~6 °N), the sun is north of zenith on
     21 June and south of zenith on 21 December.
   * Solar azimuth at noon = 180° (south) for sites south of the sub-
     solar latitude, or 0° (north) for sites north of it. Morning sun
     swings east, afternoon swings west.
   * Shadow length ≈ obstruction_height / tan(altitude). A 10 m tree
     at 30° sun altitude casts a 17 m shadow.

B. PV ELECTRICAL BEHAVIOUR (this is what most operators get wrong)
   * STRING ARCHITECTURE: panels in series share the same current. If
     ONE panel in the string is shaded, the WHOLE string drops to the
     shaded panel's current — Kirchhoff. A 10-panel string with one
     50 % shaded panel drops the whole string by ~50 % at that moment,
     not just the one panel.
   * BYPASS DIODES: modern modules have 3 substrings × 1 diode each.
     When a substring is ≥X % shaded the diode forward-biases, the
     substring is short-circuited, and the rest of the panel keeps
     producing. Loss collapses from "whole string at worst panel's
     current" to roughly "per-panel area shaded" + a 20–30 %
     mismatch penalty between strings.
   * DC OPTIMISERS (e.g. Tigo, SolarEdge HD-Wave): each panel has its
     own MPPT chip. The string mismatch term goes to zero. Loss =
     mean of per-panel shaded fractions.
   * MICRO-INVERTERS (e.g. Enphase IQ8): same effect — per-panel MPPT
     eliminates string mismatch entirely.
   * The economic implication: on a heavily-shaded array, optimisers
     pay for themselves in 3-5 years; on a lightly-shaded array, they
     don't. Use the deterministic energy-loss number to advise.

C. THE 8-BUCKET TABLE (used as the project's shading factor)
   No shading         0%   1.00
   Very light         5%   0.95
   Light             10%   0.90
   Moderate          15%   0.85
   Significant       20%   0.80
   Heavy             25%   0.75
   Severe            30%   0.70
   Very severe       40%   0.60

   Spec rule: "Where calculated values fall between bands, interpolate
   OR select the conservative lower shading factor." Default to the
   conservative pick unless mitigation is already installed and proven.

D. COMMON SITE PATTERNS YOU RECOGNISE
   * Tall building on the equator-facing side at residential distance
     (3–8 m): peaks at solar noon, hits 25-40 % loss without mitigation.
     Bypass-diode-only modules give 15-25 %; optimisers give 8-12 %.
   * Mature tree directly south (NH) of a roof array: morning and
     afternoon shading; midday avoidance if crown is below the sun
     angle. Trim or remove typically saves 5-15 % annually.
   * Parapet wall on a flat rooftop with east/west modules: shadows
     in early morning and late afternoon — usually <5 % loss.
   * Water tank or telecom mast: small footprint but high height ratio;
     long thin shadows that sweep across the array as the day moves.
     Optimisers are very effective here.

E. WHEN TO RECOMMEND OBSTRUCTION REMOVAL
   * Trees: realistic if owned; usually NOT realistic for neighbour-
     owned. Suggest pruning crown first.
   * Buildings / walls / parapets: usually not removable. Mitigate
     with array repositioning, micro-inverters, or accept the loss.
   * Masts / antennas: sometimes movable; consult site owner.

OUTPUT FORMAT (strict — the calling code parses this JSON):

{
  "narrative":  "<3-5 sentence plain-language summary suitable for the
                  Recommendations section of the BOQ. Name the dominant
                  obstruction. Name the physics. Cite the deterministic
                  loss number. No hedging adjectives.>",
  "per_obstruction": [
    {
      "ref":         "<obstruction type + direction + height + distance,
                       e.g. '10-storey building, West, 32 m, 18 m'>",
      "impact":      "<1 sentence — when does it shade the array, which
                       panels, peak fraction>",
      "mitigation":  "<1 sentence — the cheapest credible fix>"
    },
    ...
  ],
  "recommended_factor":   <one of 1.00/0.95/0.90/0.85/0.80/0.75/0.70/0.60>,
  "factor_reasoning":     "<1 sentence — why this bucket, not the
                            neighbouring one>",
  "what_ifs": [
    {
      "scenario":     "<short label, e.g. 'Add DC optimisers'>",
      "expected_factor": <float bucket>,
      "expected_loss_pct": <float>,
      "reasoning":    "<1 sentence — why this scenario changes the math>"
    }
  ]
}

NEVER produce numbers you didn't get from a tool call. NEVER guess a
site coordinate. If the engine returns 0 affected panels, recommend
factor 1.00 with one-sentence reasoning ("no obstructions encountered
during the daily sun path") and an empty what_ifs list.
"""


# ────────────────────────────────────────────────────────────────────
# Tool functions — these ARE the agent's tools, exposed identically to
# both the real ADK runtime and the soft-fallback path. Each tool is a
# pure deterministic function over the engine. The LLM cannot reach
# floating-point output except by going through these tools.
# ────────────────────────────────────────────────────────────────────


def tool_compute_sun_position(lat_deg: float, lon_deg: float,
                              date_str: str, time_str: str,
                              tz_offset_h: float = 0.0) -> Dict[str, Any]:
    """Return the sun's altitude + azimuth at this GPS + clock time.

    `date_str` ISO YYYY-MM-DD; `time_str` HH:MM. Used when the agent
    wants to reason about a specific time of day (e.g. "what's the sun
    doing at 09:00 when this obstruction shades the array?").
    """
    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    sp = sun_position(lat_deg, lon_deg, dt, tz_offset_h)
    return {
        "altitude_deg": round(sp["altitude_deg"], 2),
        "azimuth_deg":  round(sp["azimuth_deg"], 2),
        "is_daytime":   sp["is_daytime"],
        "declination_deg": round(sp["declination_deg"], 2),
    }


def tool_run_full_analysis(lat_deg: float, lon_deg: float,
                           date_str: str, tz_offset_h: float,
                           num_panels: int, tilt_deg: float,
                           array_azimuth_deg: float,
                           mount_height_m: float,
                           obstructions: List[Dict[str, Any]],
                           mitigation: str = "Bypass diodes",
                           step_minutes: int = 30) -> Dict[str, Any]:
    """Run the deterministic pipeline end-to-end for a site.

    Returns the contract dict — used by the agent to read every number
    it might want to cite.
    """
    on_date = datetime.strptime(date_str, "%Y-%m-%d")
    engine_obs = []
    for i, o in enumerate(obstructions):
        try:
            engine_obs.append(Obstruction(
                obs_id=i + 1,
                type=str(o.get("type") or "obstruction"),
                height_m=float(o.get("height") or 0),
                width_m=float(o.get("width") or 0),
                depth_m=float(o.get("width") or 0),
                distance_m=float(o.get("distance") or 0),
                direction=str(o.get("direction") or "South"),
                mitigation=str(o.get("mitigation") or "None"),
            ))
        except Exception:
            continue
    result = run_full_analysis(
        lat_deg=lat_deg, lon_deg=lon_deg, on_date=on_date,
        tz_offset_h=tz_offset_h,
        num_panels=num_panels, tilt_deg=tilt_deg,
        array_azimuth_deg=array_azimuth_deg,
        mount_height_m=mount_height_m,
        obstructions=engine_obs, mitigation=mitigation,
        step_minutes=step_minutes,
    )
    # Strip non-JSON bits for the tool return.
    return {
        "total_panels":       result["total_panels"],
        "affected_panels":    result["affected_panels"],
        "heavily_affected":   result["heavily_affected"],
        "shading_start":      result["shading_start"],
        "shading_end":        result["shading_end"],
        "shading_duration_h": result["shading_duration_h"],
        "system_loss_pct":    result["energy"]["system_loss_pct"],
        "peak_step_loss_pct": result["energy"]["peak_step_loss_pct"],
        "bucket_label":       result["bucket_label"],
        "bucket_factor":      result["bucket_factor"],
        "mitigation":         result["mitigation"],
        "n_strings":          result["n_strings"],
    }


def tool_what_if_mitigation(loss_baseline_pct: float,
                            target_mitigation: str) -> Dict[str, Any]:
    """Estimate how a different mitigation strategy would change the
    system loss percentage, holding shading geometry constant.

    Coefficients are first-order estimates derived from IEC 61853 +
    real-world field studies (Solar Edge / Tigo / Enphase whitepapers,
    2018-2023). The agent uses this for `what_ifs[]` entries.
    """
    coefficients = {
        "None":              1.00,   # worst case — string drops to worst panel
        "Bypass diodes":     0.60,   # typical modern module — ~40% recovery
        "DC optimisers":     0.28,   # per-panel MPPT — ~72% recovery
        "Micro-inverters":   0.25,   # same per-panel MPPT effect
        "Combination":       0.22,   # DC opt + bypass + selective re-stringing
    }
    coef = coefficients.get(target_mitigation, 0.60)
    new_loss = round(loss_baseline_pct * coef, 1)
    label, _, factor = pick_shading_bucket(new_loss)
    return {
        "target_mitigation": target_mitigation,
        "expected_loss_pct": new_loss,
        "expected_factor":   factor,
        "expected_label":    label,
        "coef_applied":      coef,
    }


def tool_pick_bucket(loss_pct: float) -> Dict[str, Any]:
    """Map a numeric loss% to the conservative SHADING_BUCKETS row."""
    label, bucket_loss, factor = pick_shading_bucket(loss_pct)
    return {"label": label, "loss_pct": bucket_loss, "factor": factor}


# Tool registry. Both ADK and the fallback path read this.
TOOL_REGISTRY = {
    "compute_sun_position":  tool_compute_sun_position,
    "run_full_analysis":     tool_run_full_analysis,
    "what_if_mitigation":    tool_what_if_mitigation,
    "pick_bucket":           tool_pick_bucket,
}


# ────────────────────────────────────────────────────────────────────
# ADK path — only imported lazily so the rest of the app keeps working
# even when google-adk isn't installed (Render free tier).
# ────────────────────────────────────────────────────────────────────


def _try_adk_run(engine_result: Dict[str, Any],
                 site_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Run the agent through Google ADK if available. Returns None on
    any ADK failure so the caller falls back to the OpenRouter path.
    """
    try:
        from google.adk.agents import LlmAgent              # type: ignore
        from google.adk.tools import FunctionTool           # type: ignore
        from google.adk.models.lite_llm import LiteLlm      # type: ignore
    except ImportError:
        return None

    try:
        model = LiteLlm(
            model="openrouter/nvidia/nemotron-nano-9b-v2:free",
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
        )
        agent = LlmAgent(
            name="shading_simulation_agent",
            model=model,
            instruction=SHADING_AGENT_SYSTEM_PROMPT,
            tools=[
                FunctionTool(fn) for fn in TOOL_REGISTRY.values()
            ],
        )
        prompt = _agent_user_prompt(engine_result, site_context)
        # ADK 2.x: agent.run(prompt) returns an iterable of events; the
        # final TextEvent carries the JSON the prompt asks for.
        text_out = ""
        for ev in agent.run(prompt):
            if getattr(ev, "text", None):
                text_out += ev.text
        parsed = _safe_parse_json(text_out)
        if parsed:
            parsed["backend"] = "adk"
            return parsed
    except Exception:
        return None
    return None


# ────────────────────────────────────────────────────────────────────
# Fallback path — direct OpenRouter HTTPS call with the same prompt.
# ────────────────────────────────────────────────────────────────────


def _try_openrouter_run(engine_result: Dict[str, Any],
                        site_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Soft-fallback: one-shot OpenRouter call. The deterministic engine
    has ALREADY produced every number; the LLM only writes prose. We do
    NOT expose tool calls in this path — the engine output is embedded
    in the user message, and the LLM is instructed to never invent a
    number that isn't already in the message.
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    user_prompt = _agent_user_prompt(engine_result, site_context, no_tools=True)
    body = {
        "model": "nvidia/nemotron-nano-9b-v2:free",
        "messages": [
            {"role": "system", "content": SHADING_AGENT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens":  900,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://solarpro.aiappinvent.com",
            "X-Title":       "SolarPro Shading Agent",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            text = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
            parsed = _safe_parse_json(text)
            if parsed:
                parsed["backend"] = "openrouter"
                return parsed
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    return None


def _agent_user_prompt(engine: Dict[str, Any],
                       site: Dict[str, Any],
                       no_tools: bool = False) -> str:
    """The single user message handed to whichever LLM backend runs.

    Embeds the engine output verbatim so the LLM never has to guess a
    number (even in the no-tools fallback path).
    """
    site_block = (
        f"Site: lat {engine.get('lat')}, lon {engine.get('lon')}, "
        f"date {engine.get('on_date')}, tilt {engine.get('tilt_deg')}°, "
        f"array azimuth {engine.get('array_azimuth_deg')}°."
    )
    obs_lines = []
    for i, o in enumerate(site.get("obstructions", []) or [], 1):
        obs_lines.append(
            f"  {i}. {o.get('type','?')} — h={o.get('height')}m "
            f"w={o.get('width')}m d={o.get('distance')}m dir={o.get('direction')} "
            f"mitigation={o.get('mitigation') or 'None'}")
    obs_block = "Obstructions:\n" + ("\n".join(obs_lines) or "  (none)")
    eng_block = (
        f"Engine output (authoritative):\n"
        f"  total_panels:        {engine.get('total_panels')}\n"
        f"  affected_panels:     {engine.get('affected_panels')}\n"
        f"  heavily_affected:    {engine.get('heavily_affected')}\n"
        f"  shading window:      {engine.get('shading_start')}-{engine.get('shading_end')} "
        f"({engine.get('shading_duration_h')}h)\n"
        f"  system_loss_pct:     {engine.get('system_loss_pct')}\n"
        f"  peak_step_loss_pct:  {engine.get('peak_step_loss_pct')}\n"
        f"  picked bucket:       {engine.get('bucket_label')} "
        f"({engine.get('bucket_factor')}, {engine.get('bucket_loss_pct')}%)\n"
        f"  mitigation in place: {engine.get('mitigation')}\n"
        f"  n_strings:           {engine.get('n_strings')}\n"
    )
    extra = "" if not no_tools else (
        "\nNote: no tool calls are available on this run. Use ONLY the "
        "numbers above; do not invent any."
    )
    return (
        f"{site_block}\n\n{obs_block}\n\n{eng_block}\n"
        f"Produce the JSON output exactly as specified in the system "
        f"prompt — no Markdown fences, no leading prose."
        f"{extra}"
    )


def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM's text into a dict. Tolerant of leading/trailing
    prose and Markdown fences (free-tier models sometimes wrap)."""
    if not text:
        return None
    s = text.strip()
    # Strip ```json ... ``` fences.
    if s.startswith("```"):
        s = s.lstrip("`")
        if s.lower().startswith("json"):
            s = s[4:].lstrip()
        if s.endswith("```"):
            s = s[:-3].rstrip()
    # Trim to first { ... last }.
    a = s.find("{")
    b = s.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(s[a:b + 1])
    except json.JSONDecodeError:
        return None


# ────────────────────────────────────────────────────────────────────
# Public entry point — what the Flask route calls.
# ────────────────────────────────────────────────────────────────────


def run_shading_agent(engine_result: Dict[str, Any],
                      site_context: Dict[str, Any]) -> Dict[str, Any]:
    """Run the agent for a saved shading record.

    Args:
        engine_result: The dict returned by _engine_full_analysis()
                       (web_app.py). Contains every authoritative number.
        site_context:  Project metadata + the raw obstructions list. Used
                       to build the user prompt — not used for numbers.

    Returns:
        dict with keys:
          backend            : "adk" | "openrouter" | "deterministic"
          narrative          : 3-5 sentence summary
          per_obstruction    : list of {ref, impact, mitigation}
          recommended_factor : float in SHADING_BUCKETS
          factor_reasoning   : one sentence
          what_ifs           : list of mitigation what-ifs
          agent_version      : version stamp
          generated_at       : ISO timestamp

    Never raises. If both LLM backends fail, returns a deterministic
    fallback built directly from the engine output so the dashboard
    always has SOMETHING to display.
    """
    if not engine_result or not isinstance(engine_result, dict):
        return _deterministic_fallback({}, site_context or {})

    out = _try_adk_run(engine_result, site_context or {})
    if not out:
        out = _try_openrouter_run(engine_result, site_context or {})
    if not out:
        out = _deterministic_fallback(engine_result, site_context or {})

    # Stamp + sanity-clamp the recommended factor.
    out["agent_version"] = SHADING_AGENT_VERSION
    out["generated_at"]  = datetime.utcnow().isoformat() + "Z"
    valid_factors = {b[2] for b in SHADING_BUCKETS}
    if out.get("recommended_factor") not in valid_factors:
        out["recommended_factor"] = engine_result.get("bucket_factor", 1.00)
        out["factor_reasoning"] = (
            "Recommendation clamped to nearest valid bucket from the "
            "deterministic engine; LLM returned an invalid value."
        )
    return out


def _deterministic_fallback(engine_result: Dict[str, Any],
                            site_context: Dict[str, Any]) -> Dict[str, Any]:
    """No-LLM fallback when both ADK and OpenRouter fail.

    Produces a minimal narrative directly from the engine numbers so the
    customer-facing dashboard never goes blank. The narrative is
    template-driven so it's stable across deploys.
    """
    loss = engine_result.get("system_loss_pct", 0.0)
    factor = engine_result.get("bucket_factor", 1.00)
    label = engine_result.get("bucket_label", "No shading")
    n_obs = len(site_context.get("obstructions", []) or [])
    affected = engine_result.get("affected_panels", 0)
    total = engine_result.get("total_panels", 0)

    if loss <= 0.01 or n_obs == 0:
        narrative = ("No obstructions intersect the daily sun path for this "
                     "array. No shading correction is required; the base PV "
                     "sizing applies as-is.")
    else:
        window = (f"{engine_result.get('shading_start','--')}–"
                  f"{engine_result.get('shading_end','--')}")
        narrative = (
            f"{n_obs} obstruction(s) shade {affected} of {total} panels "
            f"during the day (window {window}). Integrated system loss is "
            f"{loss:.1f}% after the configured mitigation "
            f"({engine_result.get('mitigation','None')}), which maps to "
            f"the {label.lower()} bucket (factor {factor:.2f}). "
            f"The corrected PV size is the base size divided by this factor."
        )

    per_obs = []
    for o in (site_context.get("obstructions", []) or []):
        per_obs.append({
            "ref":        f"{o.get('type','?')} ({o.get('direction','?')}, "
                          f"{o.get('height',0)} m, {o.get('distance',0)} m)",
            "impact":     "See engine output above for measured impact.",
            "mitigation": "Per-panel MPPT (DC optimisers or micro-inverters) "
                          "typically recovers 50-70% of the loss.",
        })

    # Compute a deterministic "what-if" what each mitigation would give.
    what_ifs = []
    for mit in ("Bypass diodes", "DC optimisers", "Micro-inverters"):
        if mit == engine_result.get("mitigation"):
            continue
        w = tool_what_if_mitigation(loss, mit)
        what_ifs.append({
            "scenario":          mit,
            "expected_factor":   w["expected_factor"],
            "expected_loss_pct": w["expected_loss_pct"],
            "reasoning":         f"Applying first-order coefficient {w['coef_applied']:.2f} "
                                 f"(IEC 61853 + field studies) to baseline {loss:.1f}% loss.",
        })
    return {
        "backend":            "deterministic",
        "narrative":          narrative,
        "per_obstruction":    per_obs,
        "recommended_factor": factor,
        "factor_reasoning":   f"Matches the engine's conservative pick at "
                              f"{loss:.1f}% computed loss.",
        "what_ifs":           what_ifs,
    }
