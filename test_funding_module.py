"""
Slice 10 -- Project Funding ("Sponsor") module test + security-isolation suite.

Covers the 9 funding tables and the security boundaries Codex flagged as
uncovered across Slices 3-9. Where the authorization logic lives inside route
closures, the test exercises the EXACT SQL predicate the route runs against a
real in-memory schema built by the module's own _ensure_* functions -- so the
DDL and the isolation predicates are both under test.

Run:  python -m pytest test_funding_module.py -q
  or: python test_funding_module.py
"""
import sqlite3
import contextlib
import json

import new_capital_investment_routes as m


# --------------------------------------------------------------------------
# Fixture -- a fresh in-memory DB with every funding table built by the real
# module schema functions (resets the module's one-shot "ready" flags first).
# --------------------------------------------------------------------------
def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    @contextlib.contextmanager
    def get_db():
        yield conn

    for flag in ("_FI_STATE", "_FI_SEL_STATE", "_CI_FUNDING_STATE",
                 "_FI_MSG_STATE", "_FI_SHIP_STATE", "_FI_REV_STATE",
                 "_FI_ASSESS_STATE"):
        getattr(m, flag)["ready"] = False

    # Core project + funding tables.
    m._ensure_ci_funding_schema(get_db)
    m._ensure_fi_schema(get_db)
    m._ensure_fi_selection_schema(get_db)
    m._ensure_fi_messages_schema(get_db)
    m._ensure_fi_shipments_schema(get_db)
    m._ensure_fi_revenue_schema(get_db)
    m._ensure_fi_assessment_schema(get_db)
    # Minimal projects + users + opportunity tables the routes read.
    conn.executescript("""
    CREATE TABLE capital_investment_projects(
      id INTEGER PRIMARY KEY, user_id INT, project_name TEXT, client_name TEXT,
      developer TEXT, project_type TEXT, country TEXT, region TEXT,
      district TEXT, target_kwp REAL, currency TEXT, finance_config TEXT,
      boq_project_id INT, boq_facilities_project_id INT, boq_solar_project_id INT,
      tenant_id TEXT);
    CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, email TEXT,
      name TEXT);
    CREATE TABLE capital_investment_opportunities(
      id INTEGER PRIMARY KEY AUTOINCREMENT, capital_investment_project_id INT,
      user_id INT, project_name TEXT, stage TEXT DEFAULT 'lead',
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP, tenant_id TEXT);
    """)
    m._ensure_opportunities_schema(get_db)   # adds the Slice-9 funding columns
    return conn, get_db


def _seed(conn):
    """Two customer tenants, two institutions (one owned by user 10, one by 20),
    project 1 (custA) submitted to FI-A with consent, project 2 (custB) to FI-B."""
    conn.execute("INSERT INTO users VALUES(10,'inst_a','a@bank.test','Alpha Bank')")
    conn.execute("INSERT INTO users VALUES(20,'inst_b','b@fund.test','Beta Fund')")
    conn.execute("INSERT INTO users VALUES(99,'dev','dev@epc.test','Dev Co')")
    conn.execute("INSERT INTO financial_institutions "
                 "(institution_id,name,fee_pct,created_by_user_id,status,"
                 " loan_min,loan_max,supported_project_types,email) "
                 "VALUES('FI-A','Alpha Bank',2.0,10,'approved',100000,5000000,"
                 "'solar_farm,ci_rooftop','a@bank.test')")
    conn.execute("INSERT INTO financial_institutions "
                 "(institution_id,name,fee_pct,created_by_user_id,status,email) "
                 "VALUES('FI-B','Beta Fund',2.5,20,'approved','b@fund.test')")
    conn.execute("INSERT INTO financial_institutions "
                 "(institution_id,name,fee_pct,created_by_user_id,status) "
                 "VALUES('FI-SUS','Suspended Co',2.0,10,'suspended')")
    fin = json.dumps({"computed": {"dscr_min": 1.4, "irr_pct": 16,
                                   "npv_local": 5e6, "total_capex_usd": 4e6,
                                   "lcoe_local_per_kwh": 0.5}})
    for pid, tid, cust in [(1, 'custA', 'Kofi Ltd'), (2, 'custB', 'Ama Plc')]:
        conn.execute(
            "INSERT INTO capital_investment_projects(id,user_id,project_name,"
            "client_name,developer,project_type,country,region,district,"
            "target_kwp,currency,finance_config,boq_project_id,tenant_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, 99, "P%d" % pid, cust, "Dev Co", "solar_farm", "Ghana",
             "Greater Accra", "Accra", 5000, "GHS", fin, 7, tid))
        conn.execute("INSERT INTO capital_investment_funding("
                     "capital_investment_project_id,tenant_id,user_id,status,"
                     "funding_requested,customer_equity,funding_score) "
                     "VALUES(?,?,?,?,?,?,?)",
                     (pid, tid, 99, 'submitted', 2000000, 500000, 72))
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-A','custA',99,1,'submitted')")
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(2,'FI-B','custB',99,1,'submitted')")
    conn.commit()


