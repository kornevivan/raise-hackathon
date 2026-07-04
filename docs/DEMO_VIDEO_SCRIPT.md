# 1‑minute demo video script (record against the deployed URL, scenario S1)

Set `DEMO_PACE_MS=420` so the trace streams at a readable pace. Verify the header
badge reads **“Vultr inference live”** before recording.

**0:00–0:10 — Problem.**
> “Covenant compliance checks take a credit analyst days per borrower — re‑reading a
> 200‑page agreement, rebuilding ratios in Excel. And amended definitions make the
> naive calculation *wrong*. Meet Covenant Sentinel.”

**0:10–0:22 — Plan + first retrieval.**
Click **S1 — The Amendment Twist**. Point at the trace:
> “It plans the check on the Prime model, then retrieves the covenant definition and
> threshold with VultronRetriever.” (ratio tile shows **3.55×** in red.)

**0:22–0:40 — THE TWIST (the money shot).**
> “3.55× — that’s a breach. But the gap‑check notices the EBITDA definition was
> *amended* — so it goes back a second time, **escalating Flash → Prime**, and pulls
> Amendment No. 1.” Point at the amber gap line, then the second retrieval.
> “It finds a \$4.5M acquisition add‑back in the ledger, the calculator recomputes —
> and the ratio flips to **3.42×. No breach.** It just caught a false positive.”
(Let the **3.55× → 3.42×** tiles land on screen.)

**0:40–0:52 — Cited memo + scanned page.**
> “Every claim in the memo is cited.” Click citation **[1]** → the **scanned**
> compliance certificate opens and the exact cell highlights.
> “That number came from a table on a *scanned* page — VultronRetriever read it like
> a person.” Show the verifier’s 100% grounded bar and the confidence score.

**0:52–1:00 — Human decides + close.**
> “The agent prepares the decision; the analyst makes it — Approve, Escalate, or Send
> back.” Click **Escalate for monitoring**.
> “Every claim cited, every number recomputed. VultronRetriever end to end, deployed
> on Vultr.”

## Backup
If live inference is flaky during recording, the deterministic offline mode produces
an identical trace and memo — record against that and say so in the description. The
cached‑replay of a prior live run is also instant (prompt‑hash cache).
