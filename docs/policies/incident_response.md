# Incident Response Policy

Version: 1.0 · Effective: 2026-06-25 · Owner: Engineering Lead

## Purpose

Define how SolarPro detects, contains, eradicates, and recovers from
security incidents.

## Scope

Any event that affects confidentiality, integrity, or availability of
SolarPro data or systems. Includes: data leak, unauthorised access,
ransomware, supply-chain compromise, DoS, accidental destructive op.

## Policy

1. **Severity levels**
   - **P1 (Critical)** — active data exfiltration, full outage, master
     credential leak. SLA: respond within 15 min.
   - **P2 (High)** — partial outage, suspected unauthorised access, KC
     login broken for elevated roles. SLA: 1 hour.
   - **P3 (Medium)** — single user reports, transient error spike. SLA:
     same business day.
   - **P4 (Low)** — cosmetic, low-severity finding. SLA: weekly triage.

2. **Phases**

   - **Detect** — sources: error_logs spike, audit_logs anomaly, KC
     event-stream, Render outage email, customer report.
   - **Contain** — pull the trigger that limits damage: rotate a key,
     disable a route, revoke a token, kill a deploy. Document in real
     time.
   - **Eradicate** — fix the root cause in code, test, deploy. Codex +
     Supervisor review required.
   - **Recover** — restore from backup if data was damaged; smoke
     thoroughly before declaring resolved.
   - **Learn** — write a post-mortem in `docs/IMPLEMENTATION_LOG.md`
     within 7 days. P1/P2 trigger a policy review.

3. **Communication**
   - Internal: Engineering Lead + Owner.
   - External: customers affected get an email within 24 hours of
     containment for P1/P2. Regulators per jurisdiction (GDPR
     supervisory authority within 72h if EU data involved).

4. **Evidence preservation** — DO NOT clear logs during response. The
   error_logs + audit_logs tables are append-only (M3.2 target);
   filesystem dumps preserved as workflow artifacts before any reset.

5. **Forensics readiness** — incident commander is the Engineering
   Lead. Owner has authority to engage external IR firm.

## Enforcement

- The Engineering Lead is on-call by default. Owner is the escalation.
- Failure to file a post-mortem within 7 days for P1/P2 is itself a
  policy violation.

## Review

After every P1/P2; annual otherwise.
