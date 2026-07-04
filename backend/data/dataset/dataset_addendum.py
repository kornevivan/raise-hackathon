#!/usr/bin/env python3
"""Dataset addendum v3: heterogeneous review checks.
1) Borrower-SUBMITTED Hospira certificate for 2014Q2 with UNCAPPED addbacks (claims 3.50x) —
   fuel for the certificate cross-check scenario S4.
2) Atlantic Beverage: second covenant (minimum interest coverage >= 3.00x) on its certificates.
3) filing_log.csv: submission deadlines (45 days after quarter end); Cascadia 2015Q1 is 3 days LATE.
Deterministic, additive: does not modify existing files except Atlantic certs/profile (regenerated).
"""
import csv, json, os
from datetime import date, timedelta
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); DOCS = os.path.join(OUT, "documents")
PORT = os.path.join(DOCS, "portfolio")
S = getSampleStyleSheet()
H = ParagraphStyle("H", parent=S["Title"], fontSize=13, spaceAfter=2)
Sub = ParagraphStyle("Sub", parent=S["Normal"], fontSize=8, textColor=colors.grey)
N = ParagraphStyle("N", parent=S["Normal"], fontSize=9, leading=12)
DISC = ("SYNTHETIC DEMONSTRATION DATA - RAISE Summit Hackathon demo. Fictional; "
        "NOT actual financial results.")
GOLD = json.load(open(f"{OUT}/golden_covenant_math.json"))

def money(x): return f"{x:,.1f}"

# ---------------------------------------------------------------- 1) borrower-submitted cert (WRONG: uncapped addbacks)
def borrower_submitted_cert():
    g = GOLD["2014Q2"]
    ds_full, qc_full = g["device_charges_in_window"], g["quality_charges_in_window"]  # 130 / 40
    ebitda_claimed = round(g["ebitda_naive_no_addbacks"] + ds_full + qc_full, 1)      # 995.1
    ratio_claimed = round(g["consolidated_total_debt"] / ebitda_claimed, 3)           # 3.497
    path = f"{DOCS}/borrower_submitted_certificate_2014Q2.pdf"
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows = [["Section 6.6A computation (dollars in millions)", "Amount"],
            ["Consolidated Net Income (trailing four fiscal quarters)", money(g["sum_net_income"])],
            ["plus: Consolidated Financing Expense", money(g["sum_financing_expense"])],
            ["plus: provision for income taxes", money(g["sum_taxes"])],
            ["plus: depreciation and amortization", money(g["sum_d_and_a"])],
            ["plus: Permitted Addbacks - Device Strategy charges", money(ds_full)],
            ["plus: Permitted Addbacks - quality matters charges", money(qc_full)],
            ["CONSOLIDATED ADJUSTED EBITDA", money(ebitda_claimed)],
            ["Consolidated Total Debt as of 2014-06-30", money(g["consolidated_total_debt"])],
            ["LEVERAGE RATIO", f"{ratio_claimed:.2f}x"],
            ["Covenant maximum (Section 6.6A)", "3.75x"],
            ["Compliance", "YES"]]
    t = Table(rows, colWidths=[5.1*inch, 1.5*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(-1,0),"Helvetica-Bold",9),
        ("FONT",(0,7),(-1,7),"Helvetica-Bold",9),
        ("FONT",(0,9),(-1,-1),"Helvetica-Bold",9),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.93,0.9,0.85))]))
    doc.build([Paragraph("HOSPIRA, INC. - TREASURY DEPARTMENT", H),
        Paragraph("COMPLIANCE CERTIFICATE (as submitted to the Administrative Agent)", S["Heading4"]),
        Paragraph("Fiscal Quarter ended 2014-06-30 - Received by Agent: 2014-08-08", S["Heading4"]),
        Paragraph(DISC, Sub), Spacer(1,8), t, Spacer(1,16),
        Paragraph("The undersigned officer certifies that the computations above are true and "
                  "correct. Note 1: Permitted Addbacks reflect Device Strategy and quality-matters "
                  "cash charges incurred during the four fiscal quarters covered by this "
                  "certificate.", N)])
    return {"ebitda_claimed": ebitda_claimed, "ratio_claimed": ratio_claimed}

claim = borrower_submitted_cert()

# ---------------------------------------------------------------- 2) Atlantic: add interest-coverage covenant
ATL = "Atlantic Beverage Partners Inc"
COVERAGE = {"2014Q1":3.52,"2014Q2":3.44,"2014Q3":3.37,"2014Q4":3.29,"2015Q1":3.21}  # min 3.00
LEVERAGE = {"2014Q1":3.05,"2014Q2":3.14,"2014Q3":3.22,"2014Q4":3.31,"2015Q1":3.38}  # max 3.50
EBITDA_TTM = 400.0

