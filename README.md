# Covenant Sentinel

**An agentic credit analyst that monitors a loan portfolio the way a covenant officer would** — it triages the book, reads the actual credit agreement and its amendments, **derives the covenant rules from those documents**, recomputes the ratios itself, digs through the ledger for the cause, cites comparable committee precedents, and hands the analyst a decision‑ready escalation memo where **every number is tool‑verified and every claim is cited to a page**. Then it answers follow‑up questions in a grounded chat.

Built for the **RAISE Summit Hackathon — Vultr track: "Agentic Intelligence with the VultronRetriever."** Retrieval, reasoning and deployment run on Vultr. Anchored to **two real Hospira governing documents from SEC EDGAR** (Credit Agreement 2011‑10‑28 + Amendment No. 1 2013‑04‑30).

> **The demo beat (S1, 2014 Q2).** A borrower's quarter prints **4.218× — a covenant breach**. A naive bot escalates it. Covenant Sentinel notices the EBITDA definition was *amended*, re‑retrieves Amendment No. 1, applies the Permitted Addbacks **subject to their lifetime cap** — `min($130M charges, $100M remaining cap) = $100M, so $30M is disallowed` — and recomputes **3.606× vs the 3.75× covenant. No breach**, but a thin 0.144× of headroom. It caught a false positive *and* refused to over‑credit the addback.

**Live demo:** http://45.76.15.126 (Vultr · LIVE inference) · **Video walkthrough:** https://www.youtube.com/watch?v=Ql6B7v9gmTs · also **runs with zero setup locally in REPLAY mode** (deterministic, no API key).

---

## The problem it automates

Covenant monitoring is slow, manual, and error‑prone. For every borrower, every quarter, an analyst must: find the governing agreement *and every amendment*, reconstruct the exact covenant definition (which addbacks are permitted, which caps apply, whether a threshold steps down this quarter), pull the financials, recompute the ratio by hand, explain *why* it moved, and write a memo the credit committee can act on. Miss the amendment and you raise a **false breach**; over‑credit an addback and you **miss a real one**.

Covenant Sentinel automates that whole loop:

- **Portfolio triage** — "quarter closed, review the book": rank every borrower by covenant risk with stated reasons, then one‑click deep‑run the riskiest.
- **Covenant recomputation** — trailing‑four‑quarter Adjusted EBITDA, **Permitted Addbacks with lifetime caps**, and a **date‑scheduled threshold step‑down** — *derived from the documents, not hardcoded*.
- **Cause analysis** — when leverage moves, find the driver in the transaction ledger (the S1 debt jump is a real $460M acquisition draw).
- **Precedents** — retrieve the 2–3 most comparable credit‑committee case histories.
- **Cited escalation memo** + **grounded chat** (cap math, "what changes next quarter?", what‑ifs) — every answer cited, every number tool‑computed.

---

## How to test it (3 ways)

**1 · Run the hero scenario (hosted or local).**
Open the demo URL → click **S1 · Analyze Hospira's leverage covenant**. Watch the trace: it retrieves the base definition, a **gap‑check** flags the amendment, it re‑retrieves it, applies the capped addback, and the ratio flips `4.218× → 3.606×`. Open the memo — every sentence links to the exact page it's grounded in.

**2 · Try the whole book.** Run **S0 · Portfolio review** → it ranks 3 borrowers, surfaces Hospira's **scanned** certificate via VultronRetriever, and offers a deep‑run on the top borrower — which runs the *same* pipeline on that borrower's inputs (not a canned scenario).

**3 · Upload your own documents (the general path).** Drop a credit agreement + amendment + quarterly reports (PDF) into a blank chat. The agent **derives the covenant and computes the ratio from your files alone** — no preloaded data. Missing figures → an honest *"insufficient data"*, never a guess.

```bash
# Local REPLAY (deterministic, no key) — identical trace & memo to LIVE
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install && npm run build
cd ../backend && uvicorn app.main:app --reload      # → http://localhost:8000
# Set VULTR_INFERENCE_API_KEY for LIVE mode (Vultr reasoning + retrieval).
```

---

## Architecture

A **fixed orchestration skeleton in code**; the LLM is used only at narrow, schema‑constrained points (planning, gap judgement, prose). **Every number and every verdict is deterministic** — the model never does the arithmetic.

```
S0 triage → rank borrowers → escalate the top one BY ITS INPUTS (corpus + as-of date), not a scenario id
   │
[1] PLAN            the maintenance check + the evidence it needs
[2] DERIVE SPEC     read the agreement + amendment → CovenantSpec (threshold schedule, addback caps,
                    EBITDA definition) — each field carries the citation it was extracted from
[3] EVIDENCE LOOP   (motivated, ≤3 retrieval passes)
     a. RETRIEVE    VultronRetriever page search → {doc, page, block} citations
     b. EXTRACT     per-quarter figures from the reports → structured financials
     c. COMPUTE     generic_engine: trailing-4Q Adjusted EBITDA, capped addbacks, step-down threshold
     d. CONSISTENCY cross-verify a computed figure against the filing's own text layer
     e. GAP-CHECK   an amending instrument not yet applied? → escalate Flash→Prime, re-retrieve it
[4] PRECEDENTS      VultronRetriever over committee case histories → top-3 comparables (by verdict + cause)
[5] VERIFY         every claim cited + matches a tool → grounded confidence
[6] MEMO           situation · capped-calc trail · cause · precedents · recommendation
[7] HUMAN + CHAT   Approve / Escalate / Send-back · grounded Q&A + what-if
```

