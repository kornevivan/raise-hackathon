"""Scenario configs = SELECTED INPUTS ONLY (docs corpus + tool-store bindings + trigger
question + run date). Everything else — the test quarter, whether it's a certificate
cross-check, the UI labels — is DERIVED. No covenant numbers, section refs, citation
strings, precedent IDs, or filename-keyed branches live here (enforced by
tests/test_scenario_configs_are_pure.py). The pipeline is the same for every scenario;
a scenario just chooses the inputs.
"""
from __future__ import annotations

from . import hospira

# corpus preset -> loader (a preset is a named document set, not a per-scenario file list)
CORPORA = {"hospira": "deep", "portfolio": "triage"}

SCENARIOS = {
    "S0": {"id": "S0", "corpus": "portfolio", "run_date": "2015-03-31",
           "stores": ["portfolio_index", "filing_log", "financials_quarterly"],
           "trigger": "The quarter just closed — review the portfolio and tell me which "
                      "borrower needs attention first."},
    "S3": {"id": "S3", "corpus": "hospira", "run_date": "2014-03-31",
           "stores": ["financials_quarterly", "transactions", "precedents_index"],
           "trigger": "Review Hospira's leverage covenant for this quarter and flag any "
                      "forward-looking risks."},
    "S1": {"id": "S1", "corpus": "hospira", "run_date": "2014-06-30",
           "stores": ["financials_quarterly", "transactions", "precedents_index"],
           "trigger": "Analyze Hospira's leverage covenant compliance for this quarter. "
                      "Is the borrower in breach?"},
    "S2": {"id": "S2", "corpus": "hospira", "run_date": "2015-03-31",
           "stores": ["financials_quarterly", "transactions", "precedents_index"],
           "trigger": "Check Hospira's leverage covenant compliance for this quarter."},
    "S4": {"id": "S4", "corpus": "hospira", "run_date": "2014-06-30",
           "stores": ["financials_quarterly", "transactions", "precedents_index"],
           "trigger": "Verify the borrower-submitted compliance certificate against our own "
                      "recomputation."},
}
ORDER = ["S0", "S3", "S1", "S2", "S4"]


def _quarter_for(run_date: str) -> str | None:
    _, by_q = hospira.financials()
    return next((q for q, r in by_q.items() if r.get("period_end") == run_date), None)


def derive(sc: dict) -> dict:
    """Turn a pure config into the run parameters the pipeline needs — all DERIVED."""
    trig = sc["trigger"].lower()
    crosscheck = "certificate" in trig and any(w in trig for w in ("verify", "cross-check", "recomput"))
    return {**sc, "test_quarter": _quarter_for(sc["run_date"]), "period_end": sc["run_date"],
            "crosscheck": crosscheck, "prompt": sc["trigger"], "kind": CORPORA[sc["corpus"]]}


def _short(trigger: str) -> str:
    return " ".join(trigger.split()[:6]).rstrip(".") + "…"


def _doc_labels(corpus: str) -> list[str]:
    if corpus == "portfolio":
        return ["Borrower profiles & quarterly certificates", "Hospira's latest (scanned) certificate",
                "Amendment No. 1 (step-down)"]
    return ["Credit Agreement (SEC EDGAR)", "Amendment No. 1 (SEC EDGAR)",
            "Quarterly financial reports", "Compliance certificates (incl. scanned)"]


def view(sc: dict) -> dict:
    """UI-facing view (label/blurb derived from the trigger, not stored in the config)."""
    return {"id": sc["id"], "label": f"{sc['id']} · {_short(sc['trigger'])}",
            "blurb": sc["trigger"], "prompt": sc["trigger"],
            "test_quarter": _quarter_for(sc["run_date"]), "kind": CORPORA[sc["corpus"]],
            "doc_labels": _doc_labels(sc["corpus"])}


def all_views() -> list[dict]:
    return [view(SCENARIOS[k]) for k in ORDER]


def cfg(scenario_id: str) -> dict:
    """Derived run-config for a scenario id (used by tests / prewarm)."""
    return derive(SCENARIOS[scenario_id])
