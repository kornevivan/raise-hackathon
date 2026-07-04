"""P1-C: the gap-check instrument trigger must be general, not keyed to a literal
document name. It must fire on ordinal amendments, amended-and-restated agreements,
waivers, supplements and forbearances — and NOT on covenant text with no instrument.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gapcheck import detect_instrument  # noqa: E402

POSITIVE = {
    "Amendment No. 1": "as amended by Amendment No. 1, dated April 30, 2013",
    "Second Amendment": "modified pursuant to the Second Amendment to the Credit Agreement",
    "Third Amendment": "see the Third Amendment for the revised schedule",
    "Amended and Restated": "the Amended and Restated Credit Agreement supersedes the prior terms",
    "Waiver": "the Requisite Lenders granted a Waiver of the Section 6.6 breach",
    "Forbearance": "subject to the Forbearance Agreement dated 2014",
    "2014 amendment": "as further adjusted by the 2014 Amendment then in effect",
}
NEGATIVE = [
    "The Borrower shall not permit the Leverage Ratio to exceed 3.50 to 1.00.",
    "Consolidated Adjusted EBITDA means net income plus financing expense, taxes and D&A.",
    "",
]


def test_positive_phrasings():
    for label, text in POSITIVE.items():
        got = detect_instrument(text)
        assert got, f"expected an instrument for {label!r}: {text!r} -> {got!r}"


def test_negative_phrasings():
    for text in NEGATIVE:
        assert detect_instrument(text) is None, f"false positive on {text!r}"


if __name__ == "__main__":
    test_positive_phrasings()
    test_negative_phrasings()
    for label, text in POSITIVE.items():
        print(f"  {label:22s} -> {detect_instrument(text)!r}")
    print("GAP-CHECK OK — general instrument trigger fires on all phrasings, no false positives.")
