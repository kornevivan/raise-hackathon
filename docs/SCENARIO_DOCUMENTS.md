# Scenario documents & data provenance

What each sample scenario attaches to the agent — split into **retriever‑indexed documents**
(the agent "sees" these via VultronRetriever) and **tool data stores** (structured, queried by
deterministic tools — never indexed). Plus an honest note on what is dataset‑scripted vs general.

All dataset files live under `backend/data/dataset/`. Golden files are **never** ingested
(enforced by `tests/test_scenarios.py::test_no_golden_leakage_in_ingest`).

---

## Deep runs — S1 (2014Q2) · S2 (2015Q1) · S3 (2014Q1) · S4 (2014Q2 cross‑check)
Collection: `hospira`. Same document set for all four; the test quarter differs.

**Retriever‑indexed (`app/hospira.py` → `DEEP_DOCS`):**
- `documents/credit_agreement_excerpt.pdf` — §1.1 definitions, §6.6 (faithful excerpt of the real
  2011‑10‑28 agreement; the real 98‑page PDF is available via `USE_REAL_DOCS=1`)
- `documents/amendment_no1_excerpt.pdf` — §1(d) addback caps, §1(j)/§6.6A step‑down, §2 waiver
- `documents/financial_report_2013Q3.pdf` … `financial_report_2015Q1.pdf` (7 quarters, table‑heavy)
- `documents/compliance_certificate_2014Q1.pdf`, `…_2014Q3.pdf`
- `documents/compliance_certificate_2014Q4_SCANNED.pdf` — **scanned, image‑only** (the clean 2014Q4
  copy is deliberately **excluded** from the index)
- `documents/borrower_submitted_certificate_2014Q2.pdf` — used by **S4** only

**Precedents** (separate collection `precedents`, retrieved just before the memo):
- `documents/precedents/PRECEDENT-*.pdf` (7 committee memos)

**Tool data stores (structured — not indexed):**
- `financials_quarterly.json` → the covenant engine + `financials_query`
- `transactions.csv` (SQLite) → `transactions_query` (S1: the 2014‑05‑19 $460M revolver draw)
- `documents/precedents/precedents_index.json` → precedent registry (borrower, tags)

Per scenario the engine reads the trailing‑4‑quarter window; S1 also queries transactions; S4 also
reads the borrower‑submitted certificate to compare its claim.

---

## S0 — Portfolio triage (quarter closed, 2015Q1)
Collection: `triage`.

**Retriever‑indexed (`app/orchestrator_triage.py` → `_corpus`):**
- `documents/portfolio/profile_atlantic.pdf`, `profile_cascadia.pdf`
- `documents/portfolio/certificate_atlantic_2014Q1…2015Q1.pdf` (5)
- `documents/portfolio/certificate_cascadia_2014Q1…2015Q1.pdf` (5)
- `documents/compliance_certificate_2014Q4_SCANNED.pdf` — Hospira's latest (scanned) certificate
- `documents/amendment_no1_excerpt.pdf` — for the §6.6A step‑down citation

**Tool data stores:**
- `documents/portfolio/portfolio_index.json` → borrower registry + Atlantic/Cascadia leverage series
- `documents/portfolio/filing_log.csv` → `filing_query` (Cascadia 3 days late in 2015Q1)
- Atlantic `certificate_*_2015Q1.pdf` → interest‑coverage read (3.21x vs 3.00x)
- `financials_quarterly.json` + covenant engine → Hospira's recomputed 2014Q4 ratio (3.59x)

---

## Upload mode ("New analysis")
Whatever PDF/txt files the user attaches. Indexed into a per‑upload collection; analyzed by the
**general** ad‑hoc orchestrator (covenant + threshold detection, figure extraction). No dataset
tool stores, no precedents/portfolio.

---

## What is genuine vs dataset‑scripted (read this)

**Genuine, general, and correct everywhere:**
- Every ratio/verdict is computed by the deterministic **covenant engine / `ratio_calculator`** —
  never by the LLM. Golden‑tested to the exact expected numbers.
- Retrieval runs on **VultronRetriever** (live) over the indexed pages, including the scanned image.
- On documents that have a text layer (all except the scan), citations use **real** PyMuPDF text
  positions — the highlight lands on the actual line.
- The Upload path works on arbitrary documents (extraction‑based, with honest "insufficient data").

**Dataset‑scripted (the sample scenarios S0–S4 are wired to this specific corpus; they will NOT
"just work" on arbitrary new documents — use Upload mode for that):**
- The numbers in sample mode come from the **structured** `financials_quarterly.json` +
  `transactions.csv` (and the engine), not from OCR/parsing the report PDFs.
- Which block a citation points to is chosen by deterministic **substring lookup** tuned to the
  excerpt wording (e.g. "290.0 million", "3.75 to 1.00"). On real SEC filings (different wording)
  or arbitrary uploads those exact lookups may not resolve and fall back.
- The gap‑check, precedent list, borrower‑cert reader, coverage/filing readers, and doc filters are
  keyed to the dataset's layout and filenames.

**The scanned certificate (honest):**
- We do **not** OCR it and do **not** fabricate its text or cell positions. VultronRetriever
  surfaces the scanned page visually; the 3.59x figure is our **recomputation** of 2014Q4 (from the
  structured financials + engine), and the citation points to the scanned page at the **page
  level** (no highlighted cell). Reading a specific value off the scan would require wiring an OCR
  engine (e.g. Tesseract) — intentionally not done.
