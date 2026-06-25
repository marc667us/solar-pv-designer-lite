# SolarPro Global — Policy Set

Last revised: 2026-06-25

The 12 policies in this directory map directly to SOC 2 Type II Trust
Service Criteria. Each policy is short, concrete, and grounded in what the
platform actually does today (not a generic template).

| # | Policy | TSC reference |
|---|---|---|
| 1 | [Information Security Policy](information_security.md) | CC1, CC2 |
| 2 | [Access Control Policy](access_control.md) | CC6.1, CC6.2 |
| 3 | [Password Policy](password.md) | CC6.1 |
| 4 | [Secure Development Policy](secure_development.md) | CC8.1 |
| 5 | [Backup Policy](backup.md) | A1.2 |
| 6 | [Incident Response Policy](incident_response.md) | CC7.3 |
| 7 | [Change Management Policy](change_management.md) | CC8.1 |
| 8 | [Vendor Management Policy](vendor_management.md) | CC9.2 |
| 9 | [AI Governance Policy](ai_governance.md) | CC5.1 |
| 10 | [Privacy Policy](privacy.md) | P1, P3, P4 |
| 11 | [Acceptable Use Policy](acceptable_use.md) | CC2.2 |
| 12 | [Data Classification Policy](data_classification.md) | C1.1 |

## Governance

- **Policy owner**: Engineering Lead.
- **Approver**: Owner (SolarPro Global founder).
- **Review cycle**: every 12 months OR after any High-severity incident.
- **Change log**: tracked in git (`docs/policies/`).
- **Distribution**: all engineers + auditors; mirror in onboarding handbook.

## How to use these

When a SOC 2 auditor asks "do you have a written X policy?" — point them
at the matching file. Each policy ends with concrete controls + the live
artifacts that implement them, so the auditor can independently verify.