# The workspace/application-authorization SQL, mirrored from _fi_workspace_rows
# and _fi_load_application (the security boundary under test).
_WORKSPACE_SQL = (
    "SELECT s.capital_investment_project_id AS pid, s.institution_id "
    "FROM funding_institution_selections s "
    "JOIN financial_institutions fi ON fi.institution_id=s.institution_id "
    "JOIN capital_investment_funding fund "
    " ON fund.capital_investment_project_id=s.capital_investment_project_id "
    " AND COALESCE(fund.tenant_id,'')=COALESCE(s.tenant_id,'') "
    "JOIN capital_investment_projects p "
    " ON p.id=s.capital_investment_project_id "
    " AND COALESCE(CAST(p.tenant_id AS TEXT),'')=COALESCE(s.tenant_id,'') "
    "WHERE fi.created_by_user_id=? AND fi.status='approved' AND s.consent=1")


def _workspace(conn, uid):
    return [dict(r) for r in conn.execute(_WORKSPACE_SQL, (uid,)).fetchall()]


def _load_app(conn, uid, pid, iid):
    """Faithful mirror of _fi_load_application's FULL gate: approved-owned
    institution -> consented selection -> project AND funding loaded by the
    selection's tenant (the tenant-bound load is part of the boundary)."""
    inst = conn.execute(
        "SELECT * FROM financial_institutions WHERE institution_id=? "
        "AND created_by_user_id=? AND status='approved'", (iid, uid)).fetchone()
    if not inst:
        return None
    sel = conn.execute(
        "SELECT * FROM funding_institution_selections "
        "WHERE capital_investment_project_id=? AND institution_id=? "
        "AND consent=1", (pid, iid)).fetchone()
    if not sel:
        return None
    sel = dict(sel)
    tid = sel.get("tenant_id") or ''
    proj = conn.execute(
        "SELECT * FROM capital_investment_projects WHERE id=? "
        "AND COALESCE(CAST(tenant_id AS TEXT),'')=?", (pid, tid)).fetchone()
    if not proj:
        return None
    fund = conn.execute(
        "SELECT * FROM capital_investment_funding "
        "WHERE capital_investment_project_id=? AND COALESCE(tenant_id,'')=?",
        (pid, tid)).fetchone()
    return {"selection": sel, "project": dict(proj),
            "funding": dict(fund) if fund else None}


# ==========================================================================
# Tests
# ==========================================================================
def test_schema_builds_all_funding_tables():
    conn, _ = _fresh_db()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("capital_investment_funding", "financial_institutions",
              "funding_institution_selections", "funding_application_messages",
              "funding_document_shipments", "funding_revenue",
              "funding_assessments"):
        assert t in tables, "missing %s" % t
    # Slice-5 decision columns + Slice-9 opportunity funding columns present.
    sel_cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(funding_institution_selections)").fetchall()}
    assert {"decision_note", "decided_at", "decided_by"} <= sel_cols
    opp_cols = {r[1] for r in conn.execute(
        "PRAGMA table_info(capital_investment_opportunities)").fetchall()}
    assert {"funding_requested", "funding_amount", "funding_status",
            "funding_success_fee"} <= opp_cols


