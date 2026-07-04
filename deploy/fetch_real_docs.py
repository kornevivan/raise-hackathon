"""Fetch the two REAL Hospira governing documents from SEC EDGAR and render them to
PDF in backend/data/real/ (guide §1). Reproducible; requires an internet connection
and Playwright's Chromium (installed with the frontend: `cd frontend && npx playwright
install chromium`).

    python deploy/fetch_real_docs.py

By default the demo indexes faithful, source-linked EXCERPTS of the exact governing
clauses (reliable page-level citations; the real Credit Agreement is ~98 pages and its
wording differs from the clauses we cite). To index these real PDFs instead, run the app
with USE_REAL_DOCS=1.
"""
import os
import subprocess
import sys

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "backend", "data", "real")
UA = os.getenv("SEC_UA", "CovenantSentinel/1.0 (contact: your-email@example.com)")

DOCS = [
    ("https://www.sec.gov/Archives/edgar/data/1274057/000110465911059575/a11-28867_1ex10d1.htm",
     "credit_agreement_2011-10-28"),
    ("https://www.sec.gov/Archives/edgar/data/1274057/000127405713000013/hsp-ex1012_2013331x10q.htm",
     "amendment_no1_2013-04-30"),
]

HTML2PDF = r"""
import { chromium } from 'playwright'
const jobs = JSON.parse(process.argv[2])
const b = await chromium.launch()
for (const [src, out] of jobs) {
  const pg = await b.newPage()
  await pg.goto('file://' + src, { waitUntil: 'load' })
  await pg.pdf({ path: out, format: 'Letter',
    margin: { top:'0.6in', bottom:'0.6in', left:'0.7in', right:'0.7in' }, printBackground: true })
  await pg.close()
  console.log('wrote', out)
}
await b.close()
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=60, follow_redirects=True) as c:
        for url, base in DOCS:
            r = c.get(url)
            r.raise_for_status()
            html_path = os.path.join(OUT, base + ".html")
            open(html_path, "w", encoding="utf-8").write(r.text)
            jobs.append([os.path.abspath(html_path), os.path.abspath(os.path.join(OUT, base + ".pdf"))])
            print(f"downloaded {base} ({len(r.content):,} bytes)")

    # render via Playwright (node); the repo's frontend provides it
    fe = os.path.join(HERE, "..", "frontend")
    script = os.path.join(OUT, "_html2pdf.mjs")
    open(script, "w").write(HTML2PDF)
    try:
        subprocess.run(["node", script, __import__("json").dumps(jobs)], cwd=fe, check=True)
    except Exception as e:
        print(f"\nPDF render step needs Playwright (cd frontend && npm i && npx playwright install "
              f"chromium). HTML saved in {OUT}. Error: {e}", file=sys.stderr)
    finally:
        for j in jobs:
            for ext in (".html",):
                p = j[0]
                if os.path.exists(p):
                    os.remove(p)
        if os.path.exists(script):
            os.remove(script)
    print("done →", OUT)


if __name__ == "__main__":
    main()
