"""Deterministic tools. The agent NEVER does arithmetic itself — these do, and
they return their working so every number in the memo is checkable."""
from __future__ import annotations

import json
import sqlite3

from . import config

with open(config.FINANCIALS_PATH) as _fh:
    _FIN = json.load(_fh)


def financials_query(borrower_id: str, period: str, line_item: str) -> dict:
    """Return one line item from the financial statements."""
    rec = _FIN.get(borrower_id, {}).get(period, {})
    if line_item not in rec:
        return {"ok": False, "error": f"line_item '{line_item}' not found",
                "available": sorted(rec.keys())}
    return {"ok": True, "borrower_id": borrower_id, "period": period,
            "line_item": line_item, "value": rec[line_item], "unit": "USD millions"}


def financials_all(borrower_id: str, period: str) -> dict:
    return _FIN.get(borrower_id, {}).get(period, {})


def transactions_query(borrower_id: str, period: str | None = None,
                       acquisition_related: int | None = None,
                       one_time: int | None = None,
                       category_like: str | None = None,
                       limit: int = 50) -> dict:
    """Query the transaction ledger (SQLite). Returns matching rows + an aggregate."""
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    q = "SELECT * FROM transactions WHERE borrower_id = ?"
    args: list = [borrower_id]
    if period:
        q += " AND period = ?"; args.append(period)
    if acquisition_related is not None:
        q += " AND acquisition_related = ?"; args.append(acquisition_related)
    if one_time is not None:
        q += " AND one_time = ?"; args.append(one_time)
    if category_like:
        q += " AND category LIKE ?"; args.append(f"%{category_like}%")
    q += " ORDER BY ABS(amount_usd_000) DESC LIMIT ?"; args.append(limit)
    rows = [dict(r) for r in con.execute(q, args).fetchall()]
    con.close()
    total = round(sum(r["amount_usd_000"] for r in rows) / 1000.0, 2)  # -> USD millions
    return {"ok": True, "borrower_id": borrower_id, "period": period,
            "row_count": len(rows), "total_usd_millions": total, "rows": rows}


def ratio_calculator(numerator: float, denominator: float,
                     numerator_label: str = "numerator",
                     denominator_label: str = "denominator",
                     addbacks: list[dict] | None = None) -> dict:
    """Compute a ratio with an explicit, auditable trail.

    addbacks: optional list of {"label","amount"} added to the denominator
    (e.g. EBITDA addbacks). Returns the step-by-step working."""
    addbacks = addbacks or []
    add_total = round(sum(a["amount"] for a in addbacks), 4)
    denom_adj = round(denominator + add_total, 4)
    steps = [
        f"{numerator_label} = {numerator:,.1f}",
        f"{denominator_label} (base) = {denominator:,.1f}",
    ]
    for a in addbacks:
        steps.append(f"  + addback: {a['label']} = {a['amount']:,.1f}")
    if addbacks:
        steps.append(f"{denominator_label} (adjusted) = {denom_adj:,.1f}")
    ratio = round(numerator / denom_adj, 3) if denom_adj else None
    steps.append(f"ratio = {numerator:,.1f} / {denom_adj:,.1f} = {ratio:.3f}x")
    return {"ok": True, "numerator": numerator, "denominator_base": denominator,
            "addbacks": addbacks, "addback_total": add_total,
            "denominator_adjusted": denom_adj, "ratio": ratio, "steps": steps}


TOOL_SPECS = {
    "financials_query": "Get one line item from the financial statements "
                        "(args: borrower_id, period, line_item).",
    "transactions_query": "Query the transaction ledger (args: borrower_id, period, "
                          "acquisition_related, one_time, category_like).",
    "ratio_calculator": "Compute a ratio with an auditable trail (args: numerator, "
                        "denominator, addbacks[]).",
}
