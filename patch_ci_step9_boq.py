# -*- coding: utf-8 -*-
"""
patch_ci_step9_boq.py
=====================
Generation Station Design revision - Task 1 (highest-leverage per the
System Solution Specification SSS_generation_station_design_2026-07-02.md).

Makes Capital Investment Step 9 build a REAL BOQ hierarchy that REUSES the
existing platform BOQ engine instead of leaving an empty shell:

  * derive existing _BOQ_SERVICES codes from facility + technology +
    electrical selections (facility -> BOQ section mapping, SSS section 4),
  * set boq_projects.services_csv so Section-by-Section / Build-all load
    the mapped sections,
  * create one boq_buildings + Ground Floor boq_floors row per facility,
  * write capital_investment_boq_links for traceability + idempotency,
  * add an eager, VERIFIED migration for the link table (no silent-DDL trap).

Byte-level, CRLF-aware patch (new_capital_investment_routes.py is CRLF with
some non-ASCII bytes, so we do NOT use a text editor on it).
"""

PATH = "new_capital_investment_routes.py"


def crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


data = open(PATH, "rb").read()
orig_len = len(data)

# ---------------------------------------------------------------------------
# R1 - facility/technology/electrical -> BOQ service-code mapping + helpers.
# Inserted right after ELECTRICAL_SERVICE_CODES.
# ---------------------------------------------------------------------------
R1_ANCHOR = crlf(
    "ELECTRICAL_SERVICE_CODES: set[str] = "
    "{c for c, _, _, _ in ELECTRICAL_SERVICES}\r\n"
)
assert data.count(R1_ANCHOR) == 1, "R1 anchor not unique"

