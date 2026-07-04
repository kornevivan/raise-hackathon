"""Pre-warm the Vultr response cache so the live demo replays instantly.

Runs every scenario end-to-end (up to 3 passes) until every reasoning call has a
cached Vultr response. Requires VULTR_INFERENCE_API_KEY in the environment / .env.

    python prewarm.py
"""
import time

from app import corpus, orchestrator

sces = corpus.scenarios()
for attempt in range(1, 4):
    all_live = True
    for sc in sces:
        live = off = 0
        for ev in orchestrator.run_scenario(sc):
            if ev["kind"] in ("plan", "gap", "cause", "verify", "memo"):
                if ev.get("mode") == "vultr":
                    live += 1
                elif ev.get("mode") == "offline":
                    off += 1
        if off:
            all_live = False
        print(f"attempt {attempt} {sc['id']:12s} live={live} offline={off}", flush=True)
    if all_live:
        print("ALL LIVE + CACHED", flush=True)
        break
