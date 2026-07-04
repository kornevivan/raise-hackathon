"""Precedent ("comparable case histories") retrieval (B4). No hardcoded ID list — a query
is built from the run's verdict + cause tags and the top matches are RETRIEVED from the
`precedents` collection (VultronRetriever), then the memo writer selects/justifies them.
"""
from __future__ import annotations

import json
import os
import re

from . import config, ingest

PREC_DIR = os.path.join(config.DATA_DIR, "dataset", "documents", "precedents")

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
    files = [(n, open(os.path.join(PREC_DIR, n), "rb").read())
             for n in sorted(os.listdir(PREC_DIR)) if n.endswith(".pdf")]
    res = ingest.ingest(files, collection="precedents")
    _corpus_id = res["upload_id"]
    return ingest.UPLOADS[_corpus_id]


def _pid(doc_id: str) -> str:
    m = re.search(r"(\d{4})[_-](\d{2})", doc_id)
    return f"PRECEDENT-{m.group(1)}-{m.group(2)}" if m else doc_id


def _query(verdict: str, cause_tags: list[str]) -> str:
    base = {
        "breach": "covenant breach event of default waiver amendment forbearance acceleration "
                  "waiver declined step-down threshold reset",
        "false_positive": "false positive breach reversed missed permitted addback definition "
                          "recalculation no breach process",
        "compliant": "thin headroom enhanced monitoring covenant projection no breach",
    }.get(verdict, "leverage covenant")
    return base + " " + " ".join(cause_tags)


def _relevance(meta: dict) -> str:
    ev = meta.get("event", "").rstrip(".")
    dec = meta.get("decision", "").split(".")[0]
    return (ev + " — " + dec).strip(" —")[:220]


def retrieve_for(verdict: str, cause_tags: list[str], run=None, k: int = 3):
    """Return top-k precedents [{id, borrower, relevance, tags}] and {id: citation_id}."""
    corpus = _corpus()
    idx = _load_index()
    try:
        hits = corpus["retriever"].retrieve(_query(verdict, cause_tags), tier="core", k=k)
    except Exception:
        hits = []
    cases, cites = [], {}
    for h in hits:
        pid = _pid(h.doc_id)
        meta = idx.get(pid, {})
        cases.append({"id": pid, "borrower": meta.get("borrower", pid),
                      "relevance": _relevance(meta), "tags": meta.get("tags", "")})
        if run is not None and h.blocks:
            b = h.blocks[0]
            cites[pid] = run._register({**b, "doc_id": h.doc_id, "page": h.page,
                                        "doc_title": h.doc_title, "image": h.image,
                                        "width": h.width, "height": h.height}, "core")
    return cases, cites
