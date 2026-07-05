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


def extract_financials(pages: list[dict], spec=None) -> tuple[list[str], dict]:
    """Return (order, by_q) parsed from every uploaded page that reads as a quarterly report."""
    by_q: dict[str, dict] = {}
    seen = []
    for p in pages:
        if p["doc_id"] in seen:
            continue
        seen.append(p["doc_id"])
        text = _report_text(pages, p["doc_id"])
        mp = re.search(r"(?:quarter|period|fiscal quarter)\s+ended\s+(\d{4}-\d{2}-\d{2})", text, re.I)
        if not mp:
            continue                                     # not a dated quarterly report
        q = _q_key(mp.group(1))
        row = {"period_end": mp.group(1)}
        debt = _value_after(text, _CORE["consolidated_total_debt"][0], immediate=True)
        row["consolidated_total_debt"] = debt[0] if debt else 0.0
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
        by_q[q] = row
    order = sorted(by_q, key=lambda q: by_q[q]["period_end"])
    return order, by_q
