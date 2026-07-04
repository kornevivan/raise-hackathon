# 1‑minute demo video script (record against the deployed Vultr URL, LIVE badge on)

Verify the header reads **LIVE · Vultr** (not REPLAY) before recording.

**0:00–0:10 — Problem + triage (S0).**
Click **S0 · Quarter closed**.
> "Covenant checks are quarterly, manual, and slow. Covenant Sentinel triages the book first."
Point at the trace: VultronRetriever surfaces Hospira's latest certificate — a **scanned** page —
and the agent flags Hospira #1 because its **recomputed** 2014Q4 leverage **3.59×** is already
above the **3.50× step‑down** that hits next quarter. Click
**Deep‑run Hospira (S2)** — actually, for the twist, launch **S1** from the top bar.

**0:10–0:22 — Plan + first retrieval (S1).**
> "It plans the check and retrieves the EBITDA definition and the §6.6 threshold with
> VultronRetriever." The ratio tile shows **4.218×** in red — looks like a breach.

**0:22–0:42 — THE TWIST (the money shot).**
> "4.218× — a breach. But the gap‑check notices the definition was *amended*, escalates
> Flash→Prime, and pulls Amendment No. 1." Point at the amber gap line, then retrieval #2.
> "The Permitted Addbacks are **capped** — the calculator shows `min(130, remaining 100) = 100`,
> so **$30M is disallowed** — and the ratio recomputes to **3.606× vs 3.75×. No breach**, but
> only 0.144× headroom." Let the **4.218× → 3.606×** tiles land. Note the transaction cause:
> the $460M Meridian acquisition draw moved *debt*, not EBITDA.

**0:42–0:52 — Cited memo + precedents + chat.**
Click citation **[n]** → the source clause highlights. Show the **Precedents** section
(TriState). Open **Chat**, click *"What if we repay $200M of the revolver?"* →
**`3280 / 965 = 3.399× — HYPOTHETICAL`**, verdict unchanged.
> "Every claim cited, every number from a tool, what‑ifs are simulations only."

**0:52–1:00 — Human decides + close.**
Click **Escalate**.
> "The agent prepares the decision; the analyst makes the call. VultronRetriever for retrieval,
> Vultr Serverless Inference for reasoning, deployed on Vultr."

## Notes
- S2 is the strongest single beat if you want a real breach: 3.615× trips the step‑down 3.50×,
  and the memo cites the real Hospira waiver + Novaline + Gulfport precedents.
- The demo is pre‑warmed (cache + persistent collections) so it runs instantly while staying LIVE.
  If a live call is ever slow on stage, it degrades to the identical deterministic result — the
  numbers never change (golden‑tested).
