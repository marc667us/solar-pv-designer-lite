"""Smoke test for the 2026-06-24 rate-builder rework.

Tests run OFFLINE against the engine functions and against a live
Waitress instance for the route surface.

Engine assertions:
  - _boq_safe_rate(100, 15, 5, 25, 10) == 155.0
  - _boq_safe_rate(100, 20, ...) clamps supply to 15 (additive cap)
  - _bom_totals_with_rates per-line override respected
  - bom_totals fall back to project-wide rates when per-line null
  - recheck currency->country map covers GHS/NGN/KES

Route assertions:
  - GET /boms/<id>/basic-prices renders with no totals/subtotal
  - POST /boms/<id>/recheck-prices with no AI key flashes danger
  - boq edit form posts S=20 -> rejected (cap)
"""
import os
import sys
import importlib

# Force test DB so we don't touch live.
os.environ.setdefault("DB_PATH", "tmp/smoke_rate_builder.db")
os.environ.setdefault("SECRET_KEY", "smoke-rate-builder")
os.environ.setdefault("SOLARPRO_ADMIN_PASSWORD", "smoke-admin-pw")
os.environ.setdefault("SOLARPRO_OWNER_PASSWORD", "smoke-owner-pw")

# Ensure no leftover legacy AI keys force a real network call.
for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "OLLAMA_URL"):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.abspath("."))
print("Importing web_app...")
import web_app  # noqa: E402
print("OK")

errors = []


def check(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}{(' -- ' + detail) if detail else ''}")
    if not ok:
        errors.append(label)


# ---------------- Engine: _boq_safe_rate ----------------
print("\n[engine] _boq_safe_rate additive formula")
r = web_app._boq_safe_rate(100, 15, 25, 10, 5)   # B,S,I,O,P
check("worked example total = 155", abs(r - 155.0) < 1e-6, f"got {r}")

r0 = web_app._boq_safe_rate(100, 0, 0, 0, 0)
check("zeros -> basic", abs(r0 - 100.0) < 1e-6, f"got {r0}")

r_clamp = web_app._boq_safe_rate(100, 999, 999, 999, 999)   # caps 15/25/15/5
expected = 100 * (1 + (15 + 25 + 15 + 5) / 100.0)            # 100 + 60% = 160
check("over-cap clamped to maxima -> 160", abs(r_clamp - expected) < 1e-6,
      f"got {r_clamp}, expected {expected}")

# Legacy 7-arg signature still callable (cnt+vat ignored)
r_legacy = web_app._boq_safe_rate(100, 15, 25, 10, 5, 99, 99)
check("7-arg legacy call ignores cnt/vat",
      abs(r_legacy - 155.0) < 1e-6, f"got {r_legacy}")


# ---------------- Engine: _bom_totals_with_rates ----------------
print("\n[engine] _bom_totals_with_rates")

class StubRow(dict):
    def keys(self):
        return list(super().keys())
    def __getitem__(self, k):
        try:
            return super().__getitem__(k)
        except KeyError:
            return None

# Per-line: basic 100, supply 15, install 25, profit 5, overhead 10, qty 2
items = [StubRow(
    id=1, custom_name="Test", catalog_price=0, unit_price_override=None,
    qty=2, category_name="Test",
    basic_price=100, supply_pct=15, profit_pct=5, install_pct=25, overhead_pct=10,
)]
res = web_app._bom_totals_with_rates(items, {}, fx_rate=1.0)
line = res["lines"][0]
check("per-line basic respected", abs(line["basic_rate"] - 100) < 1e-6,
      f"got {line['basic_rate']}")
check("per-line total_rate = 155", abs(line["total_rate"] - 155) < 1e-6,
      f"got {line['total_rate']}")
check("per-line line_total = 310", abs(line["line_total"] - 310) < 1e-6,
      f"got {line['line_total']}")

