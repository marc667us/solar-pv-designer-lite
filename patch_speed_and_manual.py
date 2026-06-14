"""Two changes:
  1) Skip the LLM agent call on GET so the page loads in <2 s instead
     of 27 s. The deterministic engine still runs (fast); the agent
     narrative only fires on POST when the operator saves.
  2) Honour ?manual_factor=X.XX so the human can override the agent's
     pick and see the PV calculation re-rendered against the chosen
     factor. The agent narrative gets a manual-override banner.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

# Cut the GET-time agent call.
OLD_AGENT = (b'            if _eng:\r\n'
             b'                shading = dict(shading)\r\n'
             b'                shading["engine"] = _eng\r\n'
             b'                # Also fire the agent so the analysis card appears\r\n'
             b'                # the first time the user sees the v2 dashboard.\r\n'
             b'                try:\r\n'
             b'                    from engine.agents.shading_agent import run_shading_agent\r\n'
             b'                    _ag = run_shading_agent(_eng, {"obstructions": shading.get("obstructions") or []})\r\n'
             b'                    if _ag:\r\n'
             b'                        shading["agent_v2"] = _ag\r\n'
             b'                except Exception:\r\n'
             b'                    pass\r\n')

NEW_AGENT = (b'            if _eng:\r\n'
             b'                shading = dict(shading)\r\n'
             b'                shading["engine"] = _eng\r\n'
             b'                # Skip the LLM agent on GET (free-tier latency 5-30s).\r\n'
             b'                # Agent runs only when the operator saves the form.\r\n')

# Apply manual_factor override right after the engine output is set.
OLD_RENDER = b'    return render_template("shading.html",\r\n'
NEW_RENDER = (b'    # Manual factor override (operator picks a factor; PV calc +\r\n'
              b'    # agent narrative reflect that scenario).\r\n'
              b'    try:\r\n'
              b'        _mf = float(request.args.get("manual_factor") or 0)\r\n'
              b'    except Exception:\r\n'
              b'        _mf = 0.0\r\n'
              b'    if 0.55 <= _mf <= 1.05 and shading.get("engine"):\r\n'
              b'        shading = dict(shading)\r\n'
              b'        _eng2 = dict(shading["engine"])\r\n'
              b'        _eng2["bucket_factor"] = _mf\r\n'
              b'        from engine.shading_engine import pick_shading_bucket as _psb\r\n'
              b'        _label, _loss, _f = _psb((1.0 - _mf) * 100)\r\n'
              b'        _eng2["bucket_label"] = _label\r\n'
              b'        _eng2["bucket_loss_pct"] = _loss\r\n'
              b'        shading["engine"] = _eng2\r\n'
              b'        shading["manual_override"] = {"factor": _mf, "label": _label,\r\n'
              b'                                       "loss_pct": _loss}\r\n'
              b'    return render_template("shading.html",\r\n')


def patch():
    src = open(TARGET, "rb").read()
    changes = 0
    if b"Skip the LLM agent on GET" not in src:
        if OLD_AGENT in src:
            src = src.replace(OLD_AGENT, NEW_AGENT, 1)
            changes += 1
            print("[ok] cut GET-time agent call")
        else:
            print("[fail] agent block anchor not found")
    else:
        print("[skip] agent already cut")

    if b"Manual factor override (operator picks a factor" not in src:
        if OLD_RENDER in src:
            src = src.replace(OLD_RENDER, NEW_RENDER, 1)
            changes += 1
            print("[ok] manual factor override wired")
        else:
            print("[fail] render anchor not found")
    else:
        print("[skip] manual override already wired")

    if not changes:
        return 1
    open(TARGET, "wb").write(src)
    print(f"[ok] {changes} change(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
