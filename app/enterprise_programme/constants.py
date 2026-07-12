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


# --- the lifecycle state machine (doc 3, slice 2) ----------------------------
# Hold/terminal pseudo-states. They are NOT phases -- a programme sitting in
# SUSPENDED still remembers the phase it was suspended FROM, and resumes there.
HOLD_STATES: frozenset[str] = frozenset({"SUSPENDED", "ON_HOLD"})
TERMINAL_STATES: frozenset[str] = frozenset({"CANCELLED", "CLOSED", "ARCHIVED"})
PSEUDO_STATES: frozenset[str] = HOLD_STATES | TERMINAL_STATES

# phase_code -> the phases (or pseudo-states) it may legally move to.
# Straight from docs/enterprise-programme/rebuild/05-lifecycle-gates-and-workflows.md.
# Anything not listed here is an ILLEGAL transition -- there is no "any -> any" escape,
# which is the whole point of having a spine.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "P01_CONCEPT":      ("P02_INITIATION", "CANCELLED", "ON_HOLD"),
    "P02_INITIATION":   ("P03_NEEDS", "P01_CONCEPT", "CANCELLED", "ON_HOLD"),
    "P03_NEEDS":        ("P04_FEASIBILITY", "P02_INITIATION", "ON_HOLD"),
    "P04_FEASIBILITY":  ("P05_STRUCTURING", "P03_NEEDS", "CANCELLED", "ON_HOLD"),
    "P05_STRUCTURING":  ("P06_TEMPLATES", "P04_FEASIBILITY", "SUSPENDED"),
    "P06_TEMPLATES":    ("P07_FUNDING", "P09_ENGINEERING", "P05_STRUCTURING"),
    "P07_FUNDING":      ("P08_PROCUREMENT", "P06_TEMPLATES", "ON_HOLD"),
    "P08_PROCUREMENT":  ("P09_ENGINEERING", "P10_MOBILISATION", "P07_FUNDING"),
    "P09_ENGINEERING":  ("P10_MOBILISATION", "P08_PROCUREMENT", "SUSPENDED"),
    "P10_MOBILISATION": ("P11_CONSTRUCTION", "P09_ENGINEERING", "SUSPENDED"),
    "P11_CONSTRUCTION": ("P12_COMMISSIONING", "P10_MOBILISATION", "SUSPENDED"),
    "P12_COMMISSIONING":("P13_HANDOVER", "P11_CONSTRUCTION", "SUSPENDED"),
    "P13_HANDOVER":     ("P14_OPERATIONS", "P15_EVALUATION", "CLOSED"),
    "P14_OPERATIONS":   ("P15_EVALUATION", "SUSPENDED", "CLOSED"),
    "P15_EVALUATION":   ("P16_EXPANSION", "P14_OPERATIONS", "CLOSED"),
    "P16_EXPANSION":    ("P01_CONCEPT", "P05_STRUCTURING", "CLOSED"),
}

# phase_code -> the programme status the phase puts the programme in.
# The status is DERIVED, never typed. That is what keeps 20 statuses and 16 phases
# from drifting apart into two independent (and eventually contradictory) truths.
PHASE_STATUS: dict[str, str] = {
    "P01_CONCEPT":      "Concept",
    "P02_INITIATION":   "Under Initiation",
    "P03_NEEDS":        "Under Assessment",
    "P04_FEASIBILITY":  "Under Feasibility",
    "P05_STRUCTURING":  "Approved",
    "P06_TEMPLATES":    "Approved",
    "P07_FUNDING":      "Funding Pending",
    "P08_PROCUREMENT":  "Procurement Planning",
    "P09_ENGINEERING":  "Under Design",
    "P10_MOBILISATION": "Contracted",
    "P11_CONSTRUCTION": "Under Construction",
    "P12_COMMISSIONING":"Under Commissioning",
    "P13_HANDOVER":     "Closing",
    "P14_OPERATIONS":   "Operational",
    "P15_EVALUATION":   "Operational",
    "P16_EXPANSION":    "Approved",
}

# pseudo-state -> programme status.
PSEUDO_STATE_STATUS: dict[str, str] = {
    "SUSPENDED": "Suspended",
    "ON_HOLD":   "On Hold",
    "CANCELLED": "Cancelled",
    "CLOSED":    "Closed",
    "ARCHIVED":  "Archived",
}

