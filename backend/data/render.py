"""Tiny layout engine: render a page to a PNG while recording the bounding box
and text of every block, so the agent can cite {doc_id, page, block_id} and the
UI can highlight the exact region — even on a scanned page.

No PDF toolchain required (no poppler/reportlab). Pages are images, which is
exactly what a visual page retriever like VultronRetriever consumes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

PAGE_W, PAGE_H = 1000, 1400
MARGIN = 70

_FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ],
    "mono": [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ],
}


def _load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES.get(kind, []):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default(size=size)


@dataclass
class Block:
    id: str
    bbox: list[int]  # [x, y, w, h]
    text: str
    kind: str = "paragraph"


@dataclass
class Page:
    doc_id: str
    number: int
    image_path: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.text.strip())

    def to_dict(self, rel_image: str) -> dict:
        return {
            "page": self.number,
            "image": rel_image,
            "width": PAGE_W,
            "height": PAGE_H,
            "text": self.text,
            "blocks": [
                {"id": b.id, "bbox": b.bbox, "text": b.text, "kind": b.kind}
                for b in self.blocks
            ],
        }


class PageBuilder:
    """Cursor-based vertical layout with block tracking."""

    def __init__(self, doc_id: str, number: int, bg=(252, 251, 248)):
        self.doc_id = doc_id
        self.number = number
        self.img = Image.new("RGB", (PAGE_W, PAGE_H), bg)
        self.draw = ImageDraw.Draw(self.img)
        self.y = MARGIN
        self.blocks: list[Block] = []
        self._bid = 0

    def _next_id(self) -> str:
        self._bid += 1
        return f"{self.doc_id}-p{self.number}-b{self._bid}"

    def _wrap(self, text: str, font, max_w: int) -> list[str]:
        words = text.split()
        lines, cur = [], ""
        for w in words:
            trial = (cur + " " + w).strip()
            if self.draw.textlength(trial, font=font) <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    def space(self, px: int):
        self.y += px

    def heading(self, text: str, size=30, kind="heading", center=True, color=(20, 24, 33)):
        font = _load_font("bold", size)
        w = self.draw.textlength(text, font=font)
        x = (PAGE_W - w) / 2 if center else MARGIN
        self.draw.text((x, self.y), text, font=font, fill=color)
        bid = self._next_id()
        self.blocks.append(Block(bid, [int(x), int(self.y), int(w), size + 6], text, kind))
        self.y += size + 14
        return bid

    def paragraph(self, text: str, size=20, kind="paragraph", bold=False,
                  indent=0, color=(30, 33, 40), gap=10, leading=8):
        font = _load_font("bold" if bold else "regular", size)
        max_w = PAGE_W - 2 * MARGIN - indent
        lines = self._wrap(text, font, max_w)
        y0 = self.y
        for ln in lines:
            self.draw.text((MARGIN + indent, self.y), ln, font=font, fill=color)
            self.y += size + leading
        bid = self._next_id()
        self.blocks.append(
            Block(bid, [MARGIN + indent, int(y0), max_w, int(self.y - y0)], text, kind)
        )
        self.y += gap
        return bid

    def table(self, title: Optional[str], headers: list[str], rows: list[list[str]],
              col_x: list[int], size=19, kind="table", highlight_rows: Optional[set] = None):
        """Render a simple table. Each data row becomes its own block (citable)."""
        highlight_rows = highlight_rows or set()
        bold = _load_font("bold", size)
        reg = _load_font("regular", size)
        if title:
            self.paragraph(title, size=size + 2, bold=True, gap=6)
        # header
        hy = self.y
        for i, h in enumerate(headers):
            self.draw.text((MARGIN + col_x[i], hy), h, font=bold, fill=(20, 24, 33))
        self.y += size + 8
        self.draw.line([(MARGIN, self.y), (PAGE_W - MARGIN, self.y)], fill=(120, 120, 120), width=2)
        self.y += 6
        row_ids = []
        for ridx, row in enumerate(rows):
            ry = self.y
            if ridx in highlight_rows:
                self.draw.rectangle(
                    [MARGIN - 6, ry - 3, PAGE_W - MARGIN + 6, ry + size + 6],
                    fill=(255, 246, 224),
                )
            for i, cell in enumerate(row):
                f = bold if i == 0 else reg
                self.draw.text((MARGIN + col_x[i], ry), cell, font=f, fill=(30, 33, 40))
            self.y += size + 12
            bid = self._next_id()
            self.blocks.append(
                Block(bid, [MARGIN, int(ry), PAGE_W - 2 * MARGIN, size + 10],
                      "  ".join(row), kind)
            )
            row_ids.append(bid)
        self.y += 10
        return row_ids

    def rule(self, gap=14):
        self.y += gap // 2
        self.draw.line([(MARGIN, self.y), (PAGE_W - MARGIN, self.y)], fill=(180, 180, 180), width=1)
        self.y += gap // 2

    def footer(self, text: str):
        font = _load_font("regular", 15)
        w = self.draw.textlength(text, font=font)
        self.draw.text(((PAGE_W - w) / 2, PAGE_H - 46), text, font=font, fill=(140, 140, 140))

    def save(self, out_dir: str) -> Page:
        rel = f"{self.doc_id}/p{self.number}.png"
        path = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.img.save(path)
        return Page(self.doc_id, self.number, rel, self.blocks)


def scanify(page_img_path: str, seed: int = 7):
    """Turn a clean page into a believable scan: desaturate, add paper noise,
    slight rotation and a soft shadow. The retriever/agent must still read it."""
    import random

    rnd = random.Random(seed)
    img = Image.open(page_img_path).convert("RGB")
    # paper tint + noise
    px = img.load()
    for _ in range(9000):
        x = rnd.randint(0, img.width - 1)
        y = rnd.randint(0, img.height - 1)
        d = rnd.randint(-18, 8)
        r, g, b = px[x, y]
        px[x, y] = (max(0, min(255, r + d)), max(0, min(255, g + d)), max(0, min(255, b + d - 6)))
    # slight skew
    img = img.rotate(rnd.uniform(-1.6, 1.6), expand=False, fillcolor=(238, 236, 230), resample=Image.BICUBIC)
    img.save(page_img_path)
