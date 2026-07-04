"""Generic covenant engine — parameterized math with NO borrower/covenant knowledge.
Given a CovenantSpec (derived from documents) + quarterly figures from a tool store,
it computes the ratio, applies capped addbacks and the date-scheduled threshold, and
returns a verdict with an auditable step trace. Pure functions; unit-tested.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

from .covenant_spec import CovenantSpec, Addback


@dataclass
class AddbackCalc:
    category: str
    charges_in_window: float
    cumulative_before_window: float
    remaining_cap: float
    allowed: float
    disallowed: float


@dataclass
class EngineResult:
    test_quarter: str
    period_end: str
    window: list[str]
    threshold: float | None
    numerator: float
    denom_naive: float
    denom_adjusted: float
    addbacks: list[AddbackCalc]
    ratio_naive: float | None
    ratio_correct: float | None
    compliant: bool | None
    headroom_x: float | None
    calc_steps: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


def _addback(a: Addback, window: list[str], before: list[str], by_q: dict) -> tuple[AddbackCalc, list[str]]:
    inw = round(sum(by_q[q].get(a.store_field, 0.0) for q in window), 1)
    cum = round(sum(by_q[q].get(a.store_field, 0.0) for q in before), 1)
    remaining = round(max(0.0, a.cap - cum), 1)
    allowed = round(min(inw, remaining), 1)
    disallowed = round(inw - allowed, 1)
    steps = [
        f"{a.category}: charges in trailing window = {inw:.1f}",
        f"{a.category}: cumulative before window = {cum:.1f}",
        f"{a.category}: remaining lifetime cap = max(0, {a.cap:.1f} - {cum:.1f}) = {remaining:.1f}",
        f"{a.category}: addback = min({inw:.1f}, {remaining:.1f}) = {allowed:.1f}"
        + (f"  <- {disallowed:.1f} DISALLOWED by the cap" if disallowed > 0 else ""),
    ]
    return AddbackCalc(a.category, inw, cum, remaining, allowed, disallowed), steps


def compute(spec: CovenantSpec, order: list[str], by_q: dict, test_quarter: str) -> EngineResult:
    i = order.index(test_quarter)
    n = spec.trailing_quarters
    if i < n - 1:
        return EngineResult(test_quarter, by_q[test_quarter].get("period_end", ""), [], None,
                            0, 0, 0, [], None, None, None, None,
                            gaps=[f"need {n} trailing quarters"])
    window = order[i - n + 1:i + 1]
    before = order[:i - n + 1]
    period_end = by_q[test_quarter]["period_end"]

    numerator = by_q[test_quarter].get(spec.numerator_field, 0.0)
    denom_naive = round(sum(by_q[q].get(c, 0.0) for q in window for c in spec.denominator_components), 1)

    addcalcs, add_steps, add_total = [], [], 0.0
    for a in spec.addbacks:
        ac, st = _addback(a, window, before, by_q)
        addcalcs.append(ac); add_steps += st; add_total += ac.allowed
    denom_adj = round(denom_naive + add_total, 1)

    threshold, _tc = spec.threshold_for(period_end)
    ratio_naive = round(numerator / denom_naive, 3) if denom_naive else None
    ratio_correct = round(numerator / denom_adj, 3) if denom_adj else None
    compliant = (ratio_correct <= threshold) if (ratio_correct is not None and threshold is not None) else None
    headroom = round(threshold - ratio_correct, 3) if (ratio_correct is not None and threshold is not None) else None

    steps = [
        f"Trailing window: {window[0]}-{window[-1]}",
        f"Denominator (before addbacks) = sum of {spec.denominator_components} over the window = "
        f"{denom_naive:.1f}",
        f"Naive ratio = {numerator:.1f} / {denom_naive:.1f} = "
        + (f"{ratio_naive:.3f}x" if ratio_naive is not None else "n/a"),
        *add_steps,
        f"Adjusted denominator = {denom_naive:.1f} + {add_total:.1f} = {denom_adj:.1f}",
        f"Ratio = {numerator:.1f} / {denom_adj:.1f} = "
        + (f"{ratio_correct:.3f}x" if ratio_correct is not None else "n/a"),
        (f"Threshold (FQ ending {period_end}) = {threshold:.2f}x -> "
         + ("COMPLIANT" if compliant else "BREACH") + f" (headroom {headroom:+.3f}x)")
        if threshold is not None else "Threshold: NOT FOUND in documents -> cannot conclude",
    ]
    return EngineResult(test_quarter, period_end, window, threshold, numerator, denom_naive,
                        denom_adj, addcalcs, ratio_naive, ratio_correct, compliant, headroom,
                        steps, list(spec.gaps))


def legacy_result(spec: CovenantSpec, order: list[str], by_q: dict, tq: str):
    """Adapter exposing the fields the Hospira orchestrator reads, computed via the
    generic engine + derived spec (so the demo runs on extracted rules, not hardcode)."""
    r = compute(spec, order, by_q, tq)
    win = r.window

    def s(f):
        return round(sum(by_q[q].get(f, 0.0) for q in win), 1)
    dev = next((a for a in r.addbacks if "Device" in a.category), None) \
        or AddbackCalc("Device Strategy", 0, 0, 0, 0, 0)
    qual = next((a for a in r.addbacks if "Quality" in a.category), None) \
        or AddbackCalc("Quality matters", 0, 0, 0, 0, 0)
    dev_cap = next((a.cap for a in spec.addbacks if "Device" in a.category), 0.0)
    return SimpleNamespace(
        test_quarter=tq, period_end=r.period_end, window=win, threshold=r.threshold,
        consolidated_total_debt=r.numerator,
        sum_net_income=s("net_income"), sum_financing_expense=s("financing_expense"),
        sum_taxes=s("income_tax_expense"), sum_d_and_a=s("depreciation_amortization"),
        ebitda_naive=r.denom_naive, ebitda_correct=r.denom_adjusted,
        ratio_naive=r.ratio_naive, ratio_correct=r.ratio_correct, compliant=r.compliant,
        headroom_x=r.headroom_x, calc_steps=r.calc_steps, device=dev, quality=qual,
        device_cap=dev_cap, spec=spec, gaps=r.gaps)
