# SolarPro Global — Enterprise Security Architecture

**Platform:** Intelligent Global PV Solar System Design Platform
**Security Model:** Zero Trust Multi-Tenant Architecture
**Last Updated:** 2026-06-01

---

## 1. Security Architecture Overview

```
Internet
   ↓
Cloudflare (DDoS protection, WAF, bot detection, GeoDNS, Turnstile)
   ↓
Nginx Ingress (TLS termination, rate limiting, security headers)
   ↓
Flask Backend (CSRF, session management, RBAC middleware, audit logging)
   ↓
Authentication Service (JWT + bcrypt, session table, MFA)
   ↓
Authorization Service (RBAC + tenant_id enforcement)
   ↓
Backend API Routes (tenant-filtered queries only)
   ↓
Neon PostgreSQL (Row Level Security — last line of defense)
```

---

## 2. The Zero Trust Golden Rule

> **No request reaches data unless ALL pass:**
> 1. Valid login session
> 2. Active subscription
> 3. Correct tenant_id (`organization_id` match)
> 4. Correct role & permission
> 5. PostgreSQL RLS enforcement at database layer

**Every query must be scoped to tenant:**
```python
# CORRECT:
c.execute("SELECT * FROM projects WHERE organization_id=? AND id=?", [org_id, project_id])

# WRONG — NEVER:
c.execute("SELECT * FROM projects WHERE id=?", [project_id])
```

---

## 3. User & Organization Identity

| Entity | ID Format | Example |
|--------|-----------|---------|
| User (UUID) | uuid primary key | `550e8400-e29b-41d4-a716-446655440000` |
| User (human) | `USR-000001` | USR-000042 |
| Organization | `ORG-000001` | ORG-000007 |
| Project | `PRJ-000001` | PRJ-000123 |
| Assessment | `ASM-000001` | ASM-000015 |
| Proposal | `PRP-000001` | PRP-000088 |
| Ticket | `TKT-000001` | TKT-000203 |
| Payment | `PAY-000001` | PAY-000089 |
| Subscription | `SUB-000001` | SUB-000012 |

**Never use email as primary key.** UUID is PK; human codes are for display.

---

## 4. Role-Based Access Control (RBAC)

| Role | Access Scope |
|------|-------------|
| `super_admin` | Full platform — all tenants, all data |
| `platform_admin` | Platform ops — no tenant data |
| `sales_manager` | CRM, leads, assessments, proposals |
| `engineer` | Projects, PV design, reports, BOQ |
| `proposal_officer` | Proposals, BOQ, client documents |
| `support_officer` | Tickets, helpline, CRM notes |
| `installer_user` | Own opportunities, proposals |
| `consultant_user` | Own projects and reports |
| `customer` | Own projects only |

---

## 5. Authentication

- **Password hashing:** `werkzeug.security.generate_password_hash()` (PBKDF2-SHA256)
- **Session storage:** Flask server-side sessions + `user_sessions` table
- **Session fields:** `user_id`, `organization_id`, `ip_address`, `device`, `expires_at`, `is_revoked`
- **Logout:** sets `is_revoked = TRUE` on session record
- **Logout all devices:** revokes all sessions for `user_id`
- **MFA:** `pyotp` TOTP — ⬜ Pending implementation for admin + enterprise

---

## 6. PostgreSQL Row Level Security (RLS)

Full implementation: `migrations/002_rls_policies.sql`

```sql
-- Backend sets this at the START of every request:
SET app.current_tenant = 'org-uuid';
SET app.current_user   = 'user-uuid';
SET app.current_role   = 'engineer';

-- All queries automatically filter by tenant via RLS policies.
-- Even if application code has a bug, the DB cannot return cross-tenant data.
```

### Tables with RLS:
`organizations`, `users`, `user_sessions`, `projects`, `leads`, `assessment_requests`,
`crm_opportunities`, `proposals`, `installers`, `procurement_packages`, `bidder_submissions`,
`subscriptions`, `payments`, `tickets`, `ticket_replies`, `uploaded_files`, `audit_log`, `email_logs`

---

## 7. API Security Rules

1. Never put secret API keys in frontend JavaScript
2. All keys stored in environment variables only — never in git
3. Flow: `Frontend → Backend → External APIs` (never direct)
4. Paystack public key is the only key allowed in frontend
5. All Paystack webhooks verified via HMAC-SHA512 signature
6. Rate limiting: login 5/min → lockout; AI 10/min; general API 60/min

---

## 8. Hidden Page Authorization

Every protected route requires ALL:
1. Valid login session (`@login_required` / `admin_required`)
2. Active subscription check
3. Correct `organization_id` scoping
4. Correct role/permission
5. Valid CSRF token on POST
6. Backend authorization check
7. PostgreSQL RLS enforcement

### Protected routes:
| Route | Minimum Access |
|-------|---------------|
| `/admin` | `is_admin = True` |
| `/admin/operations` | Admin only |
| `/admin/logs` | Admin only |
| `/admin/platform` | Admin only |
| `/admin/agent` | Admin only |
| `/project/<pid>/*` | Owner org match |
| `/project/<pid>/report/*` | Owner org match |

---

## 9. AI Agent Security

