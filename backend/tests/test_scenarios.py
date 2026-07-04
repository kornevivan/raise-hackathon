"""Scenario + trace-assertion + leakage-guard tests (dataset guide §3.1/3.2/3.4).

Runs the full agent pipeline offline (deterministic; same event structure as live)
and asserts golden outcomes AND agentic behavior (the trace), plus the no-`golden`
ingest guard. CI-runnable.

    cd backend && python -m tests.test_scenarios      (or pytest -q)
"""
import json
import os
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""   # force deterministic offline for CI
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import covenant_engine as ce           # noqa: E402
from app import orchestrator_hospira as oh       # noqa: E402
from app import orchestrator_triage as tr        # noqa: E402
from app import hospira, precedents              # noqa: E402

REVIEW = json.load(open(os.path.join(ce.DATASET_DIR, "golden_review_checks.json")))


def _run(scenario):
    return list(oh.run_scenario(scenario))


def test_s4_certificate_crosscheck():
    memo = next(e["payload"] for e in _run(oh.SCENARIOS["S4"]) if e["kind"] == "memo")
    cc, g = memo["crosscheck"], REVIEW["S4_certificate_crosscheck_2014Q2"]
    assert cc["claimed_ebitda"] == g["borrower_claimed_ebitda"]
    assert cc["claimed_ratio"] == g["borrower_claimed_ratio"]      # 3.497
    assert cc["recomputed_ebitda"] == g["recomputed_ebitda"]      # 965.0
    assert cc["recomputed_ratio"] == g["recomputed_ratio"]        # 3.606
    assert cc["over_added"] == 30.0 and cc["both_compliant"] is True
    assert memo["recommendation"] == "misstated_certificate"


def test_s1_trace_assertions():
    """The S1 trace must show real agentic behavior in order (guide §3.2 a–e)."""
    evs = _run(oh.SCENARIOS["S1"])
    order, seen = [], {}
    for e in evs:
        p = e.get("payload", {})
        if e["kind"] == "retrieve" and any("credit_agreement" in h["doc_id"] for h in p.get("hits", [])):
            seen["a_base_def"] = seen.get("a_base_def") or len(order); order.append("a")
        if e["kind"] == "gap" and "amendment" in (p.get("gap", {}).get("reason", "").lower()
                                                  + str(p.get("gap", {}).get("missing_document", "")).lower()):
            seen["b_gap"] = len(order); order.append("b")
        if e["kind"] == "retrieve" and any("amendment" in h["doc_id"] for h in p.get("hits", [])):
            seen["c_amendment"] = len(order); order.append("c")
        if e["kind"] == "tool" and p.get("tool") == "ratio_calculator" \
                and any("min(130.0, 100.0)" in s for s in p.get("result", {}).get("steps", [])):
            seen["d_mincalc"] = len(order); order.append("d")
        if e["kind"] == "tool" and p.get("tool") == "transactions_query" \
                and any("2014-05-19" in r["date"] and r["amount_usd_millions"] == 460.0
                        for r in p.get("result", {}).get("rows", [])):
            seen["e_txn"] = len(order); order.append("e")
    for k in ("a_base_def", "b_gap", "c_amendment", "d_mincalc", "e_txn"):
        assert k in seen, f"S1 trace missing {k}: got {order}"
    assert seen["a_base_def"] < seen["b_gap"] < seen["c_amendment"], f"out of order: {order}"


def test_s0_scanned_thumbnail():
    evs = list(tr.run_triage())
    scanned = any(e["kind"] == "retrieve" and any("SCANNED" in h["doc_id"] for h in e["payload"].get("hits", []))
                  for e in evs)
    assert scanned, "S0 triage must surface the SCANNED certificate thumbnail"
    memo = next(e["payload"] for e in evs if e["kind"] == "memo")
    assert memo["ranking"][0]["borrower"] == "Hospira, Inc."
    # review matrix: each borrower carries its own checks
    assert all(len(r.get("checks", [])) >= 2 for r in memo["ranking"])


