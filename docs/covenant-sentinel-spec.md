# Covenant Sentinel — Implementation Spec

Enterprise agent for loan covenant monitoring. Built solo at RAISE Summit Hackathon 2026, **Vultr track** (remote). This document is the single source of truth for the coding assistant. Read it fully before writing any code.

---

## 1. Goal & one-line pitch

**"An agent that watches a loan portfolio the way a credit officer would — reads the actual credit agreement, recomputes the ratios itself, digs into transactions for causes, and hands the analyst a decision-ready escalation memo where every claim is cited and every number is verifiable."**

The project must demonstrate a **multi-step agentic workflow grounded in documents** — NOT a chatbot, NOT retrieve-then-answer.

## 2. User value (this framing drives every UI/UX decision)

Target user: a **credit portfolio analyst / loan servicing officer** at a bank or direct lender.

Their pain today:
- Covenant compliance checks are quarterly, manual, and slow: re-reading a 200-page credit agreement to find the exact definition of "Consolidated EBITDA", rebuilding the ratio in Excel, hunting through the GL for what caused a change. Days of work per borrower.
- Definitions are treacherous: amendments silently change addbacks and thresholds; a naive calculation gives the wrong answer.
- Breaches discovered late are expensive (waivers, defaults, damaged relationships).

What the agent gives them:
1. **Speed**: minutes instead of days from "new financials arrived" to a decision-ready memo.
2. **Trust through citations**: every claim in the memo links to the exact clause/line in the source documents. The analyst never has to take the agent's word.
3. **Correctness through tools**: the agent never does arithmetic "in its head" — a deterministic calculator recomputes every ratio; math is checkable.
4. **Judgment stays human**: the memo ends with a recommendation + confidence score, and the human approves / escalates / sends back. The agent prepares the decision; the human makes it.

The demo's emotional beat: *the agent catches a false-positive breach that a naive calculation (and a naive RAG bot) would have reported* — because it noticed the definition references an amendment and went back for it.

## 3. Hackathon constraints (hard requirements — violating these loses the hackathon)

Judging weights: **Demo 50%, Impact 25%, Creativity 15%, Pitch 10%.** Optimize for a flawless, visually legible working demo above all else.

Track (Vultr) problem statement requires the agent to visibly: **plan → retrieve more than once when it needs to → call tools → make decisions → produce an outcome a real enterprise team could use.** Each of these five verbs must be individually identifiable in the UI trace.

Hard rules (per the official track brief "Agentic Intelligence with the VultronRetriever"):
- **ALL core LLM reasoning steps MUST run on VultronRetriever models via Vultr Serverless Inference.** This includes: planner, gap check, verifier, memo synthesis — every LLM call in the primary workflow. The three flavors (Qwen3.5-based):
  - `vultr/VultronRetrieverPrime-Qwen3.5-8B` — strongest; planner, verifier, memo
  - `vultr/VultronRetrieverCore-Qwen3.5-4.5B` — gap checks, extraction, cause analysis
  - `vultr/VultronRetrieverFlash-Qwen3.5-0.8B` — classification, routing, cheap utility calls
  Other models are permitted ONLY for "chat facilitation, UI interactions, or secondary tasks" — nothing on the core decision path. Simplest safe policy: use VultronRetriever for everything.
