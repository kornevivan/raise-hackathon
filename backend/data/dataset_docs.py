"""Faithful PDF excerpts of the two REAL Hospira credit documents (Credit Agreement
2011-10-28 and Amendment No. 1 2013-04-30). The dataset ships financial reports and
certificates but not these two governing documents (per the demo README they are
downloaded from SEC EDGAR). We render readable, citable excerpts carrying the exact
covenant mechanics (definitions, addback caps, threshold step-down, waiver), each
labeled with its SEC EDGAR source URL and a synthetic-excerpt disclaimer.

    python -m data.dataset_docs      ->  data/dataset/documents/{credit_agreement,amendment_no1}_excerpt.pdf
"""
import os

import fitz  # PyMuPDF

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset", "documents")
W, H, M = 595, 842, 56
FONT, BOLD = "helv", "hebo"

CA_URL = ("SEC EDGAR: sec.gov/Archives/edgar/data/1274057/000110465911059575/"
          "a11-28867_1ex10d1.htm")
AM_URL = ("SEC EDGAR: sec.gov/Archives/edgar/data/1274057/000127405713000013/"
          "hsp-ex1012_2013331x10q.htm")
DISCLAIMER = ("Readable excerpt of a REAL SEC-filed document, reproduced for the agent to "
              "retrieve the operative covenant mechanics. Verify against the source filing.")


def page(doc, blocks, footer):
    p = doc.new_page(width=W, height=H)
    y = M
    for kind, text in blocks:
        size = {"title": 15, "h": 11.5, "p": 10, "note": 9}.get(kind, 10)
        font = BOLD if kind in ("title", "h") else FONT
        if kind == "title":
            tw = fitz.get_text_length(text, fontname=BOLD, fontsize=size)
            p.insert_text((W / 2 - tw / 2, y + size), text, fontname=BOLD, fontsize=size)
            y += size + 12
            continue
        rect = fitz.Rect(M, y, W - M, H - M)
        left = p.insert_textbox(rect, text, fontname=font, fontsize=size, align=0, lineheight=1.3)
        used = (H - M - y) - left
        y += used + (9 if kind == "p" else 5)
    p.insert_text((M, H - 40), footer, fontname=FONT, fontsize=7.5, color=(.45, .45, .45))
    p.insert_text((M, H - 30), DISCLAIMER, fontname=FONT, fontsize=7, color=(.55, .35, .2))


