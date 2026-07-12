"""Enterprise Solar Programme -- canonical vocabularies (rebuild, slice 1).

WHY THIS FILE EXISTS
--------------------
The owner's specification (docs/enterprise-programme/source/02-lifecycle-workflows.txt)
hands us ready-made vocabularies: 16 lifecycle phases, 14 stage gates, 20 programme
statuses, 21 project statuses, 15 management controls. Those are NOT suggestions and
they are NOT free text -- they are the state machine.

Every one of them is declared here ONCE, and everything downstream (DB seed rows,
dropdown option lists, guard predicates, tests) reads from here. A status a user can
type is a status the state machine cannot reason about, so the UI never accepts one:
see docs/enterprise-programme/rebuild/06-dropdown-and-ux-spec.md.

Ordering is significant for PHASES (sequence_no) and GATES (gate order). Do not
reorder; append only.
"""

from __future__ import annotations


# --- lifecycle phases (doc 3, "SOLAR PROGRAMME INITIATION..." phases 1-16) ---
# (code, sequence_no, display name)
PHASES: list[tuple[str, int, str]] = [
    ("P01_CONCEPT",        1,  "Programme Concept and Opportunity Identification"),
    ("P02_INITIATION",     2,  "Programme Initiation"),
    ("P03_NEEDS",          3,  "Needs Assessment and Baseline Study"),
    ("P04_FEASIBILITY",    4,  "Feasibility Study and Business Case"),
    ("P05_STRUCTURING",    5,  "Programme Structuring and Master Planning"),
    ("P06_TEMPLATES",      6,  "Programme Template and Standardisation Development"),
    ("P07_FUNDING",        7,  "Funding and Commercial Structuring"),
    ("P08_PROCUREMENT",    8,  "Procurement Strategy and EPC Packaging"),
    ("P09_ENGINEERING",    9,  "Detailed Engineering and Project Generation"),
    ("P10_MOBILISATION",  10,  "Mobilisation and Implementation Readiness"),
    ("P11_CONSTRUCTION",  11,  "Construction, Installation and Delivery"),
    ("P12_COMMISSIONING", 12,  "Inspection, Testing and Commissioning"),
    ("P13_HANDOVER",      13,  "Handover and Programme Closeout"),
    ("P14_OPERATIONS",    14,  "Operations and Maintenance"),
    ("P15_EVALUATION",    15,  "Monitoring, Evaluation and Programme Optimisation"),
    ("P16_EXPANSION",     16,  "Programme Expansion and Replication"),
]

# --- stage gates (doc 3, Gate 1..Gate 14) -----------------------------------
# (code, phase_code it closes, display name, approving authority)
# `approving_authority` is a ROLE code from ROLES below -- the gate cannot be
# approved by anyone who does not hold that role (see rbac.py).
GATES: list[tuple[str, str, str, str]] = [
    ("G01",  "P01_CONCEPT",       "Programme Concept Approval",            "programme_sponsor"),
    ("G02",  "P02_INITIATION",    "Programme Initiation Approval",         "steering_committee"),
    ("G03",  "P03_NEEDS",         "Needs Assessment Approval",             "programme_manager"),
    ("G04",  "P04_FEASIBILITY",   "Feasibility and Business Case Approval","programme_sponsor"),
    ("G05",  "P05_STRUCTURING",   "Programme Master Plan Approval",        "programme_director"),
    ("G06",  "P06_TEMPLATES",     "Standardisation Approval",              "technical_director"),
    ("G07",  "P07_FUNDING",       "Financial Close or Funding Approval",   "funding_manager"),
    ("G08",  "P08_PROCUREMENT",   "Contract Award and Notice to Proceed",  "procurement_manager"),
    ("G09",  "P09_ENGINEERING",   "Design Approval and Construction Release","engineering_manager"),
    ("G10",  "P10_MOBILISATION",  "Site Mobilisation Approval",            "site_engineer"),
    ("G11",  "P11_CONSTRUCTION",  "Construction Completion Approval",      "qa_qc_manager"),
    ("G12",  "P12_COMMISSIONING", "Commissioning and Taking-Over Approval","commissioning_engineer"),
    ("G13",  "P13_HANDOVER",      "Handover and Closeout Approval",        "programme_director"),
    ("G14",  "P15_EVALUATION",    "Benefits and Performance Review",       "steering_committee"),
]

