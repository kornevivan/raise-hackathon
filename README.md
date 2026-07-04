# Covenant Sentinel

**An enterprise agent that monitors a loan portfolio the way a credit officer would** — it triages the book, reads the actual credit agreement and its amendments, recomputes the covenant ratios itself, digs through the ledger for causes, cites comparable committee precedents, and hands the analyst a decision‑ready escalation memo where **every claim is cited and every number is tool‑verified** — then answers follow‑up questions in a grounded chat.

Built for the **RAISE Summit Hackathon — Vultr track: "Agentic Intelligence with the VultronRetriever."** Retrieval, reasoning and deployment run on Vultr. Anchored to **two real Hospira credit documents from SEC EDGAR** (Credit Agreement 2011‑10‑28 + Amendment No. 1 2013‑04‑30) plus an internally‑consistent synthetic financial package.

> **The demo beat (S1, 2014Q2):** a borrower's quarter prints **4.218× — a covenant breach**. A naive bot escalates it. Covenant Sentinel notices the EBITDA definition was *amended*, re‑retrieves Amendment No. 1, applies the Permitted Addbacks **subject to their lifetime cap** — `min(130, remaining 100) = 100, so $30M is disallowed` — and recomputes **3.606× vs the 3.75× covenant. No breach**, but thin 0.144× headroom. It caught a false positive *and* didn't over‑credit the addback.

**Public demo URL:** `http://<vultr-ip>` · **Video:** _add link_

---

## What it does

- **Portfolio triage (S0)** — "quarter closed, review the book": the planner ranks all borrowers by risk with stated reasons. It surfaces Hospira's latest certificate — a **scanned, image‑only page** — via VultronRetriever (visual retrieval), and flags Hospira #1 because our **recomputed** 2014Q4 leverage (3.59×) is already above the 3.50× threshold the §6.6A **step‑down** brings next quarter. (We don't OCR the scan — the number is engine‑computed; the scan is cited at the page level. See `docs/SCENARIO_DOCUMENTS.md`.) One click deep‑runs the top borrower.
- **Deep covenant run (S1/S2/S3)** — plan → retrieve (>1, motivated) → deterministic tools → verify → cited memo. The engine implements the *real* mechanics: trailing‑four‑quarter Adjusted EBITDA, **Permitted Addbacks with lifetime caps** ($290M Device Strategy / $110M quality), and the **date‑dependent threshold** (3.75× → 3.50× after 2014‑12‑31).
- **Precedents** — before the memo, one more VultronRetriever pass over 7 credit‑committee case histories; the memo cites 2–3 comparables (S2 cites the *real* Hospira waiver, the Novaline step‑down analog, and the negative Gulfport case).
- **Grounded chat** — ask the run anything: cap math, "what changes next quarter?", "show precedents", or a **what‑if** ("repay $200M" → `3280/965 = 3.399× HYPOTHETICAL`, verdict unchanged). Every answer is cited; every number is tool‑computed; verdicts change only via a real re‑run.
- **Upload your own documents** — drop a credit agreement + financials (PDF); the agent detects the covenant and analyzes it. Missing figures → an honest "insufficient data", never a guess.

