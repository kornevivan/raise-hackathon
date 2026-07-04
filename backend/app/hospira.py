"""Hospira demo corpus + data access for sample-mode runs.

Ingests the real-mechanics document set (Credit Agreement & Amendment excerpts,
financial reports, compliance certificates incl. the scanned 2014Q4 one) through
the same PyMuPDF→pages→VultronRetriever pipeline used for uploads, and exposes the
quarterly financials + transaction ledger for the deterministic tools.
"""
from __future__ import annotations

import csv
import json
import os
from functools import lru_cache

from . import config, ingest

DATASET = os.path.join(config.DATA_DIR, "dataset")
DOCS = os.path.join(DATASET, "documents")

# documents ingested for a Hospira deep run (order matters only for nicer ids)
DEEP_DOCS = [
    "credit_agreement_excerpt.pdf",
    "amendment_no1_excerpt.pdf",
    "financial_report_2013Q3.pdf", "financial_report_2013Q4.pdf",
    "financial_report_2014Q1.pdf", "financial_report_2014Q2.pdf",
    "financial_report_2014Q3.pdf", "financial_report_2014Q4.pdf",
    "financial_report_2015Q1.pdf",
    "compliance_certificate_2014Q1.pdf", "compliance_certificate_2014Q3.pdf",
    "compliance_certificate_2014Q4.pdf", "compliance_certificate_2014Q4_SCANNED.pdf",
]

_corpus_id: str | None = None


def corpus():
    """Ingest the Hospira document set once; return the UPLOADS entry (retriever,
    pages, by_block) — identical structure to an upload."""
    global _corpus_id
    if _corpus_id and _corpus_id in ingest.UPLOADS:
        return ingest.UPLOADS[_corpus_id]
    files = []
    for name in DEEP_DOCS:
        p = os.path.join(DOCS, name)
        if os.path.exists(p):
            files.append((name, open(p, "rb").read()))
    res = ingest.ingest(files)
    _corpus_id = res["upload_id"]
    return ingest.fill_scanned_text(ingest.UPLOADS[_corpus_id], DOCS)


@lru_cache(maxsize=1)
def financials() -> tuple[list[str], dict]:
    rows = json.load(open(os.path.join(DATASET, "financials_quarterly.json")))
    return [r["quarter"] for r in rows], {r["quarter"]: r for r in rows}


@lru_cache(maxsize=1)
def transactions() -> list[dict]:
    rows = []
    with open(os.path.join(DATASET, "transactions.csv")) as fh:
        for r in csv.DictReader(fh):
            r["amount_usd_thousands"] = float(r["amount_usd_thousands"])
            rows.append(r)
    return rows


def financials_query(quarter: str, line_item: str) -> dict:
    _, by_q = financials()
    rec = by_q.get(quarter, {})
    if line_item not in rec:
        return {"ok": False, "quarter": quarter, "error": f"'{line_item}' not found",
                "available": [k for k in rec if k not in ("quarter", "period_end")]}
    return {"ok": True, "quarter": quarter, "line_item": line_item,
            "value": rec[line_item], "unit": "USD millions"}


def transactions_query(quarter: str | None = None, category: str | None = None,
                       description_like: str | None = None, min_abs: float | None = None,
                       limit: int = 20) -> dict:
    rows = transactions()
    out = []
    for r in rows:
        if quarter and r["quarter"] != quarter:
            continue
        if category and r["category"] != category:
            continue
        if description_like and description_like.lower() not in r["description"].lower():
            continue
        if min_abs is not None and abs(r["amount_usd_thousands"]) < min_abs:
            continue
        out.append(r)
    out.sort(key=lambda r: abs(r["amount_usd_thousands"]), reverse=True)
    out = out[:limit]
    return {"ok": True, "row_count": len(out),
            "total_usd_millions": round(sum(r["amount_usd_thousands"] for r in out) / 1000.0, 1),
            "rows": [{"date": r["date"], "description": r["description"],
                      "counterparty": r["counterparty"], "category": r["category"],
                      "amount_usd_millions": round(r["amount_usd_thousands"] / 1000.0, 1),
                      "quarter": r["quarter"]} for r in out]}