# --- programme status (doc 3, "RECOMMENDED PROGRAMME STATUS VALUES") ---------
# Verbatim, in the owner's order. Index 0 is the creation default.
PROGRAMME_STATUSES: list[str] = [
    "Concept", "Under Initiation", "Under Assessment", "Under Feasibility",
    "Business Case Review", "Approved", "Funding Pending", "Procurement Planning",
    "Tendering", "Contracted", "Under Design", "Under Construction",
    "Under Commissioning", "Operational", "Suspended", "On Hold", "Closing",
    "Closed", "Cancelled", "Archived",
]

# --- project status (doc 3, "RECOMMENDED PROJECT STATUS VALUES") -------------
PROJECT_STATUSES: list[str] = [
    "Beneficiary Registered", "Qualification Pending", "Qualified", "Not Qualified",
    "Template Assigned", "Project Generated", "Survey Pending", "Under Design",
    "Design Review", "Design Approved", "Procurement Pending", "Contractor Assigned",
    "Site Mobilised", "Under Construction", "Testing", "Commissioning",
    "Operational", "Under Maintenance", "Suspended", "Closed",
]

# --- template version lifecycle (master prompt s13) --------------------------
# Only these two may generate a project. Enforced in gates.py, re-checked in the
# worker -- see control C03.
TEMPLATE_STATUSES: list[str] = [
    "Draft", "Review", "Approved", "Published", "Superseded", "Archived",
]
TEMPLATE_STATUSES_GENERATIVE: frozenset[str] = frozenset({"Approved", "Published"})

# --- the 15 key programme management controls (doc 3) -----------------------
# Each maps to a guard predicate in gates.py. The tuple is
# (code, requirement, guard function name) and the test suite asserts that every
# entry here has a live guard -- a control cannot be quietly dropped.
CONTROLS: list[tuple[str, str, str]] = [
    ("C01", "No programme proceeds without an approved sponsor.",
     "require_approved_sponsor"),
    ("C02", "No beneficiary becomes a project without qualification.",
     "require_qualified_beneficiary"),
    ("C03", "No project is generated without an approved template.",
     "require_approved_template_version"),
    ("C04", "No design is issued without engineering approval.",
     "require_engineering_approval"),
    ("C05", "No procurement package is created without an approved BOQ.",
     "require_approved_boq_snapshot"),
    ("C06", "No contractor mobilises without contract approval.",
     "require_executed_contract"),
    ("C07", "No installation begins without site-readiness approval.",
     "require_site_readiness_approval"),
    ("C08", "No system is commissioned without required tests.",
     "require_required_tests_passed"),
    ("C09", "No asset is handed over without complete documentation.",
     "require_handover_dossier_complete"),
    ("C10", "No operational KPI is reported without a defined data source.",
     "require_kpi_data_source"),
    ("C11", "No AI recommendation becomes an approval automatically.",
     "require_human_approval_actor"),
    ("C12", "Every material action must be auditable.",
     "require_audit_written"),
    ("C13", "Every programme record must be tenant-scoped.",
     "require_tenant_scope"),
    ("C14", "Every programme project must retain traceability to its originating "
            "beneficiary and programme template.",
     "require_project_traceability"),
    ("C15", "Every aggregated procurement quantity must remain traceable to its "
            "source project BOQ.",
     "require_procurement_source_lines"),
]

# --- organisation types (master prompt s10) ---------------------------------
ORGANISATION_TYPES: list[tuple[str, str]] = [
    ("government",        "Government"),
    ("ministry",          "Ministry"),
    ("utility",           "Utility"),
    ("development_bank",  "Development Bank"),
    ("commercial_bank",   "Commercial Bank"),
    ("ngo",               "NGO"),
    ("donor",             "Donor Organisation"),
    ("epc_contractor",    "EPC Contractor"),
    ("consultant",        "Engineering Consultant"),
    ("ipp",               "Independent Power Producer"),
    ("education",         "Educational Institution"),
    ("healthcare",        "Healthcare Organisation"),
    ("agriculture",       "Agricultural Enterprise"),
    ("industrial",        "Industrial Organisation"),
    ("real_estate",       "Real-Estate Developer"),
    ("community",         "Community Organisation"),
    ("corporate",         "Corporate Enterprise"),
    ("personal",          "Personal Workspace"),  # the backfilled default tenant
]

# --- design strategy (master prompt s14) ------------------------------------
DESIGN_STRATEGIES: list[tuple[str, str]] = [
    ("standard",           "Standard Design (distributed installations)"),
    ("generation_station", "Generation Station Design (utility scale)"),
    ("mixed",              "Mixed (both strategies in one programme)"),
]