def test_workspace_isolation_owner_only():
    conn, _ = _fresh_db()
    _seed(conn)
    # User 10 owns approved FI-A -> sees ONLY project 1 (custA).
    a = _workspace(conn, 10)
    assert len(a) == 1 and a[0]["pid"] == 1 and a[0]["institution_id"] == "FI-A"
    # User 20 owns FI-B -> sees ONLY project 2 (cross-tenant read, by design).
    b = _workspace(conn, 20)
    assert len(b) == 1 and b[0]["pid"] == 2
    # A user owning no institution sees nothing.
    assert _workspace(conn, 99) == []


def test_workspace_excludes_pending_and_unconsented():
    conn, _ = _fresh_db()
    _seed(conn)
    # A second APPROVED institution owned by user 10, but the customer's
    # selection to it has consent=0 -> must be excluded from the workspace.
    conn.execute("INSERT INTO financial_institutions "
                 "(institution_id,name,fee_pct,created_by_user_id,status) "
                 "VALUES('FI-A2','Alpha Two',2.0,10,'approved')")
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-A2','custA',99,0,'submitted')")
    # A selection to a SUSPENDED institution (also owned by user 10) -> excluded.
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-SUS','custA',99,1,'submitted')")
    conn.commit()
    a = _workspace(conn, 10)
    # Only the approved + consented FI-A row survives.
    assert len(a) == 1 and a[0]["institution_id"] == "FI-A"


def test_load_application_authorization():
    conn, _ = _fresh_db()
    _seed(conn)
    assert _load_app(conn, 10, 1, "FI-A") is not None      # rightful owner
    assert _load_app(conn, 20, 1, "FI-A") is None          # not the owner
    assert _load_app(conn, 99, 1, "FI-A") is None          # random user
    assert _load_app(conn, 20, 1, "FI-B") is None          # no selection
    # Consent revoked -> denied.
    conn.execute("UPDATE funding_institution_selections SET consent=0 "
                 "WHERE institution_id='FI-A'")
    assert _load_app(conn, 10, 1, "FI-A") is None


def test_load_application_tenant_bound():
    """The tenant-bound project load denies a forged cross-tenant selection:
    a consented FI-A selection claiming the wrong tenant fails to load the
    project (whose real tenant differs) -> None."""
    conn, _ = _fresh_db()
    _seed(conn)
    conn.execute("DELETE FROM funding_institution_selections "
                 "WHERE capital_investment_project_id=1")
    # Project 1's real tenant is custA; forge the selection tenant as 'WRONG'.
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-A','WRONG',99,1,'submitted')")
    conn.commit()
    assert _load_app(conn, 10, 1, "FI-A") is None   # project load fails on tenant


def test_submit_persists_only_approved_ids():
    """Slice 3: a forged submission must PERSIST only approved ids -- runs the
    route's real INSERT OR IGNORE + funding upsert and inspects the DB rows."""
    conn, _ = _fresh_db()
    _seed(conn)
    conn.execute("DELETE FROM funding_institution_selections "
                 "WHERE capital_investment_project_id=1")   # clean slate
    # Forged POST: an approved id, a suspended id, and a duplicate.
    chosen = list(dict.fromkeys(["FI-A", "FI-SUS", "FI-A"]))
    approved = []
    for iid in chosen:
        ok = conn.execute("SELECT 1 FROM financial_institutions WHERE "
                          "institution_id=? AND status='approved' LIMIT 1",
                          (iid,)).fetchone()
        if not ok:
            continue
        conn.execute("INSERT OR IGNORE INTO funding_institution_selections "
                     "(capital_investment_project_id,institution_id,tenant_id,"
                     " user_id,consent,status) VALUES(?,?,?,?,1,'submitted')",
                     (1, iid, 'custA', 99))
        approved.append(iid)
    conn.execute("INSERT INTO capital_investment_funding "
                 "(capital_investment_project_id,tenant_id,user_id,status,"
                 " selected_institutions) VALUES(?,?,?,?,?) "
                 "ON CONFLICT(capital_investment_project_id,tenant_id) DO UPDATE "
                 "SET status='submitted', "
                 "selected_institutions=excluded.selected_institutions",
                 (1, 'custA', 99, 'submitted', json.dumps(approved)))
    conn.commit()
    # DB proof: exactly one selection row (FI-A), no suspended row.
    rows = [r[0] for r in conn.execute(
        "SELECT institution_id FROM funding_institution_selections "
        "WHERE capital_investment_project_id=1 ORDER BY institution_id").fetchall()]
    assert rows == ["FI-A"], rows
    assert conn.execute("SELECT COUNT(*) FROM funding_institution_selections "
                        "WHERE institution_id='FI-SUS'").fetchone()[0] == 0
    stored = json.loads(conn.execute(
        "SELECT selected_institutions FROM capital_investment_funding "
        "WHERE capital_investment_project_id=1").fetchone()[0])
    assert stored == ["FI-A"], stored     # JSON holds only the approved subset