R1_BLOCK = crlf('''

# ---------------------------------------------------------------------------
# Facility / technology / electrical  ->  existing BOQ service-code mapping.
#
# The Generation Station module REUSES the platform BOQ engine. Step 9 turns
# the wizard selections into the SAME service codes the standard BOQ engine
# uses (web_app._BOQ_SERVICES), so an auto-generated BOQ project loads real
# Section-by-Section / Build-all sections instead of an empty shell.
# Source: SSS_generation_station_design_2026-07-02.md section 4.
# ---------------------------------------------------------------------------

# Canonical non-medical BOQ service codes, in web_app._BOQ_SERVICES order, so
# the generated services_csv is deterministic. Medical services (nurse_call,
# medical_equip) are intentionally excluded from generation-plant scope.
_CI_BOQ_SERVICE_ORDER: list[str] = [
    "internal_electrical", "fire_alarm", "earthing_bonding",
    "lightning_protection", "power_supply_lv", "lan_wlan", "it_server_room",
    "voip", "ip_pa", "ip_cctv", "tv_system", "ip_clock", "bms",
]
_CI_BOQ_SERVICE_SET: set[str] = set(_CI_BOQ_SERVICE_ORDER)

# Every enabled building gets at least this baseline electrical scope.
_CI_FACILITY_DEFAULT_SERVICES: list[str] = [
    "internal_electrical", "power_supply_lv", "fire_alarm", "earthing_bonding",
]

# Building code -> BOQ service codes (SSS section 4 facility mapping).
FACILITY_BOQ_SERVICES: dict[str, list[str]] = {
    "control_room":     ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "ip_cctv", "voip",
                         "ip_pa", "earthing_bonding", "lightning_protection",
                         "bms"],
    "om_building":      ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "fire_alarm", "ip_cctv", "voip", "earthing_bonding",
                         "bms"],
    "security_gate":    ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "ip_cctv", "voip", "fire_alarm", "earthing_bonding"],
    "battery_room":     ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "it_server_room", "earthing_bonding",
                         "lightning_protection", "bms"],
    "inverter_room":    ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "earthing_bonding", "bms"],
    "switchgear_bldg":  ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "lan_wlan", "ip_cctv", "earthing_bonding",
                         "lightning_protection", "bms"],
    "transformer_bldg": ["power_supply_lv", "earthing_bonding",
                         "lightning_protection", "ip_cctv",
                         "internal_electrical"],
    "scada_bldg":       ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "ip_cctv", "voip",
                         "earthing_bonding", "lightning_protection", "bms"],
    "comms_bldg":       ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "it_server_room", "fire_alarm", "earthing_bonding",
                         "lightning_protection"],
    "spare_parts":      ["internal_electrical", "fire_alarm", "ip_cctv",
                         "lan_wlan", "earthing_bonding"],
    "workshop":         ["internal_electrical", "power_supply_lv", "lan_wlan",
                         "fire_alarm", "ip_cctv", "earthing_bonding"],
    "welfare":          ["internal_electrical", "power_supply_lv", "fire_alarm",
                         "earthing_bonding"],
    "washroom":         ["internal_electrical", "power_supply_lv",
                         "earthing_bonding"],
}

# Technology code -> BOQ service codes (SSS section 4 technology mapping).
TECHNOLOGY_BOQ_SERVICES: dict[str, list[str]] = {
    "scada":        ["lan_wlan", "it_server_room", "bms", "power_supply_lv"],
    "ems":          ["it_server_room", "lan_wlan", "bms"],
    "ppc":          ["it_server_room", "lan_wlan", "bms"],
    "weather":      ["lan_wlan", "power_supply_lv", "earthing_bonding",
                     "lightning_protection"],
    "string_mon":   ["lan_wlan", "power_supply_lv", "bms"],
    "energy_meter": ["power_supply_lv", "lan_wlan"],
    "pq_meter":     ["power_supply_lv", "lan_wlan"],
    "bms":          ["bms", "lan_wlan", "power_supply_lv", "fire_alarm"],
    "txfr_mon":     ["bms", "lan_wlan", "power_supply_lv"],
    "inv_mon":      ["bms", "lan_wlan"],
    "remote_mon":   ["lan_wlan", "it_server_room"],
    "cloud_mon":    ["lan_wlan", "it_server_room"],
    "thermal_cam":  ["ip_cctv", "lan_wlan", "power_supply_lv"],
    "ai_fault":     ["it_server_room", "lan_wlan", "bms"],
    "predictive":   ["bms", "it_server_room", "lan_wlan"],
    "gis":          ["it_server_room", "lan_wlan"],
    "asset_mgmt":   ["it_server_room", "lan_wlan"],
    "cmms":         ["it_server_room", "lan_wlan"],
    "scheduler":    ["it_server_room", "lan_wlan"],
    "wo_mgmt":      ["it_server_room", "lan_wlan"],
    "cyber":        ["lan_wlan", "it_server_room"],
    "firewall":     ["lan_wlan", "it_server_room"],
    "ind_eth":      ["lan_wlan"],
    "fibre":        ["lan_wlan"],
    "ind_wifi":     ["lan_wlan"],
    "gps_sync":     ["lan_wlan", "it_server_room"],
    "ntp":          ["it_server_room", "lan_wlan"],
    "ind_servers":  ["it_server_room"],
    "storage_srv":  ["it_server_room"],
    "backup_srv":   ["it_server_room"],
    "cloud_backup": ["it_server_room", "lan_wlan"],
    "dr":           ["it_server_room", "lan_wlan"],
    "digital_twin": ["it_server_room", "lan_wlan", "bms"],
    # drone_insp, spares -> no default BOQ service (procurement/marketplace).
}

# Module electrical-service code -> BOQ service code(s) (SSS section 5 Step 6).
ELECTRICAL_TO_BOQ_SERVICE: dict[str, list[str]] = {
    "internal_installation": ["internal_electrical"],
    "power_supply":          ["power_supply_lv"],
    "hv_distribution":       ["power_supply_lv"],
    "lv_distribution":       ["power_supply_lv"],
    "dc_collection":         ["power_supply_lv"],
    "ac_collection":         ["power_supply_lv"],
    "inverters":             ["power_supply_lv"],
    "transformers":          ["power_supply_lv"],
    "rmu":                   ["power_supply_lv"],
    "hv_switchgear":         ["power_supply_lv"],
    "lv_switchgear":         ["power_supply_lv"],
    "earthing":              ["earthing_bonding"],
    "lightning_protection":  ["lightning_protection"],
    "external_lighting":     ["power_supply_lv"],
    "fire_alarm":            ["fire_alarm"],
    "ip_cctv":               ["ip_cctv"],
    "access_control":        ["ip_cctv"],
    "voip":                  ["voip"],
    "public_address":        ["ip_pa"],
    "tv":                    ["tv_system"],
    "ip_clock":              ["ip_clock"],
    "lan":                   ["lan_wlan"],
    "wan":                   ["lan_wlan"],
    "server_infra":          ["it_server_room"],
    "scada":                 ["bms"],
}

# External works -> shared site-wide BOQ scope (added once if any selected).
EXTERNAL_WORKS_BOQ_SERVICES: list[str] = [
    "power_supply_lv", "earthing_bonding", "lightning_protection",
    "ip_cctv", "lan_wlan", "internal_electrical",
]


def _ci_facility_services(building_code: str) -> list[str]:
    """BOQ service codes for one facility/building; defaults to a baseline
    electrical scope for buildings without an explicit mapping."""
    return FACILITY_BOQ_SERVICES.get(
        building_code, _CI_FACILITY_DEFAULT_SERVICES,
    )


def _ci_order_services(codes) -> list[str]:
    """De-duplicate + restrict to valid BOQ codes + return in canonical
    _CI_BOQ_SERVICE_ORDER order for a stable services_csv."""
    have = {c for c in codes if c in _CI_BOQ_SERVICE_SET}
    return [c for c in _CI_BOQ_SERVICE_ORDER if c in have]


def _ci_derive_boq_services(fac_cfg: dict, tech_cfg: dict,
                            elec_cfg: dict) -> list[str]:
    """Union of BOQ service codes implied by facility buildings, external
    works, technology and electrical selections - ordered + valid."""
    codes: list[str] = []
    for b in (fac_cfg.get("buildings") or []):
        codes.extend(_ci_facility_services(b))
    if fac_cfg.get("external_works"):
        codes.extend(EXTERNAL_WORKS_BOQ_SERVICES)
    for t in (tech_cfg.get("selected") or []):
        codes.extend(TECHNOLOGY_BOQ_SERVICES.get(t, []))
    for e in (elec_cfg.get("selected") or []):
        codes.extend(ELECTRICAL_TO_BOQ_SERVICE.get(e, []))
    return _ci_order_services(codes)
''')

