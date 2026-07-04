"""Loads the generated corpus and exposes pages/blocks for retrieval and the UI."""
from __future__ import annotations

import json
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def load_index() -> dict:
    with open(config.INDEX_PATH) as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def all_pages() -> list[dict]:
    """Flat list of pages, each carrying its parent document metadata."""
    pages = []
    for doc in load_index()["documents"]:
        for pg in doc["pages"]:
            pages.append({
                "doc_id": doc["doc_id"],
                "doc_title": doc["title"],
                "kind": doc["kind"],
                "borrower_id": doc.get("borrower_id"),
                "scanned": doc.get("scanned", False),
                "page": pg["page"],
                "image": pg["image"],
                "width": pg["width"],
                "height": pg["height"],
                "text": pg["text"],
                "blocks": pg["blocks"],
                "page_uid": f"{doc['doc_id']}#p{pg['page']}",
            })
    return pages


def pages_for_borrower(borrower_id: str) -> list[dict]:
    return [p for p in all_pages() if p["borrower_id"] == borrower_id]


def get_block(doc_id: str, page: int, block_id: str) -> dict | None:
    for p in all_pages():
        if p["doc_id"] == doc_id and p["page"] == page:
            for b in p["blocks"]:
                if b["id"] == block_id:
                    return {**b, "doc_id": doc_id, "page": page,
                            "image": p["image"], "doc_title": p["doc_title"],
                            "width": p["width"], "height": p["height"]}
    return None


def scenarios() -> list[dict]:
    return load_index()["scenarios"]
