#!/usr/bin/env python3
"""
Synthetic demo data generator for Covenant Sentinel (RAISE Hackathon, Vultr track).

Anchored to REAL EDGAR documents (download separately, see README_demo_data.md):
  - Credit Agreement and Guaranty dated Oct 28, 2011 (Hospira, Inc. / Citibank N.A.)
  - Amendment No. 1 dated Apr 30, 2013

Covenant mechanics implemented exactly as in those documents:
  Leverage Ratio = Consolidated Total Debt (last day of FQ)
                   / Consolidated Adjusted EBITDA (trailing 4 FQ)
  Adjusted EBITDA = Net Income + Financing Expense + income taxes + D&A
                    + Permitted Addbacks (subject to lifetime caps)
  Thresholds (Amendment No.1 §1(j), Section 6.6A):
      <= 3.75 for FQs ending through 2014-12-31
      <= 3.50 for FQs ending after 2014-12-31
  Permitted Addbacks (Amendment No.1 §1(d)):
      (a) Device Strategy cash charges incurred after 2012-12-31, lifetime cap $290M
      (b) Quality-matters cash charges incurred after 2013-01-01, lifetime cap $110M
  (Non-cash one-time items are intentionally zero in this synthetic world.)

All amounts in $ millions unless noted. Ledger amounts in $ thousands.
Deterministic: seeded RNG.
"""
import csv, json, math, os, random
from datetime import date, timedelta

random.seed(20260704)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------------
# 1. Quarterly design targets ($M)
# ----------------------------------------------------------------------------
QUARTERS = ["2013Q1","2013Q2","2013Q3","2013Q4","2014Q1","2014Q2","2014Q3","2014Q4","2015Q1"]
Q_END = {"2013Q1":date(2013,3,31),"2013Q2":date(2013,6,30),"2013Q3":date(2013,9,30),
         "2013Q4":date(2013,12,31),"2014Q1":date(2014,3,31),"2014Q2":date(2014,6,30),
         "2014Q3":date(2014,9,30),"2014Q4":date(2014,12,31),"2015Q1":date(2015,3,31)}

REVENUE      = dict(zip(QUARTERS,[1020,1035,1010,1040,1025,1050,1042,1030,1015]))
CLEAN_EBITDA = dict(zip(QUARTERS,[ 238, 242, 245, 250, 248, 252, 246, 240, 235]))
DEVICE_CASH  = dict(zip(QUARTERS,[ 130,  60,  40,  30,  25,  35,  10,   5,   0]))  # cap 290 lifetime
QUALITY_CASH = dict(zip(QUARTERS,[  20,  15,  10,  10,  10,  10,  10,  10,  10]))  # cap 110 lifetime
DandA        = dict(zip(QUARTERS,[  77,  78,  78,  79,  78,  78,  79,  79,  78]))
TOTAL_DEBT   = dict(zip(QUARTERS,[3150,3130,3080,3010,3020,3480,3420,3380,3355]))
RND          = dict(zip(QUARTERS,[  80,  82,  79,  83,  81,  84,  82,  80,  79]))
TAX_RATE = 0.21
DEBT_RATE = 0.026  # blended annual cost of debt -> quarterly interest

CAP_DEVICE, CAP_QUALITY = 290.0, 110.0

def interest(q):
    return round(TOTAL_DEBT[q]*DEBT_RATE/4, 1)

def income_statement(q):
    rev = REVENUE[q]
    cogs = round(rev*0.62, 1)
    inter = interest(q)
    sga  = round(rev - CLEAN_EBITDA[q] - cogs - RND[q], 1)   # plug so clean EBITDA hits target
    onetime = DEVICE_CASH[q] + QUALITY_CASH[q]
    pretax = round(CLEAN_EBITDA[q] - DandA[q] - inter - onetime, 1)
    tax = round(pretax*TAX_RATE, 1)
    ni  = round(pretax - tax, 1)
    return {"quarter":q,"period_end":Q_END[q].isoformat(),"revenue":rev,
            "cost_of_products_sold":cogs,"sga":sga,"rnd":RND[q],
            "depreciation_amortization":DandA[q],
            "device_strategy_cash_charges":DEVICE_CASH[q],
            "quality_matters_cash_charges":QUALITY_CASH[q],
            "financing_expense":inter,"pretax_income":pretax,
            "income_tax_expense":tax,"net_income":ni,
            "consolidated_total_debt":TOTAL_DEBT[q]}

FIN = [income_statement(q) for q in QUARTERS]

