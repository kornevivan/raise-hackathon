#!/usr/bin/env python3
"""Render synthetic financial packages as table-heavy PDFs + one 'scanned' certificate."""
import json, os, io, random
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

random.seed(7)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out"); DOCS = os.path.join(OUT, "documents")
os.makedirs(DOCS, exist_ok=True)
FIN = {f["quarter"]: f for f in json.load(open(f"{OUT}/financials_quarterly.json"))}
GOLD = json.load(open(f"{OUT}/golden_covenant_math.json"))

S = getSampleStyleSheet()
H = ParagraphStyle("H", parent=S["Title"], fontSize=14, spaceAfter=4)
Sub = ParagraphStyle("Sub", parent=S["Normal"], fontSize=8.5, textColor=colors.grey)
Note = ParagraphStyle("N", parent=S["Normal"], fontSize=8)
DISCLAIMER = ("SYNTHETIC DEMONSTRATION DATA - prepared for the RAISE Summit Hackathon demo. "
              "Figures are fictional and are NOT the actual financial results of Hospira, Inc.")

def money(x): return f"({abs(x):,.1f})" if x < 0 else f"{x:,.1f}"

def qtr_label(q): return f"Q{q[-1]} {q[:4]}"

def fin_report_pdf(q):
    f = FIN[q]; qs = list(FIN.keys()); i = qs.index(q)
    prev = FIN[qs[i-4]] if i >= 4 else None
    path = f"{DOCS}/financial_report_{q}.pdf"
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.6*inch, bottomMargin=0.6*inch)
    el = [Paragraph("HOSPIRA, INC. AND SUBSIDIARIES", H),
          Paragraph(f"Condensed Consolidated Financial Data (unaudited) - Quarter ended {f['period_end']}", S["Heading3"]),
          Paragraph(DISCLAIMER, Sub), Spacer(1, 10)]
    rows = [["(dollars in millions)", qtr_label(q), qtr_label(qs[i-4]) if prev else "-"]]
    def r(label, key, sign=1):
        rows.append([label, money(sign*f[key]), money(sign*prev[key]) if prev else "-"])
    r("Net sales", "revenue")
    r("Cost of products sold", "cost_of_products_sold", -1)
    r("Selling, general and administrative", "sga", -1)
    r("Research and development", "rnd", -1)
    r("Depreciation and amortization", "depreciation_amortization", -1)
    r("Device Strategy charges (cash, one-time)", "device_strategy_cash_charges", -1)
    r("Certain quality and product related charges (cash, one-time)", "quality_matters_cash_charges", -1)
    r("Financing expense, net", "financing_expense", -1)
    r("Income (loss) before income taxes", "pretax_income")
    r("Income tax expense (benefit)", "income_tax_expense", -1)
    r("NET INCOME (LOSS)", "net_income")
    t = Table(rows, colWidths=[3.9*inch, 1.35*inch, 1.35*inch])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 9),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 9),
        ("FONT", (0,-1), (-1,-1), "Helvetica-Bold", 9),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("LINEBELOW", (0,0), (-1,0), 0.8, colors.black),
        ("LINEABOVE", (0,-1), (-1,-1), 0.8, colors.black),
        ("ROWBACKGROUNDS", (0,1), (-1,-2), [colors.white, colors.Color(0.95,0.95,0.97)]),
    ]))
    el += [t, Spacer(1, 14), Paragraph("Schedule of Consolidated Total Debt", S["Heading3"])]
    debt = f["consolidated_total_debt"]
    debt_rows = [["Instrument", "Maturity", "Outstanding ($M)"],
                 ["Revolving credit facility (Citibank N.A., Admin Agent)", "Oct 2016", money(round(debt*0.34,1))],
                 ["5.20% Senior Notes", "2020", money(round(debt*0.28,1))],
                 ["6.05% Senior Notes", "2017", money(round(debt*0.22,1))],
                 ["Other borrowings and capital leases", "various", money(round(debt-round(debt*0.34,1)-round(debt*0.28,1)-round(debt*0.22,1),1))],
                 ["CONSOLIDATED TOTAL DEBT", "", money(debt)]]
    dt = Table(debt_rows, colWidths=[3.6*inch, 1.2*inch, 1.8*inch])
    dt.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 9),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 9),
        ("FONT", (0,-1), (-1,-1), "Helvetica-Bold", 9),
        ("ALIGN", (2,0), (2,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.Color(0.88,0.9,0.95)),
    ]))
    el += [dt, Spacer(1, 12),
           Paragraph("Note 7 - One-time charges. Device Strategy charges relate to the pump retirement and "
                     "replacement initiative announced April 30, 2013 (see Amendment No. 1 to the Credit "
                     "Agreement, Disclosure Schedule). Quality and product related charges relate to the "
                     "matters described under 'Certain Quality and Product Related Matters'. All one-time "
                     "charges in this synthetic dataset are cash charges.", Note)]
    doc.build(el)
    return path

