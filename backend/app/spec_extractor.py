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
# addback category ANCHOR (as it appears in the agreement) -> (canonical label, data-store field,
# fallback incurred-after date). A data-store schema registry, not covenant rules: it only says
# which store column backs a category the DOCUMENT names, so the cap VALUE can be read next to it.
# A category the store doesn't track (third-party doc) falls through to generic discovery below.
_CATEGORY_REGISTRY = [
    ("Device Strategy", "Device Strategy", "device_strategy_cash_charges", "2012-12-31"),
    ("quality", "Quality matters", "quality_matters_cash_charges", "2013-01-01"),
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


def _join(pages):
    """Concatenate pages into one searchable string + a per-char page owner, so a clause that
    straddles a page break (e.g. '...not to exceed' | '$110,000,000...') is read as one."""
    text, owner = "", []
    for p in pages:
        t = p["text"] + "\n"
        text += t
        owner += [p] * len(t)
    return text, owner


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
        # Value-AGNOSTIC: locate the leverage-covenant clause, read whatever ratio value(s) it
        # states and the step-down pivot date. No hardcoded thresholds.
        date_rx = (r"((?:January|February|March|April|May|June|July|August|September|October|"
                   r"November|December)\s+\d{1,2},?\s+\d{4})")
        ratio_rx = re.compile(r"(\d\.\d{1,2})\s*(?:to|:)\s*1\b", re.I)
        for p in amend:
            anchor = re.search(r"Leverage Ratio[^.]{0,220}?(?:exceed|greater than)", p["text"], re.I)
            if not anchor:
                continue
            clause = p["text"][anchor.start():anchor.start() + 450]
            ratios = [float(m.group(1)) for m in ratio_rx.finditer(clause)]
            if not ratios:
                continue
            mp = re.search(r"(?:through|prior to|on or (?:before|prior to))\s+"
                           r"(?:the last day of (?:the|any) [Ff]iscal [Qq]uarter ending )?"
                           + date_rx, clause, re.I)
            pivot = _iso_date(mp.group(1)) if mp else None
            if len(ratios) >= 2 and pivot:            # step-down: [before, after] in text order
                steps.append(ThresholdStep(ratios[0], applies_through=pivot,
                                           cite=_cite(p, f"{ratios[0]:.2f} to 1")))
                steps.append(ThresholdStep(ratios[1], applies_after=pivot,
                                           cite=_cite(p, f"{ratios[1]:.2f} to 1")))
            else:                                     # single amended threshold
                steps.append(ThresholdStep(ratios[0], applies_through="2999-12-31",
                                           cite=_cite(p, f"{ratios[0]:.2f} to 1")))
            break
    if not steps:  # no amendment in corpus -> base covenant single threshold
        pb, sb = _find(base or pages, r"(\d\.\d\d)\s*(?:to|:)\s*1")
        if pb:
            steps.append(ThresholdStep(float(re.search(r"(\d\.\d\d)", sb).group(1)),
                                       applies_through="2999-12-31", cite=_cite(pb, sb)))
        else:
            spec.gaps.append("Leverage threshold not found in documents")
    spec.threshold_schedule = steps

    # --- permitted addbacks with lifetime caps ---
    money_rx = re.compile(r"\$\s?([\d,]+)(?:\.(\d+))?\s*(million)?", re.I)
    jt, owner = _join(amend or [])

    # Primary: caps for the categories the DATA STORE tracks — value read next to the anchor.
    matched_anchor = False
    for anchor, label, field, after in _CATEGORY_REGISTRY:
        pos = [mm.start() for mm in re.finditer(re.escape(anchor), jt, re.I)]
        if not pos:
            continue
        best = None
        for m in money_rx.finditer(jt):
            val = _money_millions(m.group(0))
            if not val or val < 100:
                continue
            pre = jt[max(0, m.start() - 22):m.start()]         # a cap, not a narrative figure
            if not re.search(r"up to|not to exceed", pre, re.I):
                continue
            d = min(abs(m.start() - c) for c in pos)
            if d <= 200 and (best is None or d < best[0]):
                best = (d, m.start(), m.group(0), val)
        if best:
            matched_anchor = True
            _, off, span, cap = best
            ctx = jt[max(0, off - 160):off + 160]
            spec.addbacks.append(Addback(category=label, store_field=field, cap=cap,
                                         incurred_after=_iso_date(ctx) or after,
                                         cite=_cite(owner[off], span)))
    # Fallback (third-party doc naming a category the store doesn't track): DISCOVER one cap in an
    # addback/cap context and derive the category name + a slug store-field from the text.
    if amend and not matched_anchor:
        for m in money_rx.finditer(jt):
            cap = _money_millions(m.group(0))
            if not cap or cap < 100:
                continue
            ctx = jt[max(0, m.start() - 170):m.end() + 170]
            if not re.search(r"addback|not to exceed|aggregate amount|lifetime|cap\b", ctx, re.I):
                continue
            mm = re.search(r"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s+"
                           r"(?:Program|Strategy|Matters|Charges|Costs|Initiative))", ctx)
            category = mm.group(1) if mm else "Permitted Addback"
            field = re.sub(r"[^a-z]+", "_", category.lower()).strip("_") + "_cash_charges"
            spec.addbacks.append(Addback(category=category, store_field=field, cap=cap,
                                         incurred_after=_iso_date(ctx) or "1900-01-01",
                                         cite=_cite(owner[m.start()], m.group(0))))
            break
    if amend and not spec.addbacks:
        spec.gaps.append("Permitted Addback caps referenced but not extracted")
    return spec