# ----------------------------------------------------------------------------
# 2. Covenant math (golden reference, per the real agreement as amended)
# ----------------------------------------------------------------------------
def cum_before(series, idx):
    return sum(series[QUARTERS[i]] for i in range(idx))

def covenant_test(q):
    i = QUARTERS.index(q)
    assert i >= 3, "need 4 trailing quarters"
    window = QUARTERS[i-3:i+1]
    ni    = sum(f["net_income"] for f in FIN if f["quarter"] in window)
    fin_e = sum(f["financing_expense"] for f in FIN if f["quarter"] in window)
    tax   = sum(f["income_tax_expense"] for f in FIN if f["quarter"] in window)
    da    = sum(f["depreciation_amortization"] for f in FIN if f["quarter"] in window)
    ds_w  = sum(DEVICE_CASH[w] for w in window)
    qc_w  = sum(QUALITY_CASH[w] for w in window)
    ds_cum_before = cum_before(DEVICE_CASH, i-3)
    qc_cum_before = cum_before(QUALITY_CASH, i-3)
    ds_addback = round(min(ds_w, max(0.0, CAP_DEVICE - ds_cum_before)), 1)
    qc_addback = round(min(qc_w, max(0.0, CAP_QUALITY - qc_cum_before)), 1)
    ebitda_naive    = round(ni + fin_e + tax + da, 1)                 # no addbacks
    ebitda_uncapped = round(ebitda_naive + ds_w + qc_w, 1)            # ignores caps (wrong)
    ebitda_correct  = round(ebitda_naive + ds_addback + qc_addback, 1)
    debt = TOTAL_DEBT[q]
    threshold = 3.75 if Q_END[q] <= date(2014,12,31) else 3.50
    return {"test_quarter":q,"period_end":Q_END[q].isoformat(),"window":window,
            "threshold":threshold,"consolidated_total_debt":debt,
            "sum_net_income":round(ni,1),"sum_financing_expense":round(fin_e,1),
            "sum_taxes":round(tax,1),"sum_d_and_a":round(da,1),
            "device_charges_in_window":ds_w,"device_cum_before_window":ds_cum_before,
            "device_addback_allowed":ds_addback,
            "quality_charges_in_window":qc_w,"quality_cum_before_window":qc_cum_before,
            "quality_addback_allowed":qc_addback,
            "ebitda_naive_no_addbacks":ebitda_naive,
            "ebitda_wrong_uncapped_addbacks":ebitda_uncapped,
            "ebitda_correct":ebitda_correct,
            "ratio_naive":round(debt/ebitda_naive,3),
            "ratio_wrong_uncapped":round(debt/ebitda_uncapped,3),
            "ratio_correct":round(debt/ebitda_correct,3),
            "compliant":debt/ebitda_correct <= 3.75 if Q_END[q]<=date(2014,12,31) else debt/ebitda_correct <= 3.50,
            "headroom_x":round((3.75 if Q_END[q]<=date(2014,12,31) else 3.50) - debt/ebitda_correct,3)}

GOLDEN = {q: covenant_test(q) for q in QUARTERS[3:]}

# ----------------------------------------------------------------------------
# 3. Transaction ledger ($ thousands) — aggregates reconcile to statements
# ----------------------------------------------------------------------------
DS_VENDORS = ["Pump Retirement Logistics LLC","MedDevice Collection & Destruction Inc",
              "Customer Sales Allowance - Credit Memo","Infusion Replacement Program Admin",
              "Device Quality Systems Upgrade Co"]
QC_VENDORS = ["Quality Compliance Partners LLP","FDA Remediation Consultants Group",
              "Sterile Process Validation Services"]

def month_ends(q):
    e = Q_END[q]; ms=[]
    for k in (2,1,0):
        y, m = e.year, e.month-k
        if m<1: y, m = y-1, m+12
        nm = date(y+ (m==12), (m % 12)+1, 1)
        ms.append(nm - timedelta(days=1))
    return ms

def split_amount(total_k, n, rnd):
    """split integer thousands into n positive parts summing exactly."""
    if total_k == 0: return [0]*n
    cuts = sorted(rnd.sample(range(1,total_k), min(n-1,total_k-1))) if total_k>n else []
    parts, prev = [], 0
    for c in cuts: parts.append(c-prev); prev=c
    parts.append(total_k-prev)
    while len(parts)<n: parts.append(0)
    return parts

