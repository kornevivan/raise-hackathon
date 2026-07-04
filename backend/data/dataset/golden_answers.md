# Golden Answers — Covenant Sentinel Demo Scenarios

Ground truth for testing the agent against the Hospira demo dataset.
Covenant mechanics come from the REAL documents (see README_demo_data.md):
Credit Agreement §1.1 + §6.6 (Oct 28, 2011) as amended by Amendment No. 1 (Apr 30, 2013) §1(d) and §1(j).

Key formulas the agent must reconstruct from the documents:
- **Leverage Ratio** = Consolidated Total Debt (last day of FQ) / Consolidated Adjusted EBITDA (trailing 4 FQ)
- **Adjusted EBITDA** = Net Income + Financing Expense + income taxes + D&A + Permitted Addbacks
- **Permitted Addbacks caps (Amendment No. 1)**: Device Strategy cash charges after 2012-12-31 — lifetime cap **$290.0M**; quality-matters cash charges after 2013-01-01 — lifetime cap **$110.0M**. Addback in a trailing window = min(charges in window, remaining cap at window start).
- **Threshold (amended §6.6A)**: ≤ **3.75** for FQ ending through 2014-12-31; ≤ **3.50** for FQ ending after 2014-12-31.

All dollar figures in $ millions. Exact machine-checkable numbers: `golden_covenant_math.json`.

---

## Scenario S3 — "All clear, but watch the cap" (run the check as of FQ **2014Q1**, period end 2014-03-31)

| Step | Expected value |
|---|---|
| Trailing window | 2013Q2–2014Q1 |
| ΣNet income / ΣFinancing exp. / Σtaxes / ΣD&A | 310.1 / 79.5 / 82.4 / 313.0 |
| Device charges in window / cum before window / **addback allowed** | 155.0 / 130.0 / **155.0** (cap headroom 160.0 → full) |
| Quality charges in window / **addback allowed** | 45.0 / **45.0** (cum well under 110) |
| **Adjusted EBITDA** | **985.0** |
| Consolidated Total Debt (2014-03-31) | 3,020.0 |
| **Leverage Ratio** | **3.066x** vs threshold 3.75x |
| Verdict | **COMPLIANT**, headroom 0.684x |

Expected memo: compliant, no action required. **Bonus insight the best answer includes:** cumulative Device Strategy charges reach **285.0 of the 290.0 cap** by end of 2014Q1 — only $5.0M of addback capacity remains for future quarters; flag as forward-looking risk.
Naive trap: without addbacks the ratio looks like **3.847x → false breach**.

## Scenario S1 — "The false breach and the capped addback" (run as of FQ **2014Q2**, period end 2014-06-30) — PRIMARY DEMO

| Step | Expected value |
|---|---|
| Trailing window | 2013Q3–2014Q2 |
| ΣNI / ΣFin.exp. / Σtaxes / ΣD&A | 339.9 / 81.8 / 90.3 / 313.0 |
| Naive EBITDA (no addbacks) | 825.0 → naive ratio **4.218x → "BREACH"** |
| Device charges in window | 130.0 |
| Device cum before window (2013Q1+Q2) | 190.0 → remaining cap = 290.0 − 190.0 = **100.0** |
| **Device addback allowed** | **100.0** (NOT 130.0 — $30.0M disallowed by the cap) |
| Quality addback | 40.0 (fully allowed) |
| **Adjusted EBITDA** | **965.0** |
| Consolidated Total Debt (2014-06-30) | 3,480.0 |
| **Leverage Ratio** | **3.606x** vs threshold 3.75x |
| Verdict | **COMPLIANT**, but thin headroom **0.144x** → recommend enhanced monitoring |

Cause analysis (from transactions.csv): debt jumped +$460.0M on **2014-05-19, "Revolver draw — Meridian Infusion Assets acquisition"** (matching acquisition payment same day). The EBITDA denominator was NOT the driver; the numerator was.
Expected multi-retrieval moment: EBITDA definition (§1.1, base agreement) → "Permitted Addbacks" term → **definition was AMENDED → agent must retrieve Amendment No. 1 §1(d)** for current caps, and §1(j) for the current threshold.
Wrong answers to test against: 4.218x "breach" (no addbacks); **3.497x "comfortable" (addbacks applied WITHOUT the $290M cap — the subtle failure)**; using original §6.6 threshold 3.50 from the unamended base agreement → false breach even with correct EBITDA.

## Scenario S2 — "The step-down trap" (run as of FQ **2015Q1**, period end 2015-03-31)

| Step | Expected value |
|---|---|
| Trailing window | 2014Q2–2015Q1 |
| Naive EBITDA / ratio | 883.0 / 3.800x |
| Device charges in window / cum before window / **addback allowed** | 50.0 / 285.0 / **5.0** (cap nearly exhausted) |
| Quality addback | 40.0 (cum 105.0 ≤ 110) |
| **Adjusted EBITDA** | **928.0** |
| Consolidated Total Debt (2015-03-31) | 3,355.0 |
| **Leverage Ratio** | **3.615x** |
| Threshold for FQ ending AFTER 2014-12-31 (§6.6A(b)) | **3.50x** |
| Verdict | **BREACH** (would have passed the pre-step-down 3.75x — that is the trap) |

Expected memo: Event of Default risk under §6.6A(b); escalate immediately; recommend initiating waiver/amendment discussions with the Administrative Agent (precedent: Section 2 of Amendment No. 1 itself was a waiver); note both drivers — EBITDA erosion AND near-exhaustion of the Device Strategy addback cap (only 5.0 available vs 50.0 of charges).
Wrong answer to test against: "compliant at 3.62x vs 3.75x" — an agent that retrieved the threshold from the base agreement's original §6.6 or from a stale certificate, missing the amendment's step-down schedule.