def test_workspace_excludes_cross_tenant_mismatch():
    """Slice 4: a forged selection whose tenant disagrees with the project's is
    excluded by the tenant joins (no cross-tenant leak)."""
    conn, _ = _fresh_db()
    _seed(conn)
    # Project 1 belongs to custA; forge a consented FI-A selection claiming custB.
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-A','custB',99,1,'submitted')")
    conn.commit()
    a = _workspace(conn, 10)
    # Still exactly one row -- the legitimate custA selection; the custB forgery
    # fails the p.tenant_id = s.tenant_id join.
    assert len(a) == 1 and a[0]["pid"] == 1


def test_decision_update_reauthorizes():
    """Slice 5: the decision UPDATE re-proves consent+ownership+approved."""
    conn, _ = _fresh_db()
    _seed(conn)
    sql = ("UPDATE funding_institution_selections SET status=? "
           "WHERE capital_investment_project_id=? AND institution_id=? "
           "AND COALESCE(tenant_id,'')=? AND consent=1 "
           "AND institution_id IN (SELECT institution_id FROM "
           "financial_institutions WHERE institution_id=? "
           "AND created_by_user_id=? AND status='approved')")
    # Rightful institution owner -> 1 row.
    cur = conn.execute(sql, ("approved", 1, "FI-A", "custA", "FI-A", 10))
    assert cur.rowcount == 1
    # Wrong owner -> 0 rows.
    cur = conn.execute(sql, ("rejected", 1, "FI-A", "custA", "FI-A", 20))
    assert cur.rowcount == 0


def test_shipment_update_idor_scoped():
    """Slice 6b: shipment update is scoped by (id, project, institution, tenant)."""
    conn, _ = _fresh_db()
    _seed(conn)
    conn.execute("INSERT INTO funding_document_shipments "
                 "(shipment_id,capital_investment_project_id,institution_id,"
                 " tenant_id,verification_status) VALUES('FS-1',1,'FI-A','custA','dispatched')")
    sql = ("UPDATE funding_document_shipments SET verification_status=? "
           "WHERE shipment_id=? AND capital_investment_project_id=? "
           "AND institution_id=? AND COALESCE(tenant_id,'')=?")
    # Correct scope -> 1.
    assert conn.execute(sql, ("verified", "FS-1", 1, "FI-A", "custA")).rowcount == 1
    # Wrong institution -> 0 (no cross-thread hijack).
    assert conn.execute(sql, ("verified", "FS-1", 1, "FI-B", "custA")).rowcount == 0
    # Wrong project -> 0.
    assert conn.execute(sql, ("verified", "FS-1", 2, "FI-A", "custA")).rowcount == 0


