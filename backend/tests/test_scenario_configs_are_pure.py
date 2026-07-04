"""Acceptance: a scenario config is NOTHING but selected inputs — a document corpus, tool-store
bindings, a trigger question, and a run date. No covenant numbers, section references, citation
strings, precedent IDs, or filename-keyed branches. Everything else is derived.
"""
import os
import re
import sys

os.environ["VULTR_INFERENCE_API_KEY"] = ""
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import scenarios as scen  # noqa: E402

ALLOWED_KEYS = {"id", "corpus", "run_date", "stores", "trigger"}
# These must not appear ANYWHERE in a config (the trigger is a natural-language question, so we
# forbid covenant ANSWERS — numbers/sections/precedent IDs/filenames — not English words).
FORBIDDEN = [
    (r"§|Section\s*6\.6\b", "section reference"),
    (r"PRECEDENT-\d", "precedent ID"),
    (r"\b\d+\.\d+x\b|\bto 1\.00\b|\bto 1\b", "covenant ratio number"),
    (r"\d{3},\d{3},\d{3}|\b\d{3}\.0\s*million\b", "cap number"),
    (r"_excerpt|\.pdf|financial_report_\d", "filename"),
]
# derived-field / branch-flag names may not be config KEYS (checked structurally).
FORBIDDEN_KEYS = {"crosscheck", "test_quarter", "verdict", "label", "blurb", "doc_labels"}


def test_configs_are_pure():
    for sid, sc in scen.SCENARIOS.items():
        extra = set(sc) - ALLOWED_KEYS
        assert not extra, f"{sid}: config has non-input keys {extra}"
        assert not (set(sc) & FORBIDDEN_KEYS), f"{sid}: config carries a derived-field key"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", sc["run_date"]), f"{sid}: run_date not a date"
        assert sc["corpus"] in scen.CORPORA, f"{sid}: unknown corpus"
        assert isinstance(sc["stores"], list) and sc["stores"], f"{sid}: stores must be a non-empty list"
        blob = f"{sc['trigger']} {sc['corpus']} {' '.join(sc['stores'])}"
        for pat, why in FORBIDDEN:
            m = re.search(pat, blob, re.I)
            assert not m, f"{sid}: config leaks a {why}: {m.group(0)!r}"


def test_everything_else_is_derived():
    for sid in scen.SCENARIOS:
        d = scen.cfg(sid)
        assert d["test_quarter"], f"{sid}: test_quarter not derived from run_date"
        assert isinstance(d["crosscheck"], bool)
    # the certificate cross-check is DERIVED from the trigger wording, not stored
    assert scen.cfg("S4")["crosscheck"] is True
    assert scen.cfg("S1")["crosscheck"] is False


if __name__ == "__main__":
    test_configs_are_pure()
    test_everything_else_is_derived()
    print("SCENARIO CONFIGS ARE PURE — inputs only; test_quarter / crosscheck / labels derived.")