---

## What a full-credit agent run must demonstrate (checklist per scenario)

1. Retrieves the **Leverage Ratio / Adjusted EBITDA definitions** from the base agreement (§1.1) — with page citations.
2. Notices "Permitted Addbacks" and the covenant section were **amended** → retrieves Amendment No. 1 (motivated second retrieval).
3. Pulls quarterly figures from the financial report PDFs (tables), and the prior-quarter certificate — including the **SCANNED 2014Q4 certificate** for the S2 run (table on a messy page).
4. Computes EBITDA and the ratio via a **deterministic calculator tool** (never model arithmetic), applying the min(window charges, remaining cap) logic.
5. Applies the **date-correct threshold** (3.75 vs 3.50).
6. For S1: queries transactions.csv to explain the debt jump (tool call).
7. Outputs a memo where every number traces to a citation; confidence reflects the share of verified claims.

---

## Scenario S0 — Portfolio triage (run "quarter closed" as of 2015Q1, BEFORE any deep check)

Input corpus: 3 borrowers (Hospira; Cascadia Medical Supply; Atlantic Beverage Partners),
their latest certificates (2014Q4), profiles, and Hospira's amendment.

Expected priority ranking (with reasons the planner must state):
1. **Hospira, Inc.** — three converging signals: (a) last certificate (2014Q4, the SCANNED one)
   shows 3.59x — already ABOVE the 3.50x threshold that takes effect for FQs ending after
   2014-12-31 (Amendment No. 1 §1(j) step-down); (b) Device Strategy addback cap nearly
   exhausted (285.0/290.0); (c) thin and shrinking headroom trend. → deep run required.
2. **Atlantic Beverage Partners** — headroom 0.19x at 2014Q4 (3.31 vs 3.50), five consecutive
   quarters of upward drift, no addback capacity. → standard run + trend warning
   (cite PRECEDENT-2013-06 enhanced-monitoring playbook).
3. **Cascadia Medical Supply** — headroom ~1.4x, stable. → light check only.

An agent that ranks Atlantic first (bigger headline drift) or treats Hospira as compliant
because "3.59 < 3.75" fails the triage: the step-down is the whole point.

## Precedent citations expected in the S2 (breach) memo

- **PRECEDENT-2013-04 (REAL)** — Hospira itself already obtained a waiver+amendment for a §6.6
  breach: Amendment No. 1 Section 2. Strongest argument that waiver negotiation is viable.
- **PRECEDENT-2014-08 (Novaline)** — the closest analog: a missed step-down breach resolved
  via forbearance + schedule reset. Supports the recommended action.
- **PRECEDENT-2015-01 (Gulfport)** — the counterweight: late escalation / repeat breaches led
  to waiver denial and acceleration. Justifies "escalate immediately" urgency.
An S2 memo citing no precedents, or citing only positive ones without the Gulfport risk case,
is a weaker answer.

## Precedent citation expected in the S1 (false breach) trace

- **PRECEDENT-2013-09 (TriState)** — the false-positive-from-missed-addback case; the agent
  should note its own definition-first recalculation mirrors that committee protocol.

---

# v3 addendum — heterogeneous review checks (see golden_review_checks.json for exact numbers)

## Scenario S4 — Borrower certificate cross-check (2014Q2)

Input: `documents/borrower_submitted_certificate_2014Q2.pdf` (as submitted to the Agent).
Borrower claims: Adjusted EBITDA **995.0**, Leverage Ratio **3.50x**, headroom 0.253x.
Agent recomputation (same window, correct cap logic): EBITDA **965.0**, ratio **3.606x**.
Expected finding: borrower applied the full 130.0 Device Strategy addback, ignoring the
$290.0M lifetime cap (remaining capacity at window start: 100.0) — **30.0 over-added**.
Both figures are compliant vs 3.75x, so this is NOT a breach — it is a **misstated
certificate overstating headroom ~2.5x**. Expected action: notify borrower, request a
corrected certificate; cite base agreement §1.1 (Permitted Addbacks as amended) and
Amendment No. 1 §1(d). A weaker agent that only checks the claimed ratio against the
threshold ("3.50 ≤ 3.75, fine") misses the entire point of the check.

## Atlantic Beverage — second covenant (interest coverage, min 3.00x)

2015Q1: coverage **3.21x**, headroom 0.21x, fifth consecutive quarter of decline
(3.52 → 3.21). Verdict: compliant + monitoring flag. The review plan for Atlantic must now
contain TWO computation checks (leverage AND coverage) — a plan listing only leverage is
incomplete.

## Filing-deadline check (reporting obligation, 45 days)

`documents/portfolio/filing_log.csv`. For the 2015Q1 review: **Cascadia certificate received
3 days late** (due 2015-05-15, received 2015-05-18). Expected: low-severity reporting-covenant
flag with cure path; all other filings timely. A review that skips non-numeric obligations
misses this.

## Updated S0 triage expectation (review matrix)

The planner output is now a **matrix, not a list**: per borrower, the set of applicable
checks — Hospira: leverage (§6.6A, amended definitions) + addback-capacity tracker +
certificate cross-check when a borrower-submitted certificate exists; Atlantic: leverage +
interest coverage + trend flags; Cascadia: leverage (light) + filing timeliness (LATE).
Priority order unchanged (Hospira → Atlantic → Cascadia), but each line must carry its own
check list and reasons.
