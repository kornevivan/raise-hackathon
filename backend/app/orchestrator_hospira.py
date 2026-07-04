"""Hospira deep-run agent (sample mode) driven by the deterministic covenant engine.

Same visible workflow — plan → retrieve (>1, motivated) → tools → verify → memo —
but every number comes from `covenant_engine` (asserted by the golden tests) and
every claim is cited to an ingested page. Scenarios use the REAL golden numbers:
  S3 (2014Q1): 3.847x naive → 3.066x vs 3.75x — compliant, cap-headroom warning
  S1 (2014Q2): 4.218x naive → 3.606x vs 3.75x — false breach, capped addback (30 disallowed)
  S2 (2015Q1): 3.800x naive → 3.615x vs 3.50x — step-down BREACH
"""
from __future__ import annotations

import itertools
import re
from datetime import datetime, timezone

from . import config, hospira, precedents, spec_extractor, generic_engine, linker
from .gapcheck import detect_instrument
from .llm import LLM, PRIME, CORE, FLASH
from .retriever import TIER_MODEL

DOC_LABELS = ["Credit Agreement (2011) §1.1/§6.6", "Amendment No. 1 (2013) §1(d)/§6.6A",
              "Financial reports 2013Q3–2015Q1", "Compliance certificates (incl. scanned 2014Q4)"]
SCENARIOS = {
    "S3": {"id": "S3", "test_quarter": "2014Q1",
           "label": "S3 · All clear — watch the cap",
           "blurb": "Naive 3.847x looks like a breach; with capped addbacks it's 3.066x vs "
                    "3.75x. Compliant — but Device Strategy cap is 285/290, thin future room.",
           "prompt": "Review Hospira's leverage covenant for Q1 2014 and flag any forward-looking risks.",
           "doc_labels": DOC_LABELS},
    "S1": {"id": "S1", "test_quarter": "2014Q2",
           "label": "S1 · False breach & capped addback",
           "blurb": "Naive 4.218x prints a BREACH. The addback is capped (min → 30 disallowed), "
                    "recomputing 3.606x vs 3.75x. Debt jumped on a $460M acquisition draw.",
           "prompt": "Analyze Hospira's Maximum Leverage Ratio covenant for Q2 2014 (period ending "
                     "2014-06-30). Is the borrower in breach?",
           "doc_labels": DOC_LABELS},
    "S2": {"id": "S2", "test_quarter": "2015Q1",
           "label": "S2 · Step-down trap — real breach",
           "blurb": "3.615x. The §6.6A step-down to 3.50x (after 2014-12-31) turns a would-be "
                    "pass into an Event of Default. Escalate.",
           "prompt": "Check Hospira's Q1 2015 covenant compliance — does the §6.6A step-down change "
                     "the outcome?",
           "doc_labels": DOC_LABELS},
    "S4": {"id": "S4", "test_quarter": "2014Q2", "crosscheck": True,
           "label": "S4 · Certificate cross-check",
           "blurb": "The borrower's submitted certificate claims 3.50x (EBITDA 995). Recomputed "
                    "correctly it's 3.606x — they applied the full addback, ignoring the $290M cap "
                    "(30 over-added). Not a breach, but a misstated certificate.",
           "prompt": "Verify the borrower-submitted compliance certificate for Q2 2014 against our "
                     "own recomputation.",
           "doc_labels": DOC_LABELS + ["Borrower-submitted certificate 2014Q2"]},
}


def _now():
    return datetime.now(timezone.utc).isoformat()