def compliance_cert_pdf(q, path):
    """One-page Officer's Compliance Certificate (as contemplated by the Credit Agreement)."""
    g = GOLD[q]; f = FIN[q]
    doc = SimpleDocTemplate(path, pagesize=LETTER, topMargin=0.7*inch)
    el = [Paragraph("COMPLIANCE CERTIFICATE", H),
          Paragraph("Delivered pursuant to Section 5.1 of the Credit Agreement and Guaranty dated as of "
                    "October 28, 2011 (as amended by Amendment No. 1 dated April 30, 2013), among Hospira, Inc. "
                    "and Citibank, N.A., as Administrative Agent.", Note),
          Paragraph(DISCLAIMER, Sub), Spacer(1, 8),
          Paragraph(f"Fiscal Quarter ended: {f['period_end']}", S["Heading4"])]
    rows = [["Section 6.6A computation (dollars in millions)", "Amount"],
            ["Consolidated Net Income (trailing four fiscal quarters)", money(g["sum_net_income"])],
            ["plus: Consolidated Financing Expense", money(g["sum_financing_expense"])],
            ["plus: provision for income taxes", money(g["sum_taxes"])],
            ["plus: depreciation and amortization", money(g["sum_d_and_a"])],
            ["plus: Permitted Addbacks - Device Strategy (subject to $290.0M aggregate cap)", money(g["device_addback_allowed"])],
            ["plus: Permitted Addbacks - quality matters (subject to $110.0M aggregate cap)", money(g["quality_addback_allowed"])],
            ["CONSOLIDATED ADJUSTED EBITDA", money(g["ebitda_correct"])],
            ["Consolidated Total Debt as of quarter end", money(g["consolidated_total_debt"])],
            ["LEVERAGE RATIO", f"{g['ratio_correct']:.2f}x"],
            ["Covenant maximum (Section 6.6A)", f"{g['threshold']:.2f}x"],
            ["Compliance", "YES" if g["compliant"] else "NO"]]
    t = Table(rows, colWidths=[5.1*inch, 1.5*inch])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,-1), "Helvetica", 9),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 9),
        ("FONT", (0,7), (-1,7), "Helvetica-Bold", 9),
        ("FONT", (0,9), (-1,-1), "Helvetica-Bold", 9),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("BACKGROUND", (0,0), (-1,0), colors.Color(0.88,0.9,0.95)),
    ]))
    el += [t, Spacer(1, 20),
           Paragraph("The undersigned officer certifies that the computations above are true and correct and "
                     "that no Potential Event of Default or Event of Default has occurred and is continuing.", Note),
           Spacer(1, 26),
           Paragraph("_______________________________", S["Normal"]),
           Paragraph("T. R. Marlow, Vice President and Treasurer", Note),
           Paragraph("Hospira, Inc.", Note)]
    doc.build(el)
    return path

def make_scan(src_pdf, dst_png_pdf):
    """Rasterize page 1 and degrade it into a believable office scan."""
    import subprocess
    png = src_pdf.replace(".pdf", "_raw.png")
    subprocess.run(["pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1",
                    src_pdf, src_pdf.replace(".pdf","")], check=True)
    raw = src_pdf.replace(".pdf", "-1.png")
    img = Image.open(raw).convert("L")
    img = img.rotate(random.uniform(-1.3, -0.6), expand=True, fillcolor=245)
    noise = Image.effect_noise(img.size, 14).point(lambda p: 255 if p > 90 else p)
    img = Image.blend(img, noise, 0.12)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(0.97)
    d = ImageDraw.Draw(img)
    d.text((40, img.height-60), "Scanned by HOSP-TREASURY-MFP04  2015-04-16 09:12", fill=90)
    img = img.convert("RGB")
    img.save(dst_png_pdf, "PDF", resolution=150)
    os.remove(raw)

if __name__ == "__main__":
    made = []
    for q in FIN:
        made.append(fin_report_pdf(q))
    # clean compliance certificates for the quarters BEFORE each scenario run date
    for q in ["2013Q4", "2014Q1", "2014Q3", "2014Q4"]:
        made.append(compliance_cert_pdf(q, f"{DOCS}/compliance_certificate_{q}.pdf"))
    # 2014Q4 certificate also as a messy SCAN (the one the agent must read a table from)
    make_scan(f"{DOCS}/compliance_certificate_2014Q4.pdf",
              f"{DOCS}/compliance_certificate_2014Q4_SCANNED.pdf")
    print("\n".join(sorted(os.listdir(DOCS))))
