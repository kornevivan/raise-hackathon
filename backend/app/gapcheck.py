"""Generalized gap-check trigger (P1-C).

Deterministic rule: if retrieved covenant text references a governing INSTRUMENT
(amendment / amended-and-restated / waiver / supplement / forbearance, with ordinal
variants) that has not yet been applied in the run, that is a gap → retrieve it. The
LLM only writes the explanation, never the verdict. NOT keyed to any literal document
name, so it works on "Second Amendment", "Amended and Restated Credit Agreement", etc.
"""
from __future__ import annotations

import re

_ORDINALS = (r"No\.?\s*\d+|First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth|"
             r"\d{4}")

_PATTERNS = [
    re.compile(r"\b((?:" + _ORDINALS + r")\s+Amendment)\b", re.I),
    re.compile(r"\b(Amendment\s+(?:" + _ORDINALS + r"))\b", re.I),
    re.compile(r"\b(Amended and Restated(?:\s+[A-Z][A-Za-z]+){0,4})", re.I),
    re.compile(r"\b(Forbearance(?:\s+Agreement)?)\b", re.I),
    re.compile(r"\b(Waiver(?:\s+(?:and|&)\s+Amendment)?)\b", re.I),
    re.compile(r"\b(Supplement(?:al)?(?:\s+Agreement)?)\b", re.I),
]


def detect_instrument(text: str) -> str | None:
    """Return a short instrument name if the text references one, else None."""
    if not text:
        return None
    best = None
    for pat in _PATTERNS:
        m = pat.search(text)
        if m:
            name = " ".join(m.group(1).split())
            # prefer the earliest occurrence in the text
            if best is None or m.start() < best[1]:
                best = (name, m.start())
    return best[0] if best else None
