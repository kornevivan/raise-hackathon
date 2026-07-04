"""CovenantSpec — the parameter set that fully defines a maintenance covenant, with the
citation (doc, page, span) each field was extracted from. Built at runtime by
spec_extractor from the indexed documents; consumed by generic_engine. No borrower
knowledge lives here — this is a pure data structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Cite:
    doc_id: str | None = None
    page: int | None = None
    text: str = ""          # the span the value was extracted from

    def ok(self) -> bool:
        return bool(self.text)


@dataclass
class Addback:
    category: str           # e.g. "Device Strategy"
    store_field: str        # financials_quarterly key, e.g. "device_strategy_cash_charges"
    cap: float              # lifetime cap ($M)
    incurred_after: str     # ISO date; charges after this count
    cite: Cite = field(default_factory=Cite)


@dataclass
class ThresholdStep:
    max_ratio: float
    applies_through: str | None = None   # ISO date; FQ ending on/before this
    applies_after: str | None = None     # ISO date; FQ ending after this
    cite: Cite = field(default_factory=Cite)


@dataclass
class CovenantSpec:
    name: str = "Maximum Leverage Ratio"
    numerator_field: str = "consolidated_total_debt"
    numerator_cite: Cite = field(default_factory=Cite)
    denominator_components: list[str] = field(default_factory=list)  # NI/fin/tax/DA store keys
    denominator_cite: Cite = field(default_factory=Cite)
    addbacks: list[Addback] = field(default_factory=list)
    threshold_schedule: list[ThresholdStep] = field(default_factory=list)
    trailing_quarters: int = 4
    gaps: list[str] = field(default_factory=list)

    def threshold_for(self, period_end: str) -> tuple[float | None, Cite]:
        """Pick the max ratio applicable to a fiscal quarter ending on `period_end`."""
        after = [s for s in self.threshold_schedule if s.applies_after and period_end > s.applies_after]
        if after:
            s = min(after, key=lambda s: s.applies_after)
            return s.max_ratio, s.cite
        through = [s for s in self.threshold_schedule if s.applies_through and period_end <= s.applies_through]
        if through:
            s = max(through, key=lambda s: s.applies_through)
            return s.max_ratio, s.cite
        if self.threshold_schedule:
            s = self.threshold_schedule[0]
            return s.max_ratio, s.cite
        return None, Cite()

    def all_field_cites(self) -> list[tuple[str, Cite]]:
        out = [("numerator", self.numerator_cite), ("denominator", self.denominator_cite)]
        out += [(f"addback:{a.category}", a.cite) for a in self.addbacks]
        out += [(f"threshold:{s.max_ratio}", s.cite) for s in self.threshold_schedule]
        return out

    def is_complete(self) -> bool:
        return bool(self.threshold_schedule) and self.numerator_field and self.denominator_components
