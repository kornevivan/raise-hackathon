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

# documents ingested for a Hospira deep run. Prefer the real SEC PDFs in data/real/
# if present; otherwise the faithful excerpts. Per the dataset guide: index the SCANNED
# 2014Q4 certificate and keep the CLEAN 2014Q4 copy OUT of the index (else the retriever
# prefers the clean copy and the messy-document beat disappears).
DEEP_DOCS = [
    "credit_agreement_excerpt.pdf",
    "amendment_no1_excerpt.pdf",
    "financial_report_2013Q3.pdf", "financial_report_2013Q4.pdf",
    "financial_report_2014Q1.pdf", "financial_report_2014Q2.pdf",
    "financial_report_2014Q3.pdf", "financial_report_2014Q4.pdf",
    "financial_report_2015Q1.pdf",
    "compliance_certificate_2014Q1.pdf", "compliance_certificate_2014Q3.pdf",
    "compliance_certificate_2014Q4_SCANNED.pdf",   # scanned only; clean 2014Q4 excluded
    "borrower_submitted_certificate_2014Q2.pdf",   # S4 cross-check source
]

REAL_DIR = os.path.join(config.DATA_DIR, "real")   # optional real SEC PDFs (guide §1)
REAL_MAP = {"credit_agreement_excerpt.pdf": "credit_agreement_2011-10-28.pdf",
            "amendment_no1_excerpt.pdf": "amendment_no1_2013-04-30.pdf"}

_corpus_id: str | None = None


def corpus():
    """Ingest the Hospira document set once; return the UPLOADS entry (retriever,
    pages, by_block) — identical structure to an upload."""
    global _corpus_id
    if _corpus_id and _corpus_id in ingest.UPLOADS:
        return ingest.UPLOADS[_corpus_id]
    # By default index the faithful, source-linked EXCERPTS (reliable page-level
    # citations; the real 98-page filing would swamp retrieval and its wording differs
    # from the exact clauses we cite). Set USE_REAL_DOCS=1 to index the real SEC PDFs
    # from data/real/ instead — see deploy/fetch_real_docs.py and docs/COMPLIANCE_NOTE.md.
    use_real = os.getenv("USE_REAL_DOCS", "").strip() in ("1", "true", "yes")
    files = []
    for name in DEEP_DOCS:
        real = os.path.join(REAL_DIR, REAL_MAP.get(name, ""))
        p = real if (use_real and name in REAL_MAP and os.path.exists(real)) else os.path.join(DOCS, name)
        if os.path.exists(p):
            assert "golden" not in os.path.basename(p).lower(), "ingest leakage: golden file"
            files.append((os.path.basename(p), open(p, "rb").read()))
    res = ingest.ingest(files, collection="hospira")
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


def filing_query(period: str, deadline_days: int = 45) -> dict:
    """Reporting-obligation check over the filing log (non-numeric covenant)."""
    path = os.path.join(DOCS, "portfolio", "filing_log.csv")
    late, timely = [], 0
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            if r["period"] != period:
                continue
            d = int(r["days_late"] or 0)
            if d > 0:
                late.append({"borrower": r["borrower"], "days_late": d,
                             "due_date": r["due_date"], "received_date": r["received_date"]})
            else:
                timely += 1
    return {"ok": True, "period": period, "deadline_days": deadline_days,
            "late": late, "timely_count": timely}


def read_borrower_certificate() -> dict:
    """Extract the figures the borrower CLAIMED on its submitted 2014Q2 certificate
    (the agent reads this from the ingested PDF; it is not golden)."""
    import fitz
    import re
    p = os.path.join(DOCS, "borrower_submitted_certificate_2014Q2.pdf")
    t = " ".join(fitz.open(p)[0].get_text("text").split()) if os.path.exists(p) else ""

    def num(pat):
        m = re.search(pat, t, re.I)
        return float(m.group(1).replace(",", "")) if m else None
    ebitda = num(r"CONSOLIDATED ADJUSTED EBITDA\s+([\d,]+\.?\d*)")
    device = num(r"Device Strategy charges\s+([\d,]+\.?\d*)")
    # debt appears after the period-end date on the same line — skip the date
    debt = num(r"Consolidated Total Debt as of \d{4}-\d\d-\d\d\s+([\d,]+\.?\d*)")
    ratio = round(debt / ebitda, 3) if (debt and ebitda) else None
    return {"claimed_ebitda": ebitda, "claimed_device_addback": device,
            "consolidated_total_debt": debt, "claimed_ratio": ratio, "period": "2014Q2"}


def interest_coverage_from_cert(borrower_slug: str, period: str) -> dict:
    """Read the interest-coverage ratio a borrower reported on its certificate PDF."""
    import fitz
    import re
    p = os.path.join(DOCS, "portfolio", f"certificate_{borrower_slug}_{period}.pdf")
    if not os.path.exists(p):
        return {"ok": False}
    t = " ".join(fitz.open(p)[0].get_text("text").split())
    cov = re.search(r"INTEREST COVERAGE RATIO \(min ([\d.]+)x\)\s+([\d.]+)x", t, re.I)
    if not cov:
        return {"ok": False}
    return {"ok": True, "min": float(cov.group(1)), "coverage": float(cov.group(2)),
            "headroom": round(float(cov.group(2)) - float(cov.group(1)), 2)}


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