# --- delivery models (master prompt s20 + doc 3 packaging) ------------------
DELIVERY_MODELS: list[tuple[str, str]] = [
    ("epc",               "EPC"),
    ("epcm",              "EPCM"),
    ("design_build",      "Design-Build"),
    ("turnkey",           "Turnkey"),
    ("framework",         "Framework Contract"),
    ("multiple_lots",     "Multiple Lots"),
    ("regional_package",  "Regional Packages"),
    ("district_package",  "District Packages"),
    ("technology_package","Technology Packages"),
    ("equipment_only",    "Equipment-Only Packages"),
    ("installation_only", "Installation-Only Packages"),
    ("om_package",        "O&M Packages"),
]

# --- funding sources (master prompt s19 + doc 3 phase 7) --------------------
FUNDING_SOURCES: list[tuple[str, str]] = [
    ("government_budget", "Government Budget"),
    ("development_bank",  "Development-Bank Funding"),
    ("commercial_loan",   "Commercial Loan"),
    ("green_bond",        "Green Bond"),
    ("climate_fund",      "Climate Fund"),
    ("grant",             "Grant"),
    ("ppp",               "PPP"),
    ("ipp_finance",       "Independent Power Producer Finance"),
    ("carbon_finance",    "Carbon Finance"),
    ("corporate_finance", "Corporate Finance"),
    ("community",         "Community Contribution"),
    ("csr",               "CSR Funding"),
    ("blended",           "Blended Finance"),
]

# --- RBAC: roles (master prompt s11, 37 roles + doc 3's Finance Manager) -----
# (code, display name). Nothing is globally powerful by default -- the master
# prompt says so explicitly. Power comes from PERMISSIONS below, granted per role.
ROLES: list[tuple[str, str]] = [
    ("enterprise_owner",         "Enterprise Owner"),
    ("org_admin",                "Organisation Administrator"),
    ("programme_sponsor",        "Programme Sponsor"),
    ("steering_committee",       "Programme Steering Committee"),
    ("programme_director",       "Programme Director"),
    ("programme_manager",        "Programme Manager"),
    ("technical_director",       "Technical Director"),
    ("programme_engineer",       "Programme Engineer"),
    ("design_engineer",          "Design Engineer"),
    ("engineering_manager",      "Engineering Manager"),
    ("regional_manager",         "Regional Manager"),
    ("district_coordinator",     "District Coordinator"),
    ("beneficiary_officer",      "Beneficiary Officer"),
    ("surveyor",                 "Surveyor"),
    ("gis_specialist",           "GIS Specialist"),
    ("funding_manager",          "Funding Manager"),
    ("finance_manager",          "Finance Manager"),
    ("finance_officer",          "Finance Officer"),
    ("procurement_manager",      "Procurement Manager"),
    ("contract_manager",         "Contract Manager"),
    ("fidic_engineer",           "FIDIC Engineer"),
    ("epc_contractor_admin",     "EPC Contractor Administrator"),
    ("epc_project_manager",      "EPC Project Manager"),
    ("site_engineer",            "Site Engineer"),
    ("site_supervisor",          "Site Supervisor"),
    ("warehouse_manager",        "Warehouse Manager"),
    ("logistics_officer",        "Logistics Officer"),
    ("qa_qc_manager",            "QA/QC Manager"),
    ("inspector",                "Inspector"),
    ("commissioning_engineer",   "Commissioning Engineer"),
    ("operations_manager",       "Operations Manager"),
    ("maintenance_engineer",     "Maintenance Engineer"),
    ("monitoring_operator",      "Monitoring Operator"),
    ("esg_officer",              "ESG and Carbon Officer"),
    ("auditor",                  "Auditor"),
    ("financier_viewer",         "Financier Viewer"),
    ("donor_viewer",             "Donor Viewer"),
    ("executive_viewer",         "Executive Viewer"),
    ("beneficiary_rep",          "Beneficiary Representative"),
    ("platform_support_admin",   "Platform Support Administrator"),
]

