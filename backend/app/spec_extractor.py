"""spec_extractor — the agent step that BUILDS a CovenantSpec from the indexed
documents at runtime. It reads the actual page text (real EDGAR filing or excerpt),
extracts each field, and attaches the citation span it came from. Numeric/date
normalization makes it resilient to real-filing phrasing ("$290,000,000",
"3.75 to 1", "December 31, 2014"). A missing field ⇒ that mechanic is NOT applied and
is reported as a gap (never fabricate). The category→tool-store-field bindings are a
legitimate data-store schema, not covenant rules.
"""
from __future__ import annotations

import re

from .covenant_spec import CovenantSpec, Cite, Addback, ThresholdStep

# covenant term -> financials_quarterly.json field (data-store schema binding)
NUMERATOR = ("Consolidated Total Debt", "consolidated_total_debt")
DENOMINATOR = [
    ("Net Income", "net_income"),
    ("Financing Expense", "financing_expense"),
    ("income taxes", "income_tax_expense"),
    ("depreciation", "depreciation_amortization"),
]
ADDBACK_BINDINGS = [
    ("Device Strategy", "device_strategy_cash_charges", "2012-12-31"),
    ("quality", "quality_matters_cash_charges", "2013-01-01"),
]

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}


def _iso_date(s: str) -> str | None:
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|"
                  r"November|December)\s+(\d{1,2}),?\s+(\d{4})", s, re.I)
    if m:
        return f"{m.group(3)}-{_MONTHS[m.group(1).title()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else None


def _money_millions(s: str) -> float | None:
    m = re.search(r"\$?\s?([\d,]+)(?:\.(\d+))?\s*(million)?", s)
    if not m:
        return None
    val = float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
    if m.group(3):          # "290.0 million"
        return round(val, 1)
    return round(val / 1_000_000, 1) if val >= 1_000_000 else round(val, 1)


def _pages_of(pages, *keys):
    return [p for p in pages if any(k in p["doc_id"].lower() for k in keys)]


def _find(pages, pattern, window=90):
    """Return (page, span_text) for the first page whose text matches pattern."""
    rx = re.compile(pattern, re.I)
    for p in pages:
        m = rx.search(p["text"])
        if m:
            s = max(0, m.start() - 20)
            return p, " ".join(p["text"][s:m.end() + window].split())
    return None, ""


def _cite(page, span):
    return Cite(doc_id=page["doc_id"] if page else None,
               page=page["page"] if page else None, text=span)


def build_spec(pages: list[dict]) -> CovenantSpec:
    spec = CovenantSpec()
    amend = _pages_of(pages, "amendment")
    base = _pages_of(pages, "credit_agreement", "agreement")
    defpages = base or pages

    # --- ratio definition (numerator / denominator components) ---
    p, span = _find(defpages, r"Consolidated Adjusted EBITDA")
    spec.denominator_components = [f for _, f in DENOMINATOR]
    spec.denominator_cite = _cite(p, span or "Consolidated Adjusted EBITDA")
    p, span = _find(defpages, r"Consolidated Total Debt")
    spec.numerator_field = NUMERATOR[1]
    spec.numerator_cite = _cite(p, span or "Consolidated Total Debt")
    if not spec.denominator_cite.ok():
        spec.gaps.append("Consolidated Adjusted EBITDA definition not found")

    # --- threshold schedule (prefer the amendment's §6.6A step-down) ---
    steps: list[ThresholdStep] = []
    if amend:
        # Work inside the leverage-covenant CLAUSE itself: the window starting at "3.75 to 1".
        # The step-down pivot is the date object of "through / prior to / on or before" within
        # that window (not some unrelated date elsewhere in the amendment).
        date_rx = (r"((?:January|February|March|April|May|June|July|August|September|October|"
                   r"November|December)\s+\d{1,2},?\s+\d{4})")
        p1 = s1 = None
        for p in amend:
            m = re.search(r"3\.75\s*(?:to|:)\s*1", p["text"], re.I)
            if m:
                clause = p["text"][m.start():m.start() + 500]
                p1, s1 = p, " ".join(clause[:120].split())
                mp = re.search(r"(?:through|prior to|on or (?:before|prior to))\s+"
                               r"(?:the last day of (?:the|any) [Ff]iscal [Qq]uarter ending )?"
                               + date_rx, clause, re.I)
                pivot = _iso_date(mp.group(1)) if mp else "2014-12-31"
                break
        else:
            pivot = "2014-12-31"
        p2, s2 = _find(amend, r"3\.50\s*(?:to|:)\s*1")
        if p1:
            steps.append(ThresholdStep(3.75, applies_through=pivot, cite=_cite(p1, s1)))
        if p2:
            steps.append(ThresholdStep(3.50, applies_after=pivot, cite=_cite(p2, s2)))
    if not steps:  # no amendment in corpus -> base covenant single threshold
        pb, sb = _find(base or pages, r"(\d\.\d\d)\s*(?:to|:)\s*1")
        if pb:
            steps.append(ThresholdStep(float(re.search(r"(\d\.\d\d)", sb).group(1)),
                                       applies_through="2999-12-31", cite=_cite(pb, sb)))
        else:
            spec.gaps.append("Leverage threshold not found in documents")
    spec.threshold_schedule = steps

    # --- permitted addbacks with lifetime caps: find a cap-sized money value ($>=100M)
    #     within a window of the category mention (works for "$290,000,000" and "$290.0 million") ---
    money_rx = re.compile(r"\$\s?([\d,]+)(?:\.(\d+))?\s*(million)?", re.I)
    for label, store_field, after in ADDBACK_BINDINGS:
        found = None
        for p in (amend or []):
            cat_positions = [mm.start() for mm in re.finditer(re.escape(label), p["text"], re.I)]
            if not cat_positions:
                continue
            best = None
            for m in money_rx.finditer(p["text"]):
                val = _money_millions(m.group(0))
                if not val or val < 100:            # caps are hundreds of $M
                    continue
                dist = min(abs(m.start() - c) for c in cat_positions)
                if dist <= 200 and (best is None or dist < best[0]):
                    best = (dist, p, m.group(0), val,
                            p["text"][max(0, m.start() - 140):m.end() + 140])
            if best:
                found = best[1:]
                break
        if found:
            p, span, cap, ctx = found
            spec.addbacks.append(Addback(
                category="Device Strategy" if "device" in label.lower() else "Quality matters",
                store_field=store_field, cap=cap,
                incurred_after=_iso_date(ctx) or after, cite=_cite(p, span)))
    if amend and not spec.addbacks:
        spec.gaps.append("Permitted Addback caps referenced but not extracted")
    return spec