def build():
    os.makedirs(OUT, exist_ok=True)

    # ---- Credit Agreement (2011-10-28) — §1.1 definitions + §6.6 covenant ----
    d = fitz.open()
    page(d, [
        ("title", "CREDIT AGREEMENT AND GUARANTY"),
        ("p", "dated as of October 28, 2011, among Hospira, Inc., as Borrower, the Lenders "
              "party hereto, and Citibank, N.A., as Administrative Agent. (Exhibit 10.1 to "
              "Form 8-K.)"),
        ("h", "Section 1.1  Defined Terms."),
        ("p", "“Consolidated Adjusted EBITDA” means, for any period of four consecutive "
              "fiscal quarters, Consolidated Net Income for such period plus, to the extent "
              "deducted in computing Consolidated Net Income, the sum of (a) Consolidated "
              "Financing Expense, (b) provision for income taxes, (c) depreciation and "
              "amortization expense, and (d) the Permitted Addbacks for such period, in each "
              "case determined for the Borrower and its Subsidiaries on a consolidated basis."),
        ("p", "“Permitted Addbacks” means the addbacks to Consolidated Net Income "
              "expressly permitted under this Agreement, as such term may be amended, "
              "supplemented or otherwise modified from time to time by any amendment hereto."),
        ("p", "“Consolidated Total Debt” means, as of any date, the aggregate principal "
              "amount of all Indebtedness of the Borrower and its Subsidiaries outstanding as of "
              "such date (determined on the last day of the fiscal quarter then ended)."),
        ("p", "“Leverage Ratio” means, as of the last day of any fiscal quarter, the "
              "ratio of Consolidated Total Debt as of such day to Consolidated Adjusted EBITDA "
              "for the period of four consecutive fiscal quarters ending on such day."),
    ], footer="Hospira, Inc. — Credit Agreement (Oct 28, 2011) — §1.1 — " + CA_URL)
    page(d, [
        ("h", "Section 6.6  Maximum Leverage Ratio."),
        ("p", "The Borrower shall not permit the Leverage Ratio, as of the last day of any fiscal "
              "quarter, to exceed 3.50 to 1.00."),
        ("p", "Compliance with this Section 6.6 shall be evidenced by a Compliance Certificate "
              "delivered pursuant to Section 5.1, setting forth in reasonable detail the "
              "computation of the Leverage Ratio and its components."),
        ("note", "Note: Section 6.6 and the definition of Permitted Addbacks were subsequently "
                 "amended and restated by Amendment No. 1, dated April 30, 2013 (see Section 1(d) "
                 "and Section 1(j) thereof, adding Section 6.6A). Any determination for a fiscal "
                 "quarter ending on or after April 30, 2013 gives effect to Amendment No. 1."),
    ], footer="Hospira, Inc. — Credit Agreement (Oct 28, 2011) — §6.6 — " + CA_URL)
    d.save(os.path.join(OUT, "credit_agreement_excerpt.pdf")); d.close()

    # ---- Amendment No. 1 (2013-04-30) — §1(d) caps, §1(j) step-down, §2 waiver ----
    d = fitz.open()
    page(d, [
        ("title", "AMENDMENT NO. 1 TO CREDIT AGREEMENT AND GUARANTY"),
        ("p", "dated as of April 30, 2013, among Hospira, Inc., the Lenders party hereto and "
              "Citibank, N.A., as Administrative Agent. (Exhibit 10.12 to Form 10-Q for the "
              "quarter ended March 31, 2013.)"),
        ("h", "Section 1(d).  Amendment to “Permitted Addbacks.”"),
        ("p", "The definition of “Permitted Addbacks” in Section 1.1 is amended and "
              "restated to permit, without duplication: (i) cash charges incurred after "
              "December 31, 2012 in connection with the Device Strategy described in the "
              "Disclosure Schedule, in an aggregate amount not to exceed $290.0 million over the "
              "life of the facility; and (ii) cash charges incurred after January 1, 2013 in "
              "connection with quality-remediation matters, in an aggregate amount not to exceed "
              "$110.0 million over the life of the facility. The addback for any period equals "
              "the lesser of the qualifying charges in such period and the remaining unused "
              "portion of the applicable lifetime cap."),
        ("h", "Section 1(j).  Addition of Section 6.6A (Amended Leverage Covenant)."),
        ("p", "A new Section 6.6A is added: The Borrower shall not permit the Leverage Ratio, as "
              "of the last day of any fiscal quarter, to exceed (a) 3.75 to 1.00 for any fiscal "
              "quarter ending on or prior to December 31, 2014; and (b) 3.50 to 1.00 for any "
              "fiscal quarter ending after December 31, 2014."),
    ], footer="Hospira, Inc. — Amendment No. 1 (Apr 30, 2013) — §1(d), §1(j)/§6.6A — " + AM_URL)
    page(d, [
        ("h", "Section 2.  Waiver."),
        ("p", "The Requisite Lenders hereby waive any Default or Event of Default arising solely "
              "from non-compliance with Section 6.6 (Maximum Leverage Ratio) for the fiscal "
              "quarter ended March 31, 2013. This waiver is limited to the specific period and "
              "provision described and shall not constitute a waiver of any other term."),
        ("note", "Disregarded Debt; Disclosure Schedule (Device Strategy) referenced in Section "
                 "1(d) are set forth in the exhibits to this Amendment."),
    ], footer="Hospira, Inc. — Amendment No. 1 (Apr 30, 2013) — §2 Waiver — " + AM_URL)
    d.save(os.path.join(OUT, "amendment_no1_excerpt.pdf")); d.close()

    print("wrote credit_agreement_excerpt.pdf and amendment_no1_excerpt.pdf to", OUT)


if __name__ == "__main__":
    build()
