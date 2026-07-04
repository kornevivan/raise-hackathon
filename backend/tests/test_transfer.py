"""Transfer test (acceptance): the SAME spec_extractor → generic_engine pipeline must work on a
THIRD-PARTY agreement not from this dataset, with ZERO code changes — producing a cited spec, or
an honest gap when the covenant isn't stated. Proves the rules are derived, not Hospira-specific.
"""
import os
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import spec_extractor as se, generic_engine as ge  # noqa: E402


def _page(doc_id, text):
    return {"doc_id": doc_id, "page": 1, "text": text, "width": 1000, "height": 1400,
            "image": None, "blocks": [{"id": f"{doc_id}-b1", "bbox": [0, 0, 900, 40],
                                       "text": text[:120], "kind": "paragraph"}]}


def test_transfer_third_party_agreement_yields_cited_spec():
    # a fictional, non-Hospira credit agreement with an explicit leverage covenant + amendment cap
    pages = [
        _page("acme_holdings_credit_agreement",
              "“Consolidated Adjusted EBITDA” means Consolidated Net Income plus Financing Expense, "
              "provision for income taxes, depreciation and amortization, and Permitted Addbacks. "
              "“Consolidated Total Debt” means all Indebtedness. Section 6.10 The Borrower shall not "
              "permit the Leverage Ratio to exceed 4.00 to 1.00."),
        _page("acme_first_amendment",
              "Section 1(d): Permitted Addbacks include restructuring cash charges incurred after "
              "January 1, 2020, in an aggregate amount not to exceed $150,000,000 in connection with "
              "the Restructuring Program. Section 1(j): the Leverage Ratio shall not exceed 4.00 to 1 "
              "through December 31, 2021 and 3.75 to 1 thereafter."),
    ]
    spec = se.build_spec(pages)
    assert spec.is_complete(), spec.gaps
    thr, cite = spec.threshold_for("2020-06-30")
    assert thr == 4.00 and cite.ok(), (thr, cite)
    thr2, _ = spec.threshold_for("2022-06-30")
    assert thr2 == 3.75, thr2                      # step-down derived from the amendment
    assert spec.numerator_cite.ok() and spec.denominator_cite.ok()
    caps = {a.cap for a in spec.addbacks}
    assert 150.0 in caps, caps                     # $150,000,000 cap extracted + cited
    assert all(a.cite.ok() for a in spec.addbacks)


def test_transfer_missing_threshold_reports_gap():
    pages = [_page("mystery_agreement",
                   "This is a services agreement with confidentiality and indemnity clauses. It "
                   "states no financial covenant, no leverage ratio, and no threshold.")]
    spec = se.build_spec(pages)
    assert not spec.is_complete() or not spec.threshold_schedule
    assert any("threshold" in g.lower() for g in spec.gaps), spec.gaps
    # and the engine degrades honestly (no fabricated threshold) — verdict cannot be concluded
    by_q = {"2020Q2": {"period_end": "2020-06-30", "consolidated_total_debt": 1000.0,
                       "net_income": 50, "financing_expense": 10, "income_tax_expense": 10,
                       "depreciation_amortization": 30}}
    # not enough quarters here — the point is: no threshold ⇒ compliant is None (cannot conclude)
    r = ge.compute(spec, ["2020Q2"], by_q, "2020Q2")
    assert r.threshold is None and r.compliant is None


if __name__ == "__main__":
    test_transfer_third_party_agreement_yields_cited_spec()
    test_transfer_missing_threshold_reports_gap()
    print("TRANSFER OK — same pipeline derives a cited spec from a third-party agreement, or an "
          "honest gap; zero code changes.")
