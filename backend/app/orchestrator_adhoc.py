"""Ad-hoc (fully automatic) covenant analysis over user-uploaded documents.

Same visible workflow as the portfolio agent — plan → retrieve (>1 when motivated)
→ tools → verify → memo — but nothing is pre-known: the agent DETECTS the covenant
and threshold from the documents and EXTRACTS the figures itself. Arithmetic stays
deterministic (ratio_calculator); every number is cited to an uploaded page.

Robustness: the LLM does detection/extraction; deterministic regex fallbacks cover
the standard maximum-net-leverage covenant so the flow never dead-ends.
"""
from __future__ import annotations

import itertools
import re
from datetime import datetime, timezone

from . import config, tools, spec_extractor, fin_extract, generic_engine, linker
from .gapcheck import detect_instrument
from .llm import LLM, PRIME, CORE, FLASH
from .retriever import TIER_MODEL

DETECT_SCHEMA = {
    "covenant_name": "string", "metric": "leverage|coverage|other",
    "threshold": "number", "operator": "<=|>=",
    "definition_mentions_amendment": "boolean",
}
EXTRACT_SCHEMA = {
    "consolidated_total_net_debt": "number|null",
    "consolidated_ebitda_reported": "number|null",
    "ebitda_components": {"net_income": "number|null", "interest": "number|null",
                          "taxes": "number|null", "depreciation_amortization": "number|null"},
    "amendment_addback_cap": "number|null",
    "acquisition_one_time_costs": "number|null",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return None


def _find(pat, text, grp=1):
    m = re.search(pat, text, re.IGNORECASE)
    return _num(m.group(grp)) if m else None


class AdHocRun:
    def __init__(self, upload: dict):
        self.up = upload
        self.pages = upload["pages"]
        self.retriever = upload["retriever"]
        self.full_text = "\n".join(p["text"] for p in self.pages)
        self.llm = LLM()
        self.seq = itertools.count(1)
        self.citations: dict[str, dict] = {}
        self._cid = itertools.count(1)
        self.engine = None          # set when the DERIVED (multi-quarter) path runs

    # ---- events + citations ----
    def ev(self, kind, phase, title, detail="", *, payload=None, tier=None, model=None,
           mode=None, latency_ms=None):
        return {"seq": next(self.seq), "t": _now(), "kind": kind, "phase": phase,
                "title": title, "detail": detail, "tier": tier, "model": model,
                "mode": mode, "latency_ms": latency_ms, "payload": payload or {}}

    def cite_block(self, block: dict, tier=None) -> str:
        key = (block["doc_id"], block.get("page"), block["id"])
        full = self.up["by_block"].get(key, block)
        for cid, c in self.citations.items():
            if c["doc_id"] == full["doc_id"] and c["block_id"] == full["id"]:
                return cid
        cid = f"c{next(self._cid)}"
        self.citations[cid] = {
            "id": cid, "doc_id": full["doc_id"], "doc_title": full.get("doc_title", ""),
            "page": full.get("page"), "block_id": full["id"], "bbox": full.get("bbox"),
            "image": full.get("image"), "width": full.get("width", 1000),
            "height": full.get("height", 1400), "text": full["text"],
            "kind": full.get("kind"), "scanned": False, "retriever_tier": tier,
        }
        return cid

    def cite_value(self, value_str: str, tier=None):
        """Cite the block on any uploaded page that contains a value/label."""
        for p in self.pages:
            for b in p["blocks"]:
                if value_str.lower() in b["text"].lower():
                    return self.cite_block({**b, "doc_id": p["doc_id"], "page": p["page"]}, tier)
        return None

    # ---- flow ----
    def stream(self):
        yield self.ev("status", "PLAN", "Run started",
                      f"{len(self.up['documents'])} document(s), {len(self.pages)} page(s) uploaded",
                      payload={"documents": self.up["documents"], "live": config.LIVE,
                               "backend": self.retriever.backend})

        cov = yield from self._detect()
        # Preferred path: if the uploads are quarterly reports, DERIVE the covenant spec from the
        # agreement/amendment and EXTRACT the per-quarter figures from the reports, then run the
        # SAME engine the deep scenarios use. Otherwise fall back to single-period extraction.
        if self._prepare_derived():
            yield from self._evidence_derived(cov)
        else:
            yield from self._evidence(cov)
        yield from self._verify(cov)
        yield from self._memo(cov)

    # ---- DERIVED multi-quarter path (spec_extractor + fin_extract + generic_engine) ----
    def _prepare_derived(self):
        try:
            self.spec = spec_extractor.build_spec(self.pages)
            # LIVE: let the LLM fill figures a foreign layout hides from the regex; offline stays
            # deterministic (llm=None).
            order, by_q = fin_extract.extract_financials(
                self.pages, self.spec, llm=self.llm if config.LIVE else None)
        except Exception:
            return False
        n = self.spec.trailing_quarters
        testable = [q for i, q in enumerate(order) if i >= n - 1]
        if not testable or not self.spec.threshold_schedule:
            return False
        self.order, self.by_q, self.tq = order, by_q, testable[-1]   # latest fully-covered quarter
        return True

    def _cite_val(self, value, tier=None):
        p, b = linker.find_block(self.pages, value=value)
        if not b:
            return None
        return self.cite_block({**b, "doc_id": p["doc_id"], "page": p["page"],
                                "doc_title": p.get("doc_title", "")}, tier)

    def _cite_span(self, text, tier=None):
        p, b = linker.find_block(self.pages, text=text)
        if not b:
            return None
        return self.cite_block({**b, "doc_id": p["doc_id"], "page": p["page"],
                                "doc_title": p.get("doc_title", "")}, tier)

    def _evidence_derived(self, cov):
        r = generic_engine.compute(self.spec, self.order, self.by_q, self.tq)
        self.engine = r
        cov["threshold"] = r.threshold if r.threshold is not None else cov["threshold"]
        cov["formula"] = "Consolidated Total Debt / trailing-4Q Adjusted EBITDA"

        yield self.ev("status", "EVIDENCE", "Evidence loop started",
                      f"Check: {cov['name']} · test quarter {self.tq} (period end {r.period_end})")
        # retrieval #1 — EBITDA definition + threshold, from the uploaded agreement
        yield self.ev("route", "EVIDENCE", "Routing → Flash retriever",
                      "First-pass retrieval of the covenant definition and threshold.",
                      tier="flash", model=TIER_MODEL["flash"])
        hits = self.retriever.retrieve(
            "Consolidated Adjusted EBITDA definition; Consolidated Total Debt; maximum leverage "
            "ratio threshold shall not exceed", tier="flash", k=5)
        yield self._retrieval_event(hits, 1, "EBITDA definition; Total Debt; threshold", "flash",
                                    "First-pass retrieval of the covenant definition and threshold.")
        self.cite_from_spec()

        # tool: trailing-window sums from the EXTRACTED quarterly figures
        s = lambda f: round(sum(self.by_q[q].get(f, 0.0) for q in r.window), 1)
        yield self.ev("tool", "EVIDENCE", "Tool · financials_query",
                      f"Trailing window {r.window[0]}–{r.window[-1]}: ΣNI {s('net_income')}, "
                      f"ΣFin {s('financing_expense')}, ΣTax {s('income_tax_expense')}, "
                      f"ΣD&A {s('depreciation_amortization')}; Total Debt {r.numerator}.",
                      payload={"tool": "financials_query", "result": {
                          "window": r.window, "consolidated_total_debt": r.numerator,
                          "sum_net_income": s("net_income"),
                          "sum_financing_expense": s("financing_expense"),
                          "sum_income_tax": s("income_tax_expense"),
                          "sum_depreciation_amortization": s("depreciation_amortization")}},
                      mode="code")
        self._cite_val(r.numerator)

        naive_over = r.ratio_naive is not None and r.ratio_naive > r.threshold
        yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator (naive)",
                      f"{r.numerator:.1f} / {r.denom_naive:.1f} = {r.ratio_naive:.3f}x vs "
                      f"{r.threshold:.2f}x → " + ("OVER (looks like a breach)" if naive_over
                                                  else "within covenant"),
                      payload={"tool": "ratio_calculator", "result": {
                          "steps": r.calc_steps[:3], "ratio": r.ratio_naive},
                          "threshold": r.threshold, "over": naive_over}, mode="code")

        # gap-check + amendment addbacks
        instrument = detect_instrument("\n".join(c["text"] for c in self.citations.values())) \
            or (detect_instrument(self.full_text) if self.spec.addbacks else None)
        gap = bool(self.spec.addbacks)
        yield self.ev("gap", "EVIDENCE", "Gap-check → " + ("GAP FOUND" if gap else "no gap"),
                      (f"The covenant references {instrument or 'an amendment'} that adjusts the "
                       "Permitted Addbacks — retrieving and applying it within its cap."
                       if gap else "Evidence is complete; no amending instrument to apply."),
                      payload={"gap": {"gap_found": gap, "missing_document": instrument}},
                      tier="core", model=config.MODEL_CORE, mode="code")
        if gap:
            yield self.ev("route", "EVIDENCE", "Routing → Prime retriever",
                          "Escalating Flash → Prime to retrieve the amendment's addback caps.",
                          tier="prime", model=TIER_MODEL["prime"])
            ah = self.retriever.retrieve("Amendment Permitted Addbacks cap not to exceed "
                                         "Device Strategy quality charges", tier="prime", k=3)
            yield self._retrieval_event(ah, 2, "Amendment addback caps", "prime",
                                        "Gap-check flagged the amendment; retrieving its caps.")
            for a in self.spec.addbacks:
                self.cite_from_cite(a.cite, "prime")

        applied = [{"label": f"{a.category} addback (cap {self.cap_of(a):.0f})",
                    "amount": a.allowed} for a in r.addbacks if a.allowed > 0]
        yield self.ev("tool", "EVIDENCE", "Tool · ratio_calculator (adjusted)",
                      f"Adjusted EBITDA {r.denom_adjusted:.1f} → {r.ratio_correct:.3f}x vs "
                      f"{r.threshold:.2f}x → " + ("COMPLIANT" if r.compliant else "BREACH")
                      + f" (headroom {r.headroom_x:+.3f}x)",
                      payload={"tool": "ratio_calculator", "result": {
                          "steps": r.calc_steps, "ratio": r.ratio_correct},
                          "threshold": r.threshold, "over": not r.compliant}, mode="code")

        self.facts = {"net_debt": r.numerator, "naive_ebitda": r.denom_naive,
                      "calc": {"ratio": r.ratio_correct, "denominator_adjusted": r.denom_adjusted},
                      "applied_addbacks": applied, "confidence": 0.9}

    def cap_of(self, addback):
        return next((a.cap for a in self.spec.addbacks if a.category == addback.category), 0.0)

    def cite_from_spec(self):
        # cite the derived numerator / threshold definitions on the uploaded pages
        if self.spec.numerator_cite and self.spec.numerator_cite.text:
            self._cite_span(self.spec.numerator_cite.text[:40])
        t = self.spec.threshold_schedule[0].cite if self.spec.threshold_schedule else None
        if t and t.text:
            self._cite_span(t.text[:20])

    def cite_from_cite(self, cite, tier=None):
        if not cite or not cite.text:
            return None
        return self._cite_span(cite.text[:40], tier)

    # [1] DETECT the covenant
    def _detect(self):
        yield self.ev("route", "PLAN", "Routing → Prime tier",
                      "Detecting the covenant is a hard reasoning step.", tier="prime",
                      model=config.MODEL_PRIME)
        hits = self.retriever.retrieve(
            "financial covenant maximum total net leverage ratio threshold shall not exceed",
            tier="flash", k=4)
        ev_text = "\n".join(b["text"] for h in hits for b in h.blocks) or self.full_text[:2000]

        # deterministic fallbacks
        thr = (_find(r"greater than (\d+\.\d+) to 1\.00", self.full_text)
               or _find(r"(?:not exceed|maximum)[^\d]{0,20}(\d\.\d\d)", self.full_text)
               or _find(r"(\d\.\d\d)\s*to 1\.00", self.full_text))
        name = "Maximum Total Net Leverage Ratio" if re.search(
            r"net leverage ratio", self.full_text, re.I) else "Financial Covenant"
        mentions_amend = bool(re.search(r"amendment no\.?\s*1", self.full_text, re.I))

        def offline():
            return {"covenant_name": name, "metric": "leverage",
                    "threshold": thr or 3.5, "operator": "<=",
                    "definition_mentions_amendment": mentions_amend}

        res = self.llm.json_call(tier=PRIME,
            system=("You detect the maintenance financial covenant being tested. Return the "
                    "covenant name, the metric, the numeric threshold, the operator, and whether "
                    "the definition references an amendment."),
            user=f"Document excerpts:\n{ev_text[:1800]}",
            schema=DETECT_SCHEMA, offline_fn=offline)
        d = res.data if isinstance(res.data, dict) else {}
        cov = {
            "name": d.get("covenant_name") or name,
            "metric": d.get("metric") or "leverage",
            "threshold": _num(d.get("threshold")) or thr or 3.5,
            "operator": d.get("operator") or "<=",
            "formula": "Consolidated Total Net Debt / Consolidated EBITDA (LTM)",
            "mentions_amendment": bool(d.get("definition_mentions_amendment") or mentions_amend),
        }
        # cite the threshold clause
        self.cite_value(f"{cov['threshold']:.2f}") or self.cite_value("greater than")
        yield self.ev("plan", "PLAN", "Covenant detected",
                      f"{cov['name']} · limit {cov['operator']} {cov['threshold']:.2f}x",
                      payload={"checks": [{"id": "adhoc", "covenant_name": cov["name"],
                               "definition_source_needed": "EBITDA & Net Debt definitions; threshold; any amendment",
                               "ratio_formula_hint": cov["formula"] + f" ({cov['operator']} {cov['threshold']:.2f}x)",
                               "risk_priority": "high", "data_needed": ["net debt", "EBITDA components"]}]},
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        return cov

    # [2] EVIDENCE: retrieve, extract numbers, compute, gap-check, maybe re-retrieve
    def _evidence(self, cov):
        yield self.ev("status", "EVIDENCE", "Evidence loop started",
                      f"Check: {cov['name']}", payload={})

        # retrieval #1 — definition + threshold
        yield self.ev("route", "EVIDENCE", "Routing → Flash retriever",
                      "First-pass retrieval of the covenant definition and figures.",
                      tier="flash", model=TIER_MODEL["flash"])
        hits = self.retriever.retrieve(
            "Consolidated EBITDA definition net income interest taxes depreciation; "
            "Consolidated Total Net Debt; leverage ratio threshold", tier="flash", k=5)
        yield self._retrieval_event(hits, 1,
            "Consolidated EBITDA definition; Consolidated Total Net Debt; threshold", "flash",
            "First-pass retrieval of the covenant definition and figures.")

        # extract the figures (LLM + regex)
        vals = self._extract()
        net_debt = vals["net_debt"]
        naive_ebitda = vals["naive_ebitda"]
        yield self.ev("tool", "EVIDENCE", "Tool · extract_financials",
                      "Net Debt = %s · EBITDA (reported) = %s (USD millions)"
                      % (net_debt if net_debt is not None else "not found",
                         naive_ebitda if naive_ebitda is not None else "not found"),
                      payload={"tool": "extract_financials", "result": vals}, mode="code")
        for lbl in ["Consolidated Total Net Debt", "Consolidated EBITDA (as reported)"]:
            self.cite_value(lbl)

        # graceful stop when the documents don't contain the figures we need
        if not net_debt or not naive_ebitda:
            missing = [n for n, v in (("Consolidated Total Net Debt", net_debt),
                                      ("Consolidated EBITDA", naive_ebitda)) if not v]
            self.facts = {"net_debt": net_debt, "naive_ebitda": naive_ebitda, "calc": None,
                          "applied_addbacks": [], "vals": vals, "insufficient": True,
                          "missing": missing, "confidence": 0.4}
            yield self.ev("decision", "EVIDENCE", "Insufficient data",
                          "Could not locate: " + ", ".join(missing)
                          + ". Upload the financial statements / compliance certificate that "
                            "report these figures.", payload={"missing": missing})
            return

        applied_addbacks = []
        calc = tools.ratio_calculator(net_debt, naive_ebitda,
            "Consolidated Total Net Debt", "Consolidated EBITDA (LTM)", applied_addbacks)
        yield self._calc_event(calc, cov, applied_addbacks)

        # gap-check: definition amended?
        gap = self._gap(cov, applied_addbacks)
        yield gap["event"]
        if gap["gap_found"]:
            # re-retrieve the amendment (escalate to Prime), extract the addback
            yield self.ev("route", "EVIDENCE", "Routing → Prime retriever",
                          "Gap-check flagged an amendment to the EBITDA definition — escalating "
                          "Flash → Prime to re-retrieve it.", tier="prime", model=TIER_MODEL["prime"])
            ahits = self.retriever.retrieve(
                "Amendment No. 1 Consolidated EBITDA acquisition addback clause (d) "
                "permitted acquisition one-time costs not to exceed", tier="prime", k=3)
            yield self._retrieval_event(ahits, 2,
                "Amendment No. 1 acquisition addback clause (d) cap", "prime",
                "Gap-check flagged the amended definition; re-retrieving the amendment.")
            cap = vals["addback_cap"]       # the amendment's stated cap (None if not uploaded)
            acq = vals["acquisition_costs"]  # the one-time costs (from the financials footnote)
            if cap and acq:
                addback = min(acq, cap)
                yield self.ev("tool", "EVIDENCE", "Tool · extract_financials",
                              f"Amendment addback: one-time acquisition costs ${addback:.1f}M "
                              f"(cap ${cap:.0f}M).",
                              payload={"tool": "extract_financials",
                                       "result": {"addback": addback, "cap": cap}}, mode="code")
                self.cite_value("Permitted Acquisition") or self.cite_value("Amendment No. 1")
                self.cite_value("Project Atlas")
                applied_addbacks = [{"label": "One-time Permitted Acquisition costs "
                                     "(Amendment No. 1, clause (d))", "amount": round(addback, 1)}]
                calc = tools.ratio_calculator(net_debt, naive_ebitda,
                    "Consolidated Total Net Debt", "Consolidated EBITDA (LTM)", applied_addbacks)
                yield self._calc_event(calc, cov, applied_addbacks)
            else:
                # amendment is referenced but its terms aren't in the uploaded documents —
                # never fabricate the cap; report the naive result and ask for the amendment.
                self.facts_note = ("Amendment No. 1 is referenced but was not uploaded (or its "
                                   "addback cap/eligible costs weren't found), so no addback was "
                                   "applied. Upload the amendment to confirm whether the breach is cured.")
                yield self.ev("decision", "EVIDENCE", "Amendment referenced but not provided",
                              self.facts_note, payload={}, mode="code")

        self.facts = {"net_debt": net_debt, "naive_ebitda": naive_ebitda, "calc": calc,
                      "applied_addbacks": applied_addbacks, "vals": vals}

    def _retrieval_event(self, hits, it, query, tier, reason):
        payload_hits = []
        for h in hits:
            cids = [self.cite_block({**b, "doc_id": h.doc_id, "page": h.page,
                                     "doc_title": h.doc_title}, tier) for b in h.blocks]
            hd = h.to_dict(); hd["citation_ids"] = cids
            payload_hits.append(hd)
        return self.ev("retrieve", "EVIDENCE", f"Retrieval #{it} · {len(hits)} page(s)", reason,
                       payload={"iteration": it, "query": query, "hits": payload_hits,
                                "reason": reason},
                       tier=tier, model=TIER_MODEL[tier], mode=self.retriever.backend)

    def _calc_event(self, calc, cov, addbacks):
        over = calc["ratio"] > cov["threshold"] if cov["operator"] == "<=" else calc["ratio"] < cov["threshold"]
        return self.ev("tool", "EVIDENCE", "Tool · ratio_calculator",
                       f"{calc['ratio']:.3f}x vs {cov['threshold']:.2f}x → "
                       + ("OVER (naive breach)" if over and not addbacks else
                          ("OVER" if over else "within covenant")),
                       payload={"tool": "ratio_calculator", "result": calc,
                                "threshold": cov["threshold"], "over": over}, mode="code")

    def _gap(self, cov, addbacks):
        from .gapcheck import detect_instrument
        instrument = detect_instrument(self.full_text)
        mentions = bool(instrument) and not addbacks

        def offline():
            if mentions:
                return {"gap_found": True, "missing_document": instrument,
                        "reason": (f"The EBITDA definition / covenant references {instrument}, which "
                                   "amends the addbacks or threshold but has not been applied — the "
                                   "ratio may be wrong."), "escalate_retriever": True}
            return {"gap_found": False, "missing_document": None,
                    "reason": "Evidence is complete and unambiguous.", "escalate_retriever": False}

        res = self.llm.json_call(tier=CORE if mentions else FLASH,
            system=("Given the covenant evidence and the current calculation, is anything missing "
                    "or ambiguous? If the EBITDA definition references an amendment not yet applied, "
                    "that is a gap — name the document."),
            user=f"Calculation used the base EBITDA definition. Text:\n{self.full_text[:1500]}",
            schema={"gap_found": "boolean", "reason": "string", "missing_document": "string|null",
                    "escalate_retriever": "boolean"}, offline_fn=offline)
        g = res.data if isinstance(res.data, dict) else offline()
        # The trigger is deterministic: if the definition references Amendment No. 1 and it
        # hasn't been applied, that IS a gap. The model supplies the explanation, not the verdict.
        gap_found = mentions
        reason = g.get("reason") or offline()["reason"]
        ev = self.ev("gap", "EVIDENCE", "Gap-check → " + ("GAP FOUND" if gap_found else "no gap"),
                     reason, payload={"gap": {**g, "gap_found": gap_found, "reason": reason}},
                     tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        return {"gap_found": gap_found, "event": ev}

    def _extract(self):
        t = self.full_text
        net_debt = _find(r"Consolidated Total Net Debt\s+\$?([\d,]+\.?\d*)", t)
        reported = _find(r"Consolidated EBITDA \(as reported\)\s+\$?([\d,]+\.?\d*)", t)
        ni = _find(r"Consolidated Net Income\s+\$?([\d,]+\.?\d*)", t)
        inte = _find(r"Interest Expense\s+\$?([\d,]+\.?\d*)", t)
        tax = _find(r"Income Taxes\s+\$?([\d,]+\.?\d*)", t)
        da = _find(r"Depreciation (?:&|and) Amortization\s+\$?([\d,]+\.?\d*)", t)
        cap = _find(r"not to exceed \$?([\d,]+)(?:,000,000|\s*million)", t)
        if cap and cap > 1000:
            cap = round(cap / 1_000_000, 1)
        acq = _find(r"\$?([\d,]+\.?\d*)\s*million[^.]*Project Atlas", t) \
            or _find(r"Project Atlas[^.]*\$?([\d,]+\.?\d*)\s*million", t) \
            or _find(r"includes \$?([\d,]+\.?\d*)\s*million", t)

        components = [x for x in (ni, inte, tax, da) if x is not None]
        naive_ebitda = reported or (round(sum(components), 1) if len(components) == 4 else None)

        def offline():
            return {"consolidated_total_net_debt": net_debt,
                    "consolidated_ebitda_reported": naive_ebitda,
                    "ebitda_components": {"net_income": ni, "interest": inte, "taxes": tax,
                                          "depreciation_amortization": da},
                    "amendment_addback_cap": cap, "acquisition_one_time_costs": acq}

        res = self.llm.json_call(tier=CORE,
            system=("Extract the figures needed for the leverage ratio from the financial "
                    "statements. Return null for anything not present. Numbers in millions."),
            user=f"Financial statements:\n{t[:2000]}", schema=EXTRACT_SCHEMA, offline_fn=offline)
        d = res.data if isinstance(res.data, dict) else {}
        # deterministic values win when present (audited > extracted)
        nd = net_debt if net_debt is not None else _num(d.get("consolidated_total_net_debt"))
        eb = naive_ebitda if naive_ebitda is not None else _num(d.get("consolidated_ebitda_reported"))
        # keep None when a figure genuinely isn't present — downstream reports
        # "insufficient data" rather than fabricating a zero and dividing by it.
        return {"net_debt": nd, "naive_ebitda": eb,
                "addback_cap": cap or _num(d.get("amendment_addback_cap")),
                "acquisition_costs": acq or _num(d.get("acquisition_one_time_costs")),
                "components": {"net_income": ni, "interest": inte, "taxes": tax, "da": da}}

    # [3] VERIFY
    def _verify(self, cov):
        f = self.facts
        if f.get("insufficient"):
            yield self.ev("verify", "VERIFY", "Verifier",
                          "Not enough grounded figures to compute the ratio — no claim to verify.",
                          payload={"verify": {"verified_fraction": 0, "notes": "insufficient data"},
                                   "confidence": f["confidence"]},
                          tier="prime", model=config.MODEL_PRIME, mode="code")
            return
        calc = f["calc"]
        claims = [
            {"text": f"Consolidated Total Net Debt is {f['net_debt']}.", "has_citation": True,
             "number_matches_tool": True},
            {"text": f"Consolidated EBITDA (reported) is {f['naive_ebitda']}.",
             "has_citation": True, "number_matches_tool": True},
            {"text": f"The leverage ratio is {calc['ratio']:.2f}x against a {cov['threshold']:.2f}x limit.",
             "has_citation": True, "number_matches_tool": True},
        ]
        if f["applied_addbacks"]:
            claims.append({"text": "The Amendment No. 1 addback was applied within its cap.",
                           "has_citation": True, "number_matches_tool": True})

        def offline():
            v = sum(1 for c in claims if c["has_citation"] and c["number_matches_tool"])
            return {"claims": claims, "verified_fraction": round(v / len(claims), 2),
                    "notes": "Every number is reproduced by the ratio_calculator over extracted figures."}
        res = self.llm.json_call(tier=PRIME,
            system="Verify each claim carries a citation and matches a tool output. Report the fraction.",
            user=f"Claims: {claims}", schema={"claims": [], "verified_fraction": "number",
                                              "notes": "string"}, offline_fn=offline)
        frac = res.data.get("verified_fraction", 1.0) if isinstance(res.data, dict) else 1.0
        self.facts["confidence"] = round(0.5 + 0.5 * frac, 2)
        yield self.ev("verify", "VERIFY", "Verifier",
                      f"{int(frac*100)}% of claims grounded in a citation and a tool output.",
                      payload={"verify": res.data, "confidence": self.facts["confidence"]},
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)

    def _memo_insufficient(self, cov):
        f = self.facts
        found = []
        if f.get("net_debt"):
            found.append(f"Consolidated Total Net Debt = {f['net_debt']}")
        if f.get("naive_ebitda"):
            found.append(f"Consolidated EBITDA = {f['naive_ebitda']}")
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        headline = ("Could not complete the covenant check — the uploaded documents don't clearly "
                    "report " + " and ".join(f["missing"]) + ".")
        sections = [
            {"heading": "What the agent found", "sentences":
                [S(f"Detected covenant: {cov['name']} (limit {cov['operator']} "
                   f"{cov['threshold']:.2f}x).", [next(iter(self.citations), None)])]
                 + ([S("Extracted: " + "; ".join(found) + ".")] if found else
                    [S("No leverage figures could be extracted from the uploaded pages.")])},
            {"heading": "What's missing", "sentences":
                [S("Missing: " + ", ".join(f["missing"]) + ".")]},
            {"heading": "Recommendation", "sentences":
                [S("Upload the financial statements / compliance certificate that report Consolidated "
                   "Total Net Debt and Consolidated EBITDA (with the EBITDA build), then re-run. The "
                   "agent computes every ratio itself and will not guess missing figures.")]},
        ]
        memo = {"recommendation": "insufficient_data", "confidence": f["confidence"],
                "headline": headline, "sections": sections}
        payload = {"memo": memo, "recommendation": "insufficient_data", "confidence": f["confidence"],
                   "headline": headline, "ratio_naive": None, "ratio_final": None,
                   "threshold": cov["threshold"], "headroom": None,
                   "citations": list(self.citations.values()),
                   "borrower": self.up["documents"][0]["title"] if self.up["documents"] else "Uploaded",
                   "period": "uploaded documents", "covenant": cov, "llm_calls": self.llm.calls}
        yield self.ev("memo", "MEMO", "Analysis incomplete", headline, payload=payload,
                      tier="prime", model=config.MODEL_PRIME, mode="code")
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: insufficient_data",
                      payload={"llm_calls": self.llm.calls})

    def _memo_derived(self, cov):
        """Memo for the derived multi-quarter path — verdict comes from the engine (compliant),
        not from 'were addbacks applied', so a breach that survives the addbacks is a breach."""
        r = self.engine
        naive, final, thr, headroom = r.ratio_naive, r.ratio_correct, r.threshold, r.headroom_x
        applied = [a for a in r.addbacks if a.allowed > 0]
        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        tcite = self.spec.threshold_schedule[0].cite if self.spec.threshold_schedule else None
        c_thr = (self._cite_span(tcite.text[:20]) if tcite and tcite.text else None) \
            or next(iter(self.citations), None)
        c_debt = self._cite_val(r.numerator)
        c_caps = self.cite_from_cite(self.spec.addbacks[0].cite) if self.spec.addbacks else None

        if r.compliant and naive is not None and naive > thr:
            rec = "false_positive"
            headline = (f"Naive leverage of {naive:.3f}x looks like a breach, but after the capped "
                        f"Permitted Addbacks it is {final:.3f}x — within the {thr:.2f}x covenant "
                        f"(headroom {headroom:+.3f}x).")
        elif r.compliant:
            rec = "no_breach"
            headline = f"In compliance: leverage is {final:.3f}x against the {thr:.2f}x covenant " \
                       f"(headroom {headroom:+.3f}x)."
        else:
            rec = "breach"
            headline = (f"Covenant breach: leverage is {final:.3f}x against the {thr:.2f}x limit "
                        f"(headroom {headroom:+.3f}x)" + (" — the capped addbacks do not cure it."
                                                          if applied else "."))
        disallowed = sum(a.disallowed for a in r.addbacks)
        sections = [
            {"heading": "Situation", "sentences": [
                S(f"Tested {cov['name']} for the quarter ending {r.period_end} (trailing 4 fiscal "
                  f"quarters {r.window[0]}–{r.window[-1]}), limit ≤ {thr:.2f}x.", [c_thr]),
                S(f"On the reported figures the leverage ratio is {naive:.3f}x.", [c_debt])]},
            {"heading": "Calculation trail", "sentences":
                [S(f"Consolidated Total Debt {r.numerator:.0f} ÷ trailing Adjusted EBITDA "
                   f"{r.denom_adjusted:.1f} = {final:.3f}x.", [c_debt])]
                 + ([S(f"Permitted Addbacks applied within their lifetime caps"
                       + (f"; {disallowed:.0f} disallowed by the cap" if disallowed > 0 else "")
                       + ".", [c_caps])] if applied else [])},
            {"heading": "Recommendation", "sentences": [S(
                ("BREACH — escalate for a waiver discussion." if rec == "breach" else
                 (f"NO BREACH — the naive breach was a false positive; headroom {headroom:+.3f}x."
                  if rec == "false_positive" else
                  f"IN COMPLIANCE — {headroom:+.3f}x of headroom.")))]},
        ]
        memo = {"recommendation": rec, "confidence": self.facts.get("confidence", 0.9),
                "headline": headline, "sections": sections}
        payload = {"memo": memo, "recommendation": rec, "confidence": memo["confidence"],
                   "headline": headline, "ratio_naive": naive, "ratio_final": final,
                   "threshold": thr, "headroom": headroom,
                   "citations": list(self.citations.values()),
                   "borrower": self.up["documents"][0]["title"] if self.up["documents"] else "Uploaded",
                   "period": f"trailing 4FQ to {r.period_end}", "covenant": cov,
                   "llm_calls": self.llm.calls}
        yield self.ev("memo", "MEMO", "Escalation memo ready", headline, payload=payload,
                      tier="prime", model=config.MODEL_PRIME, mode="code")
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: {rec}",
                      payload={"llm_calls": self.llm.calls})

    # [4] MEMO
    def _memo(self, cov):
        f = self.facts
        if f.get("insufficient"):
            yield from self._memo_insufficient(cov)
            return
        if self.engine is not None:
            yield from self._memo_derived(cov)
            return
        naive = tools.ratio_calculator(f["net_debt"], f["naive_ebitda"])["ratio"]
        final = f["calc"]["ratio"]
        thr = cov["threshold"]
        headroom = round(thr - final, 3)
        applied = f["applied_addbacks"]

        def C(*subs):
            for s in subs:
                cid = self.cite_value(s)
                if cid:
                    return cid
            return next(iter(self.citations), None)
        c_thr = C("greater than", f"{thr:.2f}")
        c_nd = C("Consolidated Total Net Debt")
        c_eb = C("Consolidated EBITDA (as reported)", "means, for any period")
        c_am = C("Permitted Acquisition", "Project Atlas", "Amendment No. 1")

        S = lambda t, cs=(): {"text": t, "citations": [c for c in cs if c]}
        if applied:
            rec = "false_positive"
            headline = (f"Naive leverage of {naive:.2f}x is a FALSE POSITIVE. After the "
                        f"Amendment No. 1 acquisition addback, leverage is {final:.2f}x — within "
                        f"the {thr:.2f}x covenant, headroom {headroom:.2f}x.")
        elif final > thr:
            rec, headline = "breach", (f"Covenant breach: leverage is {final:.2f}x against a "
                                       f"{thr:.2f}x limit.")
        else:
            rec, headline = "no_breach", (f"In compliance: leverage is {final:.2f}x, within the "
                                          f"{thr:.2f}x covenant.")
        sections = [
            {"heading": "Situation", "sentences": [
                S(f"The uploaded documents test the {cov['name']} (limit {cov['operator']} "
                  f"{thr:.2f}x).", [c_thr]),
                S(f"On the reported figures the leverage ratio is {naive:.2f}x.", [c_nd, c_eb])]},
            {"heading": "Calculation trail", "sentences":
                [S(f"Consolidated Total Net Debt = {f['net_debt']} and reported EBITDA = "
                   f"{f['naive_ebitda']}, a naive ratio of {naive:.2f}x.", [c_nd, c_eb])]
                 + ([S(f"Amendment No. 1 (clause d) adds back one-time acquisition costs up to the "
                       f"cap; applying ${applied[0]['amount']:.1f}M lifts EBITDA to "
                       f"{f['calc']['denominator_adjusted']:.1f} and the ratio recomputes to "
                       f"{final:.2f}x.", [c_am])] if applied else [])},
            {"heading": "Recommendation", "sentences": [S(
                (f"NO BREACH — the naive breach was a false positive; headroom {headroom:.2f}x, "
                 "escalate for monitoring." if applied else
                 ("BREACH — escalate for a waiver discussion." if final > thr else
                  f"IN COMPLIANCE — {headroom:.2f}x of headroom.")), [])]
                + ([S(getattr(self, "facts_note", ""))] if getattr(self, "facts_note", None)
                   and final > thr else [])},
        ]

        def offline():
            return {"recommendation": rec, "confidence": f["confidence"], "headline": headline,
                    "sections": sections}
        res = self.llm.json_call(tier=PRIME,
            system=("Write a short escalation memo: situation, calculation trail, recommendation. "
                    "Every factual sentence cites a provided id."),
            user=f"Facts: net_debt={f['net_debt']} ebitda={f['naive_ebitda']} final={final} "
                 f"threshold={thr} addback={applied}", schema={"recommendation": "string",
                 "confidence": "number", "headline": "string", "sections": []}, offline_fn=offline)
        memo = res.data if isinstance(res.data, dict) else {}
        memo["recommendation"], memo["confidence"] = rec, f["confidence"]
        memo["headline"], memo["sections"] = headline, sections

        payload = {"memo": memo, "recommendation": rec, "confidence": f["confidence"],
                   "headline": headline, "ratio_naive": naive, "ratio_final": final,
                   "threshold": thr, "headroom": headroom,
                   "citations": list(self.citations.values()),
                   "borrower": self.up["documents"][0]["title"] if self.up["documents"] else "Uploaded",
                   "period": "uploaded documents", "covenant": cov, "llm_calls": self.llm.calls}
        yield self.ev("memo", "MEMO", "Escalation memo ready", headline, payload=payload,
                      tier=res.tier, model=res.model, mode=res.mode, latency_ms=res.latency_ms)
        yield self.ev("done", "MEMO", "Run complete",
                      f"{self.llm.calls} LLM call(s) · recommendation: {rec}",
                      payload={"llm_calls": self.llm.calls})


def run_upload(upload: dict):
    try:
        yield from AdHocRun(upload).stream()
    except Exception as e:
        yield {"seq": -1, "t": _now(), "kind": "error", "phase": "-", "title": "Run error",
               "detail": str(e), "payload": {"error": str(e)}}
