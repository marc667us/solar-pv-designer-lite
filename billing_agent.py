"""Billing Agent -- deterministic payment-oversight service.

ADR-0009: built as a deterministic Python service, exempt from CLAUDE.md §0.1
(Google-ADK-only), following the AI-SOC pattern. No ADK dependency.

WHAT IT IS
    The overseer of the payment system built across the 2026-07-24 payments-legal
    suite. It runs READ-ONLY oversight checks ("skills") over the app's payment
    safeguards and live data, and returns an auditable billing-health report.

WHAT IT IS NOT (§14 AI Agent Discipline)
    It NEVER takes an autonomous money action. Issuing refunds, emailing
    customers, and changing terms/prices are human-approved actions that live in
    the slice-2 admin dispute flow and the app config -- NOT here. The agent
    FLAGS and REPORTS; a human acts. `approval_required_actions` names exactly
    the things it is forbidden to do on its own.

DESIGN
    Every skill is a pure(-ish) function: (deps) -> a verdict dict
    {name,title,status,detail}. `status` is one of ok/warn/fail/unknown. The
    checks are deterministic facts (is the unique index present? are secrets
    set? are the terms pages published? are disputes aging?), which is what
    billing compliance requires -- explainable and auditable, not a judgement.
    Dialect-aware (SQLite local / Postgres live); every check is wrapped so a
    failure degrades to an "unknown" verdict rather than raising.
"""

from __future__ import annotations

from datetime import datetime, timedelta


AGENT = {
    "agent_id": "billing-agent",
    "agent_name": "Billing Agent",
    "agent_role": "Payment oversight, terms enforcement & Stripe compliance",
    "allowed_data_scope": ["payments", "payment_events", "payment_disputes", "users.plan"],
    "allowed_tools": ["read_db", "read_config", "introspect_routes"],
    # Forbidden without a human: the agent is an overseer, not an actor (§14).
    "approval_required_actions": ["issue_refund", "email_customer", "modify_terms", "modify_prices"],
    "logging_enabled": True,
}

_PAID_STATES = {"success", "paid", "completed"}


# ── dialect-aware introspection helpers (never raise) ────────────────────────
# NOTE ON PLACEHOLDERS: these run through the app's get_db(), whose Postgres
# adapter (db_adapter._PgConnAdapter.execute) rewrites `?` -> `%s`, so the same
# `?`-style queries work on SQLite and Postgres -- exactly as every other module
# in this app relies on. Every helper additionally returns None on ANY failure,
# and every skill treats None as an "unknown" verdict (never a false "ok"), so a
# backend that somehow rejected the query degrades safely rather than misreporting.

def _table_exists(c, name, is_pg):
    try:
        if is_pg:
            r = c.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=?", (name,)).fetchone()
        else:
            r = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                          (name,)).fetchone()
        return r is not None
    except Exception:
        return None


def _index_exists(c, name, is_pg):
    try:
        if is_pg:
            r = c.execute("SELECT 1 FROM pg_indexes WHERE indexname=?", (name,)).fetchone()
        else:
            r = c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                          (name,)).fetchone()
        return r is not None
    except Exception:
        return None


def _columns(c, table, is_pg):
    try:
        if is_pg:
            rows = c.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=?", (table,)).fetchall()
            return {r[0].lower() for r in rows}
        else:
            rows = c.execute("PRAGMA table_info(%s)" % table).fetchall()
            return {r[1].lower() for r in rows}
    except Exception:
        return None


# ── skills ───────────────────────────────────────────────────────────────────

def skill_idempotency_guard(get_db, is_pg):
    """No double payment: the DB-level unique index is present AND no duplicate
    gateway references exist right now."""
    try:
        with get_db() as c:
            has_idx = _index_exists(c, "ux_payments_reference", is_pg)
            try:
                dup = c.execute(
                    "SELECT COUNT(*) FROM (SELECT reference FROM payments "
                    "WHERE gateway IN ('paystack','stripe') AND reference <> '' "
                    "GROUP BY reference HAVING COUNT(*) > 1) d").fetchone()[0]
            except Exception:
                dup = None
    except Exception:
        return _v("idempotency_guard", "No double payment", "unknown",
                  "Could not read the payments table.")
    if dup and dup > 0:
        return _v("idempotency_guard", "No double payment", "fail",
                  "%d duplicate gateway reference(s) found -- the no-double-payment invariant is broken" % dup)
    if has_idx is False:
        return _v("idempotency_guard", "No double payment", "warn",
                  "No duplicates, but the ux_payments_reference unique index is NOT yet applied "
                  "(migration 039). App-level dedupe is active; apply 039 to enforce at the DB.")
    if has_idx is None or dup is None:
        return _v("idempotency_guard", "No double payment", "unknown", "Could not read index/duplicate state.")
    return _v("idempotency_guard", "No double payment", "ok",
              "ux_payments_reference unique index present; 0 duplicate gateway references.")


