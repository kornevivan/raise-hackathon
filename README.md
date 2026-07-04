# Covenant Sentinel

**An enterprise agent that monitors a loan portfolio the way a credit officer would** — it reads the actual credit agreement, recomputes the covenant ratios itself, digs through the transaction ledger for causes, and hands the analyst a decision‑ready escalation memo where **every claim is cited and every number is verifiable**.

Built for the **RAISE Summit Hackathon — Vultr track: “Agentic Intelligence with the VultronRetriever.”** Retrieval, reasoning and deployment all run on Vultr.

> **The demo beat:** a borrower’s quarter prints a **3.55× leverage ratio — a covenant breach.** A naive bot (or a naive analyst) escalates it. Covenant Sentinel notices the EBITDA definition was *amended*, re‑retrieves **Amendment No. 1**, applies the acquisition‑cost add‑back, and recomputes **3.42× — no breach.** It caught a false positive by reading the documents like a human.

---

## Why this is an *agent*, not a RAG chatbot

The Vultr brief asks for a system that **plans → retrieves more than once when it needs to → calls tools → makes decisions → produces a usable outcome.** Each verb is individually visible in the live trace:

| Verb | Where you see it |
|---|---|
| **Plan** | The planner (Prime tier) enumerates the checks and the evidence each one needs. |
| **Retrieve (>1×, motivated)** | Retrieval #1 pulls the covenant definition. A **gap‑check** notices the definition was amended → **Retrieval #2** goes back for the amendment, with the reason logged. |
| **Call tools** | Deterministic `financials_query`, `transactions_query`, and `ratio_calculator` — the agent never does arithmetic itself. |
| **Decide** | The evidence loop closes, the verifier grounds every claim, and the memo carries a recommendation + confidence. |
| **Outcome a team can use** | A cited escalation memo with Approve / Escalate / Send‑back. |

---

## The three‑tier VultronRetriever design (the creative multi‑agent story)

VultronRetriever is a **layout‑aware visual page retriever** (ColPali / late‑interaction family) — it reads a rendered page image, tables, charts and **scans** included. We use all three flavors, **escalated by difficulty**, and log every routing decision:

- **Flash‑0.8B** → routine first‑pass page lookups (cheap, frequent).
- **Core‑4.5B** → standard evidence retrieval.
- **Prime‑8B** → hard / ambiguous / layout‑heavy pages. When the gap‑check flags the amended definition, retrieval **escalates Flash → Prime** to pull the amendment carefully.

Reasoning runs on **Vultr Serverless Inference** chat models, also in three cognitive tiers (planner/verifier/memo on the strongest model; gap‑checks and extraction on lighter ones). The trace shows, per step, *which tier thought and why* — e.g. “Flash classified → Prime reasoned.”

> **Messy‑document bonus:** the Q4 compliance certificate is a **scanned, skewed, noisy image‑PDF**. In the demo the agent pulls a number **from a table on that scanned page**, and clicking the citation highlights the exact cell — VultronRetriever’s advertised strength.

---

## Architecture

```
Trigger: "Run covenant check for borrower X, new quarter"
        │
   [1] PLANNER            Prime · strict JSON      → checks + evidence needs
        │
   [2] EVIDENCE LOOP  (per check, ≤3 iterations, orchestrated in code)
        │   a. RETRIEVE   VultronRetriever page search  → {doc, page, block} citations
        │   b. TOOLS      financials_query · transactions_query · ratio_calculator
        │   c. GAP‑CHECK  "definition references an amendment not yet applied?"
        │                 → motivated re‑retrieval (escalate Flash→Prime), logged
        │
   [3] VERIFIER           every claim has a citation + matches a tool output
        │                 → grounded confidence = verified fraction
   [4] MEMO SYNTHESIS     situation · calc trail · cause · recommendation, all cited
        │
   [5] HUMAN‑IN‑THE‑LOOP  Approve / Escalate / Send‑back
```

