"""Document ROLE registry — the single place that classifies a corpus document by the part it
plays (base agreement, amendment, quarterly report, scanned certificate, ...). The orchestrators
and tools filter by ROLE, never by an inline filename pattern (B6): if a document were named
differently, only this registry changes. Classification uses the doc_id because that is the only
metadata the retriever carries; the point is that it lives in ONE registry with role semantics,
not as magic substrings sprinkled through the business logic.
"""
from __future__ import annotations

# role -> predicate over a lower-cased doc_id
_ROLES = {
    "base_agreement":       lambda d: "credit_agreement" in d,
    "amendment":            lambda d: "amend" in d,
    "financial_report":     lambda d: "financial_report" in d,
    "scanned_certificate":  lambda d: "scanned" in d,
    "borrower_certificate": lambda d: "borrower_submitted" in d,
    "compliance_certificate": lambda d: "compliance_certificate" in d and "scanned" not in d,
    "portfolio_profile":    lambda d: "profile_" in d,
    "portfolio_certificate": lambda d: "certificate_" in d,
    "precedent":            lambda d: "precedent" in d,
}


def matches(doc_id: str, role: str) -> bool:
    pred = _ROLES.get(role)
    return bool(pred and doc_id and pred(doc_id.lower()))


def role_of(doc_id: str) -> str | None:
    d = (doc_id or "").lower()
    for role, pred in _ROLES.items():
        if pred(d):
            return role
    return None


def is_scanned(doc_id: str) -> bool:
    return matches(doc_id, "scanned_certificate")


def pages_with_role(pages, role: str):
    return [p for p in pages if matches(p.get("doc_id", ""), role)]
