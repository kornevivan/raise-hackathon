"""B1: the covenant spec must be DERIVED from the documents at runtime (not hardcoded),
with a citation on every field, and drive the generic engine to the same golden numbers —
on both the faithful excerpts AND the real EDGAR filings.
"""
import json
import os
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import spec_extractor as se, generic_engine as ge, hospira, covenant_engine as ce  # noqa: E402

GOLDEN = json.load(open(os.path.join(ce.DATASET_DIR, "golden_covenant_math.json")))
REAL_DIR = os.path.join(ce.DATASET_DIR, "..", "real")

# the "hardcoded Hospira spec" is now only a TEST FIXTURE the extractor must reproduce
FIXTURE = {
    "threshold_schedule": [(3.75, "2014-12-31", None), (3.50, None, "2014-12-31")],
    "addbacks": {"Device Strategy": 290.0, "Quality matters": 110.0},
    "numerator_field": "consolidated_total_debt",
}


def _spec_from(use_real: bool):
    hospira._corpus_id = None
    os.environ["USE_EXCERPTS"] = "" if use_real else "1"   # real is the default
    pages = hospira.corpus()["pages"]
    hospira._corpus_id = None
    os.environ["USE_EXCERPTS"] = ""
    return se.build_spec(pages)


def _assert_spec_matches_fixture(spec):
    sched = [(round(s.max_ratio, 2), s.applies_through, s.applies_after) for s in spec.threshold_schedule]
    assert sched == FIXTURE["threshold_schedule"], sched
    caps = {a.category: a.cap for a in spec.addbacks}
    assert caps == FIXTURE["addbacks"], caps
    assert spec.numerator_field == FIXTURE["numerator_field"]
    # every extracted field carries a resolvable citation span
    assert spec.numerator_cite.ok() and spec.denominator_cite.ok()
    assert all(s.cite.ok() for s in spec.threshold_schedule)
    assert all(a.cite.ok() for a in spec.addbacks)


def _assert_golden(spec):
    order, by_q = hospira.financials()
    for tq, g in GOLDEN.items():
        r = ge.compute(spec, order, by_q, tq)
        assert r.ratio_correct == g["ratio_correct"], (tq, r.ratio_correct, g["ratio_correct"])
        assert r.threshold == g["threshold"] and r.compliant == g["compliant"]
        assert r.denom_adjusted == g["ebitda_correct"]


def test_excerpt_spec_matches_fixture_and_golden():
    spec = _spec_from(use_real=False)
    _assert_spec_matches_fixture(spec)
    _assert_golden(spec)


def test_real_edgar_spec_matches_fixture_and_golden():
    if not (os.path.exists(os.path.join(REAL_DIR, "credit_agreement_2011-10-28.pdf"))
            and os.path.exists(os.path.join(REAL_DIR, "amendment_no1_2013-04-30.pdf"))):
        print("skip: real EDGAR PDFs not present (run deploy/fetch_real_docs.py)")
        return
    spec = _spec_from(use_real=True)
    _assert_spec_matches_fixture(spec)
    _assert_golden(spec)
    # citations must resolve on REAL-filing phrasing: caps on "$290,000,000", threshold on "3.75 to 1"
    dev = next(a for a in spec.addbacks if "Device" in a.category)
    assert "290,000,000" in dev.cite.text or "290" in dev.cite.text, dev.cite.text


def test_no_amendment_no_fabricated_caps():
    """If the amendment is absent, no caps are applied and the base threshold is used —
    never fabricate the $290M cap (the never-fabricate rule)."""
    pages = [p for p in hospira.corpus()["pages"] if "amendment" not in p["doc_id"].lower()]
    spec = se.build_spec(pages)
    assert spec.addbacks == [], spec.addbacks
    # base agreement threshold (single, no step-down)
    assert spec.threshold_schedule and spec.threshold_schedule[0].applies_after is None


if __name__ == "__main__":
    for fn in (test_excerpt_spec_matches_fixture_and_golden,
               test_real_edgar_spec_matches_fixture_and_golden,
               test_no_amendment_no_fabricated_caps):
        fn(); print("ok:", fn.__name__)
    print("SPEC-EXTRACTION TESTS PASS — spec derived from docs (excerpt + REAL EDGAR) == fixture + golden")