- **VultronRetriever must also be the document retrieval layer.** Per the brief it is a layout-aware page retriever: "reads a page the way a person does, taking in the full layout including tables, charts, and scans, and returns the most relevant pages." Design retrieval around **pages, not text chunks** (see Architecture). Verify the exact invocation mode (embedding endpoint vs chat-style vs rerank) from the HF model cards + Vultr API in Phase 0.
- **Vultr is the backbone for retrieval, reasoning, AND deployment.** Backend must be deployed on Vultr (VM or Vultr services) with a **public demo URL** — an explicit deliverable. Docker-compose + Caddy/nginx on a small Cloud Compute instance; $200 credits cover it many times over. State "deployed on Vultr" in README and video. Vultr GPUs are NOT available — Serverless Inference only for all LLM workloads.
- Required deliverables (explicit in the brief): public GitHub repo with setup steps, backend deployed on Vultr, public demo URL, recorded demo video, clear written explanation of architecture / agent workflow / use case.
- **Bonus points** (explicit in the brief): creative multi-agent or tool-using designs; handling messy real-world documents well (tables, charts, scans). Both are targeted below.
- **Small-model discipline**: with an 8B model as the strongest reasoner, every prompt must be narrow and structured — strict JSON schemas, 1–2 few-shot examples per prompt, temperature 0–0.2, short focused contexts (page-level evidence only, never whole documents). The code orchestration skeleton is what makes 8B-class models reliable; never ask them for open-ended multi-step autonomy.
- **Public GitHub repo**, all work created during the event (no pre-written code; this spec/plan is fine, code is not). Commit early and often — commit history is evidence of during-event work.
- **Banned project types** to stay clearly away from: basic RAG, dashboards-as-main-feature, Streamlit. Consequence: the main screen is an **agent run + memo**, not charts. No Streamlit; build a real web app. Multi-step behavior must be real, not cosmetic.
- Submission: short **1-minute demo video** (YouTube/Loom) + repo + description. Remote judging is based on the video, description, and repo — the video is the demo; treat it as the primary deliverable.

## 4. Architecture

Fixed orchestration skeleton in code; LLM judgment only at narrow, well-specified points. No unbounded recursion, no free-form agent loops. Every LLM call has a JSON schema, a timeout, and a retry-once-with-repair policy.

```
Trigger (new quarterly financials for borrower X / user clicks "Run check")
   │
   ▼
[1] PLANNER  (LLM: strongest available model, e.g. kimi-k2-instruct)
    Input: borrower profile, list of covenants (extracted once at ingest), new period metadata
    Output (strict JSON): list of checks; per check: covenant id, definition_source_needed,
    ratio_formula_hint, data_needed, risk_priority
   │
   ▼
[2] EVIDENCE LOOP  (per check; max 3 iterations; orchestrated in code)
    a. RETRIEVE: VultronRetriever page-level search over the document index →
       covenant definition clause, threshold, relevant amendment pages.
       Retrieval unit = page (layout-aware, handles tables/scans); every result
       carries {doc_id, page, span} for citation rendering and UI highlighting.
    b. TOOLS (deterministic, in code):
       - ratio_calculator(formula, inputs) → exact arithmetic, returns steps
       - financials_query(period, line_item) → values from the financial statements
       - transactions_query(filters) → rows from the transaction ledger (SQLite)
       - (optional) web_search(query) → market context, only if time permits
    c. GAP CHECK (LLM, small/fast model): "Given the goal of this check and the
       evidence collected, is anything missing or ambiguous? If the definition
       references another document/amendment, name it." → if gaps: targeted
       re-retrieval, loop again (≤3 total). THIS is the motivated multi-retrieval
       the track demands — log the reason for every extra retrieval.
   │
   ▼
[3] VERIFIER  (LLM pass, may use a reasoning model)
    Input: draft findings. Checks: every factual claim has a citation id;
    every number matches a calculator/tool output. Uncited claims → removed
    or flagged. Produces per-finding confidence + overall confidence score
    (grounded: fraction of claims verified, not a vibe number).
   │
   ▼
[4] MEMO SYNTHESIS  (LLM)
    Escalation memo: situation, calculation trail, cause analysis,
    recommendation (comply / at-risk / breach / false-positive), confidence.
    Every sentence that states a fact carries a citation marker [n].
   │
   ▼
[5] HUMAN-IN-THE-LOOP (UI)
    Approve / Escalate / Send back with a note (send-back re-runs the affected
    check with the note injected into the planner context — exactly once).
```

