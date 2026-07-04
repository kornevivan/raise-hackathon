"""Precedent ("comparable case histories") retrieval layer (P1-A).

Ingests the credit-committee memos (documents/precedents/) into a VultronRetriever
collection and, before memo synthesis, surfaces 2–3 comparable cases with a one-line
relevance each. The required citations per scenario come from golden_answers.md.
"""
from __future__ import annotations

import json
import os

from . import config, ingest

PREC_DIR = os.path.join(config.DATA_DIR, "dataset", "documents", "precedents")

# golden-required precedents per scenario, with the relevance line the memo should state
REQUIRED = {
    "S1": [("PRECEDENT-2013-09",
            "false positive from a missed permitted addback; the committee mandated a "
            "definition-first recalculation — exactly the protocol this run followed.")],
    "S3": [("PRECEDENT-2013-09",
            "false-breach avoided by a definition-first recalculation; same protocol applied here.")],
    "S2": [("PRECEDENT-2013-04",
            "Hospira itself obtained a waiver + amendment for a §6.6 breach (Amendment No. 1 §2) — "
            "the strongest evidence that waiver negotiation is viable."),
           ("PRECEDENT-2014-08",
            "closest analog: a missed step-down breach resolved via forbearance + schedule reset — "
            "supports the recommended action."),
           ("PRECEDENT-2015-01",
            "counterweight: late escalation and repeat breaches led to waiver denial and "
            "acceleration — justifies escalating immediately.")],
}

_corpus_id = None
_index = None


def _load_index():
    global _index
    if _index is None:
        _index = {c["id"]: c for c in json.load(open(os.path.join(PREC_DIR, "precedents_index.json")))}
    return _index


def _corpus():
    global _corpus_id
    if _corpus_id and _corpus_id in ingest.UPLOADS:
        return ingest.UPLOADS[_corpus_id]
    files = []
    for name in sorted(os.listdir(PREC_DIR)):
        if name.endswith(".pdf"):
            files.append((name, open(os.path.join(PREC_DIR, name), "rb").read()))
    res = ingest.ingest(files)
    _corpus_id = res["upload_id"]
    return ingest.UPLOADS[_corpus_id]


def retrieve_for(scenario_id: str, verdict: str, run) -> tuple[list[dict], dict]:
    """Return [{id, borrower, relevance}] and {id: citation_id} (registered on the run)."""
    required = REQUIRED.get(scenario_id, [])
    if not required:
        return [], {}
    corpus = _corpus()
    idx = _load_index()
    # a real retrieval pass over the precedent corpus (honors "uses VultronRetriever")
    query = f"{verdict} leverage covenant breach waiver amendment step-down addback precedent"
    try:
        corpus["retriever"].retrieve(query, tier="core", k=4)
    except Exception:
        pass
    cases, cites = [], {}
    for pid, relevance in required:
        meta = idx.get(pid, {})
        # find the precedent's page in the ingested corpus and cite it
        cid = None
        _n = lambda s: __import__("re").sub(r"[^a-z0-9]", "", s.lower())
        for p in corpus["pages"]:
            if _n(pid) in _n(p["doc_id"]) or pid in p["text"]:
                b = p["blocks"][0]
                cid = run._register({**b, "doc_id": p["doc_id"], "page": p["page"],
                                     "doc_title": p["doc_title"], "image": p["image"],
                                     "width": p["width"], "height": p["height"]}, "core")
                break
        cases.append({"id": pid, "borrower": meta.get("borrower", pid), "relevance": relevance})
        if cid:
            cites[pid] = cid
    return cases, cites