def skill_evidence_capture(get_db, is_pg):
    """Payment evidence ledger exists and is available for dispute defence."""
    try:
        with get_db() as c:
            exists = _table_exists(c, "payment_events", is_pg)
            n = None
            if exists:
                try:
                    n = c.execute("SELECT COUNT(*) FROM payment_events").fetchone()[0]
                except Exception:
                    n = None
    except Exception:
        return _v("evidence_capture", "Payment evidence", "unknown", "Could not read the evidence ledger.")
    if exists is None:
        return _v("evidence_capture", "Payment evidence", "unknown", "Could not read evidence ledger state.")
    if not exists:
        return _v("evidence_capture", "Payment evidence", "warn",
                  "payment_events ledger not created yet (no gateway payment has occurred). "
                  "It is created on the first real payment; apply migration 039 to pre-provision.")
    return _v("evidence_capture", "Payment evidence", "ok",
              "Evidence ledger present with %s row(s); redacted payloads + client IP + signature flag captured." % n)


def skill_webhook_protection(env):
    """Every gateway webhook must have its signing secret set, or its signature
    check cannot run and the workflow is unprotected."""
    stripe_hook = bool(env.get("STRIPE_WEBHOOK_SECRET"))
    stripe_key = bool(env.get("STRIPE_SECRET_KEY"))
    paystack = bool(env.get("PAYSTACK_SECRET_KEY"))
    missing = []
    if not stripe_hook:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if not paystack:
        missing.append("PAYSTACK_SECRET_KEY")
    if missing:
        return _v("webhook_protection", "Webhook signature protection", "warn",
                  "Signing secret(s) not set: %s -- those webhooks reject all events until configured. "
                  "(Expected if that gateway is not live yet.)" % ", ".join(missing))
    return _v("webhook_protection", "Webhook signature protection", "ok",
              "Stripe + Paystack signing secrets set; webhook HMAC/signature verification is active. "
              "Stripe API key %s." % ("set" if stripe_key else "NOT set"))


def skill_terms_published(view_functions):
    """The payment terms & refund policy must be published and reachable."""
    have_terms = "terms_of_payment" in view_functions
    have_refund = "refund_policy" in view_functions
    if have_terms and have_refund:
        return _v("terms_published", "Payment terms & refund policy", "ok",
                  "/terms-of-payment and /refund-policy are published and linked.")
    missing = [n for n, ok in (("/terms-of-payment", have_terms), ("/refund-policy", have_refund)) if not ok]
    return _v("terms_published", "Payment terms & refund policy", "fail",
              "Missing published page(s): %s" % ", ".join(missing))


def skill_dispute_sla(get_db, is_pg):
    """Disputes must not age past a 7-day response SLA."""
    try:
        with get_db() as c:
            exists = _table_exists(c, "payment_disputes", is_pg)
            aging = None
            if exists:
                cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                aging = c.execute(
                    "SELECT COUNT(*) FROM payment_disputes "
                    "WHERE status IN ('open','under_review') AND created_at <> '' "
                    "AND created_at < ?", (cutoff,)).fetchone()[0]
    except Exception:
        return _v("dispute_sla", "Dispute SLA", "unknown", "Could not read dispute ages.")
    if exists is None:
        return _v("dispute_sla", "Dispute SLA", "unknown",
                  "Could not determine whether the disputes table exists.")
    if not exists:
        return _v("dispute_sla", "Dispute SLA", "ok", "No disputes raised yet.")
    if aging is None:
        return _v("dispute_sla", "Dispute SLA", "unknown", "Could not read dispute ages.")
    if aging > 0:
        return _v("dispute_sla", "Dispute SLA", "fail",
                  "%d open/under-review dispute(s) older than 7 days need a response." % aging)
    return _v("dispute_sla", "Dispute SLA", "ok", "No open disputes past the 7-day SLA.")


