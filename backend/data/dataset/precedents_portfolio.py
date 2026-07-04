#!/usr/bin/env python3
"""Precedent case-history memos + light portfolio borrowers for Covenant Sentinel demo.
Adds the 'retrieves comparable case histories' and portfolio-triage layers."""
import json, os
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PREC = os.path.join(OUT, "documents", "precedents")
PORT = os.path.join(OUT, "documents", "portfolio")
os.makedirs(PREC, exist_ok=True); os.makedirs(PORT, exist_ok=True)

S = getSampleStyleSheet()
H = ParagraphStyle("H", parent=S["Title"], fontSize=13, spaceAfter=2)
Sub = ParagraphStyle("Sub", parent=S["Normal"], fontSize=8, textColor=colors.grey)
N = ParagraphStyle("N", parent=S["Normal"], fontSize=9, leading=12)
DISC = ("SYNTHETIC DEMONSTRATION DATA - RAISE Summit Hackathon demo. Fictional unless "
        "explicitly sourced to SEC EDGAR.")

# ---------------------------------------------------------------- precedents
PRECEDENTS = [
 dict(id="PRECEDENT-2013-04", borrower="Hospira, Inc.", date="2013-04-30",
      covenant="Leverage Ratio (Section 6.6) max 3.50x", measured="3.68x (Q1 2013)",
      event="Covenant breach for the fiscal quarter ended 2013-03-31 driven by Device "
            "Strategy cash charges.",
      decision="WAIVER + AMENDMENT. Requisite Lenders waived Section 6.6 non-compliance "
               "(Amendment No. 1, Section 2) and amended the covenant: new Section 6.6A "
               "threshold 3.75x through FQ ending 2014-12-31, stepping down to 3.50x "
               "thereafter; Permitted Addbacks expanded with $290.0M Device Strategy and "
               "$110.0M quality-matters caps (Amendment No. 1, Section 1(d)).",
      outcome="Facility continued; amendment fee paid; enhanced quarterly reporting.",
      source="REAL DOCUMENT: Amendment No. 1 dated 2013-04-30, Exhibit 10.12 to Hospira Form "
             "10-Q (Q1 2013), SEC EDGAR: sec.gov/Archives/edgar/data/1274057/000127405713000013/"
             "hsp-ex1012_2013331x10q.htm",
      tags="breach, waiver, amendment, addback-caps, threshold-reset"),
 dict(id="PRECEDENT-2012-11", borrower="Lakeshore Packaging Corp.", date="2012-11-19",
      covenant="Total Net Leverage max 3.75x", measured="3.91x (Q3 2012)",
      event="Breach after debt-funded tuck-in acquisition; EBITDA contribution lagged one quarter.",
      decision="WAIVER granted for one test period. 25 bps waiver fee; pricing grid shifted +50 bps "
               "until leverage below 3.25x for two consecutive quarters.",
      outcome="Cured next quarter; pricing restored 2013Q3.",
      source="Synthetic precedent (fictional borrower).",
      tags="breach, waiver, acquisition-driven, pricing-bump"),
 dict(id="PRECEDENT-2013-09", borrower="TriState Components LLC", date="2013-09-12",
      covenant="Total Net Leverage max 3.50x", measured="reported 3.62x; corrected 3.31x",
      event="FALSE POSITIVE. Internal calculation omitted a permitted addback for restructuring "
            "charges expressly allowed by the credit agreement definition of EBITDA.",
      decision="NO BREACH. Committee required a definition-first recalculation protocol: every "
               "covenant computation must quote the operative definition and any amendments "
               "before escalation to lenders.",
      outcome="Process fix; no lender notification was ultimately required.",
      source="Synthetic precedent (fictional borrower).",
      tags="false-positive, addbacks, definition-check"),
 dict(id="PRECEDENT-2014-03", borrower="Harbor Dining Group Inc.", date="2014-03-27",
      covenant="Senior Secured Leverage max 4.00x", measured="4.18x (Q4 2013)",
      event="Breach on seasonal EBITDA trough.",
      decision="EQUITY CURE exercised per credit agreement cure rights; sponsor contributed "
               "$35.0M treated as EBITDA for the test period.",
      outcome="Compliance restored; one of two permitted cures consumed.",
      source="Synthetic precedent (fictional borrower).",
      tags="breach, equity-cure"),
 dict(id="PRECEDENT-2014-08", borrower="Novaline Chemicals Corp.", date="2014-08-21",
      covenant="Total Net Leverage: 4.00x stepping down to 3.75x after 2014-06-30", measured="3.88x (Q2 2014)",
      event="STEP-DOWN MISSED. Borrower tested against the stale 4.00x threshold; the scheduled "
            "step-down to 3.75x had taken effect, producing an unnoticed breach discovered by "
            "the agent bank.",
      decision="FORBEARANCE 60 days, then amendment resetting the step-down schedule; 40 bps fee; "
               "covenant headroom reporting added to compliance certificate.",
      outcome="Resolved; relationship strain noted by committee.",
      source="Synthetic precedent (fictional borrower).",
      tags="breach, step-down-trap, forbearance, amendment"),
 dict(id="PRECEDENT-2013-06", borrower="Redwood Fitness Holdings", date="2013-06-10",
      covenant="Total Net Leverage max 3.50x", measured="3.41x (Q1 2013)",
      event="THIN HEADROOM (<0.15x) two consecutive quarters; no breach.",
      decision="ENHANCED MONITORING: monthly management accounts, 13-week cash flow, covenant "
               "projection two quarters forward at each test date.",
      outcome="Deleveraged below 3.0x by 2014Q1; monitoring lifted.",
      source="Synthetic precedent (fictional borrower).",
      tags="thin-headroom, monitoring, no-breach"),
 dict(id="PRECEDENT-2015-01", borrower="Gulfport Marine Services Inc.", date="2015-01-15",
      covenant="Total Net Leverage max 3.50x", measured="4.35x (Q4 2014)",
      event="Breach with deteriorating liquidity; second breach in four quarters.",
      decision="WAIVER DECLINED by lender group. Default declared; facility accelerated; "
              "restructuring advisors engaged.",
      outcome="Negative precedent: late escalation and repeat breaches reduce waiver likelihood.",
      source="Synthetic precedent (fictional borrower).",
      tags="breach, waiver-declined, default"),
]

