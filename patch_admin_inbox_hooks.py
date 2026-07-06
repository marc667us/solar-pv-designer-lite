# Pattern A byte-patches: fan real fault/issue sources into the admin inbox.
#   1. _record_error (unhandled 500s)  -> _admin_notify(source='error', critical)
#   2. assistant_escalate (helpline)   -> _admin_notify(source='ticket', warning)
# Both call the later-defined _admin_notify (module global at runtime). Guarded
# so re-running is a no-op.
data = open("web_app.py", "rb").read()
orig = data
changed = []
missing = []  # hooks that were neither applied nor already present -> fail loud

# ── Hook 1a: capture the error_logs INSERT cursor ──
a1 = (b'            c.execute(\r\n'
      b'                "INSERT INTO error_logs (request_id, route, method, status, "')
b1 = (b'            _enq_cur = c.execute(\r\n'
      b'                "INSERT INTO error_logs (request_id, route, method, status, "')
if b'_enq_cur = c.execute(' in data:
    print("SKIP hook1a: already patched")
elif a1 in data:
    data = data.replace(a1, b1, 1); changed.append("hook1a")
else:
    missing.append("hook1a")

# ── Hook 1b: notify on recorded 500s ──
a2 = (b'                 stack_trace, ip, ua, user_id, tenant_id, fingerprint),\r\n'
      b'            )\r\n'
      b'    except Exception as _e:')
b2 = (b'                 stack_trace, ip, ua, user_id, tenant_id, fingerprint),\r\n'
      b'            )\r\n'
      b'            _err_id = getattr(_enq_cur, "lastrowid", None)\r\n'
      b'        try:\r\n'
      b'            if int(status or 500) >= 500:\r\n'
      b'                _admin_notify("error", "critical",\r\n'
      b'                              (error_type or "Application error") + " - " + (route or ""),\r\n'
      b'                              (error_message or "")[:400], ref_type="error_log",\r\n'
      b'                              ref_id=_err_id, fingerprint=fingerprint, tenant_id=tenant_id)\r\n'
      b'        except Exception:\r\n'
      b'            pass\r\n'
      b'    except Exception as _e:')
if b'_admin_notify("error", "critical",' in data:
    print("SKIP hook1b: already patched")
elif a2 in data:
    data = data.replace(a2, b2, 1); changed.append("hook1b")
else:
    missing.append("hook1b")

# ── Hook 2: notify on helpline escalation ──
a3 = (b'        tid = c.execute("SELECT last_insert_rowid()").fetchone()[0]\r\n'
      b'\r\n'
      b'    return jsonify({"ok": True, "ticket_id": tid})')
b3 = (b'        tid = c.execute("SELECT last_insert_rowid()").fetchone()[0]\r\n'
      b'\r\n'
      b'    try:\r\n'
      b'        _admin_notify("ticket", "warning", "Escalated helpline ticket #" + str(tid),\r\n'
      b'                      subject, ref_type="ticket", ref_id=tid)\r\n'
      b'    except Exception:\r\n'
      b'        pass\r\n'
      b'    return jsonify({"ok": True, "ticket_id": tid})')
if b'Escalated helpline ticket #' in data:
    print("SKIP hook2: already patched")
elif a3 in data:
    data = data.replace(a3, b3, 1); changed.append("hook2")
else:
    missing.append("hook2")

if missing:
    # Fail loud: these hooks are the source of real 500/ticket notifications.
    # A silent miss would ship an inbox that never populates from faults.
    raise SystemExit("FAIL: producer-hook anchors not found (web_app.py line "
                     "endings changed?): " + ", ".join(missing))

if data != orig:
    open("web_app.py", "wb").write(data)
    print("OK: applied", changed)
else:
    print("NO CHANGE")
