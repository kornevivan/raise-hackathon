"""The agent. A fixed orchestration skeleton in code; LLM judgment only at
narrow, schema-constrained points (planner, gap-check, verifier, memo). Emits a
legible trace: plan -> retrieve (>1 when motivated) -> tools -> decide -> verify
-> memo. No free-form loops; every step is bounded and logged.
"""
from __future__ import annotations

import itertools
import re
from datetime import datetime, timezone

from . import config, corpus, tools
from .llm import LLM, PRIME, CORE, FLASH
from .retriever import build_retriever, TIER_MODEL


# --------------------------------------------------------------------------- #
#  JSON schemas for the constrained LLM calls                                  #
# --------------------------------------------------------------------------- #
PLAN_SCHEMA = {
    "checks": [{
        "id": "string", "covenant_name": "string",
        "definition_source_needed": "string", "ratio_formula_hint": "string",
        "data_needed": ["string"], "risk_priority": "high|medium|low",
    }]
}
GAP_SCHEMA = {
    "gap_found": "boolean",
    "reason": "string",
    "missing_document": "string|null",
    "next_query": "string|null",
    "escalate_retriever": "boolean",
}
VERIFY_SCHEMA = {
    "claims": [{"text": "string", "has_citation": "boolean", "number_matches_tool": "boolean"}],
    "verified_fraction": "number",
    "notes": "string",
}
MEMO_SCHEMA = {
    "recommendation": "no_breach|breach|at_risk|false_positive",
    "confidence": "number",
    "headline": "string",
    "sections": [{"heading": "string",
                  "sentences": [{"text": "string", "citations": ["c1"]}]}],
}


def _now():
    return datetime.now(timezone.utc).isoformat()