### Model assignment (three-tier VultronRetriever routing — this IS the "creative multi-agent design" bonus story)
- `VultronRetrieverPrime-Qwen3.5-8B`: planner, verifier, memo synthesis, hard gap checks.
- `VultronRetrieverCore-Qwen3.5-4.5B`: routine gap checks, evidence extraction, cause analysis over transaction slices.
- `VultronRetrieverFlash-Qwen3.5-0.8B`: classification, query routing, citation-format checks — anything cheap and frequent.
- A tiny router (code + Flash) decides which tier handles each step by task complexity; log the routing decision in the trace ("thought with Flash / escalated to Prime") — cheap to build, memorable in the pitch.
- **Retrieval**: VultronRetriever as a layout-aware page retriever over rendered document pages. Exact invocation mode TBD in Phase 0 from the HF cards (`huggingface.co/collections/vultr/vultronretriever`) — could be embedding-style (embed pages + query, cosine top-k), rerank-style, or generative scoring. Build a thin `retriever.py` interface so the rest of the code doesn't care.
- Pipeline: PDF/HTML → per-page render + extracted text → index pages with VultronRetriever → retrieval returns page ids → reasoning steps receive page content; citations are `{doc_id, page, span}` and the UI highlights the page region.
- No non-Vultron models anywhere in the core path. If a secondary nicety is added (e.g., small-talk chat greeter), isolate it and label it clearly as non-core.

### Tool calling strategy
Do NOT assume the API supports the OpenAI `tools` parameter. Default design: **structured JSON output** — the model returns `{"action": "call_tool", "tool": "...", "args": {...}}` or `{"action": "final", ...}`; the orchestrator parses (with one repair retry on invalid JSON) and executes. If `tools` turns out to be supported natively, switch — but the JSON path must work regardless.

### Hard budgets (enforced in code)
- ≤ 3 evidence-loop iterations per check; ≤ 12 LLM calls per full run; per-call timeout 60s; total run watchdog 4 min.
- One send-back re-run max per check.
- Cache LLM responses keyed by (model, prompt hash) during development to save credits and make replays instant.

## 5. Tech stack

- **Backend**: Python 3.11+, FastAPI. Orchestrator as an explicit state machine (plain code, no LangGraph magic unless it demonstrably saves time). SSE or WebSocket to stream trace events to the UI.
- **Frontend**: Next.js (or Vite+React) + Tailwind. Two-pane layout: left = live agent trace (plan → retrievals with "why" → tool calls with inputs/outputs → loop iterations → verifier results), right = document viewer / memo. Citations in the memo are clickable → right pane scrolls to and highlights the exact source span.
- **Storage**: SQLite for transactions ledger + run history. Vector store: Vultr Turnkey RAG if it works smoothly; fallback: `sqlite-vec` or FAISS locally with whatever embedding endpoint Vultr offers.
- **LLM client**: `openai` SDK with `base_url=https://api.vultrinference.com/v1`. One thin wrapper module (`llm.py`) — all model names, budgets, caching, JSON-repair logic live there. Nothing else in the codebase calls the API directly.

## 6. Data plan

Hybrid: **real anchor document + internally consistent synthetic operational data**, generated by a seeded script committed to the repo (`data/generate.py`).

1. **Real credit agreement** from SEC EDGAR (public filings, exhibits 10.x). Requirements: has quarterly-tested **maintenance covenants** (e.g., max total net leverage ratio, min fixed charge coverage); ideally has a filed **amendment** touching a definition. Use EDGAR full-text search (efts.sec.gov) for phrases like "maximum total net leverage ratio". Download the exhibit HTML/PDF, keep the source URL in the README.
   - If a suitable real amendment can't be found quickly (>1h of searching), write a synthetic Amendment No. 1 in authentic legal style that adds a one-time acquisition-cost addback to the EBITDA definition. Label real vs synthetic honestly in README.
