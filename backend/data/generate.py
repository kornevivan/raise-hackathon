"""Seeded synthetic corpus for Covenant Sentinel.

Everything is generated FROM one set of numbers so a judge clicking any citation
sees figures that reconcile: the transaction ledger aggregates up to the financial
statements, and the financial statements feed the covenant ratio.

Run:  python -m data.generate      (from the backend/ directory)

Outputs (all committed, deterministic):
  data/corpus/<doc>/pNN.png     rendered page images (incl. one scanned page)
  data/corpus/index.json        documents -> pages -> citable blocks
  data/financials.json          structured line items  (source for financials_query)
  data/ledger.csv               transaction ledger      (source for transactions_query)
  data/covenant.sqlite          ledger + financials in SQLite
  data/scenarios.json           the three demo runs
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3

from render import PageBuilder, scanify  # type: ignore

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")
SEED = 20260704

# --------------------------------------------------------------------------- #
#  THE NUMBERS  (single source of truth — everything else derives from this)   #
# --------------------------------------------------------------------------- #

BORROWERS = {
    "meridian": {
        "id": "meridian",
        "name": "Meridian Logistics Holdings, Inc.",
        "short": "Meridian Logistics",
        "agreement_date": "March 14, 2023",
        "agent_bank": "First Continental Bank, N.A.",
        "covenant": {
            "name": "Maximum Total Net Leverage Ratio",
            "formula": "Consolidated Total Net Debt / Consolidated EBITDA (LTM)",
            "threshold": 3.50,
            "operator": "<=",
            "test": "quarterly",
        },
        # LTM leverage trend the analyst sees across quarters
        "trend": {"Q1-2025": 2.80, "Q2-2025": 3.10, "Q3-2025": 3.33, "Q4-2025": 3.55},
        "period": "Q4-2025",
        # Q4 balance-sheet & EBITDA build (USD millions, LTM)
        "fin": {
            "revenue_ltm": 612.4,
            "net_income_ltm": 41.0,
            "interest_expense_ltm": 28.5,
            "income_taxes_ltm": 12.8,
            "depreciation_amortization_ltm": 36.0,
            # naive EBITDA = 41.0 + 28.5 + 12.8 + 36.0 = 118.3
            "senior_term_loan": 300.0,
            "revolving_facility": 120.0,
            "finance_leases": 32.0,
            # total debt = 452.0
            "cash_and_equivalents": 32.0,
            # net debt = 420.0
            "acquisition_one_time_costs": 4.5,  # Project Atlas — expensed in Q4 SG&A
        },
        "has_amendment": True,
        "scanned_cert": True,
    },
    "cascade": {
        "id": "cascade",
        "name": "Cascade Manufacturing Corp.",
        "short": "Cascade Manufacturing",
        "agreement_date": "June 2, 2022",
        "agent_bank": "Union Harbor Trust",
        "covenant": {
            "name": "Maximum Total Net Leverage Ratio",
            "formula": "Consolidated Total Net Debt / Consolidated EBITDA (LTM)",
            "threshold": 3.50,
            "operator": "<=",
            "test": "quarterly",
        },
        "trend": {"Q1-2025": 3.05, "Q2-2025": 3.28, "Q3-2025": 3.61, "Q4-2025": 4.04},
        "period": "Q4-2025",
        "fin": {
            "revenue_ltm": 421.0,   # collapsed from ~540 after losing anchor customer
            "net_income_ltm": 18.0,
            "interest_expense_ltm": 31.0,
            "income_taxes_ltm": 7.0,
            "depreciation_amortization_ltm": 40.0,
            # EBITDA = 96.0
            "senior_term_loan": 280.0,
            "revolving_facility": 118.0,
            "finance_leases": 22.0,
            # total debt = 420.0
            "cash_and_equivalents": 32.0,
            # net debt = 388.0  -> 388/96 = 4.04x  BREACH
            "acquisition_one_time_costs": 0.0,
        },
        "has_amendment": False,
        "scanned_cert": False,
    },
    "northwind": {
        "id": "northwind",
        "name": "Northwind Retail Group, LLC",
        "short": "Northwind Retail",
        "agreement_date": "September 9, 2023",
        "agent_bank": "First Continental Bank, N.A.",
        "covenant": {
            "name": "Maximum Total Net Leverage Ratio",
            "formula": "Consolidated Total Net Debt / Consolidated EBITDA (LTM)",
            "threshold": 3.50,
            "operator": "<=",
            "test": "quarterly",
        },
        "trend": {"Q1-2025": 2.20, "Q2-2025": 2.28, "Q3-2025": 2.31, "Q4-2025": 2.35},
        "period": "Q4-2025",
        "fin": {
            "revenue_ltm": 388.0,
            "net_income_ltm": 33.0,
            "interest_expense_ltm": 14.0,
            "income_taxes_ltm": 9.0,
            "depreciation_amortization_ltm": 20.0,
            # EBITDA = 76.0
            "senior_term_loan": 150.0,
            "revolving_facility": 30.0,
            "finance_leases": 8.0,
            # total debt = 188.0
            "cash_and_equivalents": 9.4,
            # net debt = 178.6 -> 178.6/76 = 2.35x  OK
            "acquisition_one_time_costs": 0.0,
        },
        "has_amendment": False,
        "scanned_cert": False,
    },
}


def derive(b: dict) -> dict:
    f = b["fin"]
    naive_ebitda = round(
        f["net_income_ltm"] + f["interest_expense_ltm"]
        + f["income_taxes_ltm"] + f["depreciation_amortization_ltm"], 1)
    total_debt = round(f["senior_term_loan"] + f["revolving_facility"] + f["finance_leases"], 1)
    net_debt = round(total_debt - f["cash_and_equivalents"], 1)
    adj_ebitda = round(naive_ebitda + f["acquisition_one_time_costs"], 1)
    return {
        "naive_ebitda": naive_ebitda,
        "adjusted_ebitda": adj_ebitda,
        "total_debt": total_debt,
        "net_debt": net_debt,
        "naive_ratio": round(net_debt / naive_ebitda, 3),
        "adjusted_ratio": round(net_debt / adj_ebitda, 3),
    }


def m(x: float) -> str:
    return f"{x:,.1f}"


# --------------------------------------------------------------------------- #
#  Ledger — the acquisition cluster that (a) explains the EBITDA drop and      #
#  (b) qualifies for the Amendment addback lives in Q4.                        #
# --------------------------------------------------------------------------- #

def build_ledger() -> list[dict]:
    import random
    rnd = random.Random(SEED)
    rows: list[dict] = []
    tid = 1000
    quarters = ["Q1-2025", "Q2-2025", "Q3-2025", "Q4-2025"]
    vendors_ops = ["Atlas Fuel Co", "Interstate Freight", "PortSide Terminals", "MetroPayroll",
                   "TransFleet Leasing", "Harbor Insurance", "CityPower Utilities", "OfficeWorks"]
    cats = ["Fuel", "Payroll", "Leasing", "Utilities", "Insurance", "Terminal Fees", "Maintenance"]

    for b in BORROWERS.values():
        for q in quarters:
            # background operating expenses
            for _ in range(rnd.randint(28, 40)):
                tid += 1
                rows.append({
                    "txn_id": f"T{tid}",
                    "borrower_id": b["id"],
                    "period": q,
                    "date": f"{q[-4:]}-{ {'Q1':'02','Q2':'05','Q3':'08','Q4':'11'}[q[:2]] }-{rnd.randint(1,27):02d}",
                    "vendor": rnd.choice(vendors_ops),
                    "category": rnd.choice(cats),
                    "memo": "Recurring operating expense",
                    "amount_usd_000": round(rnd.uniform(80, 950), 1),
                    "one_time": 0,
                    "acquisition_related": 0,
                })

        # Meridian: bury the Project Atlas acquisition cluster in Q4 (sums to 4.5M)
        if b["id"] == "meridian":
            atlas = [
                ("Whitmore & Cole LLP", "Legal — M&A", "Project Atlas — acquisition legal fees", 1800.0),
                ("Bridgepoint Advisory", "Advisory", "Project Atlas — financial advisory (buy-side)", 1400.0),
                ("Deloitte QoE Team", "Due Diligence", "Project Atlas — quality-of-earnings & tax DD", 700.0),
                ("Meridian Integration PMO", "Integration", "Project Atlas — one-time integration & retention", 600.0),
            ]
            for vendor, cat, memo, amt in atlas:
                tid += 1
                rows.append({
                    "txn_id": f"T{tid}",
                    "borrower_id": "meridian",
                    "period": "Q4-2025",
                    "date": f"2025-11-{rnd.randint(3,26):02d}",
                    "vendor": vendor,
                    "category": cat,
                    "memo": memo,
                    "amount_usd_000": amt,
                    "one_time": 1,
                    "acquisition_related": 1,
                })

        # Cascade: revenue collapse — a big customer credit/loss in Q4
        if b["id"] == "cascade":
            tid += 1
            rows.append({
                "txn_id": f"T{tid}",
                "borrower_id": "cascade",
                "period": "Q4-2025",
                "date": "2025-10-15",
                "vendor": "Anchor customer: Vertex Retail",
                "category": "Revenue — Lost Contract",
                "memo": "Termination of Vertex master supply agreement (~28% of revenue)",
                "amount_usd_000": -58000.0,
                "one_time": 0,
                "acquisition_related": 0,
            })
    return rows


# --------------------------------------------------------------------------- #
#  Document rendering                                                          #
# --------------------------------------------------------------------------- #

def doc_credit_agreement(b: dict) -> tuple[dict, list]:
    d = derive(b)
    cov = b["covenant"]
    doc_id = f"{b['id']}_credit_agreement"
    pages = []

    # Page 1 — cover / definitions
    p = PageBuilder(doc_id, 1)
    p.heading("CREDIT AGREEMENT")
    p.space(6)
    p.paragraph(f"dated as of {b['agreement_date']}", size=18, bold=True)
    p.paragraph(f"among {b['name']}, as Borrower, the Lenders party hereto, "
                f"and {b['agent_bank']}, as Administrative Agent.", size=18, gap=18)
    p.heading("ARTICLE I — DEFINITIONS", size=22, center=False)
    p.paragraph(
        '“Consolidated EBITDA” means, for any period, Consolidated Net Income for such '
        "period plus, without duplication and to the extent deducted in computing such "
        "Consolidated Net Income, the sum of (a) Consolidated Interest Expense, (b) provision "
        "for income taxes, (c) depreciation and amortization expense, and (d) other non-cash "
        "charges, in each case for such period, all as further adjusted pursuant to any "
        "amendment to this Agreement then in effect. See also Section 6.10 (Financial Covenant).",
        size=18)
    p.paragraph(
        '“Consolidated Total Net Debt” means, as of any date, the aggregate principal amount of '
        "all Indebtedness of the Borrower and its Restricted Subsidiaries (including the Term "
        "Loans, Revolving Loans and Finance Lease Obligations) less unrestricted Cash and Cash "
        "Equivalents as of such date.", size=18)
    p.paragraph(
        '“Total Net Leverage Ratio” means, as of any Test Date, the ratio of Consolidated Total '
        "Net Debt as of such date to Consolidated EBITDA for the most recently ended period of "
        "four consecutive fiscal quarters (LTM).", size=18)
    p.footer(f"{b['short']} — Credit Agreement — Page 1")
    pages.append(p.save(CORPUS))

    # Page 2 — the maintenance covenant (Section 6.10) — the threshold lives here
    p = PageBuilder(doc_id, 2)
    p.heading("ARTICLE VI — FINANCIAL COVENANTS", size=22, center=False)
    p.paragraph("Section 6.10  Maximum Total Net Leverage Ratio.", size=19, bold=True, gap=6)
    p.paragraph(
        f"The Borrower shall not permit the Total Net Leverage Ratio, determined as of the last "
        f"day of any fiscal quarter (each a “Test Date”), commencing with the fiscal quarter "
        f"ending after the Closing Date, to be greater than {cov['threshold']:.2f} to 1.00.",
        size=18)
    p.paragraph(
        "Compliance with this Section 6.10 shall be tested quarterly and evidenced by a "
        "Compliance Certificate delivered pursuant to Section 5.01(c), setting forth in "
        "reasonable detail the calculation of the Total Net Leverage Ratio, including each "
        "component of Consolidated EBITDA and Consolidated Total Net Debt.", size=18, gap=18)
    if b["has_amendment"]:
        p.paragraph(
            "Note: The definition of Consolidated EBITDA set forth in Article I has been amended. "
            "See Amendment No. 1 to this Credit Agreement, dated October 3, 2025, which modifies "
            "clause (d) of such definition. Any calculation of the Total Net Leverage Ratio for a "
            "Test Date occurring on or after October 3, 2025 shall give effect to Amendment No. 1.",
            size=18, bold=True, color=(120, 60, 20))
    p.footer(f"{b['short']} — Credit Agreement — Page 2")
    pages.append(p.save(CORPUS))

    document = {"doc_id": doc_id, "title": f"Credit Agreement — {b['short']}",
                "kind": "credit_agreement", "borrower_id": b["id"]}
    return document, pages


def doc_amendment(b: dict) -> tuple[dict, list]:
    doc_id = f"{b['id']}_amendment_1"
    pages = []
    p = PageBuilder(doc_id, 1)
    p.heading("AMENDMENT NO. 1", size=28)
    p.paragraph("to the Credit Agreement", size=18, bold=True)
    p.paragraph(
        f"This AMENDMENT NO. 1 (this “Amendment”), dated as of October 3, 2025, amends that "
        f"certain Credit Agreement dated as of {b['agreement_date']} (the “Credit Agreement”) "
        f"among {b['name']}, the Lenders party thereto and {b['agent_bank']}, as Administrative "
        f"Agent. Capitalized terms used and not otherwise defined herein have the meanings "
        f"assigned in the Credit Agreement.", size=18, gap=16)
    p.paragraph("Section 1.  Amendment to Definition of Consolidated EBITDA.", size=19, bold=True, gap=6)
    p.paragraph(
        "Clause (d) of the definition of “Consolidated EBITDA” in Article I of the Credit "
        "Agreement is hereby amended and restated in its entirety to read as follows:", size=18)
    p.paragraph(
        "“(d) other non-cash charges, PLUS, to the extent deducted in computing Consolidated Net "
        "Income, one-time fees, costs and expenses incurred in connection with any Permitted "
        "Acquisition consummated during such period (including legal, advisory, due diligence and "
        "integration costs), in an aggregate amount not to exceed $10,000,000 for any period of "
        "four consecutive fiscal quarters,”", size=18, bold=True, indent=24,
        color=(120, 60, 20), gap=16)
    p.paragraph("Section 2.  Effectiveness.", size=19, bold=True, gap=6)
    p.paragraph(
        "This Amendment shall be effective as of October 3, 2025 and shall apply to the "
        "determination of the Total Net Leverage Ratio for each Test Date occurring on or after "
        "such date, including the fiscal quarter ending December 31, 2025.", size=18)
    p.paragraph("Section 3.  Ratification.", size=19, bold=True, gap=6)
    p.paragraph(
        "Except as expressly amended hereby, the Credit Agreement remains in full force and "
        "effect and is hereby ratified and confirmed in all respects.", size=18)
    p.footer(f"{b['short']} — Amendment No. 1 — Page 1")
    pages.append(p.save(CORPUS))
    document = {"doc_id": doc_id, "title": f"Amendment No. 1 — {b['short']}",
                "kind": "amendment", "borrower_id": b["id"]}
    return document, pages


def doc_financials(b: dict) -> tuple[dict, list]:
    d = derive(b)
    f = b["fin"]
    doc_id = f"{b['id']}_financials_{b['period'].lower()}"
    pages = []

    # Page 1 — income statement + EBITDA build (table-heavy)
    p = PageBuilder(doc_id, 1)
    p.heading(f"{b['short'].upper()}", size=24)
    p.paragraph(f"Consolidated Financial Statements — {b['period']} (LTM)", size=18, bold=True)
    p.paragraph("(unaudited; USD in millions)", size=15, gap=16)
    cx = [0, 560]
    p.table("Consolidated Income Statement (LTM)", ["Line Item", "Amount"], [
        ["Total Revenue", m(f["revenue_ltm"])],
        ["Consolidated Net Income", m(f["net_income_ltm"])],
        ["  + Consolidated Interest Expense", m(f["interest_expense_ltm"])],
        ["  + Provision for Income Taxes", m(f["income_taxes_ltm"])],
        ["  + Depreciation & Amortization", m(f["depreciation_amortization_ltm"])],
        ["Consolidated EBITDA (as reported)", m(d["naive_ebitda"])],
    ], cx, highlight_rows={5})
    if f["acquisition_one_time_costs"] > 0:
        p.paragraph(
            f"Footnote 4: SG&A for the period includes "
            f"${m(f['acquisition_one_time_costs'])}M of one-time fees and expenses incurred in "
            f"connection with the Project Atlas acquisition (legal, advisory, due diligence and "
            f"integration). These charges are potentially addback-eligible — see Amendment No. 1.",
            size=16, color=(90, 70, 40))
    p.footer(f"{b['short']} — Financial Statements — Page 1")
    pages.append(p.save(CORPUS))

    # Page 2 — balance sheet / debt schedule
    p = PageBuilder(doc_id, 2)
    p.heading(f"{b['short'].upper()}", size=24)
    p.paragraph(f"Debt Schedule & Net Debt Reconciliation — {b['period']}", size=18, bold=True)
    p.paragraph("(USD in millions)", size=15, gap=16)
    p.table("Consolidated Total Net Debt", ["Component", "Amount"], [
        ["Senior Term Loan", m(f["senior_term_loan"])],
        ["Revolving Facility (drawn)", m(f["revolving_facility"])],
        ["Finance Lease Obligations", m(f["finance_leases"])],
        ["Total Indebtedness", m(d["total_debt"])],
        ["Less: Cash & Cash Equivalents", f"({m(f['cash_and_equivalents'])})"],
        ["Consolidated Total Net Debt", m(d["net_debt"])],
    ], [0, 560], highlight_rows={5})
    p.footer(f"{b['short']} — Financial Statements — Page 2")
    pages.append(p.save(CORPUS))

    document = {"doc_id": doc_id, "title": f"Financial Statements {b['period']} — {b['short']}",
                "kind": "financials", "borrower_id": b["id"]}
    return document, pages


def doc_compliance_cert(b: dict, scanned: bool) -> tuple[dict, list]:
    d = derive(b)
    f = b["fin"]
    doc_id = f"{b['id']}_compliance_cert_{b['period'].lower()}"
    pages = []
    p = PageBuilder(doc_id, 1)
    p.heading("COMPLIANCE CERTIFICATE", size=26)
    p.paragraph(f"Delivered pursuant to Section 5.01(c) — Fiscal Quarter ended December 31, 2025",
                size=17, bold=True)
    p.paragraph(
        f"The undersigned, the Chief Financial Officer of {b['name']}, hereby certifies that the "
        f"following calculation of the Total Net Leverage Ratio is true and correct as of the "
        f"Test Date:", size=17, gap=14)
    # Note: the certificate reports the NAIVE ratio (pre-amendment) — this is the trap.
    p.table("Total Net Leverage Ratio Calculation", ["Component", "Amount"], [
        ["Consolidated Total Net Debt", m(d["net_debt"])],
        ["Consolidated EBITDA (LTM, as reported)", m(d["naive_ebitda"])],
        ["Total Net Leverage Ratio (as reported)", f"{d['naive_ratio']:.2f}x"],
        ["Covenant Threshold (Section 6.10)", f"{b['covenant']['threshold']:.2f}x"],
    ], [0, 560], highlight_rows={2})
    status = "IN COMPLIANCE" if d["naive_ratio"] <= b["covenant"]["threshold"] else "REVIEW REQUIRED"
    p.paragraph(f"Preliminary status (as reported, pre-amendment): {status}.", size=17, bold=True, gap=18)
    p.paragraph("By: ______________________________", size=18)
    p.paragraph("Name: Dana R. Whitfield", size=17)
    p.paragraph("Title: Chief Financial Officer", size=17)
    page = p.save(CORPUS)
    if scanned:
        scanify(os.path.join(CORPUS, page.image_path), seed=SEED)
    pages.append(page)
    document = {"doc_id": doc_id,
                "title": f"Compliance Certificate {b['period']} — {b['short']}"
                         + (" (SCANNED)" if scanned else ""),
                "kind": "compliance_certificate", "borrower_id": b["id"], "scanned": scanned}
    return document, pages


# --------------------------------------------------------------------------- #
#  Orchestration                                                              #
# --------------------------------------------------------------------------- #

def build():
    os.makedirs(CORPUS, exist_ok=True)
    documents = []
    index_docs = []

    for b in BORROWERS.values():
        builders = [doc_credit_agreement(b), doc_financials(b),
                    doc_compliance_cert(b, scanned=b["scanned_cert"])]
        if b["has_amendment"]:
            builders.insert(1, doc_amendment(b))
        for document, pages in builders:
            rel_pages = [pg.to_dict(pg.image_path) for pg in pages]
            index_docs.append({**document, "pages": rel_pages})

    # ledger + financials.json + sqlite
    ledger = build_ledger()
    with open(os.path.join(HERE, "ledger.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ledger[0].keys()))
        w.writeheader()
        w.writerows(ledger)

    financials = {}
    for b in BORROWERS.values():
        d = derive(b)
        financials[b["id"]] = {
            b["period"]: {
                "revenue_ltm": b["fin"]["revenue_ltm"],
                "net_income_ltm": b["fin"]["net_income_ltm"],
                "interest_expense_ltm": b["fin"]["interest_expense_ltm"],
                "income_taxes_ltm": b["fin"]["income_taxes_ltm"],
                "depreciation_amortization_ltm": b["fin"]["depreciation_amortization_ltm"],
                "consolidated_ebitda_reported": d["naive_ebitda"],
                "senior_term_loan": b["fin"]["senior_term_loan"],
                "revolving_facility": b["fin"]["revolving_facility"],
                "finance_leases": b["fin"]["finance_leases"],
                "total_indebtedness": d["total_debt"],
                "cash_and_equivalents": b["fin"]["cash_and_equivalents"],
                "consolidated_total_net_debt": d["net_debt"],
                "acquisition_one_time_costs": b["fin"]["acquisition_one_time_costs"],
            }
        }
    with open(os.path.join(HERE, "financials.json"), "w") as fh:
        json.dump(financials, fh, indent=2)

    # SQLite
    dbp = os.path.join(HERE, "covenant.sqlite")
    if os.path.exists(dbp):
        os.remove(dbp)
    con = sqlite3.connect(dbp)
    con.execute("""CREATE TABLE transactions(
        txn_id TEXT, borrower_id TEXT, period TEXT, date TEXT, vendor TEXT,
        category TEXT, memo TEXT, amount_usd_000 REAL, one_time INT, acquisition_related INT)""")
    con.executemany("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    [tuple(r.values()) for r in ledger])
    con.commit()
    con.close()

    # scenarios
    scenarios = []
    for key, label, blurb in [
        ("meridian", "S1 — The Amendment Twist",
         "Naive leverage prints 3.55x (breach!). The agent notices the EBITDA definition was "
         "amended, re-retrieves Amendment No. 1, applies the acquisition addback, and recomputes "
         "3.42x — no breach, but only 0.08x of headroom."),
        ("cascade", "S2 — Genuine Breach",
         "Leverage at 4.04x driven by a real revenue collapse visible in the ledger. No addback "
         "saves it. Escalate immediately."),
        ("northwind", "S3 — All Clear",
         "Healthy borrower at 2.35x. The agent passes quickly — calibrated, not alarmist."),
    ]:
        b = BORROWERS[key]
        d = derive(b)
        scenarios.append({
            "id": f"S-{key}",
            "label": label,
            "blurb": blurb,
            "borrower_id": b["id"],
            "borrower_name": b["short"],
            "period": b["period"],
            "covenant": b["covenant"],
            "trend": b["trend"],
            "expected": {
                "naive_ratio": d["naive_ratio"],
                "adjusted_ratio": d["adjusted_ratio"],
                "has_amendment": b["has_amendment"],
            },
        })

    index = {"documents": index_docs, "scenarios": scenarios,
             "generated_seed": SEED}
    with open(os.path.join(HERE, "corpus", "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
    with open(os.path.join(HERE, "scenarios.json"), "w") as fh:
        json.dump({"scenarios": scenarios}, fh, indent=2)

    npages = sum(len(dd["pages"]) for dd in index_docs)
    print(f"Generated {len(index_docs)} documents, {npages} pages, {len(ledger)} ledger rows.")
    for key in BORROWERS:
        d = derive(BORROWERS[key])
        print(f"  {key:10s} naive={d['naive_ratio']:.3f}x  adjusted={d['adjusted_ratio']:.3f}x  "
              f"threshold={BORROWERS[key]['covenant']['threshold']:.2f}x")


if __name__ == "__main__":
    build()