def memo_pdf(p):
    path = f"{PREC}/{p['id']}.pdf"
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows = [["Field", "Detail"],
            ["Borrower", p["borrower"]], ["Committee date", p["date"]],
            ["Covenant", p["covenant"]], ["Measured level", p["measured"]],
            ["Event", p["event"]], ["Committee decision", p["decision"]],
            ["Outcome", p["outcome"]], ["Source", p["source"]], ["Tags", p["tags"]]]
    t = Table([[r[0], Paragraph(r[1], N)] for r in rows], colWidths=[1.4*inch, 5.2*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(0,-1),"Helvetica-Bold",9),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.88,0.9,0.95)),
        ("VALIGN",(0,0),(-1,-1),"TOP")]))
    doc.build([Paragraph("CREDIT COMMITTEE MEMORANDUM - COVENANT EVENT RECORD", H),
               Paragraph(f"Case ID: {p['id']}", S["Heading4"]), Paragraph(DISC, Sub),
               Spacer(1,8), t])

for p in PRECEDENTS: memo_pdf(p)
json.dump(PRECEDENTS, open(f"{PREC}/precedents_index.json","w"), indent=2)

# ---------------------------------------------------------------- portfolio
BORROWERS = {
 "Cascadia Medical Supply Corp": dict(
    facility="$900M revolving credit facility, matures 2018-06; First National Bank as Admin Agent",
    covenant_max=3.50, step_down=None,
    ratios={"2014Q1":2.18,"2014Q2":2.11,"2014Q3":2.05,"2014Q4":2.09,"2015Q1":2.14},
    notes="Stable distributor; no one-time charges; no amendments."),
 "Atlantic Beverage Partners Inc": dict(
    facility="$1.4B term loan B + revolver, matures 2019-03; Meridian Bank as Admin Agent",
    covenant_max=3.50, step_down=None,
    ratios={"2014Q1":3.05,"2014Q2":3.14,"2014Q3":3.22,"2014Q4":3.31,"2015Q1":3.38},
    notes="Leverage drifting upward five consecutive quarters on soft volumes; "
          "no amendments; no addback capacity in agreement."),
}

def borrower_profile(name, b):
    path = f"{PORT}/profile_{name.split()[0].lower()}.pdf"
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows = [["Field","Detail"],["Borrower",name],["Facility",b["facility"]],
            ["Financial covenant", f"Total Net Leverage Ratio not to exceed {b['covenant_max']:.2f}x, "
             "tested quarterly on a trailing-four-quarter basis"],
            ["Amendments","None"],["Portfolio notes", b["notes"]]]
    t = Table([[r[0],Paragraph(r[1],N)] for r in rows], colWidths=[1.4*inch,5.2*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(0,-1),"Helvetica-Bold",9),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.88,0.9,0.95)),
        ("VALIGN",(0,0),(-1,-1),"TOP")]))
    doc.build([Paragraph("BORROWER PROFILE", H), Paragraph(name, S["Heading3"]),
               Paragraph(DISC, Sub), Spacer(1,8), t])

def borrower_cert(name, b, q):
    ratio = b["ratios"][q]; ebitda = 400.0
    debt = round(ratio*ebitda,1)
    path = f"{PORT}/certificate_{name.split()[0].lower()}_{q}.pdf"
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    rows=[["Computation (dollars in millions)","Amount"],
          ["Consolidated EBITDA (trailing four fiscal quarters)", f"{ebitda:,.1f}"],
          ["Total Net Debt as of quarter end", f"{debt:,.1f}"],
          ["TOTAL NET LEVERAGE RATIO", f"{ratio:.2f}x"],
          ["Covenant maximum", f"{b['covenant_max']:.2f}x"],
          ["Headroom", f"{b['covenant_max']-ratio:.2f}x"],
          ["Compliance", "YES" if ratio<=b["covenant_max"] else "NO"]]
    t=Table(rows,colWidths=[4.8*inch,1.6*inch])
    t.setStyle(TableStyle([("FONT",(0,0),(-1,-1),"Helvetica",9),
        ("FONT",(0,0),(-1,0),"Helvetica-Bold",9),
        ("FONT",(0,3),(-1,3),"Helvetica-Bold",9),
        ("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("GRID",(0,0),(-1,-1),0.4,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.Color(0.88,0.9,0.95))]))
    doc.build([Paragraph("COMPLIANCE CERTIFICATE", H),
               Paragraph(f"{name} - Fiscal Quarter ended {q}", S["Heading4"]),
               Paragraph(DISC, Sub), Spacer(1,8), t])

for name,b in BORROWERS.items():
    borrower_profile(name,b)
    for q in b["ratios"]: borrower_cert(name,b,q)

json.dump({"portfolio":["Hospira, Inc."]+list(BORROWERS),
           "borrower_data":BORROWERS}, open(f"{PORT}/portfolio_index.json","w"), indent=2)
print("precedents:", len(os.listdir(PREC)), "| portfolio:", len(os.listdir(PORT)))