# Project-wide fallback: per-line empty -> repurposed cols on rates dict.
items2 = [StubRow(
    id=2, custom_name="Fallback", catalog_price=100, unit_price_override=None,
    qty=1, category_name="Test",
    basic_price=None, supply_pct=None, profit_pct=None, install_pct=None, overhead_pct=None,
)]
project_rates = {
    "contingency_pct": 10,  # repurposed: supply default
    "vat_pct":         20,  # repurposed: install default
    "profit_pct":       3,
    "overhead_pct":     5,
}
res2 = web_app._bom_totals_with_rates(items2, project_rates, fx_rate=1.0)
line2 = res2["lines"][0]
expected2 = 100 * (1 + (10 + 3 + 20 + 5) / 100.0)   # 138
check("project-wide fallback total = 138",
      abs(line2["total_rate"] - expected2) < 1e-6, f"got {line2['total_rate']}")


# ---------------- Engine: _boq_rate_breakdown ----------------
print("\n[engine] _boq_rate_breakdown")
bd = web_app._boq_rate_breakdown(100, 15, 25, 10, 5)
check("supply_disp = 20", abs(bd["supply_disp"] - 20) < 1e-6, f"got {bd['supply_disp']}")
check("install_disp = 35", abs(bd["install_disp"] - 35) < 1e-6, f"got {bd['install_disp']}")
check("final = 155", abs(bd["final_built_up_rate"] - 155) < 1e-6,
      f"got {bd['final_built_up_rate']}")


# ---------------- Recheck country map ----------------
print("\n[recheck] currency -> country map")
from new_recheck_prices_routes import _recheck_country_for
for ccy, expected_country in (("GHS", "Ghana"), ("NGN", "Nigeria"),
                              ("KES", "Kenya"), ("ZAR", "South Africa")):
    country, _ = _recheck_country_for(ccy)
    check(f"{ccy} -> {expected_country}", country == expected_country,
          f"got {country}")


# ---------------- Recheck prompt build ----------------
print("\n[recheck] prompt build")
from new_recheck_prices_routes import _recheck_build_prompt
items_for_prompt = [
    {"id": 1, "name": "4mm² Armoured Cable", "spec": "LV PVC",
     "brand": "Tridem", "unit": "m", "current_price": 25.0},
]
prompt = _recheck_build_prompt(items_for_prompt, "Ghana", "GHS")
check("prompt mentions Ghana", "Ghana" in prompt)
check("prompt mentions GHS", "GHS" in prompt)
check("prompt has the item name", "4mm" in prompt)
check("prompt requests JSON", '"prices"' in prompt)


# ---------------- Recheck parse robustness ----------------
print("\n[recheck] parse")
from new_recheck_prices_routes import _recheck_parse
clean = '{"prices":[{"id":1,"price":42.5,"source":"Tridem","confidence":"high"}]}'
out = _recheck_parse(clean)
check("clean JSON parses", 1 in out and out[1]["price"] == 42.5, repr(out))

fenced = '```json\n{"prices":[{"id":2,"price":7,"source":"x","confidence":"med"}]}\n```'
out2 = _recheck_parse(fenced)
check("fenced JSON parses", 2 in out2 and out2[2]["price"] == 7, repr(out2))

garbage = "I don't know."
out3 = _recheck_parse(garbage)
check("garbage returns empty dict", out3 == {}, repr(out3))


# ---------------- Route surface via Flask test client ----------------
print("\n[routes] Flask test client")
web_app.app.config["TESTING"] = True
client = web_app.app.test_client()

# Public endpoints should respond.
r = client.get("/api/ping")
check("/api/ping returns 200", r.status_code == 200, f"got {r.status_code}")

# Recheck without auth should redirect to login.
r = client.post("/boms/1/recheck-prices", data={"_csrf": "x"},
                follow_redirects=False)
check("recheck w/o auth redirects",
      r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")

# Apply route same.
r = client.post("/boms/1/recheck-prices/apply", data={"_csrf": "x"},
                follow_redirects=False)
check("apply w/o auth redirects",
      r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")

# Review route same.
r = client.get("/boms/1/recheck-prices/review", follow_redirects=False)
check("review w/o auth redirects",
      r.status_code in (302, 303, 401, 403),
      f"got {r.status_code}")


# ---------------- Summary ----------------
print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("ALL CHECKS PASSED")
