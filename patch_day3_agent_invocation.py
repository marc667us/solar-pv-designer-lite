"""Day 3 patch: invoke the ADK shading agent in the project_shading route
right after the deterministic engine has produced its output. Persist the
agent's narrative + per-obstruction analysis + what-ifs on
data["shading"]["agent_v2"] so the template can render it.

Soft-failures never break the route — the agent's run_shading_agent()
already swallows exceptions and falls back to a deterministic narrative.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = (b'        # Day-1 wiring: also run the deterministic engine. Adds rich\r\n'
       b'        # output under data["shading"]["engine"]; legacy keys above are\r\n'
       b'        # preserved unchanged so this is a pure additive change.\r\n'
       b'        _eng = _engine_full_analysis(project, obstructions)\r\n'
       b'        if _eng:\r\n'
       b'            data["shading"]["engine"] = _eng\r\n')

NEW = (b'        # Day-1 wiring: also run the deterministic engine. Adds rich\r\n'
       b'        # output under data["shading"]["engine"]; legacy keys above are\r\n'
       b'        # preserved unchanged so this is a pure additive change.\r\n'
       b'        _eng = _engine_full_analysis(project, obstructions)\r\n'
       b'        if _eng:\r\n'
       b'            data["shading"]["engine"] = _eng\r\n'
       b'            # Day-3 wiring: hand the engine output to the ADK shading\r\n'
       b'            # agent for narrative + per-obstruction analysis + mitigation\r\n'
       b'            # what-ifs. Agent never raises; on full failure it returns a\r\n'
       b'            # deterministic narrative built from the engine numbers.\r\n'
       b'            try:\r\n'
       b'                from engine.agents.shading_agent import run_shading_agent\r\n'
       b'                _agent_out = run_shading_agent(_eng, {"obstructions": obstructions})\r\n'
       b'                if _agent_out:\r\n'
       b'                    data["shading"]["agent_v2"] = _agent_out\r\n'
       b'            except Exception as _ae:\r\n'
       b'                try:\r\n'
       b'                    app.logger.warning("shading agent failure: %s", _ae)\r\n'
       b'                except Exception:\r\n'
       b'                    pass\r\n')


def patch():
    src = open(TARGET, "rb").read()
    if b"run_shading_agent" in src:
        print("[skip] agent invocation already present")
        return 0
    if OLD not in src:
        print("[fail] anchor not found")
        return 2
    new_src = src.replace(OLD, NEW, 1)
    open(TARGET, "wb").write(new_src)
    print(f"[ok] wired ADK shading agent ({len(src)} -> {len(new_src)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
