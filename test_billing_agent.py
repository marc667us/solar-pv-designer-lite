"""Tests for billing_agent.py (deterministic payment-oversight service, ADR-0009).

In-memory SQLite + fake view_functions/env. No web_app import, no network.
"""

from __future__ import annotations

import contextlib
import sqlite3

import pytest

import billing_agent as ba


def _db_with(cols_extra="", index=True, disputes=True, events=True, dup=False,
             aging=False):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE payments (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, "
        "gateway TEXT, plan TEXT, amount_usd REAL, currency TEXT, reference TEXT, "
        "status TEXT, created_at TEXT" + cols_extra + ")")
    if index:
        conn.execute("CREATE UNIQUE INDEX ux_payments_reference ON payments(reference) "
                     "WHERE reference <> '' AND gateway IN ('paystack','stripe')")
    conn.execute("INSERT INTO payments (user_id,gateway,reference,status) VALUES (1,'paystack','r1','success')")
    if dup:
        # Insert a duplicate directly into a table WITHOUT the guarding index by
        # dropping it first (simulate a pre-fix state with real duplicates).
        conn.execute("DROP INDEX IF EXISTS ux_payments_reference")
        conn.execute("INSERT INTO payments (user_id,gateway,reference,status) VALUES (2,'paystack','r1','success')")
    if events:
        conn.execute("CREATE TABLE payment_events (id INTEGER PRIMARY KEY, reference TEXT, event_type TEXT)")
        conn.execute("INSERT INTO payment_events (reference,event_type) VALUES ('r1','payment_recorded')")
    if disputes:
        conn.execute("CREATE TABLE payment_disputes (id INTEGER PRIMARY KEY, reference TEXT, "
                     "user_id INTEGER, status TEXT, created_at TEXT)")
        if aging:
            conn.execute("INSERT INTO payment_disputes (reference,user_id,status,created_at) "
                         "VALUES ('r1',1,'open','2020-01-01 00:00:00')")
    conn.commit()

    @contextlib.contextmanager
    def get_db():
        yield conn
        conn.commit()
    return get_db


FULL_VIEWS = {"terms_of_payment", "refund_policy", "stripe_webhook",
              "paystack_webhook", "upgrade", "account_invoice", "admin_disputes"}
FULL_ENV = {"STRIPE_WEBHOOK_SECRET": "x", "STRIPE_SECRET_KEY": "x", "PAYSTACK_SECRET_KEY": "x"}


def test_all_green_when_everything_present():
    r = ba.run_oversight(_db_with(), FULL_VIEWS, FULL_ENV, is_pg=False)
    assert r["overall_status"] == "ok"
    assert r["score"] == 100
    assert {s["name"] for s in r["skills"]} == {
        "idempotency_guard", "evidence_capture", "webhook_protection",
        "terms_published", "dispute_sla", "stripe_compliance", "workflow_protection"}


def test_duplicate_payments_is_a_hard_fail():
    r = ba.run_oversight(_db_with(dup=True), FULL_VIEWS, FULL_ENV, is_pg=False)
    idem = next(s for s in r["skills"] if s["name"] == "idempotency_guard")
    assert idem["status"] == "fail"
    assert r["overall_status"] == "fail"


def test_missing_terms_page_fails():
    views = FULL_VIEWS - {"refund_policy"}
    r = ba.run_oversight(_db_with(), views, FULL_ENV, is_pg=False)
    terms = next(s for s in r["skills"] if s["name"] == "terms_published")
    assert terms["status"] == "fail"
    assert "/refund-policy" in terms["detail"]


def test_missing_webhook_secret_warns():
    env = {"STRIPE_SECRET_KEY": "x", "STRIPE_WEBHOOK_SECRET": "x"}  # no paystack
    r = ba.run_oversight(_db_with(), FULL_VIEWS, env, is_pg=False)
    wh = next(s for s in r["skills"] if s["name"] == "webhook_protection")
    assert wh["status"] == "warn"
    assert "PAYSTACK_SECRET_KEY" in wh["detail"]


def test_aging_dispute_fails_sla():
    r = ba.run_oversight(_db_with(aging=True), FULL_VIEWS, FULL_ENV, is_pg=False)
    sla = next(s for s in r["skills"] if s["name"] == "dispute_sla")
    assert sla["status"] == "fail"


def test_missing_index_is_warn_not_fail_when_no_duplicates():
    r = ba.run_oversight(_db_with(index=False), FULL_VIEWS, FULL_ENV, is_pg=False)
    idem = next(s for s in r["skills"] if s["name"] == "idempotency_guard")
    assert idem["status"] == "warn"      # app-level dedupe still active; not a hard fail


