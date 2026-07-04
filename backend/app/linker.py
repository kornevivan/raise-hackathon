"""General evidence linker (B3) — links a computed value or an extracted span to the
page block that supports it, with numeric / threshold / date normalization. Replaces
tuned substring lookups so citations resolve on real-filing phrasing:
    "$290,000,000" == "290.0 million" == "290,000,000"
    "3.50:1.00"    == "3.50 to 1.00"  == "3.50x"
Candidate spans come from the ACTUAL ingested pages (PyMuPDF text).
"""
from __future__ import annotations

import re


def _num(x) -> float | None:
    try:
        return float(str(x).replace(",", "").replace("$", "").strip())
    except Exception:
        return None


def value_variants(value: float) -> list[str]:
    """String forms the same monetary/ratio value can appear as in a filing."""
    v = float(value)
    out = set()
    # ratio forms
    out.update({f"{v:.2f}", f"{v:.2f}x", f"{v:.2f} to 1", f"{v:.2f} to 1.00", f"{v:.2f}:1.00",
                f"{v:.1f}"})
    # money forms (value given in $M)
    if v >= 1:
        out.add(f"{v:,.1f} million")
        out.add(f"{v:,.0f} million")
        whole = int(round(v * 1_000_000))
        out.add(f"{whole:,}")            # 290,000,000
        out.add(f"${whole:,}")
        out.add(f"{v:,.1f}")             # 290.0
        out.add(f"{v:,.0f}")             # 290
    return [s for s in out if s]


def find_block(pages, value=None, text=None):
    """Return (page, block) whose text supports `value` (any variant) or contains `text`.
    Prefers table blocks / shorter blocks for a tighter highlight. Callers scope the document
    set by ROLE (docroles) before calling — the linker itself does no filename matching."""
    variants = [v.lower() for v in value_variants(value)] if value is not None else []
    needle = (text or "").lower().strip()
    best = None
    for p in pages:
        for b in p["blocks"]:
            t = b["text"].lower()
            hit = (needle and needle[:40] in t) or any(v in t for v in variants)
            if not hit:
                # numeric fallback: normalized number appears as a token
                if value is not None:
                    toks = re.findall(r"\$?[\d,]+(?:\.\d+)?", t)
                    hit = any(_num(tok) == _num(f"{value:.1f}") or _num(tok) == round(value * 1e6)
                              for tok in toks)
                if not hit:
                    continue
            score = (2 if b.get("kind") == "table" else 0) - len(b["text"]) / 500.0
            if best is None or score > best[0]:
                best = (score, p, b)
    return (best[1], best[2]) if best else (None, None)