def test_live_doc_set_is_real_no_excerpts():
    """A0-A1: the live deep corpus indexes the REAL EDGAR PDFs (no `_excerpt`) and all 9
    financial reports; the clean 2014Q4 certificate is excluded."""
    os.environ["USE_EXCERPTS"] = ""
    hospira._corpus_id = None
    docs = [d["doc_id"] for d in hospira.corpus()["documents"]]
    assert any("2011_10_28" in d for d in docs), "real credit agreement not indexed"
    assert any("2013_04_30" in d for d in docs), "real amendment not indexed"
    assert not any("excerpt" in d for d in docs), f"_excerpt in live index: {docs}"
    assert sum("financial_report" in d for d in docs) == 9, "need all 9 financial reports"
    assert not any(d == "compliance_certificate_2014Q4" for d in docs), "clean 2014Q4 must be excluded"


def test_no_golden_leakage_in_ingest():
    """CI guard: no ingested document may reference a golden file (guide §2)."""
    for entry in (hospira.corpus(), tr._corpus(), precedents._corpus()):
        for d in entry["documents"]:
            assert "golden" not in d["doc_id"].lower() and "golden" not in d["title"].lower(), d


def test_atlantic_coverage_and_filing():
    cov = hospira.interest_coverage_from_cert("atlantic", "2015Q1")
    assert cov["ok"] and cov["coverage"] == 3.21 and cov["min"] == 3.0
    late = hospira.filing_query("2015Q1")["late"]
    assert len(late) == 1 and late[0]["borrower"].startswith("Cascadia") and late[0]["days_late"] == 3


def test_negative_only_agreement_no_financials():
    """Upload path, no financial figures present → honest 'insufficient data', no invented
    numbers (guide §3.4.2)."""
    from app import ingest, orchestrator_adhoc
    docs = os.path.join(ce.DATASET_DIR, "documents")
    files = [("credit_agreement_excerpt.pdf", open(os.path.join(docs, "credit_agreement_excerpt.pdf"), "rb").read())]
    up = ingest.UPLOADS[ingest.ingest(files, collection=None)["upload_id"]]
    memo = next(e["payload"] for e in orchestrator_adhoc.run_upload(up) if e["kind"] == "memo")
    assert memo["recommendation"] == "insufficient_data", memo["recommendation"]
    assert memo["ratio_final"] is None


def test_negative_amendment_referenced_but_absent():
    """Upload agreement+financials that REFERENCE an amendment, without the amendment itself →
    the agent must not fabricate the $290M cap / apply an addback it cannot cite (guide §3.4.1)."""
    from app import ingest, orchestrator_adhoc
    # a synthetic doc that mentions Amendment No. 1 but doesn't provide its terms, plus figures
    body = (b"Consolidated EBITDA means net income plus interest, taxes and D&A, as amended by "
            b"Amendment No. 1. Section 6.6 threshold to be greater than 3.50 to 1.00. "
            b"Consolidated Total Net Debt 420.0. Consolidated EBITDA (as reported) 118.3.")
    up = ingest.UPLOADS[ingest.ingest([("agreement_note.txt", body)])["upload_id"]]
    evs = list(orchestrator_adhoc.run_upload(up))
    memo = next(e["payload"] for e in evs if e["kind"] == "memo")
    # no addback fabricated → the naive ratio stands (not a false-positive with an invented cap)
    assert memo["recommendation"] != "false_positive", memo["recommendation"]
    assert memo["ratio_final"] == memo["ratio_naive"], (memo["ratio_naive"], memo["ratio_final"])


if __name__ == "__main__":
    for fn in (test_s4_certificate_crosscheck, test_s1_trace_assertions, test_s0_scanned_thumbnail,
               test_no_golden_leakage_in_ingest, test_atlantic_coverage_and_filing,
               test_negative_only_agreement_no_financials, test_negative_amendment_referenced_but_absent):
        fn(); print("ok:", fn.__name__)
    print("SCENARIO + TRACE + GUARD + NEGATIVE TESTS PASS")