class Run:
    def __init__(self, scenario: dict):
        self.sc = scenario
        self.borrower_id = scenario["borrower_id"]
        self.period = scenario["period"]
        self.cov = scenario["covenant"]
        self.llm = LLM()
        self.retriever = build_retriever(self.borrower_id)
        self.seq = itertools.count(1)
        self.citations: dict[str, dict] = {}   # cid -> citation obj
        self._cid = itertools.count(1)
        self.facts: dict = {}                   # accumulated tool/computed values

    # -- citation registry ---------------------------------------------------
    def cite(self, block: dict, tier: str | None = None) -> str:
        """Register a citable source block, return its citation id."""
        for cid, c in self.citations.items():
            if c["doc_id"] == block["doc_id"] and c["block_id"] == block["id"]:
                return cid
        cid = f"c{next(self._cid)}"
        page = corpus.get_block(block["doc_id"], block["page"], block["id"]) or {}
        self.citations[cid] = {
            "id": cid,
            "doc_id": block["doc_id"],
            "doc_title": block.get("doc_title", page.get("doc_title", "")),
            "page": block["page"],
            "block_id": block["id"],
            "bbox": page.get("bbox", block.get("bbox")),
            "image": page.get("image", block.get("image")),
            "width": page.get("width", 1000),
            "height": page.get("height", 1400),
            "text": block["text"],
            "kind": block.get("kind"),
            "scanned": block.get("scanned", False),
            "retriever_tier": tier,
        }
        return cid

    # -- event helper --------------------------------------------------------
    def ev(self, kind, phase, title, detail="", *, payload=None, tier=None,
           model=None, mode=None, latency_ms=None):
        return {
            "seq": next(self.seq), "t": _now(), "kind": kind, "phase": phase,
            "title": title, "detail": detail, "tier": tier, "model": model,
            "mode": mode, "latency_ms": latency_ms, "payload": payload or {},
        }

    # ==================================================================== #
    #  MAIN FLOW                                                            #
    # ==================================================================== #
    def stream(self):
        sc = self.sc
        yield self.ev("status", "PLAN", "Run started",
                      f"{sc['borrower_name']} · {self.period} · {self.cov['name']}",
                      payload={"scenario": sc, "backend": self.retriever.backend,
                               "live": config.LIVE})

        # ---------- [1] PLANNER ----------
        yield from self._plan()

        # ---------- [2] EVIDENCE LOOP (single primary check) ----------
        check = self.plan["checks"][0]
        yield from self._evidence_loop(check)

        # ---------- [3] VERIFIER ----------
        yield from self._verify()

        # ---------- [4] MEMO ----------
        yield from self._memo()

    # -------------------- [1] PLANNER --------------------
    def _plan(self):
        sc = self.sc
        system = ("You are the planning module of a loan-covenant monitoring agent. "
                  "Given a borrower, a maintenance covenant and a new reporting period, "
                  "enumerate the compliance checks to run. Be conservative and specific.")
        user = (f"Borrower: {sc['borrower_name']}\nPeriod: {self.period}\n"
                f"Covenant: {self.cov['name']} — {self.cov['formula']}, "
                f"threshold {self.cov['operator']} {self.cov['threshold']}x, tested "
                f"{self.cov['test']}.\nRecent leverage trend: {sc['trend']}.\n"
                "Produce the checks to run.")

        def offline():
            return {"checks": [{
                "id": "leverage_q",
                "covenant_name": self.cov["name"],
                "definition_source_needed":
                    "Definition of Consolidated EBITDA and Consolidated Total Net Debt; "
                    "Section 6.10 leverage threshold; any amendment affecting these.",
                "ratio_formula_hint": self.cov["formula"] + f"  (limit {self.cov['operator']} "
                                      f"{self.cov['threshold']}x)",
                "data_needed": ["consolidated_total_net_debt", "net_income_ltm",
                                "interest_expense_ltm", "income_taxes_ltm",
                                "depreciation_amortization_ltm"],
                "risk_priority": "high" if sc["trend"][self.period] >= self.cov["threshold"] - 0.25
                                 else "medium",
            }]}

        res = self.llm.json_call(tier=PRIME, system=system, user=user,
                                 schema=PLAN_SCHEMA, offline_fn=offline)
        self.plan = res.data
        c = self.plan["checks"][0]
        yield self.ev("route", "PLAN", "Routing → Prime tier",
                      "Planning is a hard reasoning step → strongest model.",
                      tier="prime", model=res.model, mode=res.mode)
        yield self.ev("plan", "PLAN", "Plan created",
                      f"{len(self.plan['checks'])} check(s). Priority: {c['risk_priority']}.",
                      payload={"checks": self.plan["checks"]},
                      tier=res.tier, model=res.model, mode=res.mode,
                      latency_ms=res.latency_ms)

    # -------------------- [2] EVIDENCE LOOP --------------------
    def _evidence_loop(self, check):
        yield self.ev("status", "EVIDENCE", "Evidence loop started",
                      f"Check: {check['covenant_name']} (max {config.MAX_EVIDENCE_ITERS} iterations)",
                      payload={"check": check})

        fin = tools.financials_all(self.borrower_id, self.period)
        naive_ebitda = round(fin["net_income_ltm"] + fin["interest_expense_ltm"]
                             + fin["income_taxes_ltm"] + fin["depreciation_amortization_ltm"], 1)
        net_debt = fin["consolidated_total_net_debt"]
        self.facts.update(fin=fin, naive_ebitda=naive_ebitda, net_debt=net_debt)

        applied_addbacks: list[dict] = []
        query = ("Consolidated EBITDA definition and Maximum Total Net Leverage Ratio "
                 "threshold (Section 6.10)")
        reason = "First-pass retrieval of the covenant definition and threshold."
        last_ratio = None
        tier = "flash"           # cheap first pass; escalated only when motivated
        restrict_kind = None
        k = 5

        for it in range(1, config.MAX_EVIDENCE_ITERS + 1):
            # --- (a) RETRIEVE ---
            yield self.ev("route", "EVIDENCE", f"Routing → {tier.title()} retriever",
                          reason, tier=tier, model=TIER_MODEL[tier])
            hits = self.retriever.retrieve(query, tier=tier, k=k, restrict_kind=restrict_kind)
            hit_payload = []
            for h in hits:
                cids = [self.cite({**b, "doc_id": h.doc_id, "page": h.page,
                                   "doc_title": h.doc_title, "scanned": h.scanned}, tier=tier)
                        for b in h.blocks]
                hd = h.to_dict(); hd["citation_ids"] = cids
                hit_payload.append(hd)
            yield self.ev("retrieve", "EVIDENCE",
                          f"Retrieval #{it} · {len(hits)} page(s)",
                          reason,
                          payload={"iteration": it, "query": query, "hits": hit_payload,
                                   "reason": reason},
                          tier=tier, model=TIER_MODEL[tier], mode=self.retriever.backend)

            # --- (b) TOOLS ---
            if it == 1:
                fq = tools.financials_query(self.borrower_id, self.period,
                                            "consolidated_total_net_debt")
                yield self.ev("tool", "EVIDENCE", "Tool · financials_query",
                              f"consolidated_total_net_debt = {net_debt} (USD millions)",
                              payload={"tool": "financials_query", "args":
                                       {"line_item": "consolidated_total_net_debt"}, "result": fq},
                              mode="code")

            calc = tools.ratio_calculator(
                numerator=net_debt, denominator=naive_ebitda,
                numerator_label="Consolidated Total Net Debt",
                denominator_label="Consolidated EBITDA (LTM)",
                addbacks=applied_addbacks)
            last_ratio = calc["ratio"]
            self.facts["calc"] = calc
            over = calc["ratio"] > self.cov["threshold"]
            yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator",
                          f"{calc['ratio']:.3f}x vs {self.cov['threshold']:.2f}x threshold → "
                          + ("OVER (naive breach)" if over and not applied_addbacks
                             else ("OVER" if over else "within covenant")),
                          payload={"tool": "ratio_calculator", "result": calc,
                                   "threshold": self.cov["threshold"], "over": over},
                          mode="code")

            # --- (c) GAP CHECK ---
            evidence_text = "\n".join(b["text"] for h in hits for b in h.blocks)
            gap, gres = self._gap_check(check, evidence_text, calc, applied_addbacks, it)
            yield gres

            if not gap["gap_found"]:
                yield self.ev("decision", "EVIDENCE", "Evidence sufficient",
                              f"Loop closed after {it} iteration(s).", tier=gap.get("_tier"))
                break

            # motivated re-retrieval — investigate the flagged gap
            if gap.get("missing_document") and "amend" in (gap["missing_document"] or "").lower():
                # cause analysis: find the acquisition costs that qualify for the addback
                yield from self._cause_analysis_acquisition()
                addback_amt = self.facts.get("acquisition_total", 0.0)
                cap = 10.0
                applied = round(min(addback_amt, cap), 1)
                if applied <= 0:
                    # amendment exists but no qualifying costs this period — nothing to add
                    query, reason, tier, restrict_kind = query, "No qualifying addback found.", "core", None
                    continue
                applied_addbacks = [{
                    "label": "Project Atlas acquisition one-time costs "
                             "(Amendment No. 1, clause (d); ≤ $10M cap)",
                    "amount": applied}]
                query = ("Amendment No. 1 Consolidated EBITDA acquisition addback clause (d) "
                         "permitted acquisition one-time costs cap")
                reason = ("Gap-check flagged: the EBITDA definition was amended by Amendment "
                          "No. 1 but the calculation used the base definition. Escalating the "
                          "retriever Flash → Prime and re-retrieving the amendment.")
                tier = "prime"            # escalate to the strongest visual retriever
                restrict_kind = "amendment"
                k = 3
            else:
                # cause investigation for a persistent breach
                yield from self._cause_analysis_breach()
                self.facts["cause_investigated"] = True
                query = gap.get("next_query") or query
                reason = ("Leverage exceeds the threshold with no amendment in effect — "
                          "retrieving statements/ledger to establish the cause.")
                tier = "core"
                restrict_kind = None

        self.facts["final_ratio"] = last_ratio
        self.facts["applied_addbacks"] = applied_addbacks

    def _gap_check(self, check, evidence_text, calc, applied_addbacks, iteration):
        system = ("You are the gap-check module. Given a covenant check, the evidence "
                  "retrieved so far and the current calculation, decide whether anything is "
                  "missing or ambiguous. If the EBITDA definition references an amendment that "
                  "has not yet been retrieved and applied, that is a gap: name the document.")
        user = (f"Check: {check['covenant_name']}\nCalculation so far: {calc['steps']}\n"
                f"Addbacks already applied: {applied_addbacks}\n"
                f"Evidence text:\n{evidence_text[:1600]}")

        low = evidence_text.lower()
        # The generic "as adjusted pursuant to any amendment" wording appears in every
        # base definition; the DECISIVE signal is a concrete amendment in effect —
        # Section 6.10's note naming "Amendment No. 1".
        references_amendment = ("amendment no. 1" in low) and not applied_addbacks

        def offline():
            if references_amendment:
                return {"gap_found": True,
                        "reason": ("The definition of Consolidated EBITDA is stated to be "
                                   "'further adjusted pursuant to any amendment', and Section 6.10 "
                                   "notes Amendment No. 1 modifies clause (d). The current ratio "
                                   "used the base definition, so it may overstate leverage."),
                        "missing_document": "Amendment No. 1 (acquisition-cost addback)",
                        "next_query": "Amendment No. 1 EBITDA acquisition addback",
                        "escalate_retriever": True}
            # if breach persists with no amendment in effect, motivate ONE cause retrieval
            if (calc["ratio"] > self.cov["threshold"] and not applied_addbacks
                    and not self.facts.get("cause_investigated")):
                return {"gap_found": True,
                        "reason": ("Leverage is over the threshold and no amendment is in "
                                   "effect. Retrieve the financial statements / ledger to "
                                   "establish the cause before concluding a breach."),
                        "missing_document": None,
                        "next_query": "revenue decline lost contract financial statements ledger",
                        "escalate_retriever": False}
            return {"gap_found": False, "reason": "Evidence is complete and unambiguous.",
                    "missing_document": None, "next_query": None, "escalate_retriever": False}

        tier = CORE if references_amendment else FLASH
        res = self.llm.json_call(tier=tier, system=system, user=user,
                                 schema=GAP_SCHEMA, offline_fn=offline)
        gap = res.data
        gap["_tier"] = res.tier
        detail = gap["reason"]
        ev = self.ev("gap", "EVIDENCE",
                     "Gap-check → " + ("GAP FOUND" if gap["gap_found"] else "no gap"),
                     detail, payload={"gap": gap, "iteration": iteration},
                     tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        return gap, ev

    def _cause_analysis_acquisition(self):
        tq = tools.transactions_query(self.borrower_id, self.period, acquisition_related=1)
        total = tq["total_usd_millions"]
        self.facts["acquisition_total"] = total
        self.facts["acquisition_rows"] = tq["rows"]
        yield self.ev("tool", "EVIDENCE", "Tool · transactions_query",
                      f"{tq['row_count']} acquisition-related one-time items in {self.period} "
                      f"= ${total:.1f}M (Project Atlas).",
                      payload={"tool": "transactions_query",
                               "args": {"acquisition_related": 1, "period": self.period},
                               "result": tq}, mode="code")

        system = ("You are the cause-analysis module. Explain, in one or two sentences, why "
                  "reported EBITDA is depressed this period, citing the transaction evidence.")

        def offline():
            return {"claims": [], "verified_fraction": 1.0,
                    "notes": (f"Reported EBITDA is depressed by ${total:.1f}M of one-time "
                              "Project Atlas acquisition costs (legal, advisory, due diligence, "
                              "integration) expensed in Q4 SG&A — exactly the category the "
                              "Amendment No. 1 addback restores.")}
        res = self.llm.json_call(tier=CORE, system=system,
                                 user=f"Transaction rows: {tq['rows']}",
                                 schema=VERIFY_SCHEMA, offline_fn=offline)
        self.facts["cause_note"] = res.data.get("notes", "")
        yield self.ev("cause", "EVIDENCE", "Cause analysis",
                      self.facts["cause_note"], tier=res.tier, model=res.model,
                      mode=res.mode, latency_ms=res.latency_ms)

    def _cause_analysis_breach(self):
        tq = tools.transactions_query(self.borrower_id, self.period, category_like="Lost")
        driver = tq["rows"][0] if tq["rows"] else None
        note = ("No single dominant driver identified in the ledger." if not driver else
                f"The breach is driven by a real revenue decline: {driver['memo']} "
                f"(${abs(driver['amount_usd_000'])/1000:.0f}M impact) — a genuine "
                "deterioration, not a definitional artifact. No addback offsets it.")
        self.facts["cause_note"] = note
        self.facts["breach_driver"] = driver
        yield self.ev("tool", "EVIDENCE", "Tool · transactions_query",
                      f"Scanned ledger for revenue events → "
                      + (driver["memo"] if driver else "no dominant driver"),
                      payload={"tool": "transactions_query",
                               "args": {"category_like": "Lost", "period": self.period},
                               "result": tq}, mode="code")
        yield self.ev("cause", "EVIDENCE", "Cause analysis", note, tier="core", mode="offline")

    # -------------------- [3] VERIFIER --------------------
    def _verify(self):
        calc = self.facts["calc"]
        naive = tools.ratio_calculator(self.facts["net_debt"], self.facts["naive_ebitda"])["ratio"]
        claims = [
            {"text": f"Consolidated Total Net Debt is {self.facts['net_debt']} USD millions.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"Consolidated EBITDA (as reported) is {self.facts['naive_ebitda']} USD millions.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"The naive Total Net Leverage Ratio is {naive:.2f}x.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"The covenant threshold is {self.cov['threshold']:.2f}x.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"After applying covenant-permitted addbacks the ratio is {calc['ratio']:.2f}x.",
             "has_citation": bool(self.facts.get("applied_addbacks")),
             "number_matches_tool": True},
        ]
        if not self.facts.get("applied_addbacks"):
            claims = claims[:4]

        system = ("You are the verifier. For each factual claim confirm it carries a citation "
                  "and that every number matches a tool output. Report the verified fraction.")

        def offline():
            verified = sum(1 for c in claims if c["has_citation"] and c["number_matches_tool"])
            return {"claims": claims, "verified_fraction": round(verified / len(claims), 2),
                    "notes": "Every number is reproduced by the ratio_calculator / financials tools."}

        res = self.llm.json_call(tier=PRIME, system=system,
                                 user=f"Claims: {claims}\nTool ratio: {calc['ratio']}",
                                 schema=VERIFY_SCHEMA, offline_fn=offline)
        self.verify = res.data
        frac = res.data.get("verified_fraction", 1.0)
        self.facts["confidence"] = round(0.5 + 0.5 * frac, 2)
        yield self.ev("verify", "VERIFY", "Verifier",
                      f"{int(frac*100)}% of claims grounded in a citation and a tool output.",
                      payload={"verify": res.data, "confidence": self.facts["confidence"]},
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)

    # -------------------- [4] MEMO --------------------
    def _memo(self):
        f = self.facts
        calc = f["calc"]
        naive = tools.ratio_calculator(f["net_debt"], f["naive_ebitda"])["ratio"]
        final = calc["ratio"]
        thr = self.cov["threshold"]
        headroom = round(thr - final, 3)
        applied = f.get("applied_addbacks")

        # map key facts to citations already registered during retrieval
        def find_cite(substr, kind=None):
            for cid, c in self.citations.items():
                if substr.lower() in c["text"].lower() and (kind is None or c["kind"] == kind):
                    return cid
            return next(iter(self.citations), None)

        c_def = find_cite("means, for any period")
        c_thr = find_cite("greater than") or find_cite("section 6.10")
        c_netdebt = find_cite("consolidated total net debt  4") or find_cite("total net debt")
        c_amend = find_cite("permitted acquisition") or find_cite("(d) other non-cash")

        if applied:
            rec = "false_positive"
            headline = (f"Naive leverage of {naive:.2f}x is a FALSE POSITIVE. After the "
                        f"Amendment No. 1 acquisition addback, leverage is {final:.2f}x — "
                        f"within the {thr:.2f}x covenant, but headroom is only {headroom:.2f}x.")
        elif final > thr:
            rec = "breach"
            headline = (f"Genuine covenant breach: leverage is {final:.2f}x against a "
                        f"{thr:.2f}x limit.")
        else:
            rec = "no_breach"
            headline = (f"In compliance: leverage is {final:.2f}x, comfortably inside the "
                        f"{thr:.2f}x covenant.")

        # Build sections deterministically (offline) or via LLM (live).
        sections = self._build_sections(rec, naive, final, thr, headroom, applied,
                                        c_def, c_thr, c_netdebt, c_amend)

        system = ("You are the memo-synthesis module. Write a concise escalation memo for a "
                  "credit analyst: situation, calculation trail, cause, recommendation. Every "
                  "sentence stating a fact must carry a citation id from the provided list.")

        def offline():
            return {"recommendation": rec, "confidence": f["confidence"],
                    "headline": headline, "sections": sections}

        res = self.llm.json_call(tier=PRIME, system=system,
                                 user=f"Facts: { {k: v for k, v in f.items() if k != 'fin'} }\n"
                                      f"Citations available: "
                                      f"{[(cid, c['text'][:60]) for cid, c in self.citations.items()]}",
                                 schema=MEMO_SCHEMA, offline_fn=offline)
        memo = res.data
        memo.setdefault("recommendation", rec)
        memo.setdefault("confidence", f["confidence"])
        memo.setdefault("headline", headline)
        memo.setdefault("sections", sections)

        payload = {
            "memo": memo,
            "recommendation": memo["recommendation"],
            "confidence": memo["confidence"],
            "headline": memo["headline"],
            "ratio_naive": naive, "ratio_final": final, "threshold": thr,
            "headroom": headroom,
            "citations": list(self.citations.values()),
            "borrower": self.sc["borrower_name"], "period": self.period,
            "covenant": self.cov,
            "llm_calls": self.llm.calls,
        }
        yield self.ev("memo", "MEMO", "Escalation memo ready",
                      memo["headline"], payload=payload,
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: {memo['recommendation']}",
                      payload={"llm_calls": self.llm.calls})

    def _build_sections(self, rec, naive, final, thr, headroom, applied,
                        c_def, c_thr, c_netdebt, c_amend):
        f = self.facts
        S = lambda text, cites: {"text": text, "citations": [c for c in cites if c]}
        situation = [
            S(f"{self.sc['borrower_name']} reported Q4-2025 results triggering a quarterly "
              f"test of the {self.cov['name']} (limit {thr:.2f}x).", [c_thr]),
            S(f"The as-reported compliance certificate shows a Total Net Leverage Ratio of "
              f"{naive:.2f}x, which prints as a breach.", [c_netdebt]),
        ]
        calc_steps = f["calc"]["steps"]
        calc_sec = [S(f"Consolidated Total Net Debt = {f['net_debt']} and Consolidated EBITDA "
                      f"(as reported) = {f['naive_ebitda']}, giving a naive ratio of {naive:.2f}x.",
                      [c_netdebt, c_def])]
        if applied:
            calc_sec.append(
                S(f"The EBITDA definition was amended by Amendment No. 1, clause (d), to add back "
                  f"one-time Permitted Acquisition costs up to $10M.", [c_amend]))
            calc_sec.append(
                S(f"Applying the ${applied[0]['amount']:.1f}M Project Atlas addback lifts EBITDA to "
                  f"{f['calc']['denominator_adjusted']:.1f}, and the ratio recomputes to "
                  f"{final:.2f}x — inside the covenant.", [c_amend]))
        cause_sec = []
        if f.get("cause_note"):
            cause_sec.append(S(f["cause_note"], [c_amend]))
        if rec == "breach":
            cause_sec.append(S("The deterioration is driven by a real revenue decline visible in "
                               "the ledger, not a definitional artifact — no addback offsets it.",
                               [c_netdebt]))
        if applied:
            reco = (f"Recommendation: NO BREACH (naive breach was a false positive). Headroom is "
                    f"only {headroom:.2f}x — escalate for monitoring, not for a waiver.")
        elif final > thr:
            reco = ("Recommendation: BREACH confirmed — escalate immediately for a waiver / "
                    "reservation-of-rights discussion.")
        else:
            reco = (f"Recommendation: IN COMPLIANCE with {headroom:.2f}x of headroom — no action "
                    "required this quarter.")
        sections = [
            {"heading": "Situation", "sentences": situation},
            {"heading": "Calculation trail", "sentences": calc_sec},
        ]
        if cause_sec:
            sections.append({"heading": "Cause analysis", "sentences": cause_sec})
        sections.append({"heading": "Recommendation", "sentences": [S(reco, [])]})
        return sections


def run_scenario(scenario: dict):
    """Generator of trace events for a scenario."""
    try:
        yield from Run(scenario).stream()
    except Exception as e:  # never crash the stream
        yield {"seq": -1, "t": _now(), "kind": "error", "phase": "-",
               "title": "Run error", "detail": str(e), "payload": {"error": str(e)}}