| Agent | Can | Cannot |
|-------|-----|--------|
| Prospecting AI | Read/write opportunities, update CRM | Delete subscriptions, modify payments |
| Helpline AI | Read assessments, create follow-up tasks | Issue refunds, approve payments |

---

## 10. Payment Security

1. Frontend initiates payment only (Paystack reference)
2. Backend verifies payment server-side (`/api/paystack.co/transaction/verify`)
3. Webhook HMAC-SHA512 signature verified on every event
4. Subscription activated only after backend verification
5. Amount, currency, customer email all matched before activation
6. Payment references stored; duplicate references rejected
7. All payment events logged to `payments` table + audit_log

---

## 11. Bot & Scraper Protection

- `robots.txt` — blocks `/admin`, `/dashboard`, `/project`, `/api` from crawlers ✅
- `flask_limiter` rate limiting on all public endpoints ✅
- Login throttling — 5 failed → 15-minute lockout ✅
- Cloudflare Turnstile — ⬜ Pending (registration, assessment forms)
- Session validation on all AJAX API calls ✅

---

## 12. Security Monitoring (Admin Operations Center)

Available at `/admin/operations`:

| Metric | Alert Level |
|--------|------------|
| Failed logins > 10/hour | WARNING |
| Tenant isolation violations | CRITICAL |
| Service downtime | CRITICAL |
| API error rate > 5% | WARNING |
| Queue backlog > 100 | WARNING |

---

## 13. Disaster Recovery

| Service | Target Recovery Time |
|---------|---------------------|
| Website | < 4 hours |
| CRM data | < 2 hours |
| Payments | < 1 hour |
| Database | < 2 hours |

**Backup via Admin Ops Center:** `/admin/operations` → Backup & Recovery section → "Backup Now"

**Kubernetes rollback:**
```bash
kubectl rollout undo deployment/solarpro-backend -n solar-production
```

---

## 14. Customer Data Ownership

**Customer owns:** Assessment data, lead data, project data, uploaded files, proposals
**Platform owns:** Software, algorithms, templates, AI models, scoring engines

---

## 15. Security Maturity Checklist

### ✅ Implemented
- [x] Password hashing (PBKDF2-SHA256)
- [x] CSRF protection on all POST forms
- [x] Brute-force login lockout (5 attempts → 15 min)
- [x] Content Security Policy headers
- [x] Paystack webhook HMAC signature verification
- [x] Audit log table in DB
- [x] `robots.txt` blocking crawlers from auth/admin
- [x] Health check endpoints (`/api/health`, `/api/health/database`, `/api/health/redis`, `/api/health/queue`, `/api/health/storage`, `/api/health/ai`)
- [x] Structured JSON logging (app, audit, security, AI, queue)
- [x] Admin Operations Center — NOC/SOC/AI/Backup dashboards
- [x] Session log viewer (`/admin/logs`)
- [x] K8s NetworkPolicy (zero-trust pod-to-pod)
- [x] K8s PodDisruptionBudget (HA during maintenance)
- [x] PostgreSQL schema with UUID PKs + human IDs (USR-/ORG-/PAY-)
- [x] RLS policies on all 18 tenant-owned tables
- [x] CI/CD pipeline with security scanning (pip-audit, Semgrep, Trivy)
- [x] Docker non-root user
- [x] Multi-region K8s manifests (dev/staging/production)
- [x] Geo-aware deployment architecture

### ⬜ Pending (must complete before enterprise launch)
- [ ] **Admin 2FA** — `pyotp` TOTP (HIGH PRIORITY)
- [ ] **DMARC DNS record:** `_dmarc.aiappinvent.com TXT "v=DMARC1; p=none; rua=mailto:marc667us@yahoo.com"`
- [ ] **Resend domain verification** — SPF/DKIM records on Namecheap
- [ ] **SMTP_* GitHub Secrets** — for Render production email
- [ ] **Cloudflare Turnstile** on registration, login, assessment forms
- [ ] **Daily automated DB backup** to cloud storage
- [ ] **Neon PostgreSQL migration** from SQLite (use `migrations/001_postgresql_schema.sql`)
- [ ] **K8s cluster provisioning** (GKE / EKS / DigitalOcean)
- [ ] **Geo-routing setup** — Cloudflare Load Balancing + GeoDNS
- [ ] **Database sharding** — tenant-based consistent hash sharding

---

## 16. App Security Risk Register (from securityMD plan)

| Risk | Impact | Control |
|------|--------|---------|
| API key exposure | Attackers abuse API quota/billing | Keys in env vars only; proxy pattern |
| Payment webhook abuse | Unauthorized subscription activation | HMAC verification + amount match |
| AI cost abuse | High OpenRouter/Anthropic cost | Rate limits per plan; Ollama for internal tasks |
| Login brute force | Account takeover | 5-attempt lockout + audit log |
| Token theft | Account takeover | HTTP-only cookies; short expiry; revocation |
| Tenant data leakage | Cross-customer data exposure | tenant_id on every query + RLS |
| Admin compromise | Full system takeover | 2FA (pending) + IP tracking + audit logs |
| SMTP abuse | Spam/blacklisting | SPF/DKIM/DMARC (pending) + send limits |
| Disaster/data loss | Business interruption | Daily backups + K8s rollback + Neon PITR |
