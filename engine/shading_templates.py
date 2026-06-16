"""Reference-template matcher for the AI 3D Shading Simulation Agent.

The catalogue holds engineering-attribute fingerprints extracted from
the owner's reference dashboards (Documents/pvsolar1/real shading/,
2026-06-14). We LEARN from those reference scenes' engineering profile
(mount type, obstruction mix, severity, PV calc) -- we do NOT ship the
original images. The agent picks the closest catalogue entry by
weighted feature scoring; the dashboard renders the user's site with
our own original 3D scene, optionally informed by the matched
profile's hints.

Design choice — per the four-gate review (gate 1: Codex, gate 2:
Supervisor, gate 3: Work Reviewer, gate 4: Work Scheduler), we use
weighted feature matching rather than an image-embedding model because:

  * The library is small (3 reference scenes today).
  * The features that matter for "closest scene" are engineering
    attributes (mount type, obstruction count, dominant obstruction
    type, severity) — not pixel-level similarity.
  * Runs on Render free tier with no model load.
  * Adding a new template is a pure-data edit to the JSON; no retrain.

If the library grows past ~50 scenes, swap this module for an embedding
matcher behind the SAME `pick_reference_template(site_context)` API.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


# Direction labels accepted in both compass-letter and long forms.
_DIRECTION_ALIASES = {
    "n": "North", "north": "North",
    "nne": "North-North-East", "north-north-east": "North-North-East",
    "ne": "North-East", "north-east": "North-East", "northeast": "North-East",
    "ene": "East-North-East", "east-north-east": "East-North-East",
    "e": "East", "east": "East",
    "ese": "East-South-East", "east-south-east": "East-South-East",
    "se": "South-East", "south-east": "South-East", "southeast": "South-East",
    "sse": "South-South-East", "south-south-east": "South-South-East",
    "s": "South", "south": "South",
    "ssw": "South-South-West", "south-south-west": "South-South-West",
    "sw": "South-West", "south-west": "South-West", "southwest": "South-West",
    "wsw": "West-South-West", "west-south-west": "West-South-West",
    "w": "West", "west": "West",
    "wnw": "West-North-West", "west-north-west": "West-North-West",
    "nw": "North-West", "north-west": "North-West", "northwest": "North-West",
    "nnw": "North-North-West", "north-north-west": "North-North-West",
}


def _normalize_direction(raw: Any) -> str:
    s = (str(raw or "").strip().lower())
    return _DIRECTION_ALIASES.get(s, str(raw or "").strip())


def _normalize_mount_type(raw: Any) -> str:
    """Mirror engine._normalize_mount_type so this module is independent
    of web_app.py. Returns one of: ground / rooftop_flat / rooftop_sloped.
    """
    s = (str(raw or "").strip().lower())
    if not s:
        return "rooftop_sloped"
    if "ground" in s:
        return "ground"
    if s in ("flat", "membrane", "concrete",
             "rooftop_flat", "rooftop_membrane"):
        return "rooftop_flat"
    return "rooftop_sloped"


def _obstruction_features(obstructions: List[Dict[str, Any]]) -> Dict[str, float]:
    """Convert an obstruction list into the same match-feature schema the
    template catalogue uses, so both sides can be cosine-scored."""
    feats = {
        "is_ground_mounted":      0.0,    # set by caller
        "is_rooftop":             0.0,    # set by caller
        "has_tall_building":      0.0,
        "has_tree":               0.0,
        "has_wall":               0.0,
        "has_tank":               0.0,
        "has_hill":               0.0,
        "has_cluster":            0.0,
        "has_neighbour_building": 0.0,
        "max_height_m":           0.0,
        "min_distance_m":         9999.0,
        "obstruction_count":      0.0,
        "dominant_direction":     "",
    }
    feats["obstruction_count"] = float(len(obstructions or []))
    n_cluster = 0
    for o in (obstructions or []):
        t = str(o.get("type") or "").lower()
        h = float(o.get("height") or 0)
        d = float(o.get("distance") or 0)
        if "tree" in t:
            feats["has_tree"] = 1.0
        if "wall" in t or "parapet" in t:
            feats["has_wall"] = 1.0
        if "tank" in t:
            feats["has_tank"] = 1.0
        if "hill" in t or "mound" in t or "terrain" in t:
            feats["has_hill"] = 1.0
        if "cluster" in t:
            feats["has_cluster"] = 1.0
            n_cluster += 1
        if "neighbour" in t or "nearby" in t:
            feats["has_neighbour_building"] = 1.0
        if "storey" in t or "story" in t or "building" in t:
            if h >= 12:
                feats["has_tall_building"] = 1.0
        feats["max_height_m"] = max(feats["max_height_m"], h)
        if d > 0:
            feats["min_distance_m"] = min(feats["min_distance_m"], d)
    # >=3 buildings counts as cluster-shaped even if the operator didn't
    # type "cluster" (per 3d10 plan §7 selectSceneTemplate priority chain).
    bldg_count = sum(
        1 for o in (obstructions or [])
        if "building" in str(o.get("type") or "").lower()
        or "storey" in str(o.get("type") or "").lower()
        or "cluster" in str(o.get("type") or "").lower()
    )
    if bldg_count >= 3:
        feats["has_cluster"] = 1.0
    if feats["min_distance_m"] >= 9999.0:
        feats["min_distance_m"] = 0.0
    # Pick the direction of the tallest obstruction.
    tallest = None
    for o in (obstructions or []):
        h = float(o.get("height") or 0)
        if tallest is None or h > float(tallest.get("height") or 0):
            tallest = o
    feats["dominant_direction"] = (
        _normalize_direction((tallest or {}).get("direction")) if tallest else ""
    )
    return feats


def _site_feature_vector(site_context: Dict[str, Any]) -> Dict[str, Any]:
    """Build the same feature dict from the user's site context."""
    mount = _normalize_mount_type(site_context.get("mount_type")
                                  or site_context.get("roof_type"))
    feats = _obstruction_features(site_context.get("obstructions") or [])
    feats["is_ground_mounted"] = 1.0 if mount == "ground" else 0.0
    feats["is_rooftop"]        = 0.0 if mount == "ground" else 1.0
    feats["mount_type"]        = mount
    # Severity comes from the engine; map factor to bucket label.
    factor = float(site_context.get("bucket_factor") or 0)
    if factor <= 0:
        feats["severity_bucket"] = ""
    elif factor >= 0.95:
        feats["severity_bucket"] = "very_light"
    elif factor >= 0.90:
        feats["severity_bucket"] = "light"
    elif factor >= 0.85:
        feats["severity_bucket"] = "moderate"
    elif factor >= 0.80:
        feats["severity_bucket"] = "significant"
    elif factor >= 0.75:
        feats["severity_bucket"] = "heavy"
    elif factor >= 0.70:
        feats["severity_bucket"] = "severe"
    else:
        feats["severity_bucket"] = "very_severe"
    return feats


