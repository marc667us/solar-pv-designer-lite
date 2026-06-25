"""
SolarPro role constants — single source of truth for role names.

SOC 2 M1.4 (2026-06-25). Use these constants instead of string literals
when invoking @require_role / @require_any_role so a rename or typo in
the realm export is caught at import time, not at runtime.

The SOC 2 plan called for 7 roles; 4 already existed under different
labels (mapping below), so only 3 new roles were added to the realm.

Plan name              -> realm role name
------------------------------------------
Platform Admin         -> platform_super_admin
Tenant Admin           -> tenant_admin
Supplier Admin         -> supplier_admin
Supplier Staff         -> supplier_user                # already existed
Electrical Engineer    -> solar_engineer
Electrical Estimator   -> estimator                    # already existed
Electrician            -> electrician_installer        # already existed
Procurement Officer    -> procurement_specialist
Project Manager        -> sales_manager   (closest)
Finance Officer        -> finance_officer
Client                 -> customer
Auditor                -> read_only                    # NEW
Read Only              -> read_only                    # NEW
API Client             -> api_service_account          # already existed
AI Agent               -> ai_agent                     # NEW
Background Worker      -> background_worker            # NEW

All callers should import from app.security.roles rather than spelling
the role name themselves. The constants follow the realm-prod.json names
exactly so JWT claim matching is direct.
"""
from __future__ import annotations

# ── Elevated administrative roles ────────────────────────────────────────
PLATFORM_SUPER_ADMIN  = "platform_super_admin"
MARKETPLACE_ADMIN     = "marketplace_admin"
TENANT_ADMIN          = "tenant_admin"

# ── Engineering / installation ───────────────────────────────────────────
SOLAR_ENGINEER        = "solar_engineer"
SENIOR_ENGINEER       = "senior_engineer"
ELECTRICIAN_INSTALLER = "electrician_installer"
ESTIMATOR             = "estimator"

# ── Supplier side ───────────────────────────────────────────────────────
SUPPLIER_ADMIN        = "supplier_admin"
SUPPLIER_USER         = "supplier_user"
CATALOGUE_MANAGER     = "catalogue_manager"

# ── Procurement + finance + commercial ───────────────────────────────────
PROCUREMENT_SPECIALIST = "procurement_specialist"
FINANCE_OFFICER        = "finance_officer"
SALES_AGENT            = "sales_agent"
SALES_MANAGER          = "sales_manager"

# ── Support + customer ──────────────────────────────────────────────────
SUPPORT_AGENT         = "support_agent"
CUSTOMER              = "customer"

# ── SOC 2 M1.4 additions (2026-06-25) ───────────────────────────────────
READ_ONLY         = "read_only"          # auditors / external reviewers
AI_AGENT          = "ai_agent"           # ADK/LLM agents
BACKGROUND_WORKER = "background_worker"  # celery/RQ/cron workers

# ── Service-account umbrella ────────────────────────────────────────────
API_SERVICE_ACCOUNT = "api_service_account"


# Convenience groupings (use with @require_any_role)

ELEVATED_ROLES = (
    PLATFORM_SUPER_ADMIN,
    TENANT_ADMIN,
    FINANCE_OFFICER,
    READ_ONLY,   # auditors carry this; MFA enforcement should target this group
)

TENANT_DATA_WRITERS = (
    PLATFORM_SUPER_ADMIN,
    TENANT_ADMIN,
    SOLAR_ENGINEER,
    SENIOR_ENGINEER,
    PROCUREMENT_SPECIALIST,
    SALES_MANAGER,
    SUPPLIER_ADMIN,
    SUPPLIER_USER,
    CATALOGUE_MANAGER,
)

NON_HUMAN_IDENTITIES = (
    API_SERVICE_ACCOUNT,
    AI_AGENT,
    BACKGROUND_WORKER,
)


ALL_ROLES = (
    PLATFORM_SUPER_ADMIN, MARKETPLACE_ADMIN, TENANT_ADMIN,
    SOLAR_ENGINEER, SENIOR_ENGINEER, ELECTRICIAN_INSTALLER, ESTIMATOR,
    SUPPLIER_ADMIN, SUPPLIER_USER, CATALOGUE_MANAGER,
    PROCUREMENT_SPECIALIST, FINANCE_OFFICER, SALES_AGENT, SALES_MANAGER,
    SUPPORT_AGENT, CUSTOMER,
    READ_ONLY, AI_AGENT, BACKGROUND_WORKER,
    API_SERVICE_ACCOUNT,
)