data = data.replace(R1_ANCHOR, R1_ANCHOR + R1_BLOCK, 1)

# ---------------------------------------------------------------------------
# R2 - eager VERIFIED migration for capital_investment_boq_links.
# Inserted right after the _ensure_capital_investment_schema function.
# ---------------------------------------------------------------------------
R2_ANCHOR = crlf(
    "    for ddl in _CIP_POSTGRES_MIGRATIONS:\r\n"
    "        try:\r\n"
    "            with get_db() as c:\r\n"
    "                c.execute(ddl)\r\n"
    "        except Exception:\r\n"
    "            pass\r\n"
)
assert data.count(R2_ANCHOR) == 1, "R2 anchor not unique"

R2_BLOCK = crlf('''

# ---------------------------------------------------------------------------
# capital_investment_boq_links - traceability + idempotency between a capital
# investment project's facilities and the generated BOQ buildings/floors.
# Source: SSS_generation_station_design_2026-07-02.md section 3.3.
# ---------------------------------------------------------------------------
_CIBL_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_boq_links (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    tenant_id                     TEXT,
    facility_code                 TEXT NOT NULL,
    source_kind                   TEXT NOT NULL DEFAULT 'facility',
    boq_project_id                INTEGER NOT NULL,
    boq_building_id               INTEGER,
    boq_floor_id                  INTEGER,
    service_codes_csv             TEXT DEFAULT '',
    created_at                    TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(capital_investment_project_id, facility_code, source_kind)
);
CREATE INDEX IF NOT EXISTS idx_cibl_project     ON capital_investment_boq_links(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_boq_project ON capital_investment_boq_links(boq_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_user        ON capital_investment_boq_links(user_id);
CREATE INDEX IF NOT EXISTS idx_cibl_tenant      ON capital_investment_boq_links(tenant_id);
"""

_CIBL_POSTGRES_DDL = """
CREATE TABLE IF NOT EXISTS capital_investment_boq_links (
    id                            SERIAL PRIMARY KEY,
    capital_investment_project_id INTEGER NOT NULL,
    user_id                       INTEGER NOT NULL,
    tenant_id                     UUID,
    facility_code                 TEXT NOT NULL,
    source_kind                   TEXT NOT NULL DEFAULT 'facility',
    boq_project_id                INTEGER NOT NULL,
    boq_building_id               INTEGER,
    boq_floor_id                  INTEGER,
    service_codes_csv             TEXT DEFAULT '',
    created_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(capital_investment_project_id, facility_code, source_kind)
);
CREATE INDEX IF NOT EXISTS idx_cibl_project     ON capital_investment_boq_links(capital_investment_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_boq_project ON capital_investment_boq_links(boq_project_id);
CREATE INDEX IF NOT EXISTS idx_cibl_user        ON capital_investment_boq_links(user_id);
CREATE INDEX IF NOT EXISTS idx_cibl_tenant      ON capital_investment_boq_links(tenant_id);
"""

# Verification result, remembered so a failed live-PG migration is observable
# rather than silently swallowed on every request.
_CIBL_SCHEMA_STATE: dict[str, object] = {"ready": False, "error": ""}


def _ensure_capital_investment_boq_links_schema(get_db) -> bool:
    """Eager, idempotent, per-statement schema creation for the BOQ link
    table WITH verification. Unlike a silent lazy _ensure_*, this VERIFIES the
    table is queryable and remembers the result (see _CIBL_SCHEMA_STATE), so a
    failed live-PostgreSQL migration surfaces instead of being swallowed.
    Returns True when the table is confirmed present + queryable."""
    if _CIBL_SCHEMA_STATE["ready"]:
        return True
    # SQLite fast path (executescript is Postgres-hostile -> falls through).
    try:
        with get_db() as c:
            c.executescript(_CIBL_SQLITE_DDL)
    except Exception:
        # Postgres path - one statement per transaction so an index conflict
        # cannot abort the CREATE TABLE.
        for stmt in _CIBL_POSTGRES_DDL.split(";"):
            s = stmt.strip()
            if not s:
                continue
            try:
                with get_db() as c:
                    c.execute(s)
            except Exception:
                pass
    # Verify the table is actually queryable before declaring success.
    try:
        with get_db() as c:
            c.execute("SELECT 1 FROM capital_investment_boq_links LIMIT 1")
        _CIBL_SCHEMA_STATE["ready"] = True
        _CIBL_SCHEMA_STATE["error"] = ""
    except Exception as exc:
        _CIBL_SCHEMA_STATE["ready"] = False
        _CIBL_SCHEMA_STATE["error"] = str(exc)[:300]
    return bool(_CIBL_SCHEMA_STATE["ready"])


class _CIGenerationRaceLost(Exception):
    """Raised inside the Step 9 create+claim transaction when a concurrent
    request already claimed BOQ generation for this project. Raising (rather
    than returning) rolls back the orphan boq_projects row via get_db()'s
    exception-rollback, so no partial/duplicate BOQ is left behind."""
''')

