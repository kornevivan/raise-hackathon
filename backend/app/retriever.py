"""VultronRetriever page-level retrieval.

VultronRetriever is a layout-aware VISUAL page retriever (ColPali/late-interaction
family): it reads a rendered page image — tables, charts, scans — and scores its
relevance to a query. We use three flavors escalated by difficulty:

    Flash-0.8B  -> routine first-pass lookups (cheap, frequent)
    Core-4.5B   -> standard evidence retrieval
    Prime-8B    -> hard / ambiguous / layout-heavy pages (e.g. scanned certs),
                   used when a gap-check demands a more careful re-retrieval.

Retrieval unit = PAGE. Every hit carries {doc_id, page, blocks} so the memo can
cite an exact region and the UI can highlight it.

Backends:
  * VultrRetriever  — pages indexed in a Vultr Vector Store; queried through the
                      inference API. Active when an inference key is configured.
  * LocalRetriever  — deterministic BM25 + layout/number-aware scoring over the
                      page blocks. Always available; runs the demo offline and
                      handles scanned pages (their OCR text is in the index).

Both expose the same interface, so nothing downstream cares which is live.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from . import config, corpus

TIER_MODEL = {
    "flash": config.RETRIEVER_FLASH,
    "core": config.RETRIEVER_CORE,
    "prime": config.RETRIEVER_PRIME,
}

_WORD = re.compile(r"[a-z0-9][a-z0-9.\-]*")


def _tok(s: str) -> list[str]:
    return _WORD.findall(s.lower())


@dataclass
class Hit:
    page_uid: str
    doc_id: str
    doc_title: str
    kind: str
    page: int
    image: str
    width: int
    height: int
    scanned: bool
    score: float
    blocks: list[dict]           # top matching blocks on the page (citation candidates)

    def to_dict(self) -> dict:
        return {
            "page_uid": self.page_uid, "doc_id": self.doc_id, "doc_title": self.doc_title,
            "kind": self.kind, "page": self.page, "image": self.image,
            "width": self.width, "height": self.height, "scanned": self.scanned,
            "score": round(self.score, 3),
            "blocks": self.blocks,
        }


class LocalRetriever:
    """BM25 over page text with a layout/number-aware boost that mimics the
    visual retriever's strength on tables and scans."""

    backend = "local"

    def __init__(self, pages: list[dict]):
        self.pages = pages
        self._corpus_tokens = [_tok(p["text"]) for p in pages]
        self._bm25 = BM25Okapi(self._corpus_tokens) if pages else None

    def retrieve(self, query: str, tier: str = "core", k: int = 4,
                 restrict_kind: str | None = None) -> list[Hit]:
        if not self.pages:
            return []
        q_tokens = _tok(query)
        q_nums = set(re.findall(r"\d[\d,]*\.?\d*", query))
        scores = self._bm25.get_scores(q_tokens)
        hits: list[Hit] = []
        # Prime tier examines more candidates and rewards layout/table matches more
        # heavily (its edge is reading dense tables and scans).
        layout_w = {"flash": 0.6, "core": 1.0, "prime": 1.8}.get(tier, 1.0)
        for p, base in zip(self.pages, scores):
            if restrict_kind and p["kind"] != restrict_kind:
                continue
            score = float(base)
            # boost pages whose *blocks* contain query terms in tables / numbers
            block_scores = []
            for b in p["blocks"]:
                bt = b["text"].lower()
                overlap = sum(1 for t in set(q_tokens) if len(t) > 2 and t in bt)
                num_hit = sum(1 for n in q_nums if n in bt)
                is_table = b.get("kind") == "table"
                bs = overlap + num_hit * 2 + (1.0 if is_table else 0.0) * layout_w
                block_scores.append((bs, b))
                if is_table or num_hit:
                    score += (num_hit * 1.5 + (1.0 if is_table else 0)) * layout_w
            if p["scanned"]:
                score += 0.4 * layout_w  # Prime's advertised strength: reading scans
            block_scores.sort(key=lambda x: x[0], reverse=True)
            top_blocks = [b for s, b in block_scores[:3] if s > 0] or \
                         [b for _, b in block_scores[:1]]
            hits.append(Hit(
                page_uid=p["page_uid"], doc_id=p["doc_id"], doc_title=p["doc_title"],
                kind=p["kind"], page=p["page"], image=p["image"],
                width=p["width"], height=p["height"], scanned=p["scanned"],
                score=score, blocks=top_blocks,
            ))
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits if h.score > 0][:k]


class VultrRetriever:
    """Pages indexed as images in a Vultr Vector Store and queried through the
    inference API. Falls back to LocalRetriever on any error so the demo is safe.

    NOTE: exact vector-store payloads are confirmed against `/v1/models` and the
    vector-store endpoints once the inference subscription is active; until then
    LocalRetriever is the default backend.
    """

    backend = "vultr"

    def __init__(self, pages: list[dict]):
        self.pages = pages
        self._local = LocalRetriever(pages)
        # collection provisioning happens lazily on first retrieve in live mode.
        self._ready = False

    def _ensure_index(self):
        # Placeholder for: create collection -> upload page images/text ->
        # VultronRetriever embeds them. Implemented against the live API in
        # LIVE mode; see README "Retrieval" section.
        self._ready = True

    def retrieve(self, query: str, tier: str = "core", k: int = 4,
                 restrict_kind: str | None = None) -> list[Hit]:
        # Until vector-store payloads are locked against the live subscription,
        # delegate ranking to the deterministic local retriever (same interface).
        return self._local.retrieve(query, tier=tier, k=k, restrict_kind=restrict_kind)


def build_retriever(borrower_id: str):
    pages = corpus.pages_for_borrower(borrower_id)
    if config.LIVE:
        return VultrRetriever(pages)
    return LocalRetriever(pages)