def _score(site_feats: Dict[str, Any],
           tpl_feats: Dict[str, Any],
           tpl_scene:  Dict[str, Any]) -> float:
    """Weighted scoring. Each component contributes 0..1; total 0..weight_sum.
    Weights chosen so mount type + obstruction mix dominate, severity is
    a tiebreaker. Normalized to [0, 1] at the end.

    Scene-type-defining features (hill, cluster) get higher weight per the
    3d10 plan §7 priority chain (hill > urban_cluster > multi > ...).
    """
    weights = {
        "mount":      0.20,   # rooftop vs ground is a big split
        "hill":       0.18,   # scene-type-defining per 3d10 §7 priority 1
        "cluster":    0.15,   # scene-type-defining per 3d10 §7 priority 2
        "tall_bldg":  0.08,
        "tree":       0.06,
        "wall":       0.04,
        "tank":       0.04,
        "neighbour":  0.03,
        "count":      0.08,   # 1 vs many obstructions
        "direction":  0.07,
        "severity":   0.07,
    }
    s = 0.0
    # Mount: exact match scores 1; rooftop_flat vs rooftop_sloped scores 0.6
    sm = site_feats.get("mount_type")
    tm = _normalize_mount_type(tpl_scene.get("mount_type"))
    if sm == tm:
        s += weights["mount"]
    elif (sm and tm and sm.startswith("rooftop") and tm.startswith("rooftop")):
        s += weights["mount"] * 0.6
    # Binary features
    for feat, w in [
        ("has_hill",              weights["hill"]),
        ("has_cluster",           weights["cluster"]),
        ("has_tall_building",     weights["tall_bldg"]),
        ("has_tree",              weights["tree"]),
        ("has_wall",              weights["wall"]),
        ("has_tank",              weights["tank"]),
        ("has_neighbour_building", weights["neighbour"]),
    ]:
        if site_feats.get(feat) == tpl_feats.get(feat):
            s += w
    # Count bucket: "1" vs "many"
    site_count = int(site_feats.get("obstruction_count") or 0)
    site_bucket = "1" if site_count <= 1 else "many"
    if site_bucket == str(tpl_feats.get("obstruction_count_bucket", "")):
        s += weights["count"]
    elif site_count == 0:
        s += weights["count"] * 0.5    # neutral if no obstructions yet
    # Dominant direction: exact match 1, 45° off 0.5, else 0
    sd = (site_feats.get("dominant_direction") or "").lower()
    td = (tpl_scene.get("dominant_direction") or "").lower()
    if sd and td and sd == td:
        s += weights["direction"]
    elif sd and td:
        s += weights["direction"] * 0.3
    # Severity bucket
    if (site_feats.get("severity_bucket") and
        site_feats.get("severity_bucket") == tpl_feats.get("severity_bucket")):
        s += weights["severity"]
    return round(s / sum(weights.values()), 3)


