"""The PROD upload path, on real documents only (no tool store), must DERIVE the covenant spec
from the agreement/amendment, EXTRACT the per-quarter figures from the reports, and run the SAME
engine as the deep scenarios — reaching the same verdict. Proves 'scenario = prod + pre-filled
inputs': given the borrower's documents in a blank chat, the agent computes the covenant itself.
"""
import os
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""      # deterministic / offline
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import ingest, orchestrator_adhoc, hospira, spec_extractor, fin_extract  # noqa: E402
from app import generic_engine, covenant_engine as ce  # noqa: E402

DOCS = os.path.join(ce.DATASET_DIR, "documents")
QUARTERS = ["2013Q1", "2013Q2", "2013Q3", "2013Q4", "2014Q1", "2014Q2", "2014Q3", "2014Q4", "2015Q1"]


def _upload(paths):
    files = [(os.path.basename(p), open(p, "rb").read()) for p in paths if os.path.exists(p)]
    return ingest.UPLOADS[ingest.ingest(files)["upload_id"]]


def _hospira_docs():
    return ([hospira.resolve_doc("credit_agreement_excerpt.pdf"),
             hospira.resolve_doc("amendment_no1_excerpt.pdf")]
            + [os.path.join(DOCS, f"financial_report_{q}.pdf") for q in QUARTERS])


def test_extracted_figures_match_the_store():
    """fin_extract from the DOCUMENTS reproduces the tool-store figures for every quarter."""
    up = _upload(_hospira_docs())
    spec = spec_extractor.build_spec(up["pages"])
    order, by_q = fin_extract.extract_financials(up["pages"], spec)
    _, gby = hospira.financials()
    fields = ["consolidated_total_debt", "net_income", "financing_expense", "income_tax_expense",
              "depreciation_amortization", "device_strategy_cash_charges", "quality_matters_cash_charges"]
    assert set(order) == set(QUARTERS), order
    for q in order:
        assert by_q[q]["period_end"] == gby[q]["period_end"]
        for f in fields:
            if gby[q].get(f) is not None:
                assert abs(by_q[q].get(f, 1e9) - gby[q][f]) < 0.05, (q, f, by_q[q].get(f), gby[q][f])


def test_upload_path_computes_covenant_from_documents():
    """The upload orchestrator itself reaches the deep result (2015Q1 breach 3.615x) from docs."""
    up = _upload(_hospira_docs())
    memo = next(e["payload"] for e in orchestrator_adhoc.run_upload(up) if e["kind"] == "memo")
    assert memo["recommendation"] == "breach", memo["recommendation"]
    assert memo["ratio_final"] == 3.615 and memo["threshold"] == 3.5, memo
    # same number the deep/store pipeline produces
    spec = spec_extractor.build_spec(up["pages"])
    order, by_q = fin_extract.extract_financials(up["pages"], spec)
    g = generic_engine.compute(spec, *hospira.financials(), "2015Q1")
    assert memo["ratio_final"] == g.ratio_correct


def test_upload_still_handles_single_period_fallback():
    """A single-period 'reported EBITDA' doc (no quarterly reports) still works via the fallback,
    and a referenced-but-absent amendment is NOT fabricated into an addback."""
    body = (b"Consolidated EBITDA means net income plus interest, taxes and D&A, as amended by "
            b"Amendment No. 1. Section 6.6 threshold to be greater than 3.50 to 1.00. "
            b"Consolidated Total Net Debt 420.0. Consolidated EBITDA (as reported) 118.3.")
    up = ingest.UPLOADS[ingest.ingest([("agreement_note.txt", body)])["upload_id"]]
    memo = next(e["payload"] for e in orchestrator_adhoc.run_upload(up) if e["kind"] == "memo")
    assert memo["recommendation"] != "false_positive"
    assert memo["ratio_final"] == memo["ratio_naive"]


if __name__ == "__main__":
    test_extracted_figures_match_the_store()
    test_upload_path_computes_covenant_from_documents()
    test_upload_still_handles_single_period_fallback()
    print("UPLOAD-DERIVED OK — prod path computes the covenant from documents (== deep result); "
          "single-period fallback intact.")