data = data.replace(R2_ANCHOR, R2_ANCHOR + R2_BLOCK, 1)

# ---------------------------------------------------------------------------
# R3 - rewrite the Step 9 POST body (from "# 1. Create the boq_projects row."
# up to but NOT including the GET "return render_template(...)").
# ---------------------------------------------------------------------------
R3_START = crlf("            # 1. Create the boq_projects row.\r\n")
R3_END = crlf('        return render_template(\r\n')
start = data.find(R3_START)
assert start != -1, "R3 start anchor missing"
end = data.find(R3_END, start)
assert end != -1, "R3 end anchor missing"

R3_NEW = crlf('''            # 0. Derive the BOQ service codes this plant needs from the
            #    facility, technology and electrical selections. REUSES the
            #    existing _BOQ_SERVICES codes so the generated BOQ project
            #    loads real Section-by-Section / Build-all sections.
            tech_cfg = _safe_json(proj.get("technology_config"))
            service_codes = _ci_derive_boq_services(fac_cfg, tech_cfg, elec_cfg)
            services_csv = ",".join(service_codes)
            # Tenant context from the canonical BOQ-engine source (JWT), not
            # the user row - matches web_app._boq_tenant_clause reads.
            try:
                from web_app import _kc_current_tenant_id as _kc_tid
                tenant_id = _kc_tid()
            except Exception:
                tenant_id = None

            # Eager + VERIFIED link-table migration. Honour the boolean so a
            # failed live-PG migration is observable, not silently swallowed.
            links_ready = False
            try:
                links_ready = bool(
                    _ensure_capital_investment_boq_links_schema(get_db))
            except Exception:
                links_ready = False

            project_name = (
                f"{proj['project_name']} - Capital Investment BOQ"
            )[:300]
            location = ", ".join(x for x in (proj.get("region"),
                                             proj.get("country")) if x)[:300]
            external_flag = 1 if selected_external else 0
            built_floors: list = []
            link_errors = 0
            new_boq_pid = 0

            # Create + claim + build in ONE transaction. get_db() rolls back on
            # any exception (both SQLite and the psycopg2 adapter), so a lost
            # race or a mid-build failure leaves boq_project_id NULL with no
            # orphan row - and boq_project_id goes straight NULL -> real id
            # (no leaky -1 sentinel that templates would render as "#-1").
            try:
                with get_db() as c:
                    # 1. Linked boq_projects row WITH services_csv + tenant_id.
                    try:
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, tenant_id, project_name, client_name, "
                            " location, project_type, external_works_included, "
                            " infrastructure_included, services_csv) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (uid, tenant_id, project_name,
                             proj.get("client_name") or "", location, "campus",
                             external_flag, 1, services_csv),
                        )
                    except Exception:
                        # Older schema without tenant_id / services_csv.
                        cur = c.execute(
                            "INSERT INTO boq_projects "
                            "(user_id, project_name, client_name, location, "
                            " project_type, external_works_included, "
                            " infrastructure_included) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (uid, project_name, proj.get("client_name") or "",
                             location, "campus", external_flag, 1),
                        )
                    new_boq_pid = int(cur.lastrowid or 0)

                    # 2. Atomic claim: set boq_project_id to the REAL id only
                    #    if still unset. rowcount != 1 means a concurrent POST
                    #    won - raise to roll back this orphan boq_projects row.
                    cclaim = c.execute(
                        "UPDATE capital_investment_projects "
                        "SET boq_project_id=? WHERE id=? AND user_id=? AND "
                        "(boq_project_id IS NULL OR boq_project_id=0)",
                        (new_boq_pid, pid, uid),
                    )
                    if int(getattr(cclaim, "rowcount", 0) or 0) != 1:
                        raise _CIGenerationRaceLost()

                    # 3. One boq_buildings + Ground Floor per enabled facility.
                    for b in selected_buildings:
                        label = next(
                            (L for cd, L, _, _ in BUILDING_TYPES if cd == b), b,
                        )
                        b_services = _ci_facility_services(b)
                        bid = 0
                        try:
                            bcur = c.execute(
                                "INSERT INTO boq_buildings "
                                "(project_id, tenant_id, building_name, "
                                " building_code, primary_purpose, "
                                " purpose_subtype, building_area, "
                                " number_of_floors, basement_included, "
                                " roof_level_included, external_area_included) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (new_boq_pid, tenant_id, label, b.upper(),
                                 "commercial", b, 0, 1, 0, 1, 0),
                            )
                            bid = int(bcur.lastrowid or 0)
                        except Exception:
                            try:
                                bcur = c.execute(
                                    "INSERT INTO boq_buildings "
                                    "(project_id, building_name, "
                                    " building_code, number_of_floors) "
                                    "VALUES (?,?,?,?)",
                                    (new_boq_pid, label, b.upper(), 1),
                                )
                                bid = int(bcur.lastrowid or 0)
                            except Exception:
                                bid = 0

                        # 4. Ground Floor (standard boq_floors shape).
                        fid = 0
                        if bid:
                            try:
                                fcur = c.execute(
                                    "INSERT INTO boq_floors "
                                    "(building_id, project_id, tenant_id, "
                                    " floor_name, floor_level, floor_type) "
                                    "VALUES (?,?,?,?,?,?)",
                                    (bid, new_boq_pid, tenant_id,
                                     "Ground Floor", 0, "ground"),
                                )
                                fid = int(fcur.lastrowid or 0)
                            except Exception:
                                try:
                                    fcur = c.execute(
                                        "INSERT INTO boq_floors "
                                        "(building_id, project_id, floor_name, "
                                        " floor_level, floor_type) "
                                        "VALUES (?,?,?,?,?)",
                                        (bid, new_boq_pid, "Ground Floor", 0,
                                         "ground"),
                                    )
                                    fid = int(fcur.lastrowid or 0)
                                except Exception:
                                    fid = 0
                        if fid:
                            built_floors.append((bid, fid, list(b_services)))

                        # 5. Traceability link - only when the schema verified;
                        #    count failures so they surface (never swallowed).
                        if links_ready:
                            try:
                                c.execute(
                                    "INSERT INTO capital_investment_boq_links "
                                    "(capital_investment_project_id, user_id, "
                                    " tenant_id, facility_code, source_kind, "
                                    " boq_project_id, boq_building_id, "
                                    " boq_floor_id, service_codes_csv) "
                                    "VALUES (?,?,?,?,?,?,?,?,?)",
                                    (pid, uid, tenant_id, b, "facility",
                                     new_boq_pid, bid or None, fid or None,
                                     ",".join(_ci_order_services(b_services))),
                                )
                            except Exception:
                                link_errors += 1
            except _CIGenerationRaceLost:
                # A concurrent POST won; our orphan boq_projects row was rolled
                # back by get_db()'s exception handler. Nothing to clean up.
                flash("BOQ generation is already in progress or complete for "
                      "this project.", "info")
                return redirect(url_for("capital_investment_project", pid=pid))
            except Exception:
                # Whole transaction rolled back - boq_project_id stays NULL so
                # the user can retry cleanly. Nothing partial is left behind.
                try:
                    from flask import current_app
                    current_app.logger.exception(
                        "capital step9 BOQ creation failed for pid=%s", pid)
                except Exception:
                    pass
                flash("BOQ generation failed - nothing was linked. Please try "
                      "again; the error was logged.", "danger")
                return redirect(url_for("capital_investment_step9", pid=pid))

            # 6. Auto-build the cell-level BOQ line items for every generated
            #    floor, REUSING the standard catalog + boq_rate_v3
            #    (web_app._ci_autobuild_floor_items). Runs AFTER the insert
            #    transaction closes to avoid a nested DB connection. Failures
            #    are logged + surfaced, never silently swallowed.
            items_built = 0
            try:
                from web_app import _ci_autobuild_floor_items as _autobuild
            except Exception:
                _autobuild = None
            if _autobuild:
                for _bid, _fid, _svcs in built_floors:
                    try:
                        items_built += int(
                            _autobuild(_fid, _bid, new_boq_pid, uid, _svcs)
                            or 0)
                    except Exception:
                        try:
                            from flask import current_app
                            current_app.logger.exception(
                                "capital step9 autobuild floor=%s failed", _fid)
                        except Exception:
                            pass

            # boq_project_id was already set atomically in the claim above -
            # no _save_project_field needed (that is what removed the -1 leak).
            notes = []
            if not links_ready or link_errors:
                notes.append("facility links unavailable - see admin diagnostics")
            suffix = (" (" + "; ".join(notes) + ")") if notes else ""
            if service_codes and items_built == 0:
                flash(
                    f"Linked BOQ project #{new_boq_pid} created with "
                    f"{len(selected_buildings)} building(s) and "
                    f"{len(service_codes)} service(s), but line items could "
                    f"NOT be auto-priced - open the BOQ and use Build-all to "
                    f"add them." + suffix,
                    "warning",
                )
            else:
                flash(
                    f"Linked BOQ project #{new_boq_pid} created: "
                    f"{len(selected_buildings)} building(s), "
                    f"{len(service_codes)} service(s), {items_built} priced "
                    f"line item(s) pre-loaded. Open it to review or edit."
                    + suffix,
                    "success",
                )
            return redirect(url_for("capital_investment_project", pid=pid))

''')

data = data[:start] + R3_NEW + data[end:]

open(PATH, "wb").write(data)
print("patched OK  orig=%d  new=%d  delta=%+d" % (
    orig_len, len(data), len(data) - orig_len))