def atlantic_cert(q):
    lev, cov = LEVERAGE[q], COVERAGE[q]
    debt = round(lev*EBITDA_TTM,1); interest = round(EBITDA_TTM/cov,1)
    path = f"{PORT}/certificate_atlantic_{q}.pdf"
    if os.path.exists(path): os.remove(path)
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows=[["Computation (dollars in millions)","Amount"],
          ["Consolidated EBITDA (trailing four fiscal quarters)", money(EBITDA_TTM)],
          ["Total Net Debt as of quarter end", money(debt)],
          ["TOTAL NET LEVERAGE RATIO (max 3.50x)", f"{lev:.2f}x"],
          ["Leverage headroom", f"{3.50-lev:.2f}x"],
          ["Consolidated Interest Expense (trailing four fiscal quarters)", money(interest)],
          ["INTEREST COVERAGE RATIO (min 3.00x)", f"{cov:.2f}x"],
          ["Coverage headroom", f"{cov-3.00:.2f}x"],
          ["Compliance (both covenants)", "YES" if lev<=3.50 and cov>=3.00 else "NO"]]
    t=Table(rows,colWidths=[4.8*inch,1.6*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(-1,0),"Helvetica-Bold",9),
        ("FONT",(0,3),(-1,3),"Helvetica-Bold",9),
        ("FONT",(0,6),(-1,6),"Helvetica-Bold",9),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.88,0.9,0.95))]))
    doc.build([Paragraph("COMPLIANCE CERTIFICATE", H),
               Paragraph(f"{ATL} - Fiscal Quarter ended {q}", S["Heading4"]),
               Paragraph(DISC, Sub), Spacer(1,8), t])

def atlantic_profile():
    path = f"{PORT}/profile_atlantic.pdf"
    if os.path.exists(path): os.remove(path)
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows = [["Field","Detail"],["Borrower",ATL],
            ["Facility","$1.4B term loan B + revolver, matures 2019-03; Meridian Bank as Admin Agent"],
            ["Financial covenants","(1) Total Net Leverage Ratio not to exceed 3.50x; "
             "(2) Interest Coverage Ratio (Consolidated EBITDA / Consolidated Interest Expense) "
             "of not less than 3.00x. Both tested quarterly on a trailing-four-quarter basis."],
            ["Reporting","Compliance certificate due within 45 days after each fiscal quarter end"],
            ["Amendments","None"],
            ["Portfolio notes","Leverage drifting upward and coverage drifting downward five "
             "consecutive quarters on soft volumes; no addback capacity in agreement."]]
    t = Table([[r[0],Paragraph(r[1],N)] for r in rows], colWidths=[1.4*inch,5.2*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(0,-1),"Helvetica-Bold",9),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.88,0.9,0.95)),
        ("VALIGN",(0,0),(-1,-1),"TOP")]))
    doc.build([Paragraph("BORROWER PROFILE", H), Paragraph(ATL, S["Heading3"]),
               Paragraph(DISC, Sub), Spacer(1,8), t])

atlantic_profile()
for q in COVERAGE: atlantic_cert(q)

# ---------------------------------------------------------------- 3) filing log (45-day deadline; Cascadia 2015Q1 LATE)
QEND = {"2014Q1":date(2014,3,31),"2014Q2":date(2014,6,30),"2014Q3":date(2014,9,30),
        "2014Q4":date(2014,12,31),"2015Q1":date(2015,3,31)}
def due(q): return QEND[q]+timedelta(days=45)
LOG=[]
def logrow(borrower,q,received):
    LOG.append({"borrower":borrower,"period":q,"document":"compliance_certificate",
                "due_date":due(q).isoformat(),"received_date":received.isoformat(),
                "days_late":max(0,(received-due(q)).days)})
for q in QEND:
    logrow("Hospira, Inc.",q,due(q)-timedelta(days=6))
    logrow("Atlantic Beverage Partners Inc",q,due(q)-timedelta(days=3))
    logrow("Cascadia Medical Supply Corp",q,due(q)+ (timedelta(days=3) if q=="2015Q1" else -timedelta(days=8)))
with open(f"{PORT}/filing_log.csv","w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=LOG[0].keys()); w.writeheader(); w.writerows(LOG)

# ---------------------------------------------------------------- golden addendum
golden = {
 "S4_certificate_crosscheck_2014Q2": {
   "borrower_claimed_ebitda": claim["ebitda_claimed"],
   "borrower_claimed_ratio": claim["ratio_claimed"],
   "recomputed_ebitda": GOLD["2014Q2"]["ebitda_correct"],
   "recomputed_ratio": GOLD["2014Q2"]["ratio_correct"],
   "discrepancy_cause": "borrower applied Device Strategy addback of 130.0 ignoring the 290.0 "
                        "lifetime cap (remaining capacity at window start 100.0); 30.0 over-added",
   "both_compliant": True,
   "claimed_headroom_x": round(3.75-claim["ratio_claimed"],3),
   "true_headroom_x": GOLD["2014Q2"]["headroom_x"],
   "expected_action": "notify borrower; request corrected certificate; no default event"},
 "atlantic_interest_coverage": {"covenant_min":3.00,"series":COVERAGE,
   "verdict_2015Q1":"compliant, headroom 0.21x, five-quarter downward drift -> monitoring flag"},
 "filing_compliance_2015Q1": {"deadline_days":45,
   "late":[{"borrower":"Cascadia Medical Supply Corp","days_late":3,
            "expected_action":"flag reporting covenant breach (cure: deliver certificate); "
                              "low severity but must appear in the review"}]}}
json.dump(golden, open(f"{OUT}/golden_review_checks.json","w"), indent=2)
print("addendum ok:", claim, "| filing_log rows:", len(LOG))