# The gate that must be APPROVED before a programme may LEAVE a phase going forward.
# P14 has no numbered gate (doc 3) -- it is controlled by O&M permissions instead --
# and P16's exit is controlled by an expansion approval record, not a numbered gate.
GATE_CLOSING_PHASE: dict[str, str] = {g[1]: g[0] for g in GATES}

# --- what a phase demands to be ENTERED --------------------------------------
# "The gate that closes the phase you are leaving" is NOT a sufficient rule, and the
# reviewer found the proof: doc 3 permits P06 -> P09 (start engineering while funding and
# tendering run in parallel) and P09 -> P10. Chain them and a programme reaches
# MOBILISATION having approved only G06 and G09 -- no funding close (G07), no contract
# award (G08). It would be mobilising contractors it never hired with money it never
# raised. A rework edge (P09 -> P08) walked around G07 the same way.
#
# Patching each edge is whack-a-mole, because the hole is a property of the DESTINATION,
# not of the route taken to it. So each phase declares what must be true to ENTER it, and
# that is checked on EVERY entry -- forward, skipping, or backward.
#
# The entries below are doc 3's own "blocked until passed" column, read as preconditions:
#   Gate 7 blocks major procurement    -> P08 cannot be entered without G07
#   Gate 8 blocks contractor mobilisation, Gate 9 blocks site installation
#                                      -> P10 cannot be entered without G08 and G09
#   Gate 10 blocks construction start  -> P11 needs G10, and so on down the chain.
# Phases not listed here impose no entry gate of their own.
PHASE_ENTRY_REQUIRED_GATES: dict[str, tuple[str, ...]] = {
    "P08_PROCUREMENT":   ("G07",),
    "P10_MOBILISATION":  ("G08", "G09"),
    "P11_CONSTRUCTION":  ("G10",),
    "P12_COMMISSIONING": ("G11",),
    "P13_HANDOVER":      ("G12",),
    "P14_OPERATIONS":    ("G13",),
}

# --- gates that cannot be approved before other gates ------------------------
# The remaining leak: nothing stopped G08 (Contract Award) being approved before G07
# (Financial Close). Awarding a contract you have no money for is not a routing mistake,
# it is the thing Gate 7 exists to prevent -- so the dependency belongs on the GATE, not
# on every edge that might reach it. With G08 requiring G07, mobilisation transitively
# requires funding no matter which path a programme takes to get there.
#
# G09 (Design Approval) deliberately has NO prerequisite: detailed engineering running
# ahead of financial close is normal practice and doc 3 explicitly allows P06 -> P09.
GATE_PREREQUISITE_GATES: dict[str, tuple[str, ...]] = {
    "G08": ("G07",),           # no contract award before financial close
    "G10": ("G08", "G09"),     # no mobilisation approval without a contract and a design
    "G11": ("G10",),           # no completion sign-off without mobilisation
    "G12": ("G11",),           # no commissioning without construction completion
    "G13": ("G12",),           # no handover without commissioning
}

# --- named post-holders: when the role is not enough -------------------------
# A programme NAMES the people who fill its senior posts. Where it has, the gate whose
# authority is that post must be signed BY THAT PERSON -- not merely by somebody who
# happens to hold the role tenant-wide.
#
# Without this, `sponsor_user_id` would be decorative: a programme could name Bob as
# sponsor, and any other holder of the programme_sponsor role could sign Gate 1 in his
# place, satisfying control C01 ("no programme proceeds without an approved sponsor")
# with an approval the actual sponsor never gave. The role says WHAT KIND of person may
# sign; this says WHICH ONE.
#
# role code -> the enterprise_programmes column naming its holder. A NULL column means
# the post is unfilled and the role check alone applies.
GATE_AUTHORITY_HOLDER_COLUMN: dict[str, str] = {
    "programme_sponsor":  "sponsor_user_id",
    "programme_director": "director_user_id",
    "programme_manager":  "manager_user_id",
}

# Release 1 delivers a COMPLETE lifecycle through Gate 9 (Supervisor adjudication,
# doc 09). Gates 10-14 exist, are seeded, and are deliberately BLOCKED: their guards
# fail closed until the slices that produce their evidence (construction reports, test
# results, handover dossiers) ship. A lifecycle with holes in the middle is worse than
# a shorter one that cannot be bypassed.
RELEASE_1_FINAL_GATE = "G09"
GATES_DEFERRED_BEYOND_RELEASE_1: frozenset[str] = frozenset(
    {"G10", "G11", "G12", "G13", "G14"}
)


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
