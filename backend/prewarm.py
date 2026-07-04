"""Pre-warm the Vultr response cache AND the persistent vector-store collections so
the deployed demo replays instantly and live. Requires VULTR_INFERENCE_API_KEY.

    python prewarm.py
"""
import time

from app import chat, orchestrator_hospira as oh, orchestrator_triage as tr

# S0 triage (indexes the 'triage' collection)
print("S0 triage…", flush=True)
for _ in tr.run_triage():
    pass

# deep runs + their suggested chat questions (indexes 'hospira' + 'precedents')
for sid in ("S3", "S1", "S2", "S4"):
    t0 = time.time()
    sc = oh.SCENARIOS[sid]
    memo = None
    for ev in oh.run_scenario(sc):
        if ev["kind"] == "memo":
            memo = ev["payload"]
    run = {"scenario": sc, "memo": memo}
    for q in chat.SUGGESTED.get(sid, []):
        for _ in chat.ChatSession(run).answer(q):
            pass
    print(f"{sid} + {len(chat.SUGGESTED.get(sid, []))} chat turns  {time.time()-t0:.0f}s", flush=True)

print("PREWARM DONE", flush=True)