### The three deep scenarios (real golden numbers, CI‑checked)
| Scenario | Quarter | Naive → correct | Threshold | Verdict |
|---|---|---|---|---|
| **S3** All clear, watch the cap | 2014Q1 | 3.847× → **3.066×** | 3.75× | Compliant; Device cap 285/290 warning |
| **S1** False breach & capped addback | 2014Q2 | 4.218× → **3.606×** | 3.75× | Compliant, thin 0.144× → monitor |
| **S2** Step‑down trap | 2015Q1 | 3.800× → **3.615×** | **3.50×** | **BREACH** (would've passed old 3.75×) |

---

## Architecture

Fixed orchestration skeleton in code; the LLM is used only at narrow, schema‑constrained points. **Every number and every verdict is deterministic** — the model plans, judges gaps, and writes prose; the audited engine decides the outcome.

```
S0 triage  → rank borrowers (Prime) → deep-run the top one
   │
[1] PLANNER            → the check + evidence needed
[2] EVIDENCE LOOP  (motivated, ≤3 iterations)
     a. RETRIEVE       VultronRetriever page search → {doc, page, block} citations
     b. TOOLS          covenant_engine · ratio_calculator · financials_query · transactions_query
     c. GAP-CHECK      references an amending instrument not yet applied? (generalized, not hardcoded)
                       → escalate Flash→Prime, re-retrieve the amendment
[3] PRECEDENTS         VultronRetriever over committee case histories → 2–3 comparables
[4] VERIFIER           every claim cited + matches a tool → grounded confidence
[5] MEMO               situation · capped-calc trail · cause · precedents · recommendation
[6] HUMAN + CHAT       Approve / Escalate / Send-back · grounded Q&A + what-if
```

- **Deterministic engine** (`app/covenant_engine.py`): `addback = min(charges_in_window, max(0, cap − cumulative_before_window))`, per‑category caps, §6.6A step‑down by test‑date. Verified against `data/dataset/golden_covenant_math.json` by `tests/test_golden.py` (all 6 quarters, exact).
- **Retrieval → VultronRetriever** (Flash/Core/Prime, tiered) via the Vultr **Vector Store**; results map back to local blocks for pixel‑precise citations on text‑layer documents. The **scanned** certificate is retrieved visually and cited at the page level (no OCR/fabricated cell).
- **Reasoning → Vultr Serverless Inference** (`deepseek-ai/DeepSeek-V4-Flash`). See **[docs/COMPLIANCE_NOTE.md](docs/COMPLIANCE_NOTE.md)**: the VultronRetriever models are retrieval‑only (chat endpoints return 404 — proven by `probe_vultr.py`), so core reasoning runs on a Vultr‑hosted chat model. Both requirements are met via Vultr Serverless Inference.

**Stack:** FastAPI + SSE · React + Vite + Tailwind · SQLite (chat history) · PyMuPDF ingestion · `openai` SDK → `api.vultrinference.com`.

---

## Deployed on Vultr

Single Docker image (Vite build → FastAPI serving API + SPA) on a **Vultr Cloud Compute** instance behind **Caddy**. Reasoning + retrieval on **Vultr Serverless Inference**. A pre‑warmed response cache and persistent vector‑store collections make the demo instant and **LIVE** (header badge shows LIVE vs REPLAY). Deploy: [`deploy/vultr.md`](deploy/vultr.md).

## Run locally

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m tests.test_golden && python -m tests.test_gapcheck   # CI gate — must pass
uvicorn app.main:app --reload            # :8000  (serves built UI; or run the frontend dev server)
cd ../frontend && npm install && npm run build
```
Open http://localhost:8000. Set `VULTR_INFERENCE_API_KEY` for LIVE mode; without it the deterministic REPLAY mode produces an identical trace/memo. `python backend/probe_vultr.py` prints the served models + the VultronRetriever‑chat evidence.

---

## Data — honest about real vs synthetic

- **Real (SEC EDGAR):** Hospira Credit Agreement (2011‑10‑28) §1.1/§6.6 and Amendment No. 1 (2013‑04‑30) §1(d) caps / §1(j) step‑down. The full filings are fetched + rendered to PDF by `python deploy/fetch_real_docs.py` (into `backend/data/real/`). By default the agent indexes **faithful, source‑linked excerpt PDFs** (`data/dataset_docs.py`) of the exact governing clauses — the real Credit Agreement is ~98 pages and its wording differs from the clauses we cite, so excerpts give reliable page‑level citations. Run with `USE_REAL_DOCS=1` to index the real PDFs instead (verdicts are unchanged — every number is engine‑computed, not read from prose).
- **Synthetic (seeded, labeled):** 9 quarters of financials, a ~700‑row ledger (the S1 debt jump is the real 2014‑05‑19 $460M "Meridian Infusion Assets" acquisition draw), compliance certificates incl. a **scanned** one, 7 committee precedents, and 2 extra portfolio borrowers. Every PDF footer: *"SYNTHETIC DEMONSTRATION DATA … NOT the actual financial results of Hospira, Inc."* Ground truth: `golden_answers.md` + `golden_covenant_math.json`.

## Repo layout
```
backend/app/  covenant_engine · hospira · precedents · orchestrator_{hospira,triage,adhoc}
              · chat · gapcheck · retriever · ingest · llm · main (FastAPI/SSE)
backend/tests/ test_golden.py · test_gapcheck.py           backend/data/dataset/  (Hospira dataset)
frontend/src/ App · Trace · Memo · Chat · UploadPanel · ui · api
Dockerfile · docker-compose.yml · Caddyfile · deploy/ · docs/
```
