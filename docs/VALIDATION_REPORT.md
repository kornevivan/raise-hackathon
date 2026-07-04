# Validation Report — Covenant Sentinel

Per `AGENT_DATASET_GUIDE.md` §3. All numbers are produced by the deterministic covenant
engine and the agent pipeline; golden files are used only to assert, never ingested.

Run the gates yourself:
```bash
cd backend && python -m tests.test_golden && python -m tests.test_gapcheck && python -m tests.test_scenarios
```

## 3.1 Automated golden tests — PASS

| Scenario | Trigger | Expected (golden) | Actual | ✓ |
|---|---|---|---|---|
| S1 deep run | Hospira 2014Q2 | ratio 3.606, device addback 100.0 (not 130), compliant, headroom 0.144 | 3.606 / 100.0 / COMPLIANT / 0.144 | ✅ |
| S2 deep run | Hospira 2015Q1 | threshold **3.50** (not 3.75), ratio 3.615, **BREACH** | 3.50 / 3.615 / BREACH | ✅ |
| S3 deep run | Hospira 2014Q1 | ratio 3.066, compliant; device cap 285/290 flag | 3.066 / COMPLIANT / 0.684, cap flag emitted | ✅ |
| S4 cross-check | Verify 2014Q2 borrower certificate | claimed 3.497 vs recomputed 3.606; cause = uncapped addback (+30.0); action = corrected cert, no default | claimed 3.497 / recomputed 3.606 / over_added 30.0 / `misstated_certificate` | ✅ |
| Coverage | Atlantic 2015Q1 | interest coverage 3.21 vs min 3.00, compliant + drift flag | 3.21 vs 3.00, headroom 0.21, drift flagged | ✅ |
| Filing | portfolio 2015Q1 | Cascadia 3 days late flagged; others timely | Cascadia +3d flagged, 2 timely | ✅ |
| S0 triage | Quarter closed 2015Q1 | ranking Hospira → Atlantic → Cascadia; per-borrower check lists | Hospira → Atlantic → Cascadia; review matrix (3/3/2 checks) | ✅ |

All 6 golden quarters reproduce `golden_covenant_math.json` exactly (EBITDA/addbacks/debt to 0.1;
ratios exact). Numeric tolerance well within ±0.005.

## 3.2 Trace assertions (agentic behavior) — PASS
`tests/test_scenarios.py::test_s1_trace_assertions` asserts the S1 event log contains, in order:
(a) retrieval hitting the base agreement §1.1 page → (b) a gap-check whose reason references an
amendment not yet retrieved → (c) a second retrieval hitting Amendment No. 1 → (d) a
`ratio_calculator` step containing **`min(130.0, 100.0)`** → (e) a `transactions_query` returning
the **2014-05-19 $460.0M** revolver draw. `test_s0_scanned_thumbnail` asserts a retrieval hit on
the SCANNED certificate.

## 3.3 Citation spot-checks — PASS (manual)
- Threshold citation → Amendment No. 1 page with §6.6A / "3.75 to 1.00" (NOT base §6.6).
- Addback-cap citation → Amendment No. 1 §1(d) ("$290.0 million").
- EBITDA-definition citation → base agreement §1.1 ("Consolidated Adjusted EBITDA means…").
- Financial figures → the correct quarter's report / certificate table (incl. scanned 2014Q4).

## 3.4 Negative / robustness — PASS
1. **Amendment referenced but absent** (`test_negative_amendment_referenced_but_absent`): the agent
   does NOT fabricate the $290M cap — no addback applied it cannot cite; the naive result stands
   (ratio_final == ratio_naive), recommendation ≠ `false_positive`.
2. **Only agreement, no financials** (`test_negative_only_agreement_no_financials`): verdict
   `insufficient_data`, ratio_final = null, listing what's missing — no invented threshold.
3. **Upload mode**: the two governing PDFs + financial reports run through the Upload path; the
   agent detects §6.6A itself and multi-retrieves; numbers are extraction-limited but behavior
   (motivated retrieval, honest gaps, no fabrication) holds.
4. **Paraphrase robustness**: "check covenant compliance for Hospira Q2 2014" and "is Hospira within
   its leverage covenant as of June 30, 2014" both drive the same S1 verdict (the engine is keyed
   to the test quarter, not the prompt wording).

## 3.5 Chat validation (S1) — PASS
The four suggested questions produce cited, correct answers within budget:
- cap question → `min(130,100)=100, 30 disallowed` from the calculator, cited §1(d);
- next-quarter → §6.6A step-down warning cited to the amendment;
- precedents → TriState (PRECEDENT-2013-09);
- what-if "$200M repayment" → **3,280.0 / 965.0 = 3.399x**, labeled HYPOTHETICAL, verdict unchanged.
Open questions (e.g. "what documents did you analyze?") get grounded, cited LLM answers; missing
facts get an honest "not in the documents".

## 3.6 Live-run confirmation
All scenarios (S0/S1/S2/S3/S4) + every chat suggested question were executed **against live Vultr
Serverless Inference** during pre-warm (retrieval on VultronRetriever vector-store collections
`hospira` / `triage` / `precedents`; reasoning on `deepseek-ai/DeepSeek-V4-Flash`). Header badge
reads **LIVE · Vultr**; per-step model + latency are shown in the trace. Compliance note on why
reasoning runs on a Vultr-hosted chat model (VultronRetriever chat endpoints return 404):
`docs/COMPLIANCE_NOTE.md`.

**Ingest leakage guard:** `test_no_golden_leakage_in_ingest` asserts no ingested document
references a `golden` file. The clean 2014Q4 certificate is kept OUT of the index (only the
SCANNED copy is indexed) so the messy-document beat survives.
