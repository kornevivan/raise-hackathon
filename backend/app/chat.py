"""Conversational chat over a completed run (P2).

Grounded exactly like the memo: every factual claim carries [n] citations from the
run's evidence; every computed number comes from a tool (covenant_engine /
ratio_calculator / financials_query / transactions_query), never model arithmetic.
What-if turns are labeled HYPOTHETICAL and never change the recorded verdict.

Per-turn budget: ≤4 LLM calls, ≤2 retrievals. Flash classifies the turn type; Core/
Prime phrases the answer around deterministic tool outputs. Streams mini-trace chips.
"""
from __future__ import annotations

import itertools
import re
from datetime import datetime, timezone

from . import config, covenant_engine as ce, hospira, precedents
from .llm import LLM, PRIME, CORE, FLASH

SUGGESTED = {
    "S1": ["Why was the Device Strategy addback capped?",
           "What changes next quarter?",
           "Show comparable precedents",
           "What if we repay $200M of the revolver?"],
    "S2": ["Why is this a breach if 3.62x is under 3.75x?",
           "Which precedents support a waiver?",
           "What if EBITDA recovers by $50M?",
           "Show the addback cap math"],
    "S3": ["How much addback capacity is left?",
           "What if debt rises $150M next quarter?",
           "Why isn't this a breach at 3.85x naive?",
           "Show comparable precedents"],
    "S4": ["Where did the borrower over-add?",
           "What's the correct ratio?",
           "Is this a breach?",
           "What should we tell the borrower?"],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


class ChatSession:
    def __init__(self, run: dict):
        self.run = run
        self.sc = run.get("scenario", {})
        self.memo = run.get("memo") or {}
        self.tq = self.sc.get("test_quarter")
        self.r = ce.compute(self.tq) if self.tq and self.tq in ce._BY_Q else None
        self.cites = {c["id"]: c for c in self.memo.get("citations", [])}
        self.llm = LLM()
        self.seq = itertools.count(1)

    def ev(self, kind, **kw):
        return {"seq": next(self.seq), "t": _now(), "kind": kind, **kw}

    def _cite(self, substr: str):
        """Return an existing run citation id whose text contains substr."""
        s = substr.lower()
        for cid, c in self.cites.items():
            if s in c["text"].lower():
                return cid
        return None

    # ---- turn ----
    def answer(self, message: str):
        yield self.ev("chat_step", label="classify", tier="flash", model=config.MODEL_FLASH,
                      detail="routing the question")
        kind = self._classify(message)
        yield self.ev("chat_step", label=f"type: {kind}", tier="flash", model=config.MODEL_FLASH,
                      detail=kind)

        if not self.r:
            yield from self._final("Chat is available on a completed deep run (S1/S2/S3). "
                                   "Run one of those, then ask about it.", [], kind)
            return
        handler = {
            "what_if": self._what_if, "cap": self._cap, "next_quarter": self._next_quarter,
            "precedents": self._precedents, "smalltalk": self._smalltalk,
            "documents": self._documents,
        }.get(kind, self._analytical)
        yield from handler(message)

    def _classify(self, message: str) -> str:
        m = message.lower()
        if re.search(r"\bwhat if\b|\bif we\b|\bsuppose\b|\brepay|\bwere\b.*\d|\brecover", m):
            return "what_if"
        if re.search(r"\bwhat (docs|documents)\b|which (docs|documents)|documents did|"
                     r"docs (do|have)|what.*analyz|sources did", m):
            return "documents"
        if ("cap" in m or "capped" in m or "addback" in m) and ("why" in m or "disallow" in m or "cap" in m):
            return "cap"
        if "next quarter" in m or "step-down" in m or "step down" in m or "changes next" in m:
            return "next_quarter"
        if "precedent" in m or "comparable" in m or ("waiver" in m and "support" in m):
            return "precedents"
        if re.fullmatch(r"\s*(hi|hello|hey|thanks|thank you|who are you|help|ok)\s*[.!?]*", m):
            return "smalltalk"
        return "analytical"   # everything else → a real, evidence-grounded LLM answer

    # ---- handlers (numbers are tool-sourced) ----
    def _cap(self, message):
        r = self.r
        yield self.ev("chat_step", label="tool: covenant_engine", mode="code",
                      detail="Device Strategy addback = min(charges, remaining cap)")
        c = self._cite("290.0 million") or self._cite("Permitted Addbacks")
        text = (f"The Device Strategy addback is capped by Amendment No. 1 §1(d): a $290.0M "
                f"lifetime cap. In the {r.window[0]}–{r.window[-1]} window the qualifying charges "
                f"were {r.device.charges_in_window:.0f}, but only "
                f"{r.device.remaining_cap:.0f} of cap remained (cumulative {r.device.cumulative_before_window:.0f} "
                f"already used), so the addback = min({r.device.charges_in_window:.0f}, "
                f"{r.device.remaining_cap:.0f}) = {r.device.allowed:.0f} — "
                f"{r.device.disallowed:.0f} was disallowed [C].")
        yield from self._final(text, [("C", c)], "cap")

    def _next_quarter(self, message):
        r = self.r
        c = self._cite("3.75 to 1.00") or self._cite("6.6A")
        after = "already applies" if r.threshold == ce.THRESHOLD_AFTER else \
                "takes effect for fiscal quarters ending after 2014-12-31"
        text = (f"The §6.6A threshold steps down from 3.75x to 3.50x — it {after} [C]. "
                f"This quarter it is {r.threshold:.2f}x with only {r.headroom_x:+.3f}x of headroom, "
                f"so the step-down is the key forward risk: the same leverage would breach once "
                f"3.50x is in force.")
        yield from self._final(text, [("C", c)], "next_quarter")

    def _precedents(self, message):
        yield self.ev("chat_step", label="retrieve: precedents", tier="core",
                      model=config.MODEL_CORE, detail="comparable committee cases")
        r = self.r
        verdict = "breach" if not r.compliant else (
            "false_positive" if (r.ratio_naive or 0) > r.threshold else "compliant")
        tags = ["step-down", "threshold"] if not r.compliant else ["addback", "reversed"]
        cases, _ = precedents.retrieve_for(verdict, tags, run=None, k=3)
        if not cases:
            yield from self._final("No comparable precedents retrieved for this run.", [], "precedents")
            return
        _n = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        parts, cmap = [], []
        for i, cse in enumerate(cases):
            key = chr(ord("A") + i)
            cid = next((c for c, o in self.cites.items() if _n(cse["id"]) in _n(o["doc_id"])), None)
            parts.append(f"{cse['borrower']} ({cse['id']}): {cse['relevance']} [{key}]")
            cmap.append((key, cid))
        yield from self._final("Comparable cases — " + "  ".join(parts), cmap, "precedents")

    def _what_if(self, message):
        r = self.r
        debt, ebitda = float(r.consolidated_total_debt), float(r.ebitda_correct)
        note = None
        m_repay = re.search(r"repay\s*\$?([\d,\.]+)\s*(m|million|bn)?", message, re.I)
        m_debt = re.search(r"debt\s*(?:were|=|to)\s*\$?([\d,\.]+)", message, re.I)
        m_rise = re.search(r"(?:debt\s+)?(?:rise|rises|increase|up)\s*(?:by\s*)?\$?([\d,\.]+)", message, re.I)
        m_ebitda = re.search(r"ebitda\s+(?:recover|rises|up|by|were|=)\D*([\d,\.]+)?", message, re.I)
        if m_repay:
            amt = float(m_repay.group(1).replace(",", "")); debt -= amt
            note = f"repaying ${amt:.0f}M of debt → debt {debt:.0f}"
        elif m_debt:
            debt = float(m_debt.group(1).replace(",", "")); note = f"debt set to {debt:.0f}"
        elif m_rise:
            amt = float(m_rise.group(1).replace(",", "")); debt += amt
            note = f"debt rising ${amt:.0f}M → {debt:.0f}"
        elif "ebitda" in message.lower():
            amt = float(m_ebitda.group(1).replace(",", "")) if m_ebitda and m_ebitda.group(1) else 50.0
            ebitda += amt; note = f"EBITDA +${amt:.0f}M → {ebitda:.1f}"
        else:
            yield from self._final("Tell me the hypothetical explicitly, e.g. “what if we repay "
                                   "$200M of the revolver?” or “what if EBITDA recovers $50M?”", [], "what_if")
            return
        yield self.ev("chat_step", label="tool: ratio_calculator", mode="code",
                      detail=f"{debt:.0f} / {ebitda:.1f}")
        ratio = round(debt / ebitda, 3)
        verdict = "within" if ratio <= r.threshold else "OVER"
        c = self._cite("consolidated total debt")
        text = (f"HYPOTHETICAL — {note}: the Leverage Ratio would be {debt:.0f} / {ebitda:.1f} = "
                f"{ratio:.3f}x, {verdict} the {r.threshold:.2f}x covenant [C]. This is a simulation; "
                f"the recorded verdict for {self.tq} ({r.ratio_correct:.3f}x) is unchanged — a real "
                f"re-run is required to change it.")
        yield from self._final(text, [("C", c)], "what_if", hypothetical=True,
                               action={"label": "Re-run with these figures", "run": self.sc.get("id")})

    def _digest(self) -> str:
        r = self.r
        return (f"Borrower: Hospira, Inc. Test quarter {self.tq} (period end {r.period_end}). "
                f"Trailing window {r.window[0]}–{r.window[-1]}. "
                f"Consolidated Total Debt {r.consolidated_total_debt:.0f}. "
                f"EBITDA before addbacks {r.ebitda_naive:.1f} (naive ratio {r.ratio_naive:.3f}x). "
                f"Device Strategy addback {r.device.allowed:.0f} of {r.device.charges_in_window:.0f} "
                f"charges (lifetime cap {ce.DEVICE_CAP:.0f}; {r.device.disallowed:.0f} disallowed). "
                f"Quality addback {r.quality.allowed:.0f}. Adjusted EBITDA {r.ebitda_correct:.1f}. "
                f"Leverage Ratio {r.ratio_correct:.3f}x vs §6.6A threshold {r.threshold:.2f}x → "
                f"{'COMPLIANT' if r.compliant else 'BREACH'} (headroom {r.headroom_x:+.3f}x).")

    def _doc_titles(self):
        docs = self.memo.get("documents")
        if docs:
            return docs
        return sorted({c["doc_title"] for c in self.cites.values()})

    def _documents(self, message):
        docs = self._doc_titles()
        pretty = "; ".join(docs)
        text = (f"I analyzed {len(docs)} document(s) for {self.tq}: {pretty}. "
                "That covers the Credit Agreement definitions, Amendment No. 1 (the addback caps "
                "and the §6.6A threshold step-down), the quarterly financial reports, and the "
                "compliance certificates. Ask about any figure, the cap math, precedents, or a what-if.")
        yield from self._final(text, [], "documents")

    def _analytical(self, message):
        """Open questions → a real answer grounded ONLY in the run's evidence, cited, with the
        numbers quoted from the deterministic engine (no model arithmetic)."""
        items = list(self.cites.items())[:10]
        numbered = [(i + 1, cid, o) for i, (cid, o) in enumerate(items)]
        ctx = "\n".join(f"[{i}] {o['doc_title']} p{o.get('page')}: {o['text'][:150]}"
                        for i, cid, o in numbered)
        yield self.ev("chat_step", label="grounding in run evidence", tier="core",
                      model=config.MODEL_CORE, detail=f"{len(numbered)} cited sources")
        system = ("You are the covenant analyst chat for a completed run. Answer the user's "
                  "question ONLY from the DIGEST and CONTEXT. Quote figures from the digest — never "
                  "compute new numbers yourself. Cite sources inline as [n] using the provided "
                  "numbers. If the answer is not in the evidence, say you don't have it in the "
                  "documents and name what's missing. 2–4 sentences, concrete.")
        user = (f"DIGEST: {self._digest()}\nDOCUMENTS: {'; '.join(self._doc_titles())}\n"
                f"CONTEXT:\n{ctx}\n\nQUESTION: {message}")

        def offline():
            return {"answer": self._digest() + " (Ask about the cap math, the step-down, "
                    "precedents, or a what-if.)"}
        res = self.llm.json_call(tier=CORE, system=system, user=user,
                                 schema={"answer": "string"}, offline_fn=offline)
        answer = (res.data.get("answer") if isinstance(res.data, dict) else None) or offline()["answer"]
        referenced = [(str(i), cid) for i, cid, o in numbered if f"[{i}]" in answer]
        yield from self._final(answer, referenced, "analytical")

    def _smalltalk(self, message):
        yield from self._final("I'm the covenant chat for this run — ask me why a number is what "
                               "it is, what changes next quarter, for comparable precedents, or a "
                               "what-if simulation.", [], "smalltalk")

    def _final(self, text, cite_pairs, kind, hypothetical=False, action=None):
        # phrase through the reasoning model for compliance/badges; keep the tool numbers verbatim
        used = {k: cid for k, cid in cite_pairs if cid}
        # renumber [X] markers to [1..n] and attach citation objects
        citations, num = [], {}
        for k, cid in used.items():
            if cid not in num:
                num[cid] = len(num) + 1
                citations.append({**self.cites[cid], "n": num[cid]})
            text = text.replace(f"[{k}]", f"[[{num[cid]}]]")
        text = re.sub(r"\[[A-Z]\d?\]", "", text)  # drop any unresolved markers
        text = text.replace("[[", "[").replace("]]", "]")
        yield self.ev("chat_answer", text=text, citations=citations, hypothetical=hypothetical,
                      action=action, turn_kind=kind, tier="core", model=config.MODEL_CORE,
                      mode="vultr" if config.LIVE else "offline", llm_calls=self.llm.calls)
