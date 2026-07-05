"""
Regression tests for the Check-My-Bill "pitch" (_bc_funding_model).

Owner 2026-07-05: when a customer ran Check My Bill from a load schedule WITHOUT
typing an actual bill (actual_bill == 0), the pitch measured the post-loan drop
as `monthly_save / bill`, which the zero-bill guard forced to 0% -- so it read
"your bill drops by 0%, saving GHS <n>/month", a contradiction. The fix measures
savings against a BASELINE (the actual bill, or the expected PURC bill when none
was typed). These tests lock that in and guard the bill>0 path against regression.

Run:  python -m pytest test_bill_check_pitch.py -q
"""
import os

os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "test-admin-pw")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "test-owner-pw")

import web_app as w


def _result(actual_bill, expected_total, monthly_save, target_pct=50,
            loan_payment=200.0, rec_kwp=3.0):
    return {
        "actual_bill": actual_bill,
        "expected": {"total": expected_total},
        "loan": {"estimated_monthly_payment": loan_payment,
                 "cost_per_kwp": 8000, "years": 5},
        "solar": {"estimated_monthly_saving": monthly_save,
                  "target_reduction_pct": target_pct,
                  "recommended_kwp": rec_kwp},
    }


def test_no_bill_uses_expected_baseline_not_zero_percent():
    """The reported bug: no actual bill, but a real saving -> must NOT be 0%."""
    f = w._bc_funding_model(_result(actual_bill=0, expected_total=400.0,
                                    monthly_save=200.0))
    assert f["post_loan_drop_pct"] == 50.0        # 200/400, not 0
    assert f["baseline_estimated"] is True
    assert f["current_bill"] == 400.0             # baseline shown as "today"
    assert f["actual_bill_entered"] == 0.0
    assert "about 0%" not in f["headline_pitch"]  # no nonsensical 0% drop claim
    assert "estimated from your usage" in f["headline_pitch"]


def test_no_bill_never_claims_saving_with_zero_drop():
    """A nonzero GHS saving must always come with a nonzero drop %."""
    f = w._bc_funding_model(_result(actual_bill=0, expected_total=650.0,
                                    monthly_save=325.0))
    assert f["monthly_saving"] > 0
    assert f["post_loan_drop_pct"] > 0            # the contradiction is gone


def test_entered_bill_is_unchanged_baseline_equals_bill():
    """When an actual bill is typed, baseline == bill (no behaviour change)."""
    f = w._bc_funding_model(_result(actual_bill=500.0, expected_total=480.0,
                                    monthly_save=250.0))
    assert f["baseline_estimated"] is False
    assert f["current_bill"] == 500.0             # the typed bill, not expected
    assert f["post_loan_drop_pct"] == 50.0        # 250/500
    assert f["actual_bill_entered"] == 500.0


def test_no_data_shows_prompt_not_numbers():
    """No usage and no bill -> the 'enter details' prompt, no bogus figures."""
    f = w._bc_funding_model(_result(actual_bill=0, expected_total=0.0,
                                    monthly_save=0.0, loan_payment=0.0,
                                    rec_kwp=0.0))
    assert f["post_loan_drop_pct"] == 0.0
    assert f["feasible"] is False
    assert "Enter your monthly bill" in f["headline_pitch"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("all pitch tests passed")
