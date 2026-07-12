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

# Only a Draft may be EDITED. This is the whole point of the version lifecycle, and it is
# what the master prompt means by "later template changes must not silently overwrite
# completed or approved project designs": once a version is submitted for review its
# parameters are frozen forever, and a change means a NEW version. A project generated
# from version 3 can therefore always be re-derived, because version 3 still says what it
# said on the day it was used.
TEMPLATE_STATUSES_EDITABLE: frozenset[str] = frozenset({"Draft"})

# The version state machine. Absent key == terminal (Archived).
#
# Review -> Draft is a REJECTION (the approver sends it back), which is why it is legal.
# Approved -> Review is a withdrawal before publication. Published never returns to an
# editable state: it is superseded by the next publication, never rewritten -- something
# generated from it may exist.
TEMPLATE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "Draft":      ("Review", "Archived"),
    "Review":     ("Approved", "Draft", "Archived"),
    "Approved":   ("Published", "Review", "Archived"),
    "Published":  ("Superseded", "Archived"),
    "Superseded": ("Archived",),
    "Archived":   (),
}

# --- beneficiary types (master prompt s14.1 + the vision doc) ----------------
# What a programme installs FOR. Drives the template's applicability and, from slice 5,
# the beneficiary register.
BENEFICIARY_TYPES: list[tuple[str, str]] = [
    ("home",                "Home / Household"),
    ("school",              "School"),
    ("university",          "University / Tertiary Institution"),
    ("clinic",              "Clinic / Health Post"),
    ("hospital",            "Hospital"),
    ("office",              "Office / Administrative Building"),
    ("government_building", "Government Building"),
    ("farm",                "Farm / Agricultural Facility"),
    ("cold_storage",        "Cold-Storage Facility"),
    ("water_facility",      "Water Pumping / Treatment Facility"),
    ("shop",                "Shop / Small Business"),
    ("community_facility",  "Community Facility"),
    ("industrial",          "Industrial Facility"),
    ("mine",                "Mine"),
    ("telecom_site",        "Telecom Site"),
]

# --- typical load profiles (master prompt s13 "Typical load profile") --------
LOAD_PROFILES: list[tuple[str, str]] = [
    ("residential_evening", "Residential -- evening peak"),
    ("residential_flat",    "Residential -- flat"),
    ("daytime_only",        "Daytime only (school / office)"),
    ("daytime_extended",    "Daytime extended (offices with evening use)"),
    ("continuous_24h",      "Continuous 24h (clinic / hospital / telecom)"),
    ("irrigation_seasonal", "Irrigation -- seasonal daytime"),
    ("cold_chain_24h",      "Cold chain -- continuous with compressor cycling"),
    ("industrial_shift",    "Industrial -- shift pattern"),
    ("mixed_community",     "Mixed community load"),
]

# --- system configuration (master prompt s13) -------------------------------
SYSTEM_CONFIGURATIONS: list[tuple[str, str]] = [
    ("grid_tied",       "Grid-tied"),
    ("off_grid",        "Off-grid"),
    ("hybrid",          "Hybrid (grid + storage)"),
    ("grid_backup",     "Grid-tied with backup storage"),
]

# --- O&M model (master prompt s13) ------------------------------------------
OM_MODELS: list[tuple[str, str]] = [
    ("in_house",              "In-house O&M"),
    ("contracted_om",         "Contracted O&M provider"),
    ("epc_warranty_period",   "EPC-provided during warranty period"),
    ("manufacturer_warranty", "Manufacturer warranty only"),
    ("community_managed",     "Community-managed"),
    ("not_defined",           "Not defined at template level"),
]

# --- beneficiary fields a template may REQUIRE (master prompt s12) ----------
# The template says which of these a beneficiary must supply before it may qualify.
# Slice 5 (the beneficiary register) reads the same list, so the field a template demands
# is necessarily a field the register can actually hold.
BENEFICIARY_FIELDS: list[tuple[str, str]] = [
    ("name",                  "Name"),
    ("region",                "Region"),
    ("district",              "District"),
    ("community",             "Community"),
    ("address",               "Address"),
    ("gps_coordinates",       "GPS coordinates"),
    ("contact_person",        "Contact person"),
    ("contact_details",       "Contact details"),
    ("ownership",             "Ownership"),
    ("building_type",         "Building type"),
    ("occupancy",             "Occupancy"),
    ("existing_energy_source", "Existing energy source"),
    ("electricity_consumption", "Electricity consumption"),
    ("tariff",                "Tariff"),
    ("generator_details",     "Generator details"),
    ("roof_area",             "Roof area"),
    ("land_availability",     "Land availability"),
    ("critical_loads",        "Critical loads"),
    ("priority_loads",        "Priority loads"),
    ("funding_eligibility",   "Funding eligibility"),
    ("social_impact_class",   "Social-impact classification"),
    ("priority_ranking",      "Priority ranking"),
]

