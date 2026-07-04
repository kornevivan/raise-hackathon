"""Upload ingestion: turn arbitrary uploaded documents into the same page/block
model the built-in corpus uses, so retrieval, citations and highlighting all work
on documents the user brings. PDFs are rendered to page images with text + bbox
extracted via PyMuPDF; each page is indexed into a Vultr Vector Store collection
so ranking runs on the VultronRetriever models."""
from __future__ import annotations

import os
import re
import uuid

import fitz  # PyMuPDF

from . import config
from .retriever import VultrVectorStore, LocalRetriever, TIER_MODEL, hit_from_page

UPLOAD_DIR = os.path.join(config.DATA_DIR, "uploads")
ZOOM = 2.0  # 144 dpi render

# in-memory registry: upload_id -> {documents, pages, retriever}
UPLOADS: dict[str, dict] = {}

_NUM = re.compile(r"\d")


def _block_kind(text: str) -> str:
    t = text.strip()
    if _NUM.search(t) and ("  " in t or re.search(r"\d[\d,]*\.?\d*\s*$", t)):
        return "table"
    if len(t) < 60 and t.isupper():
        return "heading"
    return "paragraph"


def _pdf_pages(upload_id: str, doc_id: str, title: str, data: bytes, out_dir: str) -> list[dict]:
    pages = []
    pdf = fitz.open(stream=data, filetype="pdf")
    for i, page in enumerate(pdf, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
        rel = f"{doc_id}/p{i}.png"
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pix.save(path)
        served = f"/uploads/{upload_id}/{rel}"
        blocks = []
        for bi, b in enumerate(page.get_text("blocks"), start=1):
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            text = " ".join(text.split())
            if not text:
                continue
            blocks.append({
                "id": f"{doc_id}-p{i}-b{bi}",
                "bbox": [int(x0 * ZOOM), int(y0 * ZOOM),
                         int((x1 - x0) * ZOOM), int((y1 - y0) * ZOOM)],
                "text": text, "kind": _block_kind(text),
            })
        scanned = not blocks   # image-only PDF page → no text layer (a real scan)
        if scanned:
            # B5: OCR the scan when Tesseract is available (prod) → real word text + bboxes, so a
            # citation can highlight the actual cell. When it isn't (local/CI), degrade honestly to
            # a page-level reference (never fabricate row text/positions).
            ocr = _ocr_blocks(pix, doc_id, i)
            blocks = ocr or [{"id": f"{doc_id}-p{i}-b1", "bbox": None,
                              "text": "[scanned page — image only; retrieved visually by VultronRetriever]",
                              "kind": "scanned"}]
        pages.append({
            "doc_id": doc_id, "doc_title": title, "kind": "uploaded",
            "borrower_id": None, "scanned": scanned, "page": i,
            "image": served, "width": pix.width, "height": pix.height,
            "text": "\n".join(b["text"] for b in blocks),
            "blocks": blocks, "page_uid": f"{doc_id}#p{i}",
        })
    pdf.close()
    return pages


def _ocr_blocks(pix, doc_id: str, page: int):
    """OCR an image-only page with Tesseract, returning line-level blocks with real bboxes.
    Returns None if pytesseract/Tesseract is unavailable (honest page-level fallback)."""
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return None
    try:
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    except Exception:
        return None
    lines: dict = {}
    for j in range(len(d["text"])):
        w = (d["text"][j] or "").strip()
        if not w or int(d.get("conf", ["-1"])[j] or -1) < 30:
            continue
        key = (d["block_num"][j], d["par_num"][j], d["line_num"][j])
        x, y, ww, hh = d["left"][j], d["top"][j], d["width"][j], d["height"][j]
        L = lines.setdefault(key, {"words": [], "x0": x, "y0": y, "x1": x + ww, "y1": y + hh})
        L["words"].append(w)
        L["x0"], L["y0"] = min(L["x0"], x), min(L["y0"], y)
        L["x1"], L["y1"] = max(L["x1"], x + ww), max(L["y1"], y + hh)
    blocks = []
    for k, (key, L) in enumerate(sorted(lines.items()), 1):
        txt = " ".join(L["words"])
        blocks.append({"id": f"{doc_id}-p{page}-b{k}",
                       "bbox": [L["x0"], L["y0"], L["x1"] - L["x0"], L["y1"] - L["y0"]],
                       "text": txt, "kind": "table" if any(c.isdigit() for c in txt) else "paragraph"})
    return blocks or None


def _txt_page(doc_id: str, title: str, data: bytes) -> list[dict]:
    text = data.decode("utf-8", "ignore")
    return [{"doc_id": doc_id, "doc_title": title, "kind": "uploaded", "borrower_id": None,
             "scanned": False, "page": 1, "image": None, "width": 1000, "height": 1400,
             "text": text,
             "blocks": [{"id": f"{doc_id}-p1-b1", "bbox": [0, 0, 1000, 1400],
                         "text": text[:4000], "kind": "paragraph"}],
             "page_uid": f"{doc_id}#p1"}]


class UploadedRetriever:
    """Same interface as the other retrievers; ranks via VultronRetriever when live,
    else local BM25 over the uploaded pages."""

    def __init__(self, upload_id: str, pages: list[dict]):
        self.pages = pages
        self.by_uid = {p["page_uid"]: p for p in pages}
        self._local = LocalRetriever(pages)
        self.backend = "vultr" if config.LIVE else "local"
        self.collection = f"up-{upload_id}"
        self._vs = VultrVectorStore() if config.LIVE else None
        self._ready = False

    def _ensure(self):
        if self._ready or not self._vs:
            return
        items = [(p["page_uid"], p["text"]) for p in self.pages if p["text"].strip()]
        self._vs.ensure_collection(self.collection, len(items), items)
        self._ready = True

    def retrieve(self, query, tier="core", k=4, restrict_kind=None):
        if self._vs:
            try:
                self._ensure()
                uids = self._vs.search(self.collection, query, model=TIER_MODEL[tier], top_k=max(k * 2, 6))
                hits = []
                for rank, uid in enumerate(uids):
                    p = self.by_uid.get(uid)
                    if not p:
                        continue
                    hits.append(hit_from_page(p, query, rank))
                    if len(hits) >= k:
                        break
                if hits:
                    return hits
            except Exception:
                pass
        return self._local.retrieve(query, tier=tier, k=k, restrict_kind=restrict_kind)


def ingest(files: list[tuple[str, bytes]], collection: str | None = None) -> dict:
    """files = [(filename, bytes)]. Returns {upload_id, documents, page_count}.
    A fixed `collection` gives a stable Vultr Vector Store name that persists across
    processes (sample corpora), so the deployed demo reuses the index instead of
    re-indexing on every boot."""
    upload_id = collection or uuid.uuid4().hex[:10]
    out_dir = os.path.join(UPLOAD_DIR, upload_id)
    os.makedirs(out_dir, exist_ok=True)
    all_pages, documents = [], []
    for idx, (fname, data) in enumerate(files):
        base = re.sub(r"[^a-zA-Z0-9]+", "_", os.path.splitext(fname)[0])[:40] or f"doc{idx}"
        doc_id = f"{base}"
        title = os.path.splitext(fname)[0]
        ext = os.path.splitext(fname)[1].lower()
        try:
            if ext == ".pdf":
                pages = _pdf_pages(upload_id, doc_id, title, data, out_dir)
            elif ext in (".txt", ".md", ".csv"):
                pages = _txt_page(doc_id, title, data)
            else:
                continue  # skip unsupported (images w/o OCR, etc.)
        except Exception:
            continue
        if not pages:
            continue
        documents.append({"doc_id": doc_id, "title": title, "kind": "uploaded",
                          "page_count": len(pages)})
        all_pages.extend(pages)

    UPLOADS[upload_id] = {
        "documents": documents, "pages": all_pages,
        "retriever": UploadedRetriever(upload_id, all_pages),
        "by_block": {(p["doc_id"], p["page"], b["id"]): {**b, **{
            "doc_id": p["doc_id"], "page": p["page"], "image": p["image"],
            "doc_title": p["doc_title"], "width": p["width"], "height": p["height"]}}
            for p in all_pages for b in p["blocks"]},
    }
    return {"upload_id": upload_id, "documents": documents, "page_count": len(all_pages)}
