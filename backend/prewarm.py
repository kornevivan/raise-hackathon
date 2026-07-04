import time, sys
from app import orchestrator, corpus
sces = corpus.scenarios()
for attempt in range(1, 4):
    alllive = True
    for sc in sces:
        live=off=0
        for ev in orchestrator.run_scenario(sc):
            if ev['kind'] in ('plan','gap','cause','verify','memo'):
                if ev.get('mode')=='vultr': live+=1
                elif ev.get('mode')=='offline': off+=1
        if off: alllive=False
        print(f"attempt {attempt} {sc['id']:12s} live={live} offline={off}", flush=True)
    if alllive:
        print("ALL LIVE + CACHED", flush=True); break
print("done", flush=True)