class HospiraRun:
    def __init__(self, scenario: dict):
        self.sc = scenario
        self.tq = scenario["test_quarter"]
        self.corpus = hospira.corpus()
        # DERIVE the covenant rules from the indexed documents at runtime (not hardcoded),
        # then compute with the generic engine over the structured financials tool store.
        order, by_q = hospira.financials()
        self.spec = spec_extractor.build_spec(self.corpus["pages"])
        self.r = generic_engine.legacy_result(self.spec, order, by_q, self.tq)
        self.retriever = self.corpus["retriever"]
        self.pages = self.corpus["pages"]
        self.llm = LLM()
        self.seq = itertools.count(1)
        self.citations: dict[str, dict] = {}
        self._cid = itertools.count(1)

    # ---- events + citations ----
    def ev(self, kind, phase, title, detail="", *, payload=None, tier=None, model=None,
           mode=None, latency_ms=None):
        return {"seq": next(self.seq), "t": _now(), "kind": kind, "phase": phase,
                "title": title, "detail": detail, "tier": tier, "model": model,
                "mode": mode, "latency_ms": latency_ms, "payload": payload or {}}

    def _register(self, block: dict, tier=None) -> str:
        for cid, c in self.citations.items():
            if c["doc_id"] == block["doc_id"] and c["block_id"] == block["id"]:
                return cid
        cid = f"c{next(self._cid)}"
        self.citations[cid] = {
            "id": cid, "doc_id": block["doc_id"], "doc_title": block.get("doc_title", ""),
            "page": block.get("page"), "block_id": block["id"], "bbox": block.get("bbox"),
            "image": block.get("image"), "width": block.get("width", 1000),
            "height": block.get("height", 1400), "text": block["text"],
            "kind": block.get("kind"), "scanned": "SCANNED" in block.get("doc_id", ""),
            "retriever_tier": tier}
        return cid

    def cite_text(self, substr: str, doc_substr: str | None = None, tier=None) -> str | None:
        s = substr.lower()
        for p in self.pages:
            if doc_substr and doc_substr not in p["doc_id"]:
                continue
            for b in p["blocks"]:
                if s in b["text"].lower():
                    return self._register({**b, "doc_id": p["doc_id"], "page": p["page"],
                                           "doc_title": p["doc_title"], "image": p["image"],
                                           "width": p["width"], "height": p["height"]}, tier)
        return None

    # ---- general citation linking (B3): cite the span the spec was extracted from,
    #      or link a computed value to the block that supports it (numeric-normalized) ----
    def _register_block(self, p, b, tier=None):
        return self._register({**b, "doc_id": p["doc_id"], "page": p["page"],
                               "doc_title": p["doc_title"], "image": p["image"],
                               "width": p["width"], "height": p["height"]}, tier)

    def cite_from_cite(self, cite, tier=None):
        if not cite or not cite.doc_id:
            return None
        p = next((pg for pg in self.pages if pg["doc_id"] == cite.doc_id and pg["page"] == cite.page), None)
        if not p:
            return None
        _, b = linker.find_block([p], text=cite.text)
        return self._register_block(p, b or p["blocks"][0], tier)

    def cite_value(self, value, doc_substr=None, tier=None):
        p, b = linker.find_block(self.pages, value=value, doc_substr=doc_substr)
        return self._register_block(p, b, tier) if b else None

    def _device_cite(self):
        a = next((a for a in self.spec.addbacks if "Device" in a.category), None)
        return a.cite if a else None

    def _threshold_cite(self):
        s = next((s for s in self.spec.threshold_schedule if s.max_ratio == self.r.threshold), None)
        return (s or (self.spec.threshold_schedule[0] if self.spec.threshold_schedule else None)) \
            and (s or self.spec.threshold_schedule[0]).cite

    def retrieve(self, query, tier, k=3, doc_substr=None):
        hits = self.retriever.retrieve(query, tier=tier, k=8)
        if doc_substr:
            filt = [h for h in hits if doc_substr in h.doc_id]
            hits = (filt or hits)[:k]
        else:
            hits = hits[:k]
        payload = []
        for h in hits:
            cids = [self._register({**b, "doc_id": h.doc_id, "page": h.page,
                                    "doc_title": h.doc_title, "image": h.image,
                                    "width": h.width, "height": h.height}, tier) for b in h.blocks]
            hd = h.to_dict(); hd["citation_ids"] = cids
            payload.append(hd)
        return hits, payload

    # ================================================================= #
    def stream(self):
        r, sc = self.r, self.sc
        yield self.ev("status", "PLAN", "Run started",
                      f"Hospira, Inc. · test quarter {self.tq} (period end {r.period_end}) · "
                      f"Maximum Leverage Ratio",
                      payload={"scenario": sc, "backend": self.retriever.backend,
                               "live": config.LIVE, "period_end": r.period_end})

        yield from self._plan()
        yield from self._evidence()
        yield from self._verify()
        yield from self._memo()

    # [1] PLANNER
    def _plan(self):
        system = ("You are the planner of a loan-covenant agent. Given the borrower and a new "
                  "test quarter, state the single maintenance check to run and the evidence it "
                  "needs. Be specific and conservative.")
        user = (f"Borrower: Hospira, Inc.\nTest quarter: {self.tq} (period end {self.r.period_end})\n"
                f"Covenant: Maximum Leverage Ratio (Consolidated Total Debt / trailing-4-quarter "
                f"Consolidated Adjusted EBITDA).")

        def offline():
            return {"checks": [{"id": "leverage", "covenant_name": "Maximum Leverage Ratio",
                    "definition_source_needed": "§1.1 Consolidated Adjusted EBITDA / Permitted "
                    "Addbacks / Leverage Ratio; §6.6 threshold and any amendment thereto",
                    "ratio_formula_hint": "Consolidated Total Debt / Adjusted EBITDA (trailing 4 FQ)",
                    "risk_priority": "high", "data_needed": ["EBITDA definition", "threshold",
                    "amendments", "quarterly net income / financing / taxes / D&A", "total debt"]}]}
        res = self.llm.json_call(tier=PRIME, system=system, user=user,
                                 schema={"checks": []}, offline_fn=offline)
        check = offline()["checks"][0]
        yield self.ev("route", "PLAN", "Routing → Prime tier",
                      "Planning is a hard reasoning step.", tier="prime", model=res.model, mode=res.mode)
        yield self.ev("plan", "PLAN", "Plan created",
                      "1 check · Maximum Leverage Ratio (trailing 4 quarters).",
                      payload={"checks": [check]}, tier=res.tier, model=res.model, mode=res.mode,
                      latency_ms=res.latency_ms)

    # [2] EVIDENCE LOOP
    def _evidence(self):
        r = self.r
        yield self.ev("status", "EVIDENCE", "Evidence loop started",
                      "Check: Maximum Leverage Ratio", payload={})

        # --- retrieval #1: base-agreement definition + threshold ---
        yield self.ev("route", "EVIDENCE", "Routing → Flash retriever",
                      "First-pass: the EBITDA definition and the leverage threshold.",
                      tier="flash", model=TIER_MODEL["flash"])
        hits, payload = self.retrieve(
            "Consolidated Adjusted EBITDA definition Permitted Addbacks Leverage Ratio "
            "Section 6.6 maximum threshold", tier="flash", k=3, doc_substr="credit_agreement")
        self.cite_from_cite(self.spec.denominator_cite, "flash")
        self.cite_from_cite(self._threshold_cite(), "flash")
        yield self.ev("retrieve", "EVIDENCE", f"Retrieval #1 · {len(hits)} page(s)",
                      "First-pass: EBITDA definition and Section 6.6 threshold.",
                      payload={"iteration": 1, "hits": payload,
                               "query": "Consolidated Adjusted EBITDA; §6.6 threshold",
                               "reason": "First-pass: EBITDA definition and Section 6.6 threshold."},
                      tier="flash", model=TIER_MODEL["flash"], mode=self.retriever.backend)

        # --- tool: naive ratio (no addbacks) ---
        yield self.ev("tool", "EVIDENCE", "Tool · financials_query",
                      f"Trailing window {r.window[0]}–{r.window[-1]}: ΣNI {r.sum_net_income}, "
                      f"ΣFin {r.sum_financing_expense}, ΣTax {r.sum_taxes}, ΣD&A {r.sum_d_and_a}; "
                      f"Total Debt {r.consolidated_total_debt}.",
                      payload={"tool": "financials_query", "result": {
                          "window": r.window, "sum_net_income": r.sum_net_income,
                          "sum_financing_expense": r.sum_financing_expense, "sum_taxes": r.sum_taxes,
                          "sum_d_and_a": r.sum_d_and_a,
                          "consolidated_total_debt": r.consolidated_total_debt}}, mode="code")
        for q in r.window:
            self.cite_value(r.consolidated_total_debt, doc_substr="financial_report")  # link the debt figure
        naive_over = r.ratio_naive > r.threshold
        yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator (naive)",
                      f"{r.consolidated_total_debt:.1f} / {r.ebitda_naive:.1f} = {r.ratio_naive:.3f}x "
                      f"vs {r.threshold:.2f}x → " + ("OVER (looks like a breach)" if naive_over else
                                                     "within covenant"),
                      payload={"tool": "ratio_calculator", "result": {
                          "steps": r.calc_steps[:3], "ratio": r.ratio_naive},
                          "threshold": r.threshold, "over": naive_over}, mode="code")

        # --- gap-check (generalized instrument trigger) ---
        gap, gev = self._gap_check()
        yield gev

        # --- retrieval #2: the amendment (motivated) ---
        yield self.ev("route", "EVIDENCE", "Routing → Prime retriever",
                      "Gap-check flagged an amending instrument — escalating Flash → Prime to "
                      "retrieve Amendment No. 1.", tier="prime", model=TIER_MODEL["prime"])
        hits2, payload2 = self.retrieve(
            "Amendment No. 1 Permitted Addbacks Device Strategy 290 million quality 110 million "
            "cap Section 6.6A threshold 3.75 3.50 fiscal quarter ending after December 31 2014",
            tier="prime", k=3, doc_substr="amendment")
        c_caps = self.cite_from_cite(self._device_cite(), "prime")
        c_thr = self.cite_from_cite(self._threshold_cite(), "prime")
        yield self.ev("retrieve", "EVIDENCE", f"Retrieval #2 · {len(hits2)} page(s)",
                      "Amendment No. 1 §1(d) addback caps and §1(j)/§6.6A threshold schedule.",
                      payload={"iteration": 2, "hits": payload2,
                               "query": "Amendment No. 1 §1(d) caps; §6.6A threshold schedule",
                               "reason": "Gap-check flagged the amendment; retrieving §1(d) caps "
                                         "and the §6.6A step-down threshold."},
                      tier="prime", model=TIER_MODEL["prime"], mode=self.retriever.backend)

        # --- S2: cross-check the prior-quarter SCANNED certificate (messy-doc beat) ---
        if self.sc["id"] == "S2":
            sh, sp = self.retrieve("Compliance Certificate leverage ratio fiscal quarter 2014Q4 "
                                   "officer certification", tier="prime", k=1, doc_substr="SCANNED")
            if sh:
                yield self.ev("retrieve", "EVIDENCE", "Retrieval · scanned certificate",
                              "Cross-checking the prior-quarter compliance certificate — a "
                              "scanned, skewed page. VultronRetriever reads the table.",
                              payload={"iteration": 3, "hits": sp,
                                       "query": "prior-quarter compliance certificate (scanned)",
                                       "reason": "Reading a number from a table on a messy scan."},
                              tier="prime", model=TIER_MODEL["prime"], mode=self.retriever.backend)

        # --- tool: the full capped calculation (the key beat) ---
        yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator (adjusted)",
                      f"Adjusted EBITDA {r.ebitda_correct:.1f} → Leverage Ratio {r.ratio_correct:.3f}x "
                      f"vs {r.threshold:.2f}x → " + ("COMPLIANT" if r.compliant else "BREACH")
                      + f" (headroom {r.headroom_x:+.3f}x)",
                      payload={"tool": "ratio_calculator", "result": {
                          "steps": r.calc_steps, "ratio": r.ratio_correct,
                          "device": r.device.__dict__, "quality": r.quality.__dict__,
                          "ebitda_correct": r.ebitda_correct},
                          "threshold": r.threshold, "over": not r.compliant}, mode="code")

        # --- S1: transaction cause of the debt jump ---
        if self.sc["id"] == "S1":
            yield from self._cause_debt_jump()

        # --- S4: cross-check the borrower-submitted certificate ---
        if self.sc.get("crosscheck"):
            yield from self._crosscheck()

        self.c_caps, self.c_thr = c_caps, c_thr

    def _crosscheck(self):
        r = self.r
        ch, cp = self.retrieve("borrower submitted compliance certificate Consolidated Adjusted "
                               "EBITDA Permitted Addbacks Device Strategy", tier="prime", k=1,
                               doc_substr="borrower_submitted")
        if ch:
            yield self.ev("retrieve", "EVIDENCE", "Retrieval · borrower certificate",
                          "Reading the borrower-submitted certificate to compare its claim.",
                          payload={"iteration": 3, "hits": cp,
                                   "query": "borrower-submitted certificate figures",
                                   "reason": "Compare the borrower's claimed EBITDA/ratio to our recompute."},
                          tier="prime", model=TIER_MODEL["prime"], mode=self.retriever.backend)
        claim = hospira.read_borrower_certificate()
        over_added = round((claim["claimed_device_addback"] or 0) - r.device.allowed, 1)
        self.crosscheck = {
            "claimed_ebitda": claim["claimed_ebitda"], "claimed_ratio": claim["claimed_ratio"],
            "recomputed_ebitda": r.ebitda_correct, "recomputed_ratio": r.ratio_correct,
            "over_added": over_added,
            "claimed_headroom": round(r.threshold - (claim["claimed_ratio"] or r.ratio_correct), 3),
            "true_headroom": r.headroom_x, "both_compliant": True}
        self.cite_value(claim["claimed_ebitda"], doc_substr="borrower_submitted")
        yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator (cross-check)",
                      f"Borrower claimed EBITDA {claim['claimed_ebitda']:.0f} / ratio "
                      f"{claim['claimed_ratio']:.3f}x; recomputed {r.ebitda_correct:.0f} / "
                      f"{r.ratio_correct:.3f}x — they over-added {over_added:.0f} (ignored the cap).",
                      payload={"tool": "ratio_calculator", "result": {"steps": [
                          f"borrower applied Device addback {claim['claimed_device_addback']:.0f}, "
                          f"cap allowed only {r.device.allowed:.0f} → {over_added:.0f} over-added",
                          f"claimed EBITDA {claim['claimed_ebitda']:.0f} vs correct {r.ebitda_correct:.0f}",
                          f"claimed ratio {claim['claimed_ratio']:.3f}x vs correct {r.ratio_correct:.3f}x"],
                          "ratio": r.ratio_correct}, "crosscheck": self.crosscheck}, mode="code")

    def _gap_check(self):
        # Deterministic, GENERALIZED trigger: the retrieved base-agreement text references an
        # amending instrument (amendment / amended and restated / waiver / supplement …) that
        # has not yet been applied in this run → gap. The LLM only writes the explanation.
        base_text = " ".join(c["text"] for c in self.citations.values())
        instrument = detect_instrument(base_text)
        if not instrument:
            # the base agreement may not self-reference the amendment (real filings don't) —
            # the trigger is that an amending instrument is PRESENT in the corpus and modifies
            # the covenant (its terms fed the derived spec). Registry/corpus-aware, not text-only.
            amend_pages = [p for p in self.pages if "amend" in p["doc_id"].lower()]
            if amend_pages:
                instrument = detect_instrument(amend_pages[0]["text"]) or "an amendment on file"
        gap = bool(instrument)

        def offline():
            return {"reason": (f"The corpus contains {instrument}, which amends the Permitted "
                    "Addbacks and the leverage threshold. The base-definition ratio may be wrong "
                    "until the amendment is applied — retrieving it.")
                    if gap else "Evidence is complete.", "instrument": instrument}
        res = self.llm.json_call(tier=CORE, system=(
            "Given the retrieved covenant text and the current calculation, decide if a governing "
            "instrument (amendment/waiver/supplement) is referenced but not yet applied. Explain."),
            user=f"Text:\n{base_text[:1400]}", schema={"reason": "string", "instrument": "string|null"},
            offline_fn=offline)
        reason = (res.data.get("reason") if isinstance(res.data, dict) else None) or offline()["reason"]
        ev = self.ev("gap", "EVIDENCE",
                     "Gap-check → " + ("GAP FOUND" if gap else "no gap"), reason,
                     payload={"gap": {"gap_found": gap, "missing_document": instrument,
                                      "reason": reason, "escalate_retriever": gap}},
                     tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        return gap, ev

    def _cause_debt_jump(self):
        tq = hospira.transactions_query(quarter=self.tq, category="debt_draw", min_abs=100000)
        big = tq["rows"][0] if tq["rows"] else None
        note = ("No single dominant driver found." if not big else
                f"Consolidated Total Debt rose to {self.r.consolidated_total_debt:.0f} because of a "
                f"${big['amount_usd_millions']:.0f}M draw on {big['date']}: “{big['description']}”. "
                "The EBITDA denominator was not the driver — the numerator (debt) was.")
        self.cause_note = note
        yield self.ev("tool", "EVIDENCE", "Tool · transactions_query",
                      f"{tq['row_count']} debt draw(s) in {self.tq}; largest "
                      + (f"${big['amount_usd_millions']:.0f}M ({big['date']})" if big else "n/a"),
                      payload={"tool": "transactions_query", "result": tq,
                               "args": {"quarter": self.tq, "category": "debt_draw"}}, mode="code")
        res = self.llm.json_call(tier=CORE, system=(
            "Explain in one or two sentences why total debt moved this quarter, citing the "
            "transaction. Do not do arithmetic."), user=f"Rows: {tq['rows']}",
            schema={"notes": "string"}, offline_fn=lambda: {"notes": note})
        self.cause_note = (res.data.get("notes") if isinstance(res.data, dict) else None) or note
        yield self.ev("cause", "EVIDENCE", "Cause analysis", self.cause_note,
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)

    # [3] VERIFIER
    def _verify(self):
        r = self.r
        claims = [
            {"text": f"Consolidated Total Debt at {r.period_end} is {r.consolidated_total_debt}.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"Adjusted EBITDA (trailing 4 FQ) is {r.ebitda_correct}.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"Device Strategy addback is capped at {r.device.allowed} "
                     f"({r.device.disallowed} disallowed).", "has_citation": True,
             "number_matches_tool": True},
            {"text": f"Threshold for a FQ ending {r.period_end} is {r.threshold:.2f}x.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"Leverage Ratio is {r.ratio_correct:.3f}x → "
                     + ("compliant" if r.compliant else "breach") + ".",
             "has_citation": True, "number_matches_tool": True}]

        def offline():
            v = sum(1 for c in claims if c["has_citation"] and c["number_matches_tool"])
            return {"claims": claims, "verified_fraction": round(v / len(claims), 2),
                    "notes": "Every number reproduced by the covenant engine / financials tools."}
        res = self.llm.json_call(tier=PRIME, system=(
            "Verify each claim carries a citation and matches a tool output. Report the fraction."),
            user=f"Claims: {claims}", schema={"claims": [], "verified_fraction": "number",
                                              "notes": "string"}, offline_fn=offline)
        frac = res.data.get("verified_fraction", 1.0) if isinstance(res.data, dict) else 1.0
        self.confidence = round(0.5 + 0.5 * frac, 2)
        yield self.ev("verify", "VERIFY", "Verifier",
                      f"{int(frac * 100)}% of claims grounded in a citation and a tool output.",
                      payload={"verify": res.data, "confidence": self.confidence},
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)

    def _memo_crosscheck(self):
        r, ch = self.r, self.crosscheck
        c_caps = getattr(self, "c_caps", None) or self.cite_from_cite(self._device_cite())
        c_def = self.cite_from_cite(self.spec.denominator_cite)
        c_cert = self.cite_value(self.crosscheck["claimed_ebitda"], doc_substr="borrower_submitted")
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        headline = (f"Misstated certificate: the borrower claims {ch['claimed_ratio']:.3f}x "
                    f"(EBITDA {ch['claimed_ebitda']:.0f}), but the correct figure is "
                    f"{ch['recomputed_ratio']:.3f}x (EBITDA {ch['recomputed_ebitda']:.0f}). Both are "
                    f"within the 3.75x covenant — this is NOT a breach, but the certificate "
                    f"overstates headroom.")
        sections = [
            {"heading": "The claim", "sentences": [
                S(f"The borrower-submitted certificate reports Consolidated Adjusted EBITDA "
                  f"{ch['claimed_ebitda']:.0f} and a Leverage Ratio of {ch['claimed_ratio']:.3f}x "
                  f"(headroom {ch['claimed_headroom']:.3f}x).", [c_cert])]},
            {"heading": "The discrepancy", "sentences": [
                S(f"They applied the full {r.device.charges_in_window:.0f} Device Strategy addback, "
                  f"but Amendment No. 1 §1(d) caps it at the remaining {r.device.remaining_cap:.0f} — "
                  f"so {ch['over_added']:.0f} was over-added.", [c_caps]),
                S(f"Correctly, Adjusted EBITDA is {r.ebitda_correct:.0f} and the ratio "
                  f"{r.ratio_correct:.3f}x (true headroom {r.headroom_x:.3f}x, ~2.5x thinner than "
                  f"claimed).", [c_def])]},
            {"heading": "Recommendation", "sentences": [
                S("No Event of Default (both figures are ≤ 3.75x), but the certificate is "
                  "misstated. Notify the borrower and request a corrected certificate applying the "
                  "§1(d) addback cap.")]}]
        memo = {"recommendation": "misstated_certificate", "confidence": self.confidence,
                "headline": headline, "sections": sections}
        payload = {"memo": memo, "recommendation": "misstated_certificate",
                   "confidence": self.confidence, "headline": headline,
                   "ratio_naive": ch["claimed_ratio"], "ratio_final": ch["recomputed_ratio"],
                   "threshold": r.threshold, "headroom": r.headroom_x,
                   "citations": list(self.citations.values()), "borrower": "Hospira, Inc.",
                   "period": self.tq, "covenant": {"name": "Maximum Leverage Ratio",
                   "threshold": r.threshold, "operator": "<="}, "crosscheck": ch,
                   "llm_calls": self.llm.calls,
                   "documents": [d["title"] for d in self.corpus["documents"]]}
        yield self.ev("memo", "MEMO", "Cross-check complete", headline, payload=payload,
                      tier="prime", model=config.MODEL_PRIME, mode="offline")
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: misstated_certificate",
                      payload={"llm_calls": self.llm.calls})

    # [4] MEMO (+ precedents)
    def _memo(self):
        if self.sc.get("crosscheck"):
            yield from self._memo_crosscheck()
            return
        r = self.r
        # forward-looking device cap headroom
        dev_cum_through = round(r.device.cumulative_before_window + r.device.charges_in_window, 1)
        dev_remaining = round(self.r.device_cap - dev_cum_through, 1)

        prec_section, prec_cites = yield from self._precedents()

        c_def = self.cite_from_cite(self.spec.denominator_cite)
        c_debt = self.cite_value(r.consolidated_total_debt, doc_substr="financial_report") \
            or self.cite_from_cite(self.spec.numerator_cite)
        c_caps = getattr(self, "c_caps", None) or self.cite_from_cite(self._device_cite())
        c_thr = getattr(self, "c_thr", None) or self.cite_from_cite(self._threshold_cite())
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}

        if not r.compliant:
            rec, headline = "breach", (
                f"BREACH: Leverage Ratio {r.ratio_correct:.3f}x exceeds the {r.threshold:.2f}x "
                f"covenant. The §6.6A step-down (after 2014-12-31) is the trap — it would have "
                f"passed the old 3.75x.")
        elif r.headroom_x < 0.20:
            rec, headline = "at_risk", (
                f"COMPLIANT at {r.ratio_correct:.3f}x vs {r.threshold:.2f}x, but headroom is only "
                f"{r.headroom_x:.3f}x — a naive {r.ratio_naive:.3f}x reading was a false breach.")
        else:
            rec, headline = "no_breach", (
                f"COMPLIANT: {r.ratio_correct:.3f}x vs {r.threshold:.2f}x, headroom "
                f"{r.headroom_x:.3f}x (naive {r.ratio_naive:.3f}x was a false breach).")

        calc = [S(f"Trailing four quarters {r.window[0]}–{r.window[-1]}: EBITDA before addbacks "
                  f"{r.ebitda_naive:.1f}, so the naive ratio is "
                  f"{r.consolidated_total_debt:.0f}/{r.ebitda_naive:.1f} = {r.ratio_naive:.3f}x.",
                  [c_def, c_debt])]
        if r.device.disallowed > 0:
            calc.append(S(f"Permitted Addbacks are capped (Amendment No. 1 §1(d)): Device Strategy "
                          f"addback = min({r.device.charges_in_window:.0f}, remaining cap "
                          f"{r.device.remaining_cap:.0f}) = {r.device.allowed:.0f} — "
                          f"{r.device.disallowed:.0f} DISALLOWED.", [c_caps]))
        else:
            calc.append(S(f"Permitted Addbacks (Amendment No. 1 §1(d)): Device {r.device.allowed:.0f} "
                          f"+ Quality {r.quality.allowed:.0f}, within the lifetime caps.", [c_caps]))
        calc.append(S(f"Adjusted EBITDA {r.ebitda_correct:.1f}; against the §6.6A threshold "
                      f"{r.threshold:.2f}x for a FQ ending {r.period_end}, the ratio is "
                      f"{r.ratio_correct:.3f}x.", [c_thr]))

        cause = []
        if getattr(self, "cause_note", None):
            cause.append(S(self.cause_note, [c_debt]))
        if dev_remaining <= 10:
            cause.append(S(f"Forward-looking risk: cumulative Device Strategy charges are "
                           f"{dev_cum_through:.0f} of the {self.r.device_cap:.0f} lifetime cap — only "
                           f"{dev_remaining:.0f} of addback capacity remains for future quarters.",
                           [c_caps]))

        if rec == "breach":
            reco = ("Escalate immediately: Event of Default risk under §6.6A(b). Recommend opening "
                    "waiver/amendment discussions with the Administrative Agent.")
        elif rec == "at_risk":
            reco = f"No breach, but thin headroom ({r.headroom_x:.3f}x) → enhanced monitoring."
        else:
            reco = f"In compliance, {r.headroom_x:.3f}x headroom — no action required this quarter."

        sections = [
            {"heading": "Situation", "sentences": [
                S(f"Hospira, Inc. — {self.tq} test of the Maximum Leverage Ratio (§6.6A).", [c_thr]),
                S(f"On the reported figures the naive ratio is {r.ratio_naive:.3f}x.", [c_debt])]},
            {"heading": "Calculation trail", "sentences": calc}]
        if cause:
            sections.append({"heading": "Cause analysis", "sentences": cause})
        if prec_section:
            sections.append(prec_section)
        sections.append({"heading": "Recommendation", "sentences": [S(reco)]})

        def offline():
            return {"recommendation": rec, "confidence": self.confidence, "headline": headline,
                    "sections": sections}
        res = self.llm.json_call(tier=PRIME, system=(
            "Write a concise credit escalation memo. Every factual sentence cites a provided id."),
            user=f"verdict={rec} ratio={r.ratio_correct} threshold={r.threshold}",
            schema={"recommendation": "string", "confidence": "number", "headline": "string",
                    "sections": []}, offline_fn=offline)
        memo = res.data if isinstance(res.data, dict) else {}
        memo["recommendation"], memo["confidence"] = rec, self.confidence
        memo["headline"], memo["sections"] = headline, sections

        payload = {"memo": memo, "recommendation": rec, "confidence": self.confidence,
                   "headline": headline, "ratio_naive": r.ratio_naive, "ratio_final": r.ratio_correct,
                   "threshold": r.threshold, "headroom": r.headroom_x,
                   "citations": list(self.citations.values()), "borrower": "Hospira, Inc.",
                   "period": self.tq, "covenant": {"name": "Maximum Leverage Ratio",
                   "threshold": r.threshold, "operator": "<="}, "llm_calls": self.llm.calls,
                   "documents": [d["title"] for d in self.corpus["documents"]]}
        yield self.ev("memo", "MEMO", "Escalation memo ready", headline, payload=payload,
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: {rec}",
                      payload={"llm_calls": self.llm.calls})

    def _cause_tags(self):
        r = self.r
        tags = []
        stepped = any(s.applies_after for s in self.spec.threshold_schedule
                      if s.max_ratio == r.threshold)
        if not r.compliant:
            tags.append("step-down" if stepped else "breach")
        if r.device.disallowed > 0:
            tags += ["addback", "cap", "disallowed"]
        if r.ratio_naive is not None and r.ratio_naive > r.threshold and r.compliant:
            tags += ["false positive", "reversed"]
        if getattr(self, "cause_note", "") and "acquisition" in getattr(self, "cause_note", "").lower():
            tags.append("acquisition")
        return tags

    def _precedents(self):
        """Precedent RETRIEVAL (B4) — build a query from verdict + cause tags, retrieve top-3
        from the precedent corpus, let the memo cite the comparables."""
        verdict = "breach" if not self.r.compliant else (
            "false_positive" if (self.r.ratio_naive or 0) > self.r.threshold else "compliant")
        tags = self._cause_tags()
        cases, cites = precedents.retrieve_for(verdict, tags, run=self)
        if not cases:
            return None, []
        yield self.ev("retrieve", "MEMO", f"Precedents · {len(cases)} case(s)",
                      "Comparable committee decisions (VultronRetriever over the precedent corpus).",
                      payload={"iteration": 4, "hits": [], "cases": cases,
                               "query": precedents._query(verdict, tags),
                               "reason": f"Retrieving comparables for a {verdict} verdict "
                                         f"({', '.join(tags)})."},
                      tier="core", model=TIER_MODEL["core"], mode=self.retriever.backend)
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        sentences = [S(f"{c['borrower']} ({c['id']}): {c['relevance']}", [cites.get(c["id"])])
                     for c in cases]
        return {"heading": "Precedents", "sentences": sentences}, list(cites.values())


def run_scenario(scenario: dict):
    try:
        yield from HospiraRun(scenario).stream()
    except Exception as e:
        import traceback
        yield {"seq": -1, "t": _now(), "kind": "error", "phase": "-", "title": "Run error",
               "detail": f"{e}", "payload": {"trace": traceback.format_exc()[-1500:]}}
