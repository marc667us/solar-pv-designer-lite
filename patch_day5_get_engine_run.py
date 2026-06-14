"""Day 5 hotfix: run the engine on GET as well so the v2 dashboard
renders the moment a project page loads. Without this, an operator
who opens /project/<pid>/shading?v2=1 on a legacy project (saved
before today) sees only the empty header — engine output is only
generated on POST.

Also patches `_engine_full_analysis` to default `num_panels` to 12
when the project hasn't been through the Loads step yet, so the
visualization still has something to draw.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

# Patch 1 — default num_panels to 12 (typical residential array) so the
# engine doesn't bail out for projects that haven't run Loads yet. The
# user still sees a representative scene + the engine's structural
# output (window, sun-path arc) even before real PV sizing.
OLD_GUARD = (b'        n_panels = int(results.get("num_panels") or 0)\r\n'
             b'\r\n'
             b'        # Without a panel count there is nothing to project shadows onto.\r\n'
             b'        if n_panels <= 0:\r\n'
             b'            return None\r\n')

NEW_GUARD = (b'        n_panels = int(results.get("num_panels") or 0)\r\n'
             b'\r\n'
             b'        # Day-5 hotfix: default to 12 panels (typical residential\r\n'
             b'        # array) when Loads step hasn\'t produced num_panels yet so\r\n'
             b'        # the v2 dashboard renders a representative scene even on a\r\n'
             b'        # fresh project. Real PV sizing comes from the loads handler\r\n'
             b'        # downstream; this is just for the shading visualization.\r\n'
             b'        if n_panels <= 0:\r\n'
             b'            n_panels = 12\r\n')

# Patch 2 — on GET, run the engine if shading.engine is missing. We pass
# the result to render_template but do NOT call save_project_data() so
# the route stays read-only.
OLD_GET = (b'    shading = project["data"].get("shading", {}) or {}\r\n'
           b'    return render_template("shading.html",\r\n'
           b'                           user=current_user(),\r\n'
           b'                           project=project,\r\n'
           b'                           shading=shading,\r\n'
           b'                           shading_factors=SHADING_FACTORS)\r\n')

NEW_GET = (b'    shading = project["data"].get("shading", {}) or {}\r\n'
           b'    # Day-5 hotfix: if the v2 flag is set and the engine has\r\n'
           b'    # never run on this project, run it now using whatever\r\n'
           b'    # obstructions are already saved. Result is local-only\r\n'
           b'    # (we do NOT save_project_data on GET); it persists only\r\n'
           b'    # when the operator hits Save on the form.\r\n'
           b'    if request.args.get("v2") and not shading.get("engine"):\r\n'
           b'        try:\r\n'
           b'            _eng = _engine_full_analysis(project, shading.get("obstructions") or [])\r\n'
           b'            if _eng:\r\n'
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
           b'                    pass\r\n'
           b'        except Exception as _e:\r\n'
           b'            try:\r\n'
           b'                app.logger.warning("v2 GET engine failure: %s", _e)\r\n'
           b'            except Exception:\r\n'
           b'                pass\r\n'
           b'    return render_template("shading.html",\r\n'
           b'                           user=current_user(),\r\n'
           b'                           project=project,\r\n'
           b'                           shading=shading,\r\n'
           b'                           shading_factors=SHADING_FACTORS)\r\n')


def patch():
    src = open(TARGET, "rb").read()
    changes = 0
    if OLD_GUARD in src:
        src = src.replace(OLD_GUARD, NEW_GUARD, 1)
        changes += 1
        print("[ok] patched n_panels guard to default to 12")
    else:
        print("[skip] n_panels guard already patched or not found")
    if OLD_GET in src:
        src = src.replace(OLD_GET, NEW_GET, 1)
        changes += 1
        print("[ok] patched GET branch to run engine on first load")
    else:
        print("[skip] GET branch already patched or not found")
    if not changes:
        return 1
    open(TARGET, "wb").write(src)
    print(f"[ok] wrote {changes} change(s) to {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
