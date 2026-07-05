# Limitations — what's genuine, what's simulated, and where the honest edge is

Covenant Sentinel is built to be **verifiable and honest**, not to overclaim. This is exactly what
is real, what is simulated for the demo, and what would break on arbitrary input — with why.

---

## 1. Financial figures are served from simulated tool stores
- In the sample scenarios, the per‑quarter figures come from structured stores
  (`financials_quarterly.json`, `transactions.csv`, the filing log) — **not** parsed from the report
  PDFs at run time.
- **Why this is the right design, not a shortcut:** in a real bank the numbers come from a financial
  database or **SEC XBRL** structured facts — you would not re‑OCR a PDF every quarter. The tool
  stores stand in for exactly those systems. Every synthetic PDF is footer‑labeled
  *"SYNTHETIC DEMONSTRATION DATA … NOT the actual financial results of Hospira, Inc."*
- **The agent does not depend on them.** The **Upload path** computes the covenant from attached
  documents alone (§3).

## 2. The covenant RULES are derived from the documents (not hardcoded)
- `spec_extractor` reads the real EDGAR filing and extracts the threshold step‑down (3.75→3.50), the
  two lifetime addback caps ($290M / $110M), and the EBITDA definition — each with its citation.
  `generic_engine` is parameterized math with **no borrower knowledge**.
- **Proven general:** `tests/test_transfer.py` runs the same pipeline on a *third‑party* agreement
  and gets a cited spec — or an honest `insufficient_data` — with **zero code changes**. The values
  are read from the document, not baked in (a hardcoded "3.75/3.50" would fail the transfer test).

## 3. Upload path = the same pipeline, on your documents
- Uploading agreement + amendment + quarterly reports runs `spec_extractor → extract → generic_engine`.
  Verified **LIVE** on the real Hospira filing (documents only): `3.800× → gap‑check → 3.615× BREACH`,
  identical to the deep scenario. See `tests/test_upload_derived.py`.
- **Figure extraction generalizes.** A generalized + LLM‑fallback extractor was validated on real
  foreign 10‑Qs (Hershey, Coca‑Cola): it maps different label wording, normalizes thousands→millions,
  and sums debt split across short‑term / current‑portion / long‑term lines. Missing figures →
  honest `insufficient_data`; nothing is fabricated.

## 4. The honest weak link is RETRIEVAL on full raw filings — not extraction
- Measured end‑to‑end on full 70–80‑page 10‑Qs (retrieve → extract): **Hershey 4/5, Coca‑Cola 1/5**.
  Given the *correct* statement text, extraction is ~perfect (10/10 on hand‑picked slices) — but on a
  full filing the semantic retriever does not reliably rank the exact consolidated‑statement pages
  above the many pages that repeat the same vocabulary (segment tables, notes, MD&A). The extractor
  then honestly returns `None`/`insufficient` rather than guessing.
- **Next hardening step:** table/structure‑aware retrieval (anchor on "CONSOLIDATED STATEMENTS OF …"
  headers; pull whole tables) and/or an **XBRL** path for SEC filings — the reliable way to get
  figures, which is also why production systems use structured feeds.

## 5. Triage mode has no upload equivalent
- Portfolio triage (S0) ranks borrowers using the portfolio registry, filing log and coverage stores.
  Its escalation now hands off **inputs** (the top borrower's corpus + as‑of date), and the deep run
  processes those inputs through the same pipeline — but there is no "upload a portfolio → rank" path;
  ranking needs the connected data stores.

## 6. The scanned certificate
- The scanned 2014Q4 certificate is image‑only. VultronRetriever surfaces it **visually** (real).
  OCR (pytesseract) reads a cell when available and the engine confirms it; otherwise the citation is
  **page‑level** — never a fabricated cell.

## 7. Reasoning model (track‑compliance nuance)
- The VultronRetriever models are **retrieval‑only** — their chat endpoints return 404 (proven by
  `probe_vultr.py`). Core reasoning therefore runs on a Vultr‑hosted chat model
  (`deepseek-ai/DeepSeek-V4-Flash`); retrieval uses the VultronRetriever flavors. Both via Vultr
  Serverless Inference. Full explanation: `docs/COMPLIANCE_NOTE.md`.

## 8. Offline REPLAY vs LIVE
- **LIVE:** retrieval on VultronRetriever (Vultr Vector Store), reasoning on Vultr inference.
- **REPLAY (no key):** deterministic local retrieval + a pre‑warmed response cache reproduce an
  identical trace/memo for CI and offline demo; visual ranking of the scan needs LIVE.

---

## What is genuine and general everywhere
- **Every ratio and verdict is deterministic** (`generic_engine` / `ratio_calculator`), never the LLM
  — asserted by `test_golden`, `test_spec_extraction`, `test_scenarios`.
- Covenant **rules derived from documents**, transfer‑tested on an unseen agreement.
- **Upload path computes the covenant from documents alone** (LIVE‑verified on the real filing).
- Retrieval on **VultronRetriever**, reasoning on **Vultr Serverless Inference**.
- Citations use **real** PyMuPDF page positions; a value links to its supporting block by
  numeric/date normalization (`linker`), not tuned substrings.
- The agent **never fabricates** an addback cap it can't cite
  (`test_scenarios::test_negative_amendment_referenced_but_absent`).