**The rules are derived, not scripted.** `spec_extractor` reads the real EDGAR filing and extracts the threshold step‑down (3.75× → 3.50×), the two addback caps ($290M / $110M), and the EBITDA definition — each with the page span it came from. `generic_engine` is parameterized math with **zero borrower knowledge**. A **transfer test** proves it: run the same pipeline on a *third‑party* agreement and it produces a cited spec — or an honest `insufficient_data` — **with zero code changes**.

**One pipeline for scenarios and uploads.** The Upload path runs the *same* `spec_extractor → extract → generic_engine`. Verified LIVE on the real Hospira filing (documents only, no preloaded store): `naive 3.800× → gap‑check Amendment No. 1 → adjusted 3.615× → BREACH` — identical to the deep scenario. A **generalized + LLM‑fallback extractor** reads foreign 10‑Q layouts (validated on real Hershey & Coca‑Cola filings: mapped their label wording, normalized thousands→millions, summed split debt lines).

- **Retrieval → VultronRetriever** (tiered Flash/Core/Prime) via the Vultr **Vector Store**; hits map back to local blocks for **pixel‑precise citations**. The scanned certificate is retrieved *visually* (OCR when available; page‑level citation otherwise — never a fabricated cell).
- **Reasoning → Vultr Serverless Inference** (`deepseek-ai/DeepSeek-V4-Flash`). The VultronRetriever models are retrieval‑only (chat endpoints return 404 — see [docs/COMPLIANCE_NOTE.md](docs/COMPLIANCE_NOTE.md)), so both Vultr requirements are met: retrieval on VultronRetriever, reasoning on a Vultr‑hosted chat model.

**Stack:** FastAPI + SSE · React + Vite + Tailwind · PyMuPDF ingestion · SQLite (chat history) · `openai` SDK → `api.vultrinference.com`. One Docker image on **Vultr Cloud Compute** behind **Caddy**; deploy: [`deploy/vultr.md`](deploy/vultr.md).

---

## The deep scenarios (real golden numbers, CI‑checked)

| Scenario | Quarter | Naive → correct | Threshold | Verdict |
|---|---|---|---|---|
| **S3** All clear, watch the cap | 2014 Q1 | 3.847× → **3.066×** | 3.75× | Compliant; Device cap 285/290 warning |
| **S1** False breach & capped addback | 2014 Q2 | 4.218× → **3.606×** | 3.75× | Compliant, thin 0.144× → monitor |
| **S2** Step‑down trap | 2015 Q1 | 3.800× → **3.615×** | **3.50×** | **BREACH** (would've passed the old 3.75×) |

---

## What's real vs simulated (read this)

- **Real (SEC EDGAR):** the Hospira Credit Agreement + Amendment No. 1. The covenant **rules are derived from these documents** at runtime — and the derivation generalizes to unseen agreements (transfer‑tested).
- **Simulated:** the **financial figures** are served from structured tool stores (`financials_quarterly.json`, a transaction ledger, a filing log). These stand in for the systems a bank agent would really query — a financial database or **SEC XBRL** structured facts. They are clearly labeled synthetic (every PDF footer: *"SYNTHETIC DEMONSTRATION DATA … NOT the actual financial results of Hospira, Inc."*).
- **The agent does not need the simulated stores.** The **Upload path computes the covenant from attached documents alone** — proven LIVE on the real filing, and the extractor generalizes to foreign 10‑Q layouts. The honest current limit is *retrieval*, not extraction: reliably surfacing the right statement tables from a full raw 100‑page filing is the next hardening step (see [docs/LIMITATIONS.md](docs/LIMITATIONS.md)).

---

## Validate it yourself

```bash
cd backend && source .venv/bin/activate
python -m tests.test_golden           # covenant math == golden, all quarters, exact
python -m tests.test_spec_extraction  # spec DERIVED from the real EDGAR filing == golden
python -m tests.test_transfer         # same pipeline on a third-party agreement → cited spec / insufficient_data
python -m tests.test_upload_derived   # upload path computes the covenant from documents (== deep result)
python -m tests.test_scenarios        # full agent traces + escalation-by-inputs + no golden leakage
# or run all:  for t in tests/test_*.py; do python -m "tests.$(basename "$t" .py)"; done
```

## Repo layout
```
backend/app/   spec_extractor · generic_engine · covenant_spec · docroles · linker · fin_extract
               hospira · precedents · scenarios · orchestrator_{hospira,triage,adhoc}
               chat · gapcheck · retriever · ingest · llm · main (FastAPI/SSE)
backend/tests/ test_golden · test_spec_extraction · test_transfer · test_upload_derived · test_scenarios · …
frontend/src/  App · Trace · Memo · Chat · UploadPanel · ui · api
Dockerfile · docker-compose.yml · Caddyfile · deploy/vultr.md
docs/  PITCH · LIMITATIONS · PRODUCT_AND_ARCHITECTURE · COMPLIANCE_NOTE · SCENARIO_DOCUMENTS · VALIDATION_REPORT
```
