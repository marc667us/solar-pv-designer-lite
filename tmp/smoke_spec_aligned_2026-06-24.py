"""Spec-aligned engine smoke test (2026-06-24 v2).

Validates the rewritten _boq_safe_rate matches the spec file's worked
example exactly: GHS 15 cable -> total GHS 31.67."""
import os, sys

os.environ.setdefault("DB_PATH", "tmp/smoke_spec_aligned.db")
os.environ.setdefault("SECRET_KEY", "smoke-spec")
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "x")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "x")
for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OLLAMA_URL"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.abspath("."))
print("Importing web_app...")
import web_app  # noqa
print("OK")

errors = []
def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{(' -- ' + detail) if detail else ''}")
    if not ok:
        errors.append(label)


# --- Spec worked example ---
# Basic = 15
# Supply build-up: Freight 0.80 + Handling 0.30 + Insurance 0.10 + Wastage 0.75 = 1.95 extras
# So Supply = 15 + 1.95 = 16.95
# Install = Labour 5.5 + Tools 0.5 + Testing 0.3 + Supervision 0.7 = 7.00 (Equipment 0)
# Prime = 16.95 + 7.00 = 23.95
# OH = 23.95 * 0.15 = 3.5925
# Profit = (23.95 + 3.5925) * 0.15 = 27.5425 * 0.15 = 4.131375
# Total = 23.95 + 3.5925 + 4.131375 = 31.673875 ~ 31.67

print("\n[engine] spec worked example (GHS 15 cable)")
basic   = 15.0
supply  = 16.95   # already computed (basic + extras)
install =  7.00
oh      = 15.0
prf     = 15.0
total   = web_app._boq_safe_rate(basic, supply, install, oh, prf, 0, 0)
check("Total = 31.67", abs(total - 31.67) < 0.01, f"got {total:.4f}")

bd = web_app._boq_rate_breakdown(basic, supply, install, oh, prf, 0, 0)
check("breakdown prime_cost = 23.95", abs(bd["prime_cost"] - 23.95) < 0.01,
      f"got {bd['prime_cost']:.4f}")
check("breakdown overhead = 3.59",   abs(bd["overhead_amount"] - 3.59) < 0.01,
      f"got {bd['overhead_amount']:.4f}")
check("breakdown profit = 4.13",     abs(bd["profit_amount"] - 4.13) < 0.01,
      f"got {bd['profit_amount']:.4f}")
check("breakdown final = 31.67",     abs(bd["final_built_up_rate"] - 31.67) < 0.01,
      f"got {bd['final_built_up_rate']:.4f}")

# Supply defaults to basic*1.10 when 0 (v4 standard-BOQ default).
total_no_supply = web_app._boq_safe_rate(15, 0, 7.00, 15, 15, 0, 0)
# v4: s -> 15*1.10 = 16.50; i stays 7.00 (>0); Prime=23.50; OH=23.50*0.15=3.525;
#     Profit=(23.50+3.525)*0.15=4.05375; Total=23.50+3.525+4.05375=31.07875
expected_v4 = 23.50 + 3.525 + 4.05375
check("supply=0 -> default basic*1.10, total ~= 31.08",
      abs(total_no_supply - expected_v4) < 0.01,
      f"got {total_no_supply:.4f}, expected {expected_v4:.4f}")

# Contingency + VAT (Ghana 12.5%)
total_with_vat = web_app._boq_safe_rate(15, 16.95, 7.00, 15, 15, 5, 12.5)
# subtotal = 31.674, cont = 31.674 * 0.05 = 1.584, vat = (31.674+1.584)*0.125 = 4.157, total = 31.674+1.584+4.157 = 37.415
sub = 31.673875
cont = sub * 0.05
vat  = (sub + cont) * 0.125
expected_vat = sub + cont + vat
check("with Cont 5 + VAT 12.5: 37.42",
      abs(total_with_vat - expected_vat) < 0.01,
      f"got {total_with_vat:.4f}, expected {expected_vat:.4f}")

# Caps clamp: OH=99 -> 20, Profit=99 -> 30.
# v4: install=0 -> defaults to 100*0.15=15. Prime=100+15=115;
#     OH=115*0.20=23; Profit=(115+23)*0.30=41.4; Total=115+23+41.4=179.4
total_clamped = web_app._boq_safe_rate(100, 100, 0, 99, 99, 0, 0)
check("OH/Profit clamped 20/30, install default applies: 179.4",
      abs(total_clamped - 179.4) < 0.01,
      f"got {total_clamped:.4f}")

print("\n[regression] still callable with 7-arg legacy signature")
r = web_app._boq_safe_rate(15, 16.95, 7, 15, 15, 0, 0)
check("7-arg legacy still works", abs(r - 31.67) < 0.01)


print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