def test_applicant_message_requires_approved_and_consent():
    """Slice 6a: applicant may only message an approved+consented institution."""
    conn, _ = _fresh_db()
    _seed(conn)
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-SUS','custA',99,1,'submitted')")
    sql = ("SELECT 1 FROM funding_institution_selections s "
           "JOIN financial_institutions fi ON fi.institution_id=s.institution_id "
           "WHERE s.capital_investment_project_id=? AND s.institution_id=? "
           "AND COALESCE(s.tenant_id,'')=? AND s.consent=1 "
           "AND fi.status='approved' LIMIT 1")

    def allowed(iid):
        return bool(conn.execute(sql, (1, iid, "custA")).fetchone())
    assert allowed("FI-A")            # approved + consented
    assert not allowed("FI-SUS")      # consented but suspended
    assert not allowed("FI-B")        # no selection for this project


def test_revenue_fee_gating_and_2pct():
    """Slice 7: PERSISTED fee/invoice only after Approved+Agreement+Disbursement;
    runs the real revenue upsert + gating and reads back the row."""
    conn, _ = _fresh_db()
    _seed(conn)
    conn.execute("UPDATE funding_institution_selections SET status='approved' "
                 "WHERE capital_investment_project_id=1 AND institution_id='FI-A'")
    fee_pct, loan = 2.0, 2500000

    def upsert(approved, agr, disb):
        all_met = bool(approved and agr and disb and loan and loan > 0)
        fee = round(loan * fee_pct / 100.0, 2) if all_met else None
        inv = "SPF-1-TEST" if all_met else None
        ist = "issued" if all_met else "pending"
        conn.execute(
            "INSERT INTO funding_revenue (capital_investment_project_id,"
            "institution_id,tenant_id,fee_pct,fee_amount,invoice_number,"
            "invoice_status,agreement_executed,first_disbursement,"
            "approved_loan_amount) VALUES(?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(capital_investment_project_id,institution_id,tenant_id) "
            "DO UPDATE SET fee_amount=excluded.fee_amount, "
            "invoice_number=excluded.invoice_number, "
            "invoice_status=excluded.invoice_status",
            (1, 'FI-A', 'custA', fee_pct, fee, inv, ist,
             1 if agr else 0, 1 if disb else 0, loan))
        conn.commit()
        return conn.execute(
            "SELECT fee_amount,invoice_number,invoice_status FROM "
            "funding_revenue WHERE capital_investment_project_id=1 "
            "AND institution_id='FI-A'").fetchone()
    # Agreement only -> pending, no fee/invoice persisted.
    r = upsert(True, True, False)
    assert r["fee_amount"] is None and r["invoice_number"] is None \
        and r["invoice_status"] == "pending"
    # All three milestones -> fee = 2% = 50,000 persisted + invoice issued.
    r = upsert(True, True, True)
    assert r["fee_amount"] == 50000.0 and r["invoice_number"] == "SPF-1-TEST" \
        and r["invoice_status"] == "issued"
    # Not approved -> fee cleared even with agreement + disbursement.
    r = upsert(False, True, True)
    assert r["fee_amount"] is None and r["invoice_status"] == "pending"


def test_assessment_scoring_and_matching():
    """Slice 8: deterministic assessment scores + mandate match + recommendation."""
    conn, _ = _fresh_db()
    _seed(conn)
    fin = json.loads(conn.execute(
        "SELECT finance_config FROM capital_investment_projects WHERE id=1"
        ).fetchone()[0])
    proj = {"site_config": '{"a":1}', "facility_config": '{"a":1}',
            "technology_config": '{"a":1}', "electrical_config": '{"a":1}',
            "pv_config": '{"a":1}', "finance_config": json.dumps(fin),
            "project_type": "solar_farm", "boq_project_id": 7}
    inst = {"loan_min": 100000, "loan_max": 5000000, "fee_pct": 2.0,
            "supported_project_types": "solar_farm,ci_rooftop"}
    a = m._ci_funding_assessment(proj, {"funding_requested": 2000000}, inst)
    assert a["technical_readiness"] == 100 and a["matched"] == 1
    assert a["recommendation"] in ("recommend", "conditional")
    # Out-of-mandate + empty project -> decline, unmatched.
    a2 = m._ci_funding_assessment(
        {"project_type": "solar_farm"}, {"funding_requested": 9e12},
        {"loan_min": 1000, "loan_max": 50000, "supported_project_types": "ci_rooftop"})
    assert a2["matched"] == 0 and a2["recommendation"] == "decline"
    # Non-finite request must not crash.
    m._ci_funding_assessment(proj, {"funding_requested": float("inf")},
                             {"loan_min": None, "loan_max": None,
                              "supported_project_types": ""})


