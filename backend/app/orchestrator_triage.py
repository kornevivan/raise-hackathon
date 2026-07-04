"""Portfolio triage — Scenario S0 (P1-B).

"Quarter closed — review the portfolio": the planner ranks all three borrowers by
risk with stated reasons, reading Hospira's latest (2014Q4, SCANNED) certificate via
VultronRetriever. Hospira must rank #1 because 3.59x is already above the 3.50x
threshold that takes effect next quarter (Amendment No. 1 §1(j) step-down). Ends by
offering the deep run on the top-ranked borrower.
"""
from __future__ import annotations

import itertools
import json
import os
from datetime import datetime, timezone

from . import config, covenant_engine as ce, ingest, hospira, linker
from .llm import LLM, PRIME
from .retriever import TIER_MODEL

DATASET = os.path.join(config.DATA_DIR, "dataset")
PORT_DIR = os.path.join(DATASET, "documents", "portfolio")

SCENARIO_S0 = {"id": "S0", "test_quarter": "2015Q1",
               "label": "S0 · Quarter closed — review the portfolio",
               "blurb": "Rank the book by risk before any deep check. Hospira surfaces #1 — its "
                        "scanned 2014Q4 certificate reads 3.59x, already above the 3.50x step-down "
                        "that hits next quarter.", "kind": "triage",
               "prompt": "The quarter just closed — review the portfolio and tell me which borrower "
                         "needs attention first.",
               "doc_labels": ["Borrower profiles (Hospira, Atlantic, Cascadia)",
                              "Latest 2014Q4 certificates (Hospira's is scanned)",
                              "Amendment No. 1 (§6.6A step-down)"]}

_corpus_id = None


def _corpus():
    """Portfolio profiles + certificates + Hospira's scanned 2014Q4 certificate + amendment."""
    global _corpus_id
    if _corpus_id and _corpus_id in ingest.UPLOADS:
        return ingest.UPLOADS[_corpus_id]
    files = []
    for name in sorted(os.listdir(PORT_DIR)):
        if name.endswith(".pdf"):
            files.append((name, open(os.path.join(PORT_DIR, name), "rb").read()))
    # Hospira's scanned certificate + the base agreement AND amendment (real by default) —
    # triage must be able to cite the base definition and the §6.6A step-down.
    extras = [os.path.join(DATASET, "documents", "compliance_certificate_2014Q4_SCANNED.pdf"),
              hospira.resolve_doc("credit_agreement_excerpt.pdf"),
              hospira.resolve_doc("amendment_no1_excerpt.pdf")]
    for p in extras:
        if os.path.exists(p):
            files.append((os.path.basename(p), open(p, "rb").read()))
    res = ingest.ingest(files, collection="triage")
    _corpus_id = res["upload_id"]
    return ingest.UPLOADS[_corpus_id]


def _now():
    return datetime.now(timezone.utc).isoformat()