# --- the beneficiary register (master prompt s12, slice 5) -------------------
# The SAME 22 field keys as BENEFICIARY_FIELDS above, with the type information the
# register needs: how to validate a typed value, and which vocabulary a coded one must
# come from. One list drives the manual form, the CSV/XLSX import mapper, the validator,
# and (through the template's `required_beneficiary_fields`) the qualification check --
# so a field a template can DEMAND is necessarily a field the register can HOLD and the
# importer can FILL. They cannot drift, because they are the same keys.
#
# A test asserts this covers BENEFICIARY_FIELDS exactly. Adding a field to one list and
# forgetting the other is how a template ends up requiring something no beneficiary can
# ever supply -- a site that can never qualify, with nothing in the UI to say why.
#
# `kind`: text | number | select | gps  (gps is "lat,lon", validated as a real coordinate)
BENEFICIARY_FIELD_SPEC: list[dict] = [
    {"key": "name",                   "kind": "text",   "required": True},
    {"key": "region",                 "kind": "text"},
    {"key": "district",               "kind": "text"},
    {"key": "community",              "kind": "text"},
    {"key": "address",                "kind": "text"},
    {"key": "gps_coordinates",        "kind": "gps"},
    {"key": "contact_person",         "kind": "text"},
    {"key": "contact_details",        "kind": "text"},
    {"key": "ownership",              "kind": "select", "source": "OWNERSHIP_TYPES"},
    {"key": "building_type",          "kind": "select", "source": "BUILDING_TYPES"},
    {"key": "occupancy",              "kind": "number"},
    {"key": "existing_energy_source", "kind": "select", "source": "ENERGY_SOURCES"},
    {"key": "electricity_consumption", "kind": "number"},   # kWh / month
    {"key": "tariff",                 "kind": "number"},    # currency / kWh
    {"key": "generator_details",      "kind": "text"},
    {"key": "roof_area",              "kind": "number"},    # m2
    {"key": "land_availability",      "kind": "number"},    # m2
    {"key": "critical_loads",         "kind": "text"},
    {"key": "priority_loads",         "kind": "text"},
    {"key": "funding_eligibility",    "kind": "select", "source": "FUNDING_ELIGIBILITY"},
    {"key": "social_impact_class",    "kind": "select", "source": "SOCIAL_IMPACT_CLASSES"},
    {"key": "priority_ranking",       "kind": "number"},
]

OWNERSHIP_TYPES: list[tuple[str, str]] = [
    ("government",  "Government-owned"),
    ("private",     "Privately owned"),
    ("community",   "Community-owned"),
    ("faith_based", "Faith-based organisation"),
    ("ngo",         "NGO-owned"),
    ("leased",      "Leased"),
]

BUILDING_TYPES: list[tuple[str, str]] = [
    ("single_storey",  "Single-storey"),
    ("multi_storey",   "Multi-storey"),
    ("compound",       "Compound / multiple blocks"),
    ("temporary",      "Temporary structure"),
    ("ground_mounted", "No building (ground-mounted site)"),
]

ENERGY_SOURCES: list[tuple[str, str]] = [
    ("grid",           "Grid only"),
    ("grid_generator", "Grid with generator backup"),
    ("generator",      "Generator only"),
    ("solar_existing", "Existing solar"),
    ("none",           "No electricity"),
]

FUNDING_ELIGIBILITY: list[tuple[str, str]] = [
    ("fully_funded",   "Fully funded by the programme"),
    ("co_funded",      "Co-funded"),
    ("self_funded",    "Self-funded"),
    ("not_eligible",   "Not eligible"),
    ("to_be_assessed", "To be assessed"),
]

SOCIAL_IMPACT_CLASSES: list[tuple[str, str]] = [
    ("critical",  "Critical (health, water, emergency)"),
    ("high",      "High"),
    ("medium",    "Medium"),
    ("low",       "Low"),
]