# --- RBAC: permissions (master prompt s11 "granular permissions") ------------
PERMISSIONS: list[tuple[str, str]] = [
    ("tenant.admin",         "Administer the organisation"),
    ("programme.create",     "Create a programme"),
    ("programme.edit",       "Edit programme setup"),
    ("programme.approve",    "Approve a programme or stage gate"),
    ("template.manage",      "Create and edit programme templates"),
    ("template.approve",     "Approve and publish template versions"),
    ("beneficiary.import",   "Import beneficiaries"),
    ("beneficiary.approve",  "Approve beneficiaries"),
    ("qualification.score",  "Score site qualification"),
    ("qualification.approve","Approve site qualification"),
    ("design.generate",      "Generate projects and designs"),
    ("engineering.approve",  "Approve designs; release for construction"),
    ("funding.manage",       "Manage funding facilities and allocations"),
    ("procurement.manage",   "Consolidate BOQs; create procurement packages"),
    ("contract.manage",      "Administer contracts"),
    ("payment.certify",      "Certify payments"),
    ("variation.approve",    "Approve variations and claims"),
    ("inspection.approve",   "Approve inspections"),
    ("commissioning.approve","Approve commissioning"),
    ("operations.access",    "Access operations and maintenance"),
    ("report.generate",      "Generate reports"),
    ("region.cross_access",  "Access data across regions"),
    ("programme.cross_access","Access data across programmes"),
    ("audit.access",         "Access the audit trail"),
]

# Role -> permissions. Absent from this map == no permissions beyond read of what
# the membership scope already allows. Viewer roles are deliberately read-only.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "enterprise_owner": ["tenant.admin", "programme.create", "programme.edit",
                         "programme.approve", "report.generate", "audit.access",
                         "region.cross_access", "programme.cross_access"],
    "org_admin":        ["tenant.admin", "programme.create", "programme.edit",
                         "report.generate", "audit.access"],
    "programme_sponsor":   ["programme.approve", "report.generate"],
    "steering_committee":  ["programme.approve", "report.generate"],
    "programme_director":  ["programme.edit", "programme.approve", "report.generate",
                            "region.cross_access", "programme.cross_access"],
    "programme_manager":   ["programme.edit", "beneficiary.approve",
                            "qualification.approve", "report.generate"],
    "technical_director":  ["template.approve", "engineering.approve",
                            "report.generate"],
    "programme_engineer":  ["template.manage", "design.generate"],
    "design_engineer":     ["design.generate"],
    "engineering_manager": ["engineering.approve", "design.generate"],
    "regional_manager":    ["beneficiary.approve", "qualification.approve",
                            "report.generate"],
    "district_coordinator":["beneficiary.import", "qualification.score"],
    "beneficiary_officer": ["beneficiary.import"],
    "surveyor":            ["qualification.score"],
    "gis_specialist":      ["qualification.score"],
    "funding_manager":     ["funding.manage", "programme.approve"],
    "finance_manager":     ["funding.manage", "payment.certify"],
    "finance_officer":     ["payment.certify"],
    "procurement_manager": ["procurement.manage", "programme.approve"],
    "contract_manager":    ["contract.manage", "variation.approve"],
    "fidic_engineer":      ["contract.manage", "payment.certify"],
    "epc_contractor_admin":["contract.manage"],
    "epc_project_manager": [],
    "site_engineer":       [],
    "site_supervisor":     [],
    "warehouse_manager":   [],
    "logistics_officer":   [],
    "qa_qc_manager":       ["inspection.approve"],
    "inspector":           ["inspection.approve"],
    "commissioning_engineer": ["commissioning.approve"],
    "operations_manager":  ["operations.access", "report.generate"],
    "maintenance_engineer":["operations.access"],
    "monitoring_operator": ["operations.access"],
    "esg_officer":         ["report.generate"],
    "auditor":             ["audit.access", "report.generate"],
    "financier_viewer":    [],
    "donor_viewer":        [],
    "executive_viewer":    ["report.generate"],
    "beneficiary_rep":     [],
    "platform_support_admin": ["audit.access"],
}


# --- convenience lookups (used by dropdown builders and guards) -------------

PHASE_CODES: list[str] = [p[0] for p in PHASES]
GATE_CODES: list[str] = [g[0] for g in GATES]
ROLE_CODES: frozenset[str] = frozenset(r[0] for r in ROLES)
PERMISSION_CODES: frozenset[str] = frozenset(p[0] for p in PERMISSIONS)

DEFAULT_PROGRAMME_STATUS = PROGRAMME_STATUSES[0]          # "Concept"
DEFAULT_PROJECT_STATUS = PROJECT_STATUSES[0]              # "Beneficiary Registered"
DEFAULT_PHASE_CODE = PHASES[0][0]                         # "P01_CONCEPT"


def permissions_for_roles(role_codes) -> frozenset[str]:
    """Union of the permissions granted by a set of role codes.

    Input:  iterable of role code strings (unknown codes are ignored, not fatal --
            a stale role row must never crash a request).
    Output: frozenset of permission code strings.
    """
    out: set[str] = set()
    for rc in role_codes or ():
        out.update(ROLE_PERMISSIONS.get(rc, ()))
    return frozenset(out)
