# Covenant Sentinel — Demo Dataset (Hospira)

Hybrid dataset: **two REAL credit documents from SEC EDGAR** + an internally consistent
**synthetic financial package** calibrated to those documents' exact covenant mechanics.

## 1. Real documents — download these yourself and ingest them into the agent

| Doc | What it gives the agent | URL |
|---|---|---|
| Credit Agreement and Guaranty, dated 2011-10-28 (Hospira, Inc.; Citibank N.A. as Admin Agent) — Exhibit 10.1 to Form 8-K | §1.1 definitions: Leverage Ratio, Consolidated Adjusted EBITDA, Consolidated Total Debt, original Permitted Addbacks; §6.6 original covenant (3.50x); Compliance Certificate mechanics | https://www.sec.gov/Archives/edgar/data/1274057/000110465911059575/a11-28867_1ex10d1.htm |
| Amendment No. 1, dated 2013-04-30 — Exhibit 10.12 to Form 10-Q (Q1 2013) | §1(d) AMENDED Permitted Addbacks with the $290M / $110M caps; §1(j) AMENDED §6.6A threshold schedule 3.75x -> 3.50x step-down after 2014-12-31; Disregarded Debt concept; Disclosure Schedule describing the Device Strategy | https://www.sec.gov/Archives/edgar/data/1274057/000127405713000013/hsp-ex1012_2013331x10q.htm |
| (context, optional) Form 8-K announcing the facility | plain-English summary of the covenant | https://www.sec.gov/Archives/edgar/data/0001274057/000110465911059575/a11-28867_18k.htm |

Tip: save each as PDF (print-to-PDF) so the page-level retriever indexes real layouts.

## 2. Synthetic package (this folder) — clearly labeled fictional numbers

- documents/financial_report_<Q>.pdf — 9 quarters (2013Q1..2015Q1), table-heavy: income
  statement with one-time charge lines + Consolidated Total Debt schedule.
- documents/compliance_certificate_<Q>.pdf — prior-quarter officer certificates with the
  full §6.6A computation (great retrieval fodder and a source of the "stale threshold" trap).
- documents/compliance_certificate_2014Q4_SCANNED.pdf — the same certificate as a skewed,
  noisy office scan. Use it in the S2 run: the agent must read a table from a messy page.
- transactions.csv — ~600 ledger rows ($ thousands); per-quarter sums reconcile EXACTLY to
  the statements (revenue, device_strategy, quality_matters categories verified by generator).
  The S1 cause is buried here: 2014-05-19 revolver draw $460.0M "Meridian Infusion Assets acquisition".
- financials_quarterly.json — machine-readable statements (for your tools / financials_query).
- golden_covenant_math.json + golden_answers.md — ground truth for all runnable quarters.

Every PDF carries the footer: "SYNTHETIC DEMONSTRATION DATA ... NOT the actual financial
results of Hospira, Inc." Keep that disclaimer in your repo README too.

## 3. Scenario map

- S3 all-clear-with-a-warning ......... run as of 2014Q1 (correct 3.066x vs 3.75x)
- S1 false breach + capped addback .... run as of 2014Q2 (naive 4.218x -> correct 3.606x)  <- primary demo
- S2 step-down trap, real breach ...... run as of 2015Q1 (3.615x vs amended 3.50x)

## 4. Regeneration

python3 generate.py && python3 render_pdfs.py && python3 precedents_portfolio.py   (seeded; deterministic; commit both scripts)

## 5. Precedents & portfolio layers (v2)

- documents/precedents/ — 7 credit-committee memos (case histories) + precedents_index.json.
  PRECEDENT-2013-04 is anchored to the REAL waiver in Amendment No. 1, Section 2.
- documents/portfolio/ — 2 additional light borrowers (profile + 5 quarterly certificates each)
  + portfolio_index.json. Enables the S0 portfolio-triage scenario (see golden_answers.md):
  start runs with "quarter closed - review the portfolio", not "check Hospira".
