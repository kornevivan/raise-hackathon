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

import httpx
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


_MARK = re.compile(r"\[\[(.+?)\]\]")


class VultrVectorStore:
    """Thin client for the Vultr Serverless Inference Vector Store (the service
    that fronts the VultronRetriever models)."""

    def __init__(self):
        self.base = config.VULTR_BASE_URL.rstrip("/")
        self._c = httpx.Client(base_url=self.base, timeout=90,
                               headers={"Authorization": f"Bearer {config.VULTR_INFERENCE_KEY}"})

    def ensure_collection(self, name: str, want_items: int, items: list[tuple[str, str]]):
        """Create the collection and (re)index `items` = [(page_uid, content)] if the
        item count doesn't already match. Idempotent across restarts."""
        existing = self._c.get(f"/vector_store/{name}/items")
        if existing.status_code == 200 and len(existing.json().get("items", [])) == want_items:
            return
        # clean slate
        self._c.delete(f"/vector_store/{name}")
        self._c.post("/vector_store", json={"name": name})
        for page_uid, content in items:
            self._c.post(f"/vector_store/{name}/items",
                         json={"content": f"[[{page_uid}]] {content}", "description": page_uid})

    def search(self, name: str, query: str, model: str, top_k: int) -> list[str]:
        """Return an ordered list of page_uids ranked by the VultronRetriever model."""
        r = self._c.post(f"/vector_store/{name}/search",
                         json={"input": query, "model": model, "top_k": top_k})
        r.raise_for_status()
        uids = []
        for res in r.json().get("results", []):
            m = _MARK.search(res.get("content", "") or "")
            if m and m.group(1) not in uids:
                uids.append(m.group(1))
        return uids


class VultrRetriever:
    """Ranking runs on the VultronRetriever models via the Vultr Vector Store;
    citations stay precise because we map each ranked page_uid back to the local
    page (blocks + bboxes). Any error degrades to LocalRetriever so the demo is
    always safe."""

    backend = "vultr"

    def __init__(self, borrower_id: str, pages: list[dict]):
        self.pages = pages
        self.by_uid = {p["page_uid"]: p for p in pages}
        self._local = LocalRetriever(pages)
        self.collection = f"cs-{borrower_id}"
        self._vs = VultrVectorStore()
        self._ready = False

    def _ensure(self):
        if self._ready:
            return
        items = [(p["page_uid"], p["text"]) for p in self.pages]
        self._vs.ensure_collection(self.collection, len(items), items)
        self._ready = True

    def _hit_from_page(self, p: dict, query: str, rank: int) -> Hit:
        q_tokens = set(_tok(query))
        scored = sorted(
            ((sum(1 for t in q_tokens if len(t) > 2 and t in b["text"].lower())
              + (2 if b.get("kind") == "table" else 0), b) for b in p["blocks"]),
            key=lambda x: x[0], reverse=True)
        top = [b for s, b in scored[:3] if s > 0] or [scored[0][1]]
        return Hit(page_uid=p["page_uid"], doc_id=p["doc_id"], doc_title=p["doc_title"],
                   kind=p["kind"], page=p["page"], image=p["image"], width=p["width"],
                   height=p["height"], scanned=p["scanned"],
                   score=round(1.0 / (rank + 1), 3), blocks=top)

    def retrieve(self, query: str, tier: str = "core", k: int = 4,
                 restrict_kind: str | None = None) -> list[Hit]:
        try:
            self._ensure()
            uids = self._vs.search(self.collection, query, model=TIER_MODEL[tier], top_k=max(k * 2, 6))
            hits: list[Hit] = []
            for rank, uid in enumerate(uids):
                p = self.by_uid.get(uid)
                if not p or (restrict_kind and p["kind"] != restrict_kind):
                    continue
                hits.append(self._hit_from_page(p, query, rank))
                if len(hits) >= k:
                    break
            if hits:
                return hits
        except Exception:
            pass
        # safe fallback — never break a run
        return self._local.retrieve(query, tier=tier, k=k, restrict_kind=restrict_kind)


_CACHE: dict[str, object] = {}


def build_retriever(borrower_id: str):
    if borrower_id in _CACHE:
        return _CACHE[borrower_id]
    pages = corpus.pages_for_borrower(borrower_id)
    r = VultrRetriever(borrower_id, pages) if config.LIVE else LocalRetriever(pages)
    _CACHE[borrower_id] = r
    return r