2. **Synthetic financials**: 4–5 quarters of statements (income statement, balance sheet, debt schedule) as structured JSON + rendered PDFs/HTML for the document viewer. The covenant ratio drifts: e.g., 2.8x → 3.1x → 3.3x → 3.45x against a 3.5x threshold, with the final quarter's *naive* calculation landing at ~3.55x.
3. **Synthetic transaction ledger**: CSV/SQLite, ~2–5k rows, internally consistent with the financials (quarter sums reconcile). Bury the story: a one-time acquisition-related expense cluster in the final quarter that (a) explains the EBITDA drop and (b) qualifies for the amendment's addback.
4. **Compliance certificates** for prior quarters (one-page synthetic PDFs) — nice retrieval fodder.
5. **Messy-document showcase (targets the explicit bonus for "handling messy real-world documents well")**: render the financial statements as table-heavy PDFs (real layout, merged cells, footnotes), and make at least one document a **scan** — e.g., the latest compliance certificate as a scanned, slightly skewed image-PDF with a signature. Script the "scanning" (render → rasterize → slight rotation/noise via Pillow). The demo must include a moment where the agent pulls a specific number **from a table on a scanned page** — this is VultronRetriever's advertised strength and free bonus points.

**Consistency is non-negotiable**: generate financials FROM the ledger (aggregate up), not independently. A judge clicking citations must see numbers that reconcile.

### Demo scenarios (seeded, reproducible)
- **S1 "The twist" (primary)**: naive ratio = 3.55x (breach!) → agent retrieves the EBITDA definition → definition references Amendment No. 1 → agent re-retrieves the amendment (logged reason!) → finds the addback → calculator recomputes → 3.42x, no breach, but headroom 0.08x → recommendation: no breach, escalate for monitoring, confidence high.
- **S2 "Clean breach"**: different borrower, genuine breach, cause = revenue collapse visible in ledger → recommendation: escalate immediately.
- **S3 "All clear"**: healthy borrower, quick pass — shows the agent is calibrated, not alarmist.

## 7. Build order (24h, solo; cut from the bottom if behind)

**Phase 0 — Validation spike (first 1.5–2h, do NOT skip):**
1. Get Vultr API key working; `GET /v1/chat/models` — confirm the three VultronRetriever model ids and their exact API names.
2. Read all three HF model cards (`huggingface.co/collections/vultr/vultronretriever`): chat template, context window, vision/page-image input support, retrieval invocation mode (embedding vs rerank vs generative), recommended usage.
3. Test Prime-8B hard: JSON-schema adherence on a planner-style prompt (5 runs), latency, whether the `tools` param exists, rate limits (10 parallel calls). Test Flash-0.8B on a classification prompt — decide if it's usable or decorative.
4. Test retrieval end-to-end on 3 sample pages (incl. one table page): index, query, check the right page comes back.
5. Find the EDGAR credit agreement (timebox: 1h).
   → After Phase 0, lock model assignments and the retriever invocation mode in `llm.py` / `retriever.py`.

**Phase 1 — Data (2–3h):** `data/generate.py` (seeded), ingest pipeline: chunk documents with offsets, embed, store. Verify retrieval quality manually on 5 queries.

**Phase 2 — Pipeline happy path (4–5h):** orchestrator state machine, planner → evidence loop (retrieve + calculator + financials_query) → memo. CLI-driven, JSON trace to stdout. Get S1 working end-to-end here before any UI.

**Phase 3 — Full agent (3–4h):** gap check + motivated re-retrieval, transactions_query + cause analysis, verifier + grounded confidence, run caching/replay.

**Phase 4 — UI (5–6h):** trace stream pane, memo pane with clickable citations + source highlighting, approve/escalate/send-back, run launcher with the 3 scenarios. Polish: the trace must be readable by a judge with zero context in 10 seconds.

