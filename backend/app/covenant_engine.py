"""Deterministic covenant engine — the real Hospira mechanics (Credit Agreement
§1.1/§6.6 dated 2011-10-28, as amended by Amendment No. 1 dated 2013-04-30 §1(d)/§1(j)).

Everything here is pure arithmetic in code — the agent never computes ratios with an
LLM. Outputs are asserted against data/dataset/golden_covenant_math.json by the
golden test harness.

Leverage Ratio = Consolidated Total Debt (last day of FQ) / Consolidated Adjusted
                 EBITDA (trailing four fiscal quarters)

Adjusted EBITDA = Σ_window (Net Income + Financing Expense + Income Taxes + D&A)
                  + Permitted Addbacks

Permitted Addbacks (Amendment No. 1 §1(d)) — LIFETIME caps, applied per category:
    addback = min(charges_in_window, max(0, cap − cumulative_charges_before_window))
  Device Strategy cash charges (after 2012-12-31): lifetime cap $290.0M
  Quality-matters cash charges (after 2013-01-01): lifetime cap $110.0M

Threshold schedule (amended §6.6A / §1(j)):
    ≤ 3.75x for fiscal quarters ending on or before 2014-12-31
    ≤ 3.50x for fiscal quarters ending after 2014-12-31
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import config

DEVICE_CAP = 290.0
QUALITY_CAP = 110.0
STEP_DOWN_DATE = "2014-12-31"   # FQ ending after this date → 3.50x
THRESHOLD_BEFORE = 3.75
THRESHOLD_AFTER = 3.50

DATASET_DIR = os.path.join(config.DATA_DIR, "dataset")
FIN_PATH = os.path.join(DATASET_DIR, "financials_quarterly.json")


def _load_financials() -> tuple[list[str], dict]:
    rows = json.load(open(FIN_PATH))
    order = [r["quarter"] for r in rows]
    by_q = {r["quarter"]: r for r in rows}
    return order, by_q


_ORDER, _BY_Q = _load_financials()


def threshold_for(period_end: str) -> float:
    """§6.6A step-down: 3.75x through FQ ending 2014-12-31, 3.50x after."""
    return THRESHOLD_BEFORE if period_end <= STEP_DOWN_DATE else THRESHOLD_AFTER


@dataclass
class AddbackResult:
    category: str
    cap: float
    charges_in_window: float
    cumulative_before_window: float
    remaining_cap: float
    allowed: float
    disallowed: float
    steps: list[str] = field(default_factory=list)


@dataclass
class CovenantResult:
    test_quarter: str
    period_end: str
    window: list[str]
    threshold: float
    consolidated_total_debt: float
    sum_net_income: float
    sum_financing_expense: float
    sum_taxes: float
    sum_d_and_a: float
    ebitda_naive: float
    device: AddbackResult
    quality: AddbackResult
    ebitda_correct: float
    ratio_naive: float
    ratio_correct: float
    compliant: bool
    headroom_x: float
    calc_steps: list[str]

    def to_dict(self) -> dict:
        return {
            "test_quarter": self.test_quarter, "period_end": self.period_end,
            "window": self.window, "threshold": self.threshold,
            "consolidated_total_debt": self.consolidated_total_debt,
            "sum_net_income": self.sum_net_income,
            "sum_financing_expense": self.sum_financing_expense,
            "sum_taxes": self.sum_taxes, "sum_d_and_a": self.sum_d_and_a,
            "device_charges_in_window": self.device.charges_in_window,
            "device_cum_before_window": self.device.cumulative_before_window,
            "device_addback_allowed": self.device.allowed,
            "device_disallowed": self.device.disallowed,
            "quality_charges_in_window": self.quality.charges_in_window,
            "quality_cum_before_window": self.quality.cumulative_before_window,
            "quality_addback_allowed": self.quality.allowed,
            "ebitda_naive_no_addbacks": self.ebitda_naive,
            "ebitda_correct": self.ebitda_correct,
            "ratio_naive": self.ratio_naive,
            "ratio_correct": self.ratio_correct,
            "compliant": self.compliant, "headroom_x": self.headroom_x,
        }


def _addback(category: str, cap: float, field_name: str, window: list[str],
             before: list[str]) -> AddbackResult:
    in_window = round(sum(_BY_Q[q][field_name] for q in window), 1)
    cum_before = round(sum(_BY_Q[q][field_name] for q in before), 1)
    remaining = round(max(0.0, cap - cum_before), 1)
    allowed = round(min(in_window, remaining), 1)
    disallowed = round(in_window - allowed, 1)
    steps = [
        f"{category}: charges in trailing window = {in_window:.1f}",
        f"{category}: cumulative charges before window = {cum_before:.1f}",
        f"{category}: remaining lifetime cap = max(0, {cap:.1f} − {cum_before:.1f}) = {remaining:.1f}",
        f"{category}: addback allowed = min({in_window:.1f}, {remaining:.1f}) = {allowed:.1f}"
        + (f"  ← {disallowed:.1f} DISALLOWED by the cap" if disallowed > 0 else ""),
    ]
    return AddbackResult(category, cap, in_window, cum_before, remaining, allowed, disallowed, steps)


def compute(test_quarter: str) -> CovenantResult:
    if test_quarter not in _BY_Q:
        raise ValueError(f"unknown quarter {test_quarter}")
    i = _ORDER.index(test_quarter)
    if i < 3:
        raise ValueError(f"need 4 trailing quarters; {test_quarter} has only {i + 1}")
    window = _ORDER[i - 3:i + 1]
    before = _ORDER[:i - 3]
    row = _BY_Q[test_quarter]
    period_end = row["period_end"]

    sni = round(sum(_BY_Q[q]["net_income"] for q in window), 1)
    sfin = round(sum(_BY_Q[q]["financing_expense"] for q in window), 1)
    stax = round(sum(_BY_Q[q]["income_tax_expense"] for q in window), 1)
    sda = round(sum(_BY_Q[q]["depreciation_amortization"] for q in window), 1)
    ebitda_naive = round(sni + sfin + stax + sda, 1)

    device = _addback("Device Strategy", DEVICE_CAP, "device_strategy_cash_charges", window, before)
    quality = _addback("Quality matters", QUALITY_CAP, "quality_matters_cash_charges", window, before)
    ebitda_correct = round(ebitda_naive + device.allowed + quality.allowed, 1)

    debt = row["consolidated_total_debt"]
    threshold = threshold_for(period_end)
    ratio_naive = round(debt / ebitda_naive, 3)
    ratio_correct = round(debt / ebitda_correct, 3)
    compliant = ratio_correct <= threshold
    headroom = round(threshold - ratio_correct, 3)

    calc_steps = [
        f"Trailing window: {window[0]}–{window[-1]}",
        f"ΣNet Income = {sni:.1f}; ΣFinancing Expense = {sfin:.1f}; "
        f"ΣIncome Taxes = {stax:.1f}; ΣD&A = {sda:.1f}",
        f"EBITDA before addbacks = {ebitda_naive:.1f}  →  naive ratio = "
        f"{debt:.1f} / {ebitda_naive:.1f} = {ratio_naive:.3f}x",
        *device.steps, *quality.steps,
        f"Adjusted EBITDA = {ebitda_naive:.1f} + {device.allowed:.1f} + {quality.allowed:.1f} "
        f"= {ebitda_correct:.1f}",
        f"Leverage Ratio = {debt:.1f} / {ebitda_correct:.1f} = {ratio_correct:.3f}x",
        f"Threshold (§6.6A, FQ ending {period_end}) = {threshold:.2f}x  →  "
        + ("COMPLIANT" if compliant else "BREACH")
        + f" (headroom {headroom:+.3f}x)",
    ]
    return CovenantResult(
        test_quarter, period_end, window, threshold, debt, sni, sfin, stax, sda,
        ebitda_naive, device, quality, ebitda_correct, ratio_naive, ratio_correct,
        compliant, headroom, calc_steps)


def runnable_quarters() -> list[str]:
    return [q for q in _ORDER if _ORDER.index(q) >= 3]
