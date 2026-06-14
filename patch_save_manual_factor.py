"""Allow the human to persist a manually-chosen shading factor.

When the POST form carries `save_manual_factor=X.XX`, the route bypasses
the obstruction-driven agent computation and saves the operator's chosen
factor directly. This is a SEPARATE flow from the existing form save:

  * Normal Save: parses obstructions, runs agent, persists agent's pick
  * Save Manual Factor: persists the human's chosen factor + tags
    data["shading"]["factor_source"] = "manual" so the dashboard shows
    a green banner confirming the override.
"""
from __future__ import annotations
import sys

TARGET = "web_app.py"

OLD = b'    if request.method == "POST":\r\n        csrf_protect()\r\n'
NEW = (b'    if request.method == "POST":\r\n'
       b'        csrf_protect()\r\n'
       b'        # Save-manual-factor: human-driven override of the agent pick.\r\n'
       b'        # Bypasses the obstruction parser + agent run; just persists\r\n'
       b'        # the chosen factor + a "source=manual" tag.\r\n'
       b'        _smf_raw = request.form.get("save_manual_factor") or ""\r\n'
       b'        if _smf_raw:\r\n'
       b'            try:\r\n'
       b'                _smf = float(_smf_raw)\r\n'
       b'            except Exception:\r\n'
       b'                _smf = 0.0\r\n'
       b'            if 0.55 <= _smf <= 1.05:\r\n'
       b'                data = project["data"]\r\n'
       b'                _existing = data.get("shading", {}) or {}\r\n'
       b'                from engine.shading_engine import pick_shading_bucket as _psb\r\n'
       b'                _label, _loss, _f = _psb((1.0 - _smf) * 100)\r\n'
       b'                _existing["factor"] = _smf\r\n'
       b'                _existing["label"] = _label\r\n'
       b'                _existing["loss_pct"] = _loss\r\n'
       b'                _existing["factor_source"] = "manual"\r\n'
       b'                _existing["saved_at"] = datetime.utcnow().isoformat() + "Z"\r\n'
       b'                _existing["saved_by"] = session.get("username", "")\r\n'
       b'                data["shading"] = _existing\r\n'
       b'                save_project_data(pid, data)\r\n'
       b'                try:\r\n'
       b'                    with get_db() as c:\r\n'
       b'                        c.execute(\r\n'
       b'                            "INSERT INTO audit_logs (user_id, username, action, ip_address, details) "\r\n'
       b'                            "VALUES (?,?,?,?,?)",\r\n'
       b'                            (session.get("user_id"), session.get("username", ""),\r\n'
       b'                             "shading_factor_manual_set", _get_real_ip(),\r\n'
       b'                             f"pid={pid} factor={_smf:.2f} label={_label}"))\r\n'
       b'                except Exception:\r\n'
       b'                    pass\r\n'
       b'                flash(f"Manual shading factor saved: {_smf:.2f} ({_label}, {_loss:.0f}% loss). "\r\n'
       b'                      f"Re-run the loads step to apply.", "success")\r\n'
       b'                return redirect(url_for("project_shading", pid=pid))\r\n'
       b'            else:\r\n'
       b'                flash("Manual factor must be between 0.55 and 1.05.", "warning")\r\n'
       b'                return redirect(url_for("project_shading", pid=pid))\r\n')


def patch():
    src = open(TARGET, "rb").read()
    if b"Save-manual-factor: human-driven override" in src:
        print("[skip] save-manual-factor already wired")
        return 0
    # Find the right occurrence — the one inside project_shading.
    if b"def project_shading" not in src:
        print("[fail] project_shading route not found")
        return 2
    idx_route = src.find(b"def project_shading")
    idx_post  = src.find(OLD, idx_route)
    if idx_post < 0:
        print("[fail] POST anchor not found in project_shading")
        return 3
    # Replace only the FIRST occurrence after the route def.
    new_src = src[:idx_post] + NEW + src[idx_post + len(OLD):]
    open(TARGET, "wb").write(new_src)
    print("[ok] save-manual-factor route handler wired")
    return 0


if __name__ == "__main__":
    sys.exit(patch())
