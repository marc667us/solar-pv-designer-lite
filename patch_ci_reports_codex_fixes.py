"""Codex review fixes (2026-07-03) for new_capital_investment_routes.py.

MED: report builder could still 500 on partially-malformed stored JSON (nested
     value stored as the wrong type, e.g. `"computed":"x"` or `"buildings":1`).
     _safe_json only guarantees the TOP level is a dict. Normalize every nested
     value the report branches read to its expected type, once, up-front - this
     covers both the pre-existing and the new report branches.

LOW: the Step 9 legacy-schema fallback INSERTs still used cur.lastrowid. Convert
     them to RETURNING id too (defense-in-depth for legacy Postgres schemas);
     the create /new path already proves RETURNING id is available everywhere
     this app runs.
"""
FN = "new_capital_investment_routes.py"
data = open(FN, "rb").read()
orig = data
def crlf(s): return s.replace("\n", "\r\n").encode("utf-8")
log = []
def repl(old, new, tag, required=True):
    global data
    n = data.count(old)
    if n == 1:
        data = data.replace(old, new); log.append(f"[OK]   {tag}")
    elif data.count(new) >= 1 and n == 0:
        log.append(f"[skip] {tag} (already applied)")
    else:
        log.append(f"[MISS] {tag} (count={n})")
        if required:
            raise SystemExit("\n".join(log) + f"\nABORT: {tag}")

# --- MED: nested-type normalization -----------------------------------------
old_norm = crlf('''    boq = boq or {}
    _boq_linked = bool(boq.get("linked"))
    _fac_list = fac.get("buildings") or []
    _tech_list = tech.get("selected") or []
    _elec_list = elec.get("selected") or []
    def _lbl(code: str) -> str:
        return str(code).replace("_", " ").title()
    def _bullets(items, empty="(none configured)"):
        items = list(items or [])
        return "\\n".join(f"- {_lbl(x)}" for x in items) if items else empty
''')
new_norm = crlf('''    boq = boq if isinstance(boq, dict) else {}
    # Harden against partially-malformed stored JSON so a report NEVER 500s:
    # _safe_json only guarantees the top level is a dict, so coerce every
    # nested value the branches read to its expected type (covers pre-existing
    # and new branches alike).
    def _D(x):
        return x if isinstance(x, dict) else {}
    def _L(x):
        return x if isinstance(x, list) else []
    sizing = _D(sizing)
    computed = _D(computed)
    computed["capex_lines_usd"] = _D(computed.get("capex_lines_usd"))
    computed["opex_lines_usd_yr"] = _D(computed.get("opex_lines_usd_yr"))
    computed["monte_carlo"] = _D(computed.get("monte_carlo"))
    fac["buildings"] = _L(fac.get("buildings"))
    tech["selected"] = _L(tech.get("selected"))
    elec["selected"] = _L(elec.get("selected"))
    reg["items"] = _D(reg.get("items"))
    _boq_linked = bool(boq.get("linked"))
    _fac_list = fac["buildings"]
    _tech_list = tech["selected"]
    _elec_list = elec["selected"]
    def _lbl(code) -> str:
        return str(code).replace("_", " ").title()
    def _bullets(items, empty="(none configured)"):
        items = _L(items)
        return "\\n".join(f"- {_lbl(x)}" for x in items) if items else empty
''')
repl(old_norm, new_norm, "MED nested-JSON normalization")

# --- LOW: RETURNING id on the 3 Step 9 legacy fallbacks ---------------------
# boq_projects legacy fallback
old_bp = crlf('''                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, project_name, client_name, location, "
                            " project_type, external_works_included, "
                            " infrastructure_included) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (uid, project_name, proj.get("client_name") or "",
                             location, "campus", external_flag, 1),
                        )
                    new_boq_pid = int(cur.lastrowid or 0)''')
new_bp = crlf('''                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, project_name, client_name, location, "
                            " project_type, external_works_included, "
                            " infrastructure_included) "
                            "VALUES (?,?,?,?,?,?,?) RETURNING id",
                            (uid, project_name, proj.get("client_name") or "",
                             location, "campus", external_flag, 1),
                        )
                        _rr2 = cur.fetchone()
                        if _rr2:
                            cur = _RetId(int(_rr2[0]))
                    new_boq_pid = int(cur.lastrowid or 0)''')
repl(old_bp, new_bp, "LOW boq_projects legacy RETURNING id")

# boq_buildings legacy fallback
old_bb = crlf('''                                bcur = c.execute(
                                    "INSERT INTO boq_buildings "
                                    "(project_id, building_name, "
                                    " building_code, number_of_floors) "
                                    "VALUES (?,?,?,?)",
                                    (new_boq_pid, label, b.upper(), 1),
                                )
                                bid = int(bcur.lastrowid or 0)''')
new_bb = crlf('''                                bcur = c.execute(
                                    "INSERT INTO boq_buildings "
                                    "(project_id, building_name, "
                                    " building_code, number_of_floors) "
                                    "VALUES (?,?,?,?) RETURNING id",
                                    (new_boq_pid, label, b.upper(), 1),
                                )
                                _br2 = bcur.fetchone()
                                bid = int(_br2[0]) if _br2 else int(bcur.lastrowid or 0)''')
repl(old_bb, new_bb, "LOW boq_buildings legacy RETURNING id")

# boq_floors legacy fallback
old_bf = crlf('''                                    fcur = c.execute(
                                        "INSERT INTO boq_floors "
                                        "(building_id, project_id, floor_name, "
                                        " floor_level, floor_type) "
                                        "VALUES (?,?,?,?,?)",
                                        (bid, new_boq_pid, "Ground Floor", 0,
                                         "ground"),
                                    )
                                    fid = int(fcur.lastrowid or 0)''')
new_bf = crlf('''                                    fcur = c.execute(
                                        "INSERT INTO boq_floors "
                                        "(building_id, project_id, floor_name, "
                                        " floor_level, floor_type) "
                                        "VALUES (?,?,?,?,?) RETURNING id",
                                        (bid, new_boq_pid, "Ground Floor", 0,
                                         "ground"),
                                    )
                                    _fr2 = fcur.fetchone()
                                    fid = int(_fr2[0]) if _fr2 else int(fcur.lastrowid or 0)''')
repl(old_bf, new_bf, "LOW boq_floors legacy RETURNING id")

if data == orig:
    print("\n".join(log)); print("\nNO CHANGES")
else:
    open(FN, "wb").write(data)
    print("\n".join(log)); print(f"\nWROTE {FN} ({len(orig)} -> {len(data)} bytes)")
