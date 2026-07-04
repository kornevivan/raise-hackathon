"""Generate text-based sample PDFs (real text layer) so the *upload* flow can be
demoed end-to-end: uploading these reproduces the S1 amendment twist. Any real
credit agreement / financials PDF works too — these are just a ready sample.

    python make_pdfs.py     ->  data/samples/*.pdf
"""
import os

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "samples")
W, H, MARGIN = 595, 842, 56  # A4 points

FONT, BOLD = "helv", "hebo"


def page(doc, blocks, footer=None):
    p = doc.new_page(width=W, height=H)
    y = MARGIN
    for kind, text in blocks:
        size = {"title": 17, "h": 12.5, "p": 10.5, "row": 10.5}.get(kind, 10.5)
        font = BOLD if kind in ("title", "h", "row") else FONT
        if kind == "title":
            tw = fitz.get_text_length(text, fontname=BOLD, fontsize=size)
            p.insert_text((W / 2 - tw / 2, y + size), text, fontname=BOLD, fontsize=size)
            y += size + 12
            continue
        rect = fitz.Rect(MARGIN, y, W - MARGIN, H - MARGIN)
        leftover = p.insert_textbox(rect, text, fontname=font, fontsize=size,
                                    align=0, lineheight=1.25)
        used = (H - MARGIN - y) - leftover
        y += used + (10 if kind == "p" else 6)
    if footer:
        p.insert_text((MARGIN, H - 34), footer, fontname=FONT, fontsize=8, color=(.5, .5, .5))


def build():
    os.makedirs(OUT, exist_ok=True)

    # 1) Credit Agreement
    d = fitz.open()
    page(d, [
        ("title", "CREDIT AGREEMENT"),
        ("p", "dated as of March 14, 2023, among Meridian Logistics Holdings, Inc., as "
              "Borrower, the Lenders party hereto, and First Continental Bank, N.A., as "
              "Administrative Agent."),
        ("h", "ARTICLE I - DEFINITIONS"),
        ("p", "“Consolidated EBITDA” means, for any period, Consolidated Net Income for "
              "such period plus, without duplication and to the extent deducted in computing "
              "such Consolidated Net Income, the sum of (a) Consolidated Interest Expense, "
              "(b) provision for income taxes, (c) depreciation and amortization expense, and "
              "(d) other non-cash charges, in each case for such period, all as further adjusted "
              "pursuant to any amendment to this Agreement then in effect."),
        ("p", "“Consolidated Total Net Debt” means, as of any date, the aggregate principal "
              "amount of all Indebtedness of the Borrower and its Restricted Subsidiaries "
              "(including the Term Loans, Revolving Loans and Finance Lease Obligations) less "
              "unrestricted Cash and Cash Equivalents as of such date."),
        ("p", "“Total Net Leverage Ratio” means, as of any Test Date, the ratio of "
              "Consolidated Total Net Debt as of such date to Consolidated EBITDA for the most "
              "recently ended period of four consecutive fiscal quarters (LTM)."),
    ], footer="Meridian Logistics - Credit Agreement - Page 1")
    page(d, [
        ("h", "ARTICLE VI - FINANCIAL COVENANTS"),
        ("h", "Section 6.10  Maximum Total Net Leverage Ratio."),
        ("p", "The Borrower shall not permit the Total Net Leverage Ratio, determined as of the "
              "last day of any fiscal quarter (each a “Test Date”), to be greater than 3.50 to "
              "1.00."),
        ("p", "Compliance with this Section 6.10 shall be tested quarterly and evidenced by a "
              "Compliance Certificate setting forth in reasonable detail the calculation of the "
              "Total Net Leverage Ratio, including each component of Consolidated EBITDA and "
              "Consolidated Total Net Debt."),
        ("p", "Note: The definition of Consolidated EBITDA set forth in Article I has been "
              "amended. See Amendment No. 1 to this Credit Agreement, dated October 3, 2025, "
              "which modifies clause (d) of such definition. Any calculation of the Total Net "
              "Leverage Ratio for a Test Date occurring on or after October 3, 2025 shall give "
              "effect to Amendment No. 1."),
    ], footer="Meridian Logistics - Credit Agreement - Page 2")
    d.save(os.path.join(OUT, "01_Credit_Agreement.pdf")); d.close()

    # 2) Amendment No. 1
    d = fitz.open()
    page(d, [
        ("title", "AMENDMENT NO. 1 TO THE CREDIT AGREEMENT"),
        ("p", "This AMENDMENT NO. 1, dated as of October 3, 2025, amends the Credit Agreement "
              "dated as of March 14, 2023 among Meridian Logistics Holdings, Inc., the Lenders "
              "party thereto and First Continental Bank, N.A., as Administrative Agent."),
        ("h", "Section 1.  Amendment to Definition of Consolidated EBITDA."),
        ("p", "Clause (d) of the definition of “Consolidated EBITDA” in Article I is hereby "
              "amended and restated to read as follows:"),
        ("p", "“(d) other non-cash charges, PLUS, to the extent deducted in computing "
              "Consolidated Net Income, one-time fees, costs and expenses incurred in connection "
              "with any Permitted Acquisition consummated during such period (including legal, "
              "advisory, due diligence and integration costs), in an aggregate amount not to "
              "exceed $10,000,000 for any period of four consecutive fiscal quarters.”"),
        ("h", "Section 2.  Effectiveness."),
        ("p", "This Amendment shall be effective as of October 3, 2025 and shall apply to the "
              "determination of the Total Net Leverage Ratio for each Test Date occurring on or "
              "after such date, including the fiscal quarter ending December 31, 2025."),
    ], footer="Meridian Logistics - Amendment No. 1 - Page 1")
    d.save(os.path.join(OUT, "02_Amendment_No_1.pdf")); d.close()

    # 3) Financial statements (LTM Q4-2025)
    d = fitz.open()
    page(d, [
        ("title", "MERIDIAN LOGISTICS - CONSOLIDATED FINANCIAL STATEMENTS"),
        ("h", "Consolidated Income Statement - Q4-2025 (LTM, USD in millions)"),
        ("row", "Total Revenue                                     612.4"),
        ("row", "Consolidated Net Income                            41.0"),
        ("row", "  plus Consolidated Interest Expense               28.5"),
        ("row", "  plus Provision for Income Taxes                  12.8"),
        ("row", "  plus Depreciation & Amortization                 36.0"),
        ("row", "Consolidated EBITDA (as reported)                118.3"),
        ("p", "Footnote 4: SG&A for the period includes $4.5 million of one-time fees and "
              "expenses incurred in connection with the Project Atlas acquisition (legal, "
              "advisory, due diligence and integration). These charges are potentially "
              "addback-eligible - see Amendment No. 1."),
    ], footer="Meridian Logistics - Financial Statements - Page 1")
    page(d, [
        ("h", "Debt Schedule & Net Debt Reconciliation - Q4-2025 (USD in millions)"),
        ("row", "Senior Term Loan                                 300.0"),
        ("row", "Revolving Facility (drawn)                        120.0"),
        ("row", "Finance Lease Obligations                         32.0"),
        ("row", "Total Indebtedness                               452.0"),
        ("row", "Less: Cash & Cash Equivalents                    (32.0)"),
        ("row", "Consolidated Total Net Debt                      420.0"),
    ], footer="Meridian Logistics - Financial Statements - Page 2")
    d.save(os.path.join(OUT, "03_Financial_Statements_Q4-2025.pdf")); d.close()

    print("Wrote sample PDFs to", OUT)
    for f in sorted(os.listdir(OUT)):
        print("  ", f)


if __name__ == "__main__":
    build()