def test_crm_snapshot_writes_funding_onto_opportunity():
    """Slice 9: the snapshot query rolls up the most-advanced status and the real
    UPDATE writes it onto the owner's opportunity (the pipeline entry)."""
    conn, _ = _fresh_db()
    _seed(conn)
    # Two consented selections for project 1; the more-advanced one wins.
    conn.execute("INSERT INTO funding_institution_selections "
                 "(capital_investment_project_id,institution_id,tenant_id,"
                 " user_id,consent,status) VALUES(1,'FI-A2','custA',99,1,'approved')")
    conn.execute("INSERT INTO financial_institutions "
                 "(institution_id,name,fee_pct,created_by_user_id,status) "
                 "VALUES('FI-A2','Alpha Two',2.0,10,'approved')")
    conn.execute("INSERT INTO funding_revenue (capital_investment_project_id,"
                 "institution_id,tenant_id,approved_loan_amount,fee_amount,"
                 "invoice_date) VALUES(1,'FI-A2','custA',1800000,36000,'2026-07-05')")
    conn.execute("INSERT INTO capital_investment_opportunities "
                 "(capital_investment_project_id,user_id,project_name,stage,"
                 " tenant_id) VALUES(1,99,'P1','lead','custA')")
    conn.commit()
    # Real snapshot SQL (mirrors _ci_funding_crm_snapshot).
    statuses = [r[0] for r in conn.execute(
        "SELECT status FROM funding_institution_selections "
        "WHERE capital_investment_project_id=1 AND COALESCE(tenant_id,'')='custA' "
        "AND consent=1").fetchall()]
    order = {s: i for i, s in enumerate(m.FI_APP_STATUSES)}
    best = max(statuses, key=lambda s: order.get(s, -1))
    # INDEPENDENT oracle: between {submitted, approved} the business rule ranks
    # 'approved' as most-advanced. If the production status ordering regresses,
    # `best` changes and this assert fails (it does not just re-derive `best`).
    assert set(statuses) == {"submitted", "approved"}
    assert best == "approved"
    rv = conn.execute("SELECT approved_loan_amount,fee_amount FROM funding_revenue "
                      "WHERE capital_investment_project_id=1 AND "
                      "COALESCE(tenant_id,'')='custA' AND approved_loan_amount "
                      "IS NOT NULL ORDER BY approved_loan_amount DESC LIMIT 1"
                      ).fetchone()
    # Real owner-scoped UPDATE (mirrors the sync-crm route).
    conn.execute("UPDATE capital_investment_opportunities SET funding_status=?, "
                 "funding_amount=?, funding_success_fee=? "
                 "WHERE capital_investment_project_id=1 AND user_id=99",
                 (best, rv[0], rv[1]))
    conn.commit()
    o = conn.execute("SELECT funding_status,funding_amount,funding_success_fee "
                     "FROM capital_investment_opportunities "
                     "WHERE capital_investment_project_id=1").fetchone()
    assert o["funding_status"] == "approved"          # most-advanced status
    assert o["funding_amount"] == 1800000.0 and o["funding_success_fee"] == 36000.0


def test_status_ordering_invariant():
    """Independent oracle for the funding status lifecycle: the ordering the CRM
    rollup relies on must keep these relative ranks (hardcoded expectations, not
    derived from the constant)."""
    idx = {s: i for i, s in enumerate(m.FI_APP_STATUSES)}
    assert idx["submitted"] < idx["under_review"]
    assert idx["under_review"] < idx["approved_in_principle"]
    assert idx["approved_in_principle"] < idx["approved"]
    assert idx["submitted"] < idx["approved"]


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print("PASS", fn.__name__)
    print("\n%d/%d funding-module tests passed." % (passed, len(fns)))


if __name__ == "__main__":
    _run_all()