rows=[]
def add(dt, desc, vendor, cat, amount_k, q):
    rows.append({"date":dt.isoformat(),"description":desc,"counterparty":vendor,
                 "category":cat,"amount_usd_thousands":amount_k,"quarter":q})

for q in QUARTERS:
    f = next(x for x in FIN if x["quarter"]==q)
    mes = month_ends(q)
    # revenue receipts: 30 customers/quarter
    rev_parts = split_amount(int(f["revenue"]*1000), 30, random)
    for j,p in enumerate(rev_parts):
        d = mes[j%3] - timedelta(days=random.randint(0,27))
        add(d, "Trade receivables collection", f"Hospital Group {j+1:02d}", "revenue", p, q)
    # cogs & opex
    for name,total,cat,vend in [("Materials & production", f["cost_of_products_sold"], "cogs","Contract Manufacturer"),
                                ("Selling, general & administrative", f["sga"], "sga","Corporate Services"),
                                ("Research & development", f["rnd"], "rnd","R&D Programs")]:
        for j,p in enumerate(split_amount(int(total*1000), 12, random)):
            d = mes[j%3] - timedelta(days=random.randint(0,27))
            add(d, name, f"{vend} {j%4+1}", cat, -p, q)
    # one-time: device strategy
    for j,p in enumerate(split_amount(int(f["device_strategy_cash_charges"]*1000), 6, random)):
        if p==0: continue
        d = mes[j%3] - timedelta(days=random.randint(0,20))
        add(d, "Device Strategy program cash charge", DS_VENDORS[j%len(DS_VENDORS)], "device_strategy", -p, q)
    # one-time: quality matters
    for j,p in enumerate(split_amount(int(f["quality_matters_cash_charges"]*1000), 4, random)):
        if p==0: continue
        d = mes[j%3] - timedelta(days=random.randint(0,20))
        add(d, "Quality remediation cash charge", QC_VENDORS[j%len(QC_VENDORS)], "quality_matters", -p, q)
    # interest
    add(mes[2], "Interest payment on credit facilities", "Citibank N.A. as Admin Agent",
        "interest", -int(f["financing_expense"]*1000), q)
    # taxes
    add(mes[2], "Income tax payment/(refund)", "Tax Authorities", "tax", -int(f["income_tax_expense"]*1000), q)

# debt movements (drive TOTAL_DEBT path; cause for 2014Q2 jump buried here)
add(date(2013,5,10),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-20000,"2013Q2")
add(date(2013,8,15),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-50000,"2013Q3")
add(date(2013,11,20),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-70000,"2013Q4")
add(date(2014,2,14),"Revolver draw - working capital","Citibank N.A. as Admin Agent","debt_draw",10000,"2014Q1")
add(date(2014,5,19),"Revolver draw - Meridian Infusion Assets acquisition","Citibank N.A. as Admin Agent","debt_draw",460000,"2014Q2")
add(date(2014,5,19),"Acquisition consideration - Meridian Infusion Assets (one-time)","Meridian Infusion Holdings","acquisition",-460000,"2014Q2")
add(date(2014,8,22),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-60000,"2014Q3")
add(date(2014,11,18),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-40000,"2014Q4")
add(date(2015,2,20),"Revolver repayment","Citibank N.A. as Admin Agent","debt_repayment",-25000,"2015Q1")

rows.sort(key=lambda r:r["date"])
with open(f"{OUT}/transactions.csv","w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

# reconciliation check: ledger vs statements
ok=True
for q in QUARTERS:
    f=next(x for x in FIN if x["quarter"]==q)
    for cat,col in [("revenue","revenue"),("device_strategy","device_strategy_cash_charges"),
                    ("quality_matters","quality_matters_cash_charges")]:
        s=abs(sum(r["amount_usd_thousands"] for r in rows if r["quarter"]==q and r["category"]==cat))/1000
        if abs(s-f[col])>0.001: ok=False; print("MISMATCH",q,cat,s,f[col])
print("Ledger reconciliation:","OK" if ok else "FAILED")

with open(f"{OUT}/financials_quarterly.json","w") as fh: json.dump(FIN,fh,indent=2)
with open(f"{OUT}/golden_covenant_math.json","w") as fh: json.dump(GOLDEN,fh,indent=2)
print(json.dumps({q:{"naive":g["ratio_naive"],"uncapped":g["ratio_wrong_uncapped"],
                     "correct":g["ratio_correct"],"thr":g["threshold"],"ok":g["compliant"]}
                  for q,g in GOLDEN.items()}, indent=1))