def test_pci_card_column_fails_stripe_compliance():
    # A payments table that stores a card number is a PCI-scope violation.
    r = ba.run_oversight(_db_with(cols_extra=", card_number TEXT"),
                         FULL_VIEWS, FULL_ENV, is_pg=False)
    sc = next(s for s in r["skills"] if s["name"] == "stripe_compliance")
    assert sc["status"] == "fail"
    assert "No card data stored" in sc["detail"]


def test_stripe_not_configured_is_na_not_a_fail():
    # Stripe is not the active gateway (no STRIPE_SECRET_KEY) -> Stripe-specific
    # compliance is N/A, NOT a hard fail. You can't fail compliance with a
    # gateway you don't use. (Paystack-only deployment.)
    env = {"PAYSTACK_SECRET_KEY": "x"}   # no STRIPE_SECRET_KEY / STRIPE_WEBHOOK_SECRET
    r = ba.run_oversight(_db_with(), FULL_VIEWS, env, is_pg=False)
    sc = next(s for s in r["skills"] if s["name"] == "stripe_compliance")
    assert sc["status"] == "ok"
    assert "not configured" in sc["detail"].lower()


def test_stripe_active_but_missing_webhook_secret_fails():
    # Stripe IS active but its webhook secret is missing -> a real compliance gap.
    env = {"STRIPE_SECRET_KEY": "x", "PAYSTACK_SECRET_KEY": "x"}  # no STRIPE_WEBHOOK_SECRET
    r = ba.run_oversight(_db_with(), FULL_VIEWS, env, is_pg=False)
    sc = next(s for s in r["skills"] if s["name"] == "stripe_compliance")
    assert sc["status"] == "fail"
    assert "Webhook signature verification: MISSING" in sc["detail"]


def test_no_card_stored_even_when_stripe_off_still_fails_pci():
    # PCI is gateway-agnostic: card columns are a fail even with Stripe off.
    env = {"PAYSTACK_SECRET_KEY": "x"}
    r = ba.run_oversight(_db_with(cols_extra=", card_number TEXT"), FULL_VIEWS, env, is_pg=False)
    sc = next(s for s in r["skills"] if s["name"] == "stripe_compliance")
    assert sc["status"] == "fail"
    assert "PCI" in sc["detail"]


def test_stripe_off_but_pci_unverifiable_is_unknown_not_ok():
    # Stripe off AND the card-column read fails -> the gateway-agnostic PCI
    # control is unverifiable, so the verdict must NOT be a false 'ok' (Codex).
    import contextlib

    @contextlib.contextmanager
    def broken_db():
        raise RuntimeError("connection gone")
        yield  # pragma: no cover

    r = ba.skill_stripe_compliance(broken_db, False, {"PAYSTACK_SECRET_KEY": "x"}, FULL_VIEWS)
    assert r["status"] == "unknown"


def test_agent_never_claims_autonomous_money_actions():
    # Governance invariant: the forbidden actions must be declared.
    for a in ("issue_refund", "email_customer", "modify_terms", "modify_prices"):
        assert a in ba.AGENT["approval_required_actions"]


def test_missing_payment_endpoint_fails_workflow():
    views = FULL_VIEWS - {"stripe_webhook"}
    r = ba.run_oversight(_db_with(), views, FULL_ENV, is_pg=False)
    wf = next(s for s in r["skills"] if s["name"] == "workflow_protection")
    assert wf["status"] == "fail"


def test_db_failure_degrades_to_unknown_never_false_ok():
    # A broken connection must NOT be reported as healthy (Codex finding #1/#3):
    # every DB-dependent skill degrades to 'unknown', and run_oversight does not
    # raise.
    import contextlib

    @contextlib.contextmanager
    def broken_db():
        raise RuntimeError("connection gone")
        yield  # pragma: no cover

    r = ba.run_oversight(broken_db, FULL_VIEWS, FULL_ENV, is_pg=False)
    by = {s["name"]: s["status"] for s in r["skills"]}
    assert by["idempotency_guard"] == "unknown"
    assert by["evidence_capture"] == "unknown"
    assert by["dispute_sla"] == "unknown"          # NOT 'ok' (the bug that was fixed)
    # non-DB skills still evaluate from views/env
    assert by["terms_published"] == "ok"
    assert by["workflow_protection"] == "ok"
    assert r["overall_status"] in ("warn", "unknown")  # never falsely 'ok'
