"""Generalized financial-figure extractor (upload/prod path).

Reads quarterly-report PAGES and builds the SAME `(order, by_q)` structure the covenant engine
consumes from a tool store — but sourced from the uploaded DOCUMENTS. Figures are matched by
semantic label (not one hardcoded string) with numeric normalization, so it works on real filing
phrasing. Addback lines are matched by the categories the derived CovenantSpec names, so a
third-party covenant's addbacks are picked up without code changes.

A figure that isn't present stays absent (the engine then reports a gap) — nothing is fabricated.
"""
from __future__ import annotations

import re

# core covenant inputs -> label alternatives seen in real filings. Order matters (first hit wins).
_CORE = {
    "consolidated_total_debt": [r"(?:consolidated\s+)?total\s+(?:net\s+)?debt"],
    "net_income": [r"net\s+income(?:\s*\(loss\))?", r"net\s+earnings(?:\s*\(loss\))?"],
    "financing_expense": [r"financing\s+expense", r"net\s+interest\s+expense", r"interest\s+expense"],
    "income_tax_expense": [r"income\s+tax\s+expense", r"provision\s+for\s+income\s+taxes",
                           r"income\s+taxes?"],
    "depreciation_amortization": [r"depreciation\s+(?:and|&)\s+amortization", r"depreciation"],
}
def _q_key(period_end: str) -> str:
    y, m, _ = period_end.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _value_after(text: str, label_rx: str, *, immediate=False):
    """First (magnitude, parenthesised) following any occurrence of label_rx. Parenthesis is read
    from the char immediately before the number (accounting shows negatives as '(22.6)').
    immediate=True requires the number right after the label (only whitespace/$) — used for the
    'TOTAL DEBT 3,480.0' summary line so a schedule header ('Total Debt Instrument ... 1,183.2')
    can't steal it. Last match wins (summary lines come after detail rows)."""
    gap = r"\s+" if immediate else r"[^\d\n]{0,25}?"
    best = None
    for m in re.finditer(label_rx + gap + r"\$?\s*([\d,]+\.\d+)", text, re.I):
        pre = text[:m.start(1)].rstrip("$ ")
        best = (_num(m.group(1)), pre.endswith("("))
    return best


def _income(hit):        # net income: parenthesised = loss = negative
    return None if hit is None else (-hit[0] if hit[1] else hit[0])


def _expense(hit):       # an EBITDA add-back: parenthesised expense = +, unparenthesised benefit = -
    return None if hit is None else (hit[0] if hit[1] else -hit[0])


def _report_text(pages, doc_id):
    return "\n".join(p["text"] for p in pages if p["doc_id"] == doc_id)


# ---- optional LLM fallback for FOREIGN layouts (different labels, whole-integer thousands,
#      debt split across short-term / current portion / long-term, D&A in the cash-flow) ----
_LLM_SCHEMA = {
    "period_end": "string|null",
    "reporting_units": "thousands|millions|billions|unknown",
    "net_income": "number|null",
    "financing_or_interest_expense": "number|null",
    "income_tax_expense": "number|null",
    "depreciation_and_amortization": "number|null",
    "total_debt": "number|null",
}
_UNIT = {"thousands": 1e-3, "millions": 1.0, "billions": 1e3}


def llm_extract_figures(text: str, llm) -> dict:
    """Map a foreign-layout financial statement to covenant fields, in $millions. The model reads
    the labels the filing actually uses and sums debt components when there's no single 'total
    debt' line. Offline this is a no-op (returns {}). Never invents — nulls stay null."""
    from .llm import PRIME
    res = llm.json_call(tier=PRIME, system=(
        "Extract leverage-covenant inputs from this financial statement. Use the labels the filing "
        "actually uses (e.g. 'Interest expense, net' -> financing expense; 'Provision for income "
        "taxes' -> income tax expense; depreciation & amortization is usually in the cash-flow "
        "statement). total_debt = short-term debt + current portion of long-term debt + long-term "
        "debt when there is no single total line. Report reporting_units. Return null for anything "
        "genuinely absent; never guess."),
        user=text[:6000], schema=_LLM_SCHEMA, offline_fn=lambda: {})
    d = res.data if isinstance(res.data, dict) else {}
    scale = _UNIT.get((d.get("reporting_units") or "").lower(), 1.0)

    def mm(v):
        try:
            return round(float(v) * scale, 1)
        except (TypeError, ValueError):
            return None
    return {"period_end": d.get("period_end"),
            "net_income": mm(d.get("net_income")),
            "financing_expense": mm(d.get("financing_or_interest_expense")),
            "income_tax_expense": mm(d.get("income_tax_expense")),
            "depreciation_amortization": mm(d.get("depreciation_and_amortization")),
            "consolidated_total_debt": mm(d.get("total_debt"))}


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _period_end(text: str) -> str | None:
    """The report's period-end date, ISO. Accepts '... ended 2014-06-30' and foreign-filing forms
    like 'Three Months Ended March 29, 2026'."""
    m = re.search(r"ended\s+(\d{4}-\d{2}-\d{2})", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"(?:months?|quarter|period)\s+ended\s+"
                  r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text, re.I)
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def extract_financials(pages: list[dict], spec=None, llm=None) -> tuple[list[str], dict]:
    """Return (order, by_q) parsed from every uploaded page that reads as a quarterly report.
    Figures are matched by regex first; when `llm` is supplied, any core field the regex missed
    (foreign layout / whole-integer thousands / debt split across lines) is filled by an LLM read
    of that report's text. llm=None keeps this fully deterministic."""
    by_q: dict[str, dict] = {}
    seen = []
    for p in pages:
        if p["doc_id"] in seen:
            continue
        seen.append(p["doc_id"])
        text = _report_text(pages, p["doc_id"])
        pe = _period_end(text)
        if not pe:
            continue                                     # not a dated quarterly report
        q = _q_key(pe)
        row = {"period_end": pe}
        debt = _value_after(text, _CORE["consolidated_total_debt"][0], immediate=True)
        if debt:
            row["consolidated_total_debt"] = debt[0]
        for field, labels in _CORE.items():
            if field == "consolidated_total_debt":
                continue
            hit = next((h for lb in labels if (h := _value_after(text, lb)) is not None), None)
            val = _income(hit) if field == "net_income" else _expense(hit)
            if val is not None:
                row[field] = val
        # addback categories the spec names -> match "<category word> ... charges <num>"
        for a in (spec.addbacks if spec else []):
            word = re.escape(a.category.split()[0])
            v = _expense(_value_after(text, word + r"[^\d\n]*?charges"))
            if v is not None:
                row[a.store_field] = v
        # LLM fallback: fill core covenant inputs the regex couldn't read on a foreign layout
        if llm is not None and any(row.get(f) is None for f in _CORE):
            filled = llm_extract_figures(text, llm)
            for f in _CORE:
                if row.get(f) is None and filled.get(f) is not None:
                    row[f] = filled[f]
        row.setdefault("consolidated_total_debt", 0.0)
        by_q[q] = row
    order = sorted(by_q, key=lambda q: by_q[q]["period_end"])
    return order, by_q
