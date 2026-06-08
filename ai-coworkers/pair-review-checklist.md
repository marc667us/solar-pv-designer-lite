# Pair-Review Checklist

Codex must verify ALL 18 items for every feature before approving:

1. **Requirement** — is the requirement fully implemented?
2. **Frontend** — is there a frontend page or component where required?
3. **Backend** — is there a backend API endpoint where required?
4. **Database** — is there a model or migration where required?
5. **Tenant filter** — does every tenant-owned query filter by `tenant_id`?
6. **RLS** — is PostgreSQL Row-Level Security applied where needed?
7. **Roles** — are roles and permissions enforced?
8. **Hidden pages** — are hidden / restricted pages protected by backend authorization (not just menu-hidden)?
9. **Validation** — are user inputs validated (schema + business rules)?
10. **Error handling** — are errors handled properly with structured error responses?
11. **Audit** — are logs and audit log entries created for important actions?
12. **Tests** — are tests included (unit, integration, security, RLS, logout)?
13. **Indexes** — are indexes added for major queries (especially tenant-scoped)?
14. **Caching** — is caching used where beneficial, with tenant-scoped keys?
15. **Queues** — are heavy jobs moved to background queues (PDF/DOCX/Excel/BOQ/reports/AI/email)?
16. **Secrets** — are secrets excluded from Git?
17. **Logout** — does logout really revoke access (refresh tokens, session_version)?
18. **Scale** — does the feature scale safely (1000 concurrent users, multi-tenant load)?