Fixed orchestration skeleton in code; the LLM is used only at narrow, schema‑constrained points (planner, gap‑check, verifier, memo). Every LLM call has a JSON schema, a timeout, a one‑shot repair retry, and a per‑run budget (≤14 calls). No free‑form agent loops.

**Stack:** FastAPI + SSE (backend) · React + Vite + Tailwind (two‑pane UI) · SQLite (ledger + runs) · `openai` SDK pointed at `https://api.vultrinference.com/v1`. One `llm.py` wrapper owns all model routing, caching and JSON repair; one `retriever.py` owns retrieval — nothing else touches the API.

---

## Deployed on Vultr

- **Backend + UI**: a single Docker image (multi‑stage: Vite build → FastAPI serving the API *and* the built SPA) on a **Vultr Cloud Compute** instance, fronted by **Caddy** (automatic HTTPS).
- **Reasoning + retrieval**: **Vultr Serverless Inference** — VultronRetriever for documents, Vultr‑served chat LLMs for reasoning. (Vultr GPUs are not used; Serverless Inference only, per the brief.)
- **Public demo URL:** _add after deploy_ · **Video:** _add link_

See [`deploy/vultr.md`](deploy/vultr.md) for the one‑command deploy.

---

## Run it locally

```bash
# 1) backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m data.generate            # deterministic corpus (already committed)
uvicorn app.main:app --reload      # :8000

# 2) frontend
cd ../frontend
npm install
npm run dev                        # :5173  (proxies /api + /corpus to :8000)
```

Open http://localhost:5173, pick a borrower, watch the agent run.

**Offline vs live Vultr.** With no key the app runs a **deterministic offline engine** — the full pipeline, trace, tools and memo behave identically, so the demo never fails and you can develop before credentials are ready. Set `VULTR_INFERENCE_API_KEY` (from a Serverless Inference subscription) to route reasoning + retrieval through Vultr; the header badge and every trace step show which backend produced them. Use `python backend/probe_vultr.py` to list the exact served model ids and lock them in `.env`.

> One activation step: Vultr requires a **verified account email** before it will create a Serverless Inference subscription. Verify the email, add the subscription, copy its key into `.env`, run `probe_vultr.py`, and the app flips to live Vultr with no code changes.

---

## Data — honest about real vs synthetic

A hybrid corpus generated by one **seeded** script ([`backend/data/generate.py`](backend/data/generate.py)) so every figure reconciles: the **transaction ledger aggregates up to the financial statements, which feed the covenant ratio.** Click any citation and the numbers tie out.

- **Documents (synthetic, authentic legal/financial style):** credit agreement with a real maintenance covenant (max total net leverage ≤ 3.50×) and a Consolidated EBITDA definition; **Amendment No. 1** adding a Permitted‑Acquisition add‑back; table‑heavy financial statements; and a **scanned** compliance certificate.
- **Structured data (synthetic, seeded):** 4 quarters of financials + a ~400‑row ledger with the Q4 “Project Atlas” acquisition‑cost cluster (\$4.5M) that both explains the EBITDA dip and qualifies for the amendment add‑back.

Everything is generated for the demo and labeled as such — no real company’s filings are used. Swapping in a real SEC EDGAR credit agreement is a drop‑in (`data/generate.py` documents where).

### The three seeded scenarios
- **S1 — The Amendment Twist:** naive 3.55× breach → amendment add‑back → 3.42×, false positive avoided, 0.08× headroom.
- **S2 — Genuine Breach:** 4.04×, driven by a real revenue collapse in the ledger; no add‑back saves it → escalate.
- **S3 — All Clear:** 2.35×, healthy; the agent passes quickly — calibrated, not alarmist.

---

## Repo layout

```
backend/
  app/  config · corpus · retriever · llm · tools · orchestrator · main (FastAPI/SSE)
  data/ generate.py · render.py · corpus/ (page images + index.json) · ledger.csv · covenant.sqlite
  probe_vultr.py
frontend/ src/  App · Trace · Memo · ui · api      (React + Vite + Tailwind)
Dockerfile · docker-compose.yml · Caddyfile · deploy/vultr.md
```
