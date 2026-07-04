# Limitations — what works only in the sample scenarios, and why

Covenant Sentinel has **two modes**. Read this before assuming a capability generalizes.

| Mode | What it is | Scope |
|---|---|---|
| **Sample scenarios (S0–S4)** | Scripted analyses wired to the committed **Hospira dataset** | Correct & tool‑verified, but **dataset‑bound** — will not "just work" on new documents |
| **Upload ("New analysis")** | The general ad‑hoc agent over whatever PDFs you attach | **General**, but weaker: extraction‑based, single‑period, honest "insufficient data" |

The design goal was a *flawless, verifiable demo* on a known corpus, not a general covenant engine.
That trade‑off is deliberate; below is exactly where it bites and why.

---

## 1. Where the numbers come from
- **Sample mode:** every figure is read from **structured stores** — `financials_quarterly.json`
  and `transactions.csv` — and computed by the deterministic engine. The agent does **not** parse
  numbers out of the financial‑report PDFs; those PDFs exist for retrieval/citation, not as the
  data source.
  **Why:** robust table extraction from arbitrary PDFs is hard and error‑prone; the dataset ships
  clean structured ground truth, so the demo's math is exact and golden‑testable.
- **Upload mode:** figures are extracted from the uploaded PDFs by regex + LLM (`extract_financials`).
  Quality depends on the document's layout; missing figures → `insufficient_data`.
  **To generalize sample‑grade accuracy:** wire a real financial‑table extractor (e.g. layout‑aware
  parsing) and feed it into the same engine.

## 2. The covenant engine is Hospira‑specific
- The trailing‑four‑quarter Adjusted EBITDA, the **per‑category lifetime addback caps**
  ($290M / $110M), and the **§6.6A date step‑down** (3.75→3.50) are encoded in
  `covenant_engine.py` to match **this** credit agreement + amendment.
- **Why:** covenant mechanics are document‑specific; there is no universal formula. Encoding the
  exact rules in code (not asking an 8B model to infer them) is what makes the numbers trustworthy.
- **Upload mode** uses a generic `Net Debt / EBITDA` single‑period ratio instead — it does **not**
  reproduce capped‑addback / step‑down logic for arbitrary agreements.
- **To generalize:** the engine would need to *derive* the rule set per agreement (a much harder,
  lower‑reliability task) rather than apply a fixed one.

## 3. Citations use deterministic substring lookup
- Sample‑mode citations are attached by code (`cite_text("290.0 million", …)`, `doc_substr="amendment"`),
  tuned to the **excerpt wording**. On real SEC filings (different phrasing — e.g. "$290,000,000",
  "3.50:1.00") or arbitrary uploads, those exact lookups may not resolve and fall back to a
  best‑effort citation.
- **Why:** citations are chosen by code, not the LLM, on purpose — small models hallucinate
  citations. Deterministic linking guarantees "every number traces to a real block" for the demo.
- **To generalize:** fuzzy/embedding‑based span linking between a computed value and the page block
  that supports it (instead of literal substring match).

## 4. The scanned certificate is not OCR'd
- The scanned 2014Q4 certificate is an **image‑only** page. VultronRetriever surfaces it *visually*
  (real), but we do **not** extract its text or cell positions: the citation is **page‑level** (no
  highlighted cell), and the 3.59x is the engine's **recomputation**, not a value read off the scan.
- **Why:** no OCR engine is wired in (a deliberate choice — see the discussion in the repo history).
- **To generalize:** add Tesseract/`pytesseract` (real OCR with word bboxes) so a value can be read
  and highlighted directly on the scan.

## 5. Retrieval offline vs live
- **Live:** retrieval runs on **VultronRetriever** (Vultr Vector Store) — including the scanned image.
- **Offline / REPLAY:** the local fallback is BM25 over page text; pages with no text (the scan) can't
  be ranked, so some sample steps present known pages deterministically instead of by ranking.
- **Why:** an offline mode is needed for CI/dev without credentials; it mirrors the trace but not the
  visual ranking.

## 6. Reasoning model (track‑compliance nuance)
- The VultronRetriever models are **retrieval‑only** (their chat endpoints return 404 — proven by
  `probe_vultr.py`). Core reasoning therefore runs on a Vultr‑hosted chat model
  (`deepseek-ai/DeepSeek-V4-Flash`). Retrieval uses the VultronRetriever flavors. Both via Vultr
  Serverless Inference. Full explanation: `docs/COMPLIANCE_NOTE.md`.

## 7. Precedents / portfolio / filing / coverage
- The precedent list per scenario (`precedents.REQUIRED`), the portfolio registry, the filing‑log
  check, and the interest‑coverage reader are keyed to the dataset's files, filenames and layouts.
- **Why:** demo scope. These are real tool calls over real dataset files, but not general services.

---

## What IS genuine and general everywhere
- All ratios/verdicts come from the **deterministic engine / `ratio_calculator`**, never the LLM —
  and are asserted by `tests/test_golden.py` + `tests/test_scenarios.py`.
- **Retrieval on VultronRetriever** (live), **reasoning on Vultr Serverless Inference**.
- On text‑layer documents, citations use **real** PyMuPDF positions (accurate highlights).
- The **gap‑check instrument trigger** is general (any amendment/waiver/supplement phrasing —
  `tests/test_gapcheck.py`), and the agent **never fabricates** an addback cap it cannot cite
  (`tests/test_scenarios.py::test_negative_amendment_referenced_but_absent`).
- The **Upload path** genuinely works on arbitrary PDFs (detect covenant → multi‑retrieve →
  extract → compute → cited memo, or honest `insufficient_data`).

See `docs/SCENARIO_DOCUMENTS.md` for the exact file/tool mapping per scenario.
