"""B3: the general citation linker resolves a value to a supporting block across real-filing
PHRASINGS (numeric / ratio / money normalization), not tuned substrings. If a filing writes a
cap as "$290,000,000" or "290.0 million", or a ratio as "3.50 to 1.00" or "3.50x", the same
value must link either way — with zero per-phrasing code.
"""
import os
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import linker  # noqa: E402


def _page(doc_id, *blocks):
    return {"doc_id": doc_id, "page": 1, "doc_title": doc_id, "image": None,
            "width": 1000, "height": 1400,
            "blocks": [{"id": f"{doc_id}-{i}", "bbox": [0, 0, 900, 40], "text": t, "kind": "paragraph"}
                       for i, t in enumerate(blocks)]}


def test_value_variants_cover_money_and_ratio_phrasings():
    v = linker.value_variants(290.0)
    assert "290,000,000" in v and "$290,000,000" in v
    assert "290.0 million" in v and "290" in v
    r = linker.value_variants(3.50)
    assert "3.50 to 1.00" in v or "3.50 to 1.00" in r
    assert "3.50x" in r and "3.50:1.00" in r


def test_same_cap_links_across_two_phrasings():
    for phrasing in ("in an amount not to exceed $290,000,000 in aggregate",
                     "up to 290.0 million of non-recurring cash charges"):
        p, b = linker.find_block([_page("amendment_x", phrasing)], value=290.0)
        assert b is not None, phrasing
        assert b["text"] == phrasing


def test_ratio_links_across_two_phrasings():
    for phrasing in ("shall not exceed 3.50 to 1.00",
                     "the Leverage Ratio of 3.50x"):
        p, b = linker.find_block([_page("credit_agreement_x", phrasing)], value=3.50)
        assert b is not None, phrasing


def test_prefers_tighter_table_block():
    pages = [_page("financial_report_x",
                   "Narrative mentioning consolidated total debt of 3,480.0 somewhere in prose here",
                   "CONSOLIDATED TOTAL DEBT 3,480.0")]
    pages[0]["blocks"][1]["kind"] = "table"
    p, b = linker.find_block(pages, value=3480.0)
    assert b["kind"] == "table" and "3,480.0" in b["text"]


if __name__ == "__main__":
    test_value_variants_cover_money_and_ratio_phrasings()
    test_same_cap_links_across_two_phrasings()
    test_ratio_links_across_two_phrasings()
    test_prefers_tighter_table_block()
    print("LINKER (B3) OK — value links across money/ratio phrasings; tighter table block preferred.")