def _reasoning_phrase(site_feats: Dict[str, Any],
                      tpl: Dict[str, Any],
                      score: float) -> str:
    """One-sentence narrative explaining the pick."""
    mount = site_feats.get("mount_type", "unspecified")
    n = int(site_feats.get("obstruction_count") or 0)
    sev = site_feats.get("severity_bucket") or "unrated"
    return (
        f"Closest match {score:.0%}: {mount} site with {n} obstruction(s) "
        f"and {sev.replace('_',' ')} severity aligns with reference "
        f"“{tpl['title']}”."
    )


# Public API --------------------------------------------------------

DEFAULT_CATALOGUE_PATH = os.path.join(
    os.path.dirname(__file__), "shading_templates.json")


def load_catalogue(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the JSON catalogue. Cached per process via lru_cache would be
    nice but kept simple here so reloads pick up edits."""
    p = path or DEFAULT_CATALOGUE_PATH
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_reference_template(site_context: Dict[str, Any],
                            catalogue: Optional[Dict[str, Any]] = None
                            ) -> Dict[str, Any]:
    """Score every template against the site context, return the best.

    Args:
        site_context: dict with mount_type/roof_type, obstructions list,
                      and optionally bucket_factor for severity matching.
        catalogue:    pre-loaded catalogue (test injection); falls back
                      to DEFAULT_CATALOGUE_PATH.

    Returns:
        {
          "template_id":      str,
          "title":            str,
          "image_url":        str (web path under /static/...),
          "match_score":      float (0..1),
          "reasoning":        str,
          "template":         <full template dict from catalogue>,
          "ranked":           [{template_id, match_score}] for all scenes
        }
    Never raises.
    """
    try:
        cat = catalogue or load_catalogue()
    except Exception as e:
        return {
            "template_id": None,
            "title": "(catalogue unavailable)",
            "image_url": "",
            "match_score": 0.0,
            "reasoning": f"Could not load template catalogue: {e!s}",
            "template": None,
            "ranked": [],
        }
    templates = cat.get("templates") or []
    if not templates:
        return {
            "template_id": None,
            "title": "(empty catalogue)",
            "match_score": 0.0,
            "reasoning": "Template catalogue is empty.",
            "template": None,
            "ranked": [],
        }
    site_feats = _site_feature_vector(site_context or {})
    ranked = []
    for tpl in templates:
        scene = tpl.get("scene_profile") or {}
        feats = tpl.get("match_features") or {}
        score = _score(site_feats, feats, scene)
        ranked.append({
            "template_id": tpl["id"],
            "match_score": score,
            "title": tpl.get("title", ""),
        })
    ranked.sort(key=lambda r: r["match_score"], reverse=True)
    best_id = ranked[0]["template_id"]
    best_tpl = next(t for t in templates if t["id"] == best_id)
    return {
        "template_id": best_tpl["id"],
        "scene_type":  best_tpl.get("scene_type", ""),
        "title":       best_tpl.get("title", ""),
        "match_score": ranked[0]["match_score"],
        "reasoning":   _reasoning_phrase(site_feats, best_tpl,
                                         ranked[0]["match_score"]),
        "template":    best_tpl,
        "ranked":      ranked,
    }
