"""Golden test harness — the deterministic covenant engine must reproduce every
value in data/dataset/golden_covenant_math.json. CI-runnable, fully offline.

    cd backend && python -m tests.test_golden      (or: pytest -q)

The build is not done until these pass.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import covenant_engine as ce  # noqa: E402

GOLDEN = json.load(open(os.path.join(ce.DATASET_DIR, "golden_covenant_math.json")))

FIELDS = [
    "threshold", "consolidated_total_debt", "sum_net_income", "sum_financing_expense",
    "sum_taxes", "sum_d_and_a", "device_charges_in_window", "device_cum_before_window",
    "device_addback_allowed", "quality_charges_in_window", "quality_cum_before_window",
    "quality_addback_allowed", "ebitda_naive_no_addbacks", "ebitda_correct",
    "ratio_naive", "ratio_correct", "compliant", "headroom_x",
]


def check_quarter(tq: str) -> list[str]:
    got = ce.compute(tq).to_dict()
    g = GOLDEN[tq]
    errs = []
    for f in FIELDS:
        if got.get(f) != g.get(f):
            errs.append(f"  {tq}.{f}: got {got.get(f)!r} != golden {g.get(f)!r}")
    return errs


def test_all_golden_quarters():
    """pytest entry point."""
    errs = []
    for tq in GOLDEN:
        errs += check_quarter(tq)
    assert not errs, "golden mismatches:\n" + "\n".join(errs)


def test_s1_disallowed_addback_line():
    """S1 (2014Q2): the cap must exclude 30.0 of Device Strategy charges, and the
    calculator step trace must show the min() and the disallowed amount."""
    r = ce.compute("2014Q2")
    assert r.device.disallowed == 30.0, r.device.disallowed
    assert r.device.allowed == 100.0
    assert any("30.0 DISALLOWED" in s for s in r.calc_steps), r.calc_steps
    assert r.ratio_correct == 3.606 and r.threshold == 3.75 and r.compliant


def test_s2_step_down_breach():
    """S2 (2015Q1): the step-down to 3.50x turns 3.615x into a BREACH."""
    r = ce.compute("2015Q1")
    assert r.threshold == 3.50 and r.ratio_correct == 3.615 and r.compliant is False


def test_s0_scanned_2014q4_number():
    """S0 triage reads 3.59x from the 2014Q4 certificate; engine reproduces 3.592x."""
    r = ce.compute("2014Q4")
    assert r.ratio_correct == 3.592 and round(r.ratio_correct, 2) == 3.59


if __name__ == "__main__":
    all_errs = []
    for q in GOLDEN:
        all_errs += check_quarter(q)
    if all_errs:
        print("GOLDEN MISMATCHES:")
        print("\n".join(all_errs))
        sys.exit(1)
    for fn in (test_s1_disallowed_addback_line, test_s2_step_down_breach,
               test_s0_scanned_2014q4_number):
        fn()
    print(f"GOLDEN OK — {len(GOLDEN)} quarters reproduced exactly; S0/S1/S2 assertions pass.")