# --- beneficiary lifecycle (doc 3's PROJECT_STATUSES, the part Release 1 reaches) ------
# NOT a second vocabulary: these are the first six of PROJECT_STATUSES verbatim, because a
# beneficiary IS the thing that becomes a project -- doc 3 starts the project status list
# at "Beneficiary Registered" for exactly that reason. Inventing a parallel set of
# beneficiary statuses would mean mapping one to the other at generation time, and a
# mapping is a place for them to disagree.
BENEFICIARY_STATUSES: list[str] = [
    "Beneficiary Registered",   # entered or imported; nobody has vouched for it yet
    "Qualification Pending",    # approved into the register; awaiting the slice-6 survey
    "Qualified",                # slice 6: it passed
    "Not Qualified",            # slice 6: it did not
    "Template Assigned",        # slice 7: a template version is attached
    "Project Generated",        # slice 7: a real SolarPro project exists
    "Rejected",                 # rejected from the register (a duplicate, out of scope)
    "Archived",
]

# Release 1 owns the first two moves. The rest are asserted here so the state machine is
# complete and slices 6-7 add their guards, not their vocabulary.
BENEFICIARY_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "Beneficiary Registered": ("Qualification Pending", "Rejected", "Archived"),
    "Qualification Pending":  ("Qualified", "Not Qualified", "Rejected", "Archived"),
    "Qualified":              ("Template Assigned", "Not Qualified", "Archived"),
    "Not Qualified":          ("Qualification Pending", "Archived"),
    "Template Assigned":      ("Project Generated", "Qualified", "Archived"),
    "Project Generated":      ("Archived",),
    "Rejected":               ("Archived",),
    "Archived":               (),
}

# Only these may be qualified (slice 6) and therefore generated from (slice 7, control C02).
BENEFICIARY_STATUSES_APPROVED: frozenset[str] = frozenset({
    "Qualification Pending", "Qualified", "Template Assigned", "Project Generated",
})

# --- site qualification (slice 6) -------------------------------------------
# Doc 3, "Site Qualification Scores" (02-lifecycle-workflows.txt:176-188): eight categories
# feeding one overall priority score. The eight are doc-3's verbatim list; the weights are
# ours (doc 3 names the categories and the overall score, but not how to combine them).
#
# EVERY SCORE IS 0-100 AND HIGHER IS ALWAYS BETTER. This matters most where it reads
# strangest: doc 3 calls two of them "risk" scores, and the naive reading -- 100 = maximum
# risk -- would silently INVERT them, ranking the most dangerous, least accessible sites
# highest and sending the programme's money to exactly the wrong villages. Nobody would see
# it; the list would just be quietly wrong. So the direction is stated in the label, in the
# form, and here: on a risk row, 100 means NO risk.
QUALIFICATION_CRITERIA: list[dict] = [
    {"key": "technical_suitability",    "weight": 20,
     "label": "Technical suitability",
     "hint": "Roof/land, structure, orientation, shading. 100 = ideal."},
    {"key": "energy_need",              "weight": 20,
     "label": "Energy need",
     "hint": "Unserved load, outage hours, generator spend. 100 = greatest need."},
    {"key": "financial_suitability",    "weight": 15,
     "label": "Financial suitability",
     "hint": "Tariff, ability to pay, payback. 100 = strongest case."},
    {"key": "social_impact",            "weight": 15,
     "label": "Social impact",
     "hint": "People served, schools/clinics, hours of service gained. 100 = greatest."},
    {"key": "implementation_readiness", "weight": 10,
     "label": "Implementation readiness",
     "hint": "Access road, land title, community consent. 100 = ready to build."},
    {"key": "security_risk",            "weight": 5,
     "label": "Security risk (100 = NO risk)",
     "hint": "Theft, vandalism, conflict. 100 = safe. A LOW score is a DANGEROUS site."},
    {"key": "environmental_risk",       "weight": 5,
     "label": "Environmental risk (100 = NO risk)",
     "hint": "Flood, dust, salt, protected land. 100 = benign. LOW = hazardous."},
    {"key": "funding_eligibility",      "weight": 10,
     "label": "Funding eligibility",
     "hint": "Fits the funder's mandate and conditions. 100 = fully eligible."},
]

# Guard the arithmetic at import time rather than discovering a 97-point "percentage" in a
# board report: the weights ARE the overall score's denominator.
assert sum(c["weight"] for c in QUALIFICATION_CRITERIA) == 100, \
    "QUALIFICATION_CRITERIA weights must sum to 100 -- the total score is a percentage"

QUALIFICATION_CRITERION_KEYS: list[str] = [c["key"] for c in QUALIFICATION_CRITERIA]
QUALIFICATION_SCORE_MIN: int = 0
QUALIFICATION_SCORE_MAX: int = 100

# The two decisions a qualification can reach. They are the SAME strings as the beneficiary
# statuses they drive, deliberately: a decision that had to be mapped onto a status would be
# somewhere for the two to disagree about whether a site is qualified.
QUALIFICATION_DECISIONS: list[str] = ["Qualified", "Not Qualified"]