class TriageRun:
    def __init__(self):
        self.corpus = _corpus()
        self.retriever = self.corpus["retriever"]
        self.pages = self.corpus["pages"]
        self.llm = LLM()
        self.seq = itertools.count(1)
        self.citations: dict[str, dict] = {}
        self._cid = itertools.count(1)
        self.port = json.load(open(os.path.join(PORT_DIR, "portfolio_index.json")))

    def ev(self, kind, phase, title, detail="", *, payload=None, tier=None, model=None,
           mode=None, latency_ms=None):
        return {"seq": next(self.seq), "t": _now(), "kind": kind, "phase": phase, "title": title,
                "detail": detail, "tier": tier, "model": model, "mode": mode,
                "latency_ms": latency_ms, "payload": payload or {}}

    def cite_text(self, substr, doc_substr=None, tier=None):
        s = substr.lower()
        for p in self.pages:
            if doc_substr and doc_substr not in p["doc_id"]:
                continue
            for b in p["blocks"]:
                if s in b["text"].lower():
                    for cid, c in self.citations.items():
                        if c["doc_id"] == p["doc_id"] and c["block_id"] == b["id"]:
                            return cid
                    cid = f"c{next(self._cid)}"
                    self.citations[cid] = {
                        "id": cid, "doc_id": p["doc_id"], "doc_title": p["doc_title"],
                        "page": p["page"], "block_id": b["id"], "bbox": b["bbox"],
                        "image": p["image"], "width": p["width"], "height": p["height"],
                        "text": b["text"], "kind": b["kind"],
                        "scanned": "SCANNED" in p["doc_id"], "retriever_tier": tier}
                    return cid
        return None

    def _ranking(self):
        """Deterministic risk ranking + per-borrower CHECK MATRIX (review checks, not a bare list)."""
        cov = hospira.interest_coverage_from_cert("atlantic", "2015Q1")   # 3.21x vs 3.00x
        late = {x["borrower"]: x for x in hospira.filing_query("2015Q1")["late"]}

        hosp = ce.compute("2014Q4")                   # 3.592x
        fwd = ce.THRESHOLD_AFTER                       # 3.50 steps in for FQ after 2014-12-31
        rows = [{
            "borrower": "Hospira, Inc.", "ratio_2014q4": round(hosp.ratio_correct, 2),
            "forward_threshold": fwd, "forward_headroom": round(fwd - hosp.ratio_correct, 3),
            "trend": "thin & shrinking", "cap": "Device Strategy addback cap nearly exhausted",
            "deep_run": "S2",
            "checks": ["Leverage §6.6A (amended definitions)",
                       "Device Strategy addback capacity (285/290 — nearly exhausted)",
                       "Certificate cross-check (borrower-submitted 2014Q2 → S4)"]}]
        for name in ("Atlantic Beverage Partners Inc", "Cascadia Medical Supply Corp"):
            d = self.port["borrower_data"][name]
            ratios = d["ratios"]; r14q4 = ratios["2014Q4"]
            drift = ratios["2015Q1"] - ratios["2014Q1"]
            checks = [f"Leverage {r14q4:.2f}x vs {d['covenant_max']:.2f}x"]
            if "Atlantic" in name:
                if cov.get("ok"):
                    checks.append(f"Interest coverage {cov['coverage']:.2f}x vs {cov['min']:.2f}x min "
                                  f"(headroom {cov['headroom']:.2f}x)")
                checks.append(f"Upward drift {drift:+.2f}x over 5 quarters")
            else:
                checks[0] += " (light)"
                lt = late.get(name)
                checks.append("Filing timeliness: LATE by %d days (reporting-covenant flag)"
                              % lt["days_late"] if lt else "Filing timeliness: timely")
            rows.append({
                "borrower": name, "ratio_2014q4": r14q4, "forward_threshold": d["covenant_max"],
                "forward_headroom": round(d["covenant_max"] - r14q4, 3),
                "trend": ("upward drift " + f"{drift:+.2f}x/5Q" if drift > 0.05 else "stable"),
                "cap": "no addback capacity" if "Atlantic" in name else "no one-time charges",
                "deep_run": None, "checks": checks})
        rows.sort(key=lambda x: x["forward_headroom"])
        return rows

    def stream(self):
        yield self.ev("status", "PLAN", "Quarter closed — portfolio review",
                      "Ranking 3 borrowers by covenant risk before any deep check.",
                      payload={"scenario": SCENARIO_S0, "live": config.LIVE,
                               "backend": self.retriever.backend})

        # surface Hospira's latest certificate — a SCANNED, image-only page. VultronRetriever
        # retrieves it visually; we do NOT OCR it, so we cite it at the page level and take the
        # 3.59x from our own recomputation of 2014Q4 (not from reading the scan).
        yield self.ev("route", "PLAN", "Routing → Prime retriever",
                      "Surfacing Hospira's latest certificate — an image-only scan — via the "
                      "visual retriever.", tier="prime", model=TIER_MODEL["prime"])
        # the borrower's latest 2014Q4 certificate is a registry fact; VultronRetriever also
        # ranks it live. Present it deterministically so the messy-doc page always shows.
        scan_hit = self.retriever.retrieve("Hospira 2014Q4 compliance certificate", tier="prime", k=6)
        scan = [h for h in scan_hit if "SCANNED" in h.doc_id][:1]
        if not scan:
            scan = self._scanned_hit_from_corpus()
        payload = []
        for h in scan:
            cids = [self._reg_hit(h, b) for b in h.blocks]
            hd = h.to_dict(); hd["citation_ids"] = cids
            payload.append(hd)
        self.scan_read = bool(linker.find_block(self.pages, value=3.59, doc_substr="SCANNED")[1])
        reason = ("Hospira 2014Q4 compliance certificate — a scan. OCR reads 3.59x off the table; "
                  "our recomputation confirms it." if self.scan_read else
                  "Hospira 2014Q4 compliance certificate — an image-only scan (no OCR available); "
                  "surfaced visually, figure recomputed from financial data.")
        yield self.ev("retrieve", "PLAN", "Retrieval · scanned certificate", reason,
                      payload={"iteration": 1, "hits": payload,
                               "query": "Hospira 2014Q4 compliance certificate", "reason": reason},
                      tier="prime", model=TIER_MODEL["prime"], mode=self.retriever.backend)

        # non-numeric obligation: filing-deadline check over the filing log
        fq = hospira.filing_query("2015Q1")
        yield self.ev("tool", "PLAN", "Tool · filing_query",
                      (f"{len(fq['late'])} late filing(s): "
                       + ", ".join(f"{x['borrower'].split()[0]} +{x['days_late']}d" for x in fq["late"])
                       if fq["late"] else "all certificates filed on time")
                      + f" ({fq['timely_count']} timely, 45-day deadline).",
                      payload={"tool": "filing_query", "result": fq}, mode="code")

        ranking = self._ranking()
        # cite the 3.59x CELL when OCR read it off the scan; else page-level (no fabricated cell)
        c_scan = self._cite_value(3.59, "SCANNED") or self._cite_scanned_page()
        c_step = self._cite_value(3.50, "amendment") or self.cite_text("6.6A", "amendment")

        # LLM writes the reasons; the ORDER is deterministic
        system = ("You are a credit portfolio planner. Given the ranked borrowers and facts, write "
                  "a one-sentence risk reason for each. Do not change the order or invent numbers.")
        user = json.dumps(ranking)

        def offline():
            return {"reasons": {
                "Hospira, Inc.": "our recomputed 2014Q4 leverage of 3.59x is already ABOVE the "
                    "3.50x threshold that takes effect next quarter under the §6.6A step-down "
                    "(the borrower's latest certificate for this quarter is a scan), with thin, "
                    "shrinking headroom and the Device Strategy addback cap nearly exhausted.",
                "Atlantic Beverage Partners Inc": "0.19x headroom (3.31x vs 3.50x) after five "
                    "consecutive quarters of upward drift and no addback capacity — standard run + "
                    "trend warning.",
                "Cascadia Medical Supply Corp": "~1.4x headroom, stable, no one-time charges — a "
                    "light check suffices."}}
        res = self.llm.json_call(tier=PRIME, system=system, user=user,
                                 schema={"reasons": {}}, offline_fn=offline)
        reasons = res.data.get("reasons", {}) if isinstance(res.data, dict) else {}
        reasons = {**offline()["reasons"], **reasons}
        for row in ranking:
            row["reason"] = reasons.get(row["borrower"], "")

        yield self.ev("plan", "PLAN", "Portfolio ranked",
                      f"#1 {ranking[0]['borrower']} (forward headroom {ranking[0]['forward_headroom']:+.2f}x).",
                      payload={"ranking": ranking}, tier=res.tier, model=res.model, mode=res.mode,
                      latency_ms=res.latency_ms)

        # triage memo — a REVIEW MATRIX: each borrower carries its own check list + reasons
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        matrix = []
        for i, rr in enumerate(ranking):
            matrix.append(S(f"#{i+1} {rr['borrower']} — {rr['reason']}", [c_scan, c_step] if i == 0 else []))
            for chk in rr.get("checks", []):
                matrix.append(S(f"     • {chk}"))
        sections = [
            {"heading": "Priority ranking & review matrix", "sentences": matrix},
            {"heading": "Recommended next step", "sentences":
                [S(f"Deep-run {ranking[0]['borrower']} for {SCENARIO_S0['test_quarter']} now — the "
                   "step-down makes this quarter the decisive test.", [c_step])]},
        ]
        memo = {"recommendation": "triage", "confidence": 0.9,
                "headline": f"Highest risk: {ranking[0]['borrower']} — recomputed 2014Q4 leverage "
                            f"{ranking[0]['ratio_2014q4']:.2f}x is above the 3.50x step-down "
                            f"effective next quarter (its latest certificate is a scan).",
                "sections": sections}
        payload = {"memo": memo, "recommendation": "triage", "confidence": 0.9,
                   "headline": memo["headline"], "ratio_naive": None, "ratio_final": None,
                   "threshold": ce.THRESHOLD_AFTER, "headroom": None,
                   "citations": list(self.citations.values()), "borrower": "Portfolio (3 borrowers)",
                   "period": "quarter close", "ranking": ranking,
                   "documents": [d["title"] for d in self.corpus["documents"]],
                   "next_action": {"run": ranking[0]["deep_run"], "borrower": ranking[0]["borrower"]},
                   "covenant": {"name": "Maximum Leverage Ratio"}, "llm_calls": self.llm.calls}
        yield self.ev("memo", "MEMO", "Triage complete", memo["headline"], payload=payload,
                      tier="prime", model=config.MODEL_PRIME, mode=res.mode)
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · top risk: {ranking[0]['borrower']}",
                      payload={"llm_calls": self.llm.calls, "next_action": payload["next_action"]})

    def _cite_value(self, value, doc_substr=None):
        p, b = linker.find_block(self.pages, value=value, doc_substr=doc_substr)
        if not b:
            return None
        return self._reg_hit(type("H", (), {
            "doc_id": p["doc_id"], "doc_title": p["doc_title"], "page": p["page"],
            "image": p["image"], "width": p["width"], "height": p["height"]})(), b)

    def _scanned_page(self):
        return next((p for p in self.pages if "SCANNED" in p["doc_id"]), None)

    def _scanned_hit_from_corpus(self):
        from .retriever import hit_from_page
        p = self._scanned_page()
        return [hit_from_page(p, "compliance certificate", 0)] if p else []

    def _cite_scanned_page(self):
        """Cite the scanned certificate at the PAGE level (no OCR, no fabricated cell)."""
        p = self._scanned_page()
        if not p:
            return None
        b = p["blocks"][0]
        return self._reg_hit(type("H", (), {
            "doc_id": p["doc_id"], "doc_title": p["doc_title"], "page": p["page"],
            "image": p["image"], "width": p["width"], "height": p["height"]})(), b)

    def _reg_hit(self, h, b):
        for cid, c in self.citations.items():
            if c["doc_id"] == h.doc_id and c["block_id"] == b["id"]:
                return cid
        cid = f"c{next(self._cid)}"
        self.citations[cid] = {"id": cid, "doc_id": h.doc_id, "doc_title": h.doc_title,
                               "page": h.page, "block_id": b["id"], "bbox": b["bbox"],
                               "image": h.image, "width": h.width, "height": h.height,
                               "text": b["text"], "kind": b.get("kind"),
                               "scanned": "SCANNED" in h.doc_id, "retriever_tier": "prime"}
        return cid


def run_triage():
    try:
        yield from TriageRun().stream()
    except Exception as e:
        import traceback
        yield {"seq": -1, "t": _now(), "kind": "error", "phase": "-", "title": "Run error",
               "detail": str(e), "payload": {"trace": traceback.format_exc()[-1500:]}}
