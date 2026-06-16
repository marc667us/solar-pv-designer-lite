"""Surface the matched reference template on the /shading dashboard.

Calls engine.shading_templates.pick_reference_template from the
project_shading GET handler and passes the result to shading.html as
`reference_template`. The template renders a "Reference scene match"
card above the 3D scene. See ADR-005 + IMPLEMENTATION_LOG entry for
2026-06-16 for the design rationale.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"
MARK = b"# AI 3D Shading Agent v2: pick reference template (2026-06-16)"


# Insert the matcher call just before the render_template call at the
# end of project_shading GET. Anchor: the existing render_template line.

OLD = (
    b'    return render_template("shading.html",\r\n'
    b'                           user=current_user(),\r\n'
    b'                           project=project,\r\n'
    b'                           shading=shading,\r\n'
    b'                           shading_factors=SHADING_FACTORS)\r\n'
)

NEW = (
    b'    # AI 3D Shading Agent v2: pick reference template (2026-06-16)\r\n'
    b'    # See engine/shading_templates.py + ADR for the catalogue + scoring.\r\n'
    b'    reference_template = None\r\n'
    b'    try:\r\n'
    b'        from engine.shading_templates import pick_reference_template as _prt\r\n'
    b'        _eng_block = shading.get("engine") or {}\r\n'
    b'        reference_template = _prt({\r\n'
    b'            "mount_type":    shading.get("mount_type") or _eng_block.get("mount_type"),\r\n'
    b'            "obstructions":  shading.get("obstructions") or [],\r\n'
    b'            "bucket_factor": _eng_block.get("bucket_factor") or shading.get("factor") or 0,\r\n'
    b'        })\r\n'
    b'    except Exception as _e:\r\n'
    b'        try:\r\n'
    b'            app.logger.warning("reference template pick failed: %s", _e)\r\n'
    b'        except Exception:\r\n'
    b'            pass\r\n'
    b'    return render_template("shading.html",\r\n'
    b'                           user=current_user(),\r\n'
    b'                           project=project,\r\n'
    b'                           shading=shading,\r\n'
    b'                           reference_template=reference_template,\r\n'
    b'                           shading_factors=SHADING_FACTORS)\r\n'
)


def patch():
    src = open(TARGET, "rb").read()
    if MARK in src:
        print("[skip] reference-template card already wired")
        return 0
    if OLD not in src:
        print("[fail] anchor not found")
        return 2
    out = src.replace(OLD, NEW, 1)
    open(TARGET, "wb").write(out)
    print("[ok] reference-template card wired into project_shading GET")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