# --- bulk import staging (slice 5) ------------------------------------------
# An import is STAGED, never applied straight to the register: rows are parsed, mapped,
# validated and shown back before a single beneficiary exists. A 4000-row spreadsheet with
# 12 bad rows must not be a choice between "import nothing" and "import 12 broken records".
IMPORT_ROW_STATUSES: list[str] = [
    "Valid",       # passes validation; will be created on commit
    "Error",       # failed validation; will be skipped, with the reason kept
    "Duplicate",   # matches a beneficiary already in this programme; skipped by default
    "Imported",    # committed -- a beneficiary now exists for this row
    "Skipped",     # the user chose not to import it
]
IMPORT_BATCH_STATUSES: list[str] = ["Staged", "Committed", "Cancelled"]

# A hard ceiling on one import. Release 1 parses and commits IN THE REQUEST -- there is no
# worker yet (Supervisor R1: the worker must be a GitHub-Actions cron hitting a drain
# endpoint, and it lands with slice 7's project generation, which is the expensive thing).
# A cap that is stated and enforced is honest; a request that silently dies at row 8000 is
# not. The UI says the number.
IMPORT_MAX_ROWS: int = 2000

# --- documents a template may REQUIRE of a beneficiary (master prompt s13) ---
# Distinct from the GATE documents in the routes module: those are evidence a PROGRAMME
# produces to pass a gate; these are evidence a SITE must supply before it is generated.
TEMPLATE_REQUIRED_DOCUMENTS: list[tuple[str, str]] = [
    ("site_survey",              "Site survey"),
    ("load_assessment",          "Load assessment"),
    ("roof_structural_report",   "Roof structural report"),
    ("land_title",               "Land title / lease"),
    ("grid_connection_letter",   "Grid connection letter"),
    ("environmental_screening",  "Environmental screening"),
    ("community_consent",        "Community consent"),
    ("electricity_bill",         "Recent electricity bill"),
]

# --- the template parameter schema (master prompt s13) ----------------------
# ONE definition, used by three things that would otherwise drift apart: the form that is
# rendered, the validator that accepts a submission, and the generator (slice 7) that
# reads a version back. A field that is not here cannot be stored, and a value that was
# never offered cannot be saved -- same rule as the phase/status vocabularies above.
#
# `kind` is how the value is captured and checked:
#   select      -- exactly one code from `source`
#   multiselect -- a list of codes from `source` (may be empty unless required)
#   number_list -- a list of positive numbers (the standard sizes a template offers)
#   number      -- one non-negative number
#   bool        -- true/false
#
# Release 1 covers the fields the generation path in slice 7 actually consumes. The rest
# of s13's list (risk template, KPI template, carbon method, drawings, reports) arrives
# with the slices that produce those artefacts -- an empty field in the UI that nothing
# reads would be a promise the system does not keep.
TEMPLATE_PARAMETER_FIELDS: list[dict] = [
    {"key": "system_configuration", "label": "System configuration",
     "kind": "select", "source": "SYSTEM_CONFIGURATIONS", "required": True},
    {"key": "typical_load_profile", "label": "Typical load profile",
     "kind": "select", "source": "LOAD_PROFILES", "required": True},
    {"key": "standard_pv_capacities_kw", "label": "Standard PV capacities (kWp)",
     "kind": "number_list", "required": True},
    {"key": "battery_options_kwh", "label": "Standard battery options (kWh)",
     "kind": "number_list", "required": False},
    {"key": "generator_integration", "label": "Generator integration",
     "kind": "bool", "required": False},
    {"key": "ups_integration", "label": "UPS integration",
     "kind": "bool", "required": False},
    {"key": "standard_equipment_ids", "label": "Standard equipment",
     "kind": "multiselect", "source": "EQUIPMENT_CATALOG", "required": False},
    {"key": "required_beneficiary_fields", "label": "Required beneficiary fields",
     "kind": "multiselect", "source": "BENEFICIARY_FIELDS", "required": True},
    {"key": "required_documents", "label": "Required site documents",
     "kind": "multiselect", "source": "TEMPLATE_REQUIRED_DOCUMENTS", "required": False},
    {"key": "funding_model", "label": "Funding model",
     "kind": "select", "source": "FUNDING_SOURCES", "required": False},
    {"key": "procurement_strategy", "label": "Procurement strategy",
     "kind": "select", "source": "DELIVERY_MODELS", "required": False},
    {"key": "om_model", "label": "O&M model",
     "kind": "select", "source": "OM_MODELS", "required": False},
    {"key": "warranty_years", "label": "Warranty (years)",
     "kind": "number", "required": False},
]

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