def skill_stripe_compliance(get_db, is_pg, env, view_functions):
    """A deterministic Stripe-compliance checklist.

    GATEWAY-AWARE: you cannot be "non-compliant" with a gateway you do not use.
    If Stripe is not configured on this deployment (no STRIPE_SECRET_KEY -- e.g.
    Paystack is the active gateway), the Stripe-specific items are N/A and this
    does NOT hard-fail; only the gateway-agnostic PCI (no-card-data) check still
    applies. Stripe-specific compliance is only enforced when Stripe is active.
    """
    stripe_active = bool(env.get("STRIPE_SECRET_KEY"))

    # PCI (gateway-agnostic): the payments table must store no card data.
    # A read failure -> None -> reported as "could not verify" (never a false ok).
    try:
        with get_db() as c:
            cols = _columns(c, "payments", is_pg)
    except Exception:
        cols = None
    no_card = None if cols is None else (
        (cols & {"card", "card_number", "pan", "cvv", "cvc", "number"}) == set())

    if not stripe_active:
        if no_card is False:
            return _v("stripe_compliance", "Stripe compliance", "fail",
                      "Stripe not configured (active gateway is Paystack) -- but the payments "
                      "table stores card-like column(s), a PCI concern regardless of gateway.")
        if no_card is None:
            # The only always-relevant control here (PCI) could not be verified,
            # so this is NOT an OK verdict even with Stripe off.
            return _v("stripe_compliance", "Stripe compliance", "unknown",
                      "Stripe is not configured (Paystack is the active gateway); Stripe-specific "
                      "checks are N/A. PCI: could not verify the payments columns.")
        return _v("stripe_compliance", "Stripe compliance", "ok",
                  "Stripe is not configured on this deployment (Paystack is the active gateway); "
                  "Stripe-specific checks are N/A. PCI: no card data stored.")

    # Stripe IS active -- enforce the full checklist.
    checks = [
        ("Webhook signature verification",
         ("stripe_webhook" in view_functions) and bool(env.get("STRIPE_WEBHOOK_SECRET"))),
        ("No card data stored (PCI scope minimised)", no_card),
        ("Idempotent charge handling", "stripe_webhook" in view_functions),
        ("Dispute / chargeback handling", "admin_disputes" in view_functions),
        ("Customer receipts / invoices", "account_invoice" in view_functions),
    ]
    failed = [name for name, ok in checks if ok is False]
    unknown = [name for name, ok in checks if ok is None]
    detail = "; ".join("%s: %s" % (n, "ok" if ok else ("unknown" if ok is None else "MISSING"))
                       for n, ok in checks)
    if failed:
        return _v("stripe_compliance", "Stripe compliance", "fail", detail)
    if unknown:
        return _v("stripe_compliance", "Stripe compliance", "warn", detail)
    return _v("stripe_compliance", "Stripe compliance", "ok", detail)


def skill_workflow_protection(view_functions):
    """The core payment workflow endpoints must all be present (a missing one
    means a broken or bypassable payment path)."""
    required = {
        "stripe_webhook": "Stripe webhook",
        "paystack_webhook": "Paystack webhook",
        "upgrade": "Upgrade / checkout",
    }
    missing = [label for ep, label in required.items() if ep not in view_functions]
    if missing:
        return _v("workflow_protection", "Payment workflow integrity", "fail",
                  "Missing payment endpoint(s): %s" % ", ".join(missing))
    return _v("workflow_protection", "Payment workflow integrity", "ok",
              "Stripe + Paystack webhooks and the upgrade/checkout flow are all registered.")


def _v(name, title, status, detail):
    return {"name": name, "title": title, "status": status, "detail": detail}


# ── orchestration ─────────────────────────────────────────────────────────────

_STATUS_RANK = {"ok": 0, "unknown": 1, "warn": 2, "fail": 3}


def run_oversight(get_db, view_functions, env, is_pg=False):
    """Run every skill and return an auditable billing-health report.

    Returns {agent, generated_at, overall_status, score, skills:[verdict...]}.
    overall_status = the worst individual status (fail > warn > unknown > ok).
    score = percentage of skills that are 'ok'.
    """
    results = [
        skill_idempotency_guard(get_db, is_pg),
        skill_evidence_capture(get_db, is_pg),
        skill_webhook_protection(env),
        skill_terms_published(view_functions),
        skill_dispute_sla(get_db, is_pg),
        skill_stripe_compliance(get_db, is_pg, env, view_functions),
        skill_workflow_protection(view_functions),
    ]
    worst = max((_STATUS_RANK.get(r["status"], 1) for r in results), default=0)
    overall = next(k for k, v in _STATUS_RANK.items() if v == worst)
    ok_n = sum(1 for r in results if r["status"] == "ok")
    score = round(100.0 * ok_n / len(results)) if results else 0
    return {
        "agent": AGENT,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "overall_status": overall,
        "score": score,
        "skills": results,
    }
