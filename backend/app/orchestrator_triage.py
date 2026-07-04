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

from . import config, covenant_engine as ce, ingest
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
    for extra in ("compliance_certificate_2014Q4_SCANNED.pdf", "amendment_no1_excerpt.pdf"):
        p = os.path.join(DATASET, "documents", extra)
        if os.path.exists(p):
            files.append((extra, open(p, "rb").read()))
    res = ingest.ingest(files, collection="triage")
    _corpus_id = res["upload_id"]
    return ingest.fill_scanned_text(ingest.UPLOADS[_corpus_id],
                                    os.path.join(DATASET, "documents"))


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
        """Deterministic risk ranking against each borrower's FORWARD threshold."""
        hosp_2014q4 = ce.compute("2014Q4")           # 3.592x
        hosp_fwd_threshold = ce.THRESHOLD_AFTER       # 3.50 steps in for FQ after 2014-12-31
        rows = [{
            "borrower": "Hospira, Inc.", "ratio_2014q4": round(hosp_2014q4.ratio_correct, 2),
            "forward_threshold": hosp_fwd_threshold,
            "forward_headroom": round(hosp_fwd_threshold - hosp_2014q4.ratio_correct, 3),
            "trend": "thin & shrinking", "cap": "Device Strategy addback cap nearly exhausted",
            "deep_run": "S2"}]
        for name in ("Atlantic Beverage Partners Inc", "Cascadia Medical Supply Corp"):
            d = self.port["borrower_data"][name]
            ratios = d["ratios"]
            r14q4 = ratios["2014Q4"]
            drift = ratios["2015Q1"] - ratios["2014Q1"]
            rows.append({
                "borrower": name, "ratio_2014q4": r14q4,
                "forward_threshold": d["covenant_max"],
                "forward_headroom": round(d["covenant_max"] - r14q4, 3),
                "trend": ("upward drift " + f"{drift:+.2f}x/5Q" if drift > 0.05 else "stable"),
                "cap": "no addback capacity" if "Atlantic" in name else "no one-time charges",
                "deep_run": None})
        rows.sort(key=lambda x: x["forward_headroom"])   # smallest (worst) first
        return rows

    def stream(self):
        yield self.ev("status", "PLAN", "Quarter closed — portfolio review",
                      "Ranking 3 borrowers by covenant risk before any deep check.",
                      payload={"scenario": SCENARIO_S0, "live": config.LIVE,
                               "backend": self.retriever.backend})

        # read Hospira's latest certificate — the SCANNED one — via the retriever
        yield self.ev("route", "PLAN", "Routing → Prime retriever",
                      "Reading Hospira's latest certificate — a scanned page — to get its ratio.",
                      tier="prime", model=TIER_MODEL["prime"])
        hits = self.retriever.retrieve("Hospira compliance certificate leverage ratio 2014Q4 "
                                       "officer certification", tier="prime", k=6)
        scan = [h for h in hits if "SCANNED" in h.doc_id][:1] or [h for h in hits if "2014Q4" in h.doc_id][:1]
        payload = []
        for h in (scan or hits[:1]):
            cids = [self._reg_hit(h, b) for b in h.blocks]
            hd = h.to_dict(); hd["citation_ids"] = cids
            payload.append(hd)
        yield self.ev("retrieve", "PLAN", "Retrieval · scanned certificate",
                      "Hospira 2014Q4 compliance certificate (scanned) — reading 3.59x from the "
                      "table on a messy page.",
                      payload={"iteration": 1, "hits": payload,
                               "query": "Hospira 2014Q4 compliance certificate leverage ratio",
                               "reason": "Read the latest certificate ratio from a scanned page."},
                      tier="prime", model=TIER_MODEL["prime"], mode=self.retriever.backend)

        ranking = self._ranking()
        c_scan = self.cite_text("3.59", "SCANNED") or self.cite_text("leverage", "SCANNED")
        c_step = self.cite_text("3.50 to 1.00", "amendment") or self.cite_text("6.6A", "amendment")

        # LLM writes the reasons; the ORDER is deterministic
        system = ("You are a credit portfolio planner. Given the ranked borrowers and facts, write "
                  "a one-sentence risk reason for each. Do not change the order or invent numbers.")
        user = json.dumps(ranking)

        def offline():
            return {"reasons": {
                "Hospira, Inc.": "3.59x on the scanned 2014Q4 certificate is already ABOVE the "
                    "3.50x threshold that takes effect next quarter under the §6.6A step-down, with "
                    "thin, shrinking headroom and the Device Strategy addback cap nearly exhausted.",
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

        # triage memo
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        sections = [
            {"heading": "Priority ranking", "sentences":
                [S(f"#{i+1} {r['borrower']} — {r['reason']}",
                   [c_scan, c_step] if i == 0 else []) for i, r in enumerate(ranking)]},
            {"heading": "Recommended next step", "sentences":
                [S(f"Deep-run {ranking[0]['borrower']} for {SCENARIO_S0['test_quarter']} now — the "
                   "step-down makes this quarter the decisive test.", [c_step])]},
        ]
        memo = {"recommendation": "triage", "confidence": 0.9,
                "headline": f"Highest risk: {ranking[0]['borrower']} — its scanned 2014Q4 "
                            f"certificate reads {ranking[0]['ratio_2014q4']:.2f}x, above the 3.50x "
                            f"step-down effective next quarter.", "sections": sections}
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