**Phase 5 — Ship (3h):** deploy to a Vultr Cloud Compute instance (docker-compose; public URL; ~1h incl. DNS-less access by IP or a free subdomain), rehearse & record the 1-min video on S1 **from the deployed URL** (script below), README (problem, architecture diagram, real-vs-synthetic data statement, EDGAR source link, deployed-on-Vultr note, how to run), submission form. Buffer for disasters.

**Stretch (only if everything above is done):** Gradium TTS "voice briefing" of the memo (30 min); web_search tool for market context; S2/S3 polish.

## 8. One-minute video script (record against S1)

0:00–0:10 — Problem: "Covenant checks take analysts days per borrower, and amended definitions make naive calculations wrong."
0:10–0:40 — Run S1 live: show the plan appear, retrieval with citation, calculator firing, the **moment the agent flags the naive breach, notices the amendment reference, re-retrieves, and reverses its own conclusion** (zoom on the trace line explaining WHY it re-retrieved).
0:40–0:55 — The memo: click a citation → source clause highlights; show confidence score and Approve/Escalate buttons.
0:40 (inside the run) — one beat where the trace shows a value pulled from a table on the scanned certificate, and one beat showing tier routing ("Flash classified → Prime reasoned").
0:55–1:00 — "Every claim cited, every number recomputed, human makes the call. VultronRetriever end to end, deployed on Vultr." 

## 9. Risks & fallbacks

| Risk | Detection | Fallback |
|---|---|---|
| No `tools` param on Vultr API | Phase 0 test | JSON-action protocol (default design) |
| VultronRetriever retrieval mode unclear / awkward | Phase 0, HF cards | Wrap whatever mode exists behind `retriever.py`; worst case use Vultron models to *rerank* candidates pre-filtered by local BM25 — still "VultronRetriever for document retrieval", document the design honestly |
| Prime-8B too weak for planner-style JSON | Phase 0 (5-run test) | Shrink the planner's job: move check enumeration into code (covenants are extracted at ingest anyway), leaving Prime only prioritization + data-needs per check; more few-shot, temp 0 |
| Flash-0.8B useless in practice | Phase 0 | Drop the router tier to Core-4.5B; keep the two-tier routing story |
| Models slow / rate-limited | Phase 0 latency test | Cache aggressively (prompt-hash cache); pre-warm the demo run; record video from cached replay if needed |
| JSON output flaky | Phase 2 | One repair-retry with error fed back; few-shot examples; temperature 0; shorten prompts |
| Scanned-page retrieval underperforms | Phase 1 | Keep the scan in the corpus but make the demo's critical lookup hit a clean table page; scan becomes a secondary flourish |
| Behind schedule | End of Phase 3 | Cut S2/S3 and stretch goals; S1 + UI + deployed URL + video is a complete winning submission |

## 10. Definition of done

- [ ] S1 runs end-to-end in < 3 minutes with zero manual intervention, twice in a row.
- [ ] Trace UI shows, separately and legibly: plan, ≥2 retrievals for the same check with a stated reason for the second, ≥2 distinct tool calls with inputs/outputs, a decision, the memo.
- [ ] Every memo claim has a clickable citation that highlights the correct source span.
- [ ] Every core-path LLM call uses a VultronRetriever model; retrieval runs on VultronRetriever; grep the codebase — zero non-Vultron model ids in the core workflow, zero non-Vultr API hosts.
- [ ] App is live on a Vultr instance with a public demo URL; the video is recorded against that deployment.
- [ ] The demo includes the agent extracting a value from a table on a messy/scanned page (bonus criterion).
- [ ] README explains architecture, agent workflow, and use case (explicit deliverable), including the three-tier Prime/Core/Flash routing.
- [ ] Repo public; README explains real (EDGAR, linked) vs synthetic (seeded script) data; commit history spans the event.
- [ ] 1-min video uploaded; submission form sent before Sunday 12:00.
