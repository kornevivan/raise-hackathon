# Covenant Sentinel — 60‑second pitch

A tight script for a one‑minute defense with a live demo. `[DEMO]` = what to show on screen.
Total spoken ≈ 155 words ≈ 60 s. Timings are cumulative.

---

### 0:00 — Essence (10s)
> "Covenant Sentinel is an **agentic credit analyst**. When a bank has to check whether a borrower
> is breaching a loan covenant, it does the whole job a human analyst does — but grounded, cited,
> and in seconds."

### 0:10 — What it automates (12s)
> "It reads the real credit agreement and its amendments, **derives the covenant rules from those
> documents**, recomputes the leverage ratio itself, finds *why* it moved in the ledger, cites
> comparable committee precedents, and writes a decision‑ready memo — every number tool‑verified,
> every claim cited to a page."

### 0:22 — Architecture (12s)
> "The orchestration is fixed in code: plan → retrieve on **VultronRetriever** → derive the spec →
> compute on a **deterministic engine** → gap‑check → memo. Reasoning and retrieval both run on
> **Vultr**. The model plans and writes prose — it **never** does the arithmetic, so verdicts are
> reproducible."

### 0:34 — Demo, one scenario (18s)
> `[DEMO: click S1]`
> "Watch. Q2 prints **4.218× — that looks like a breach**, and a naive bot escalates it.
> `[DEMO: gap-check highlights]` But the agent notices the EBITDA definition was **amended**,
> re‑retrieves Amendment No. 1, applies the addback **capped at its limit** — thirty million
> disallowed — and recomputes **3.606×. No breach.**"
>
> *(Note for the jury:* here the financial figures come from **simulated tools that return a
> company's structured data** — standing in for a bank's database or SEC XBRL.)*

### 0:52 — Close: it works without the simulated tools (8s)
> "And it doesn't need those tools. `[DEMO: drop PDFs into a blank chat]` Give it just the
> **documents** — agreement, amendment, financials — and it derives the covenant and computes the
> same breach **from the files alone**. Thank you."

---

## One‑breath version (≈20s, if time is cut)
> "Covenant Sentinel is an agentic credit analyst on Vultr. It reads a loan agreement, derives the
> covenant, and recomputes the ratio — catching a false breach when an amendment adds back capped
> charges: 4.218× becomes 3.606×, no breach, every number cited. Figures here come from simulated
> data tools, but the same agent computes the covenant from uploaded documents alone."

## Delivery notes
- Have **S1 already loaded** so the click‑to‑trace is instant (REPLAY mode = deterministic, no
  network risk on stage).
- The single memorable number: **4.218× → 3.606×** (false breach caught, $30M over‑credit refused).
- If asked "is it just scripted?": the rules are **derived from the real EDGAR filing** and pass a
  **transfer test** on a third‑party agreement with zero code changes; the **upload path** recomputed
  the real Hospira breach from documents alone, LIVE.
- If asked about limits: extraction generalizes (validated on real Hershey & Coca‑Cola 10‑Qs); the
  honest next step is retrieval robustness on full 100‑page filings.
