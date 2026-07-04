"""FastAPI surface: scenarios, a streaming agent run (SSE), document images,
and the human-in-the-loop decision endpoint."""
from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import sqlite3

from . import (config, orchestrator_adhoc, ingest, orchestrator_hospira, orchestrator_triage,
               chat, scenarios as scen)

app = FastAPI(title="Covenant Sentinel", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

DEMO_PACE_MS = int(os.getenv("DEMO_PACE_MS", "420"))
RUNS: dict[str, dict] = {}   # run_id -> {events, memo, decision}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": config.APP_VERSION,
        "live_inference": config.LIVE,
        "backend": "vultr" if config.LIVE else "offline",
        "reasoning_models": {"prime": config.MODEL_PRIME, "core": config.MODEL_CORE,
                             "flash": config.MODEL_FLASH},
        "retriever_models": {"flash": config.RETRIEVER_FLASH, "core": config.RETRIEVER_CORE,
                             "prime": config.RETRIEVER_PRIME},
        "note": ("Live Vultr inference active." if config.LIVE else
                 "Offline deterministic mode — set VULTR_INFERENCE_API_KEY to run on Vultr."),
    }


@app.get("/api/scenarios")
def scenarios():
    return {"scenarios": scen.all_views()}


@app.get("/api/run/{scenario_id}")
async def run(scenario_id: str):
    cfg = scen.SCENARIOS.get(scenario_id)
    if not cfg:
        raise HTTPException(404, f"scenario {scenario_id} not found")
    derived = scen.derive(cfg)           # everything is DERIVED from the pure config
    is_triage = cfg["corpus"] == "portfolio"
    run_id = uuid.uuid4().hex[:12]
    events: list[dict] = []
    RUNS[run_id] = {"events": events, "scenario": derived, "memo": None, "decision": None}
    gen_events = (orchestrator_triage.run_triage() if is_triage
                  else orchestrator_hospira.run_scenario(derived))

    async def gen():
        yield {"event": "run_id", "data": json.dumps({"run_id": run_id})}
        for ev in gen_events:
            events.append(ev)
            if ev["kind"] == "memo":
                RUNS[run_id]["memo"] = ev["payload"]
            yield {"event": "trace", "data": json.dumps(ev)}
            await asyncio.sleep(DEMO_PACE_MS / 1000.0)
        yield {"event": "end", "data": json.dumps({"run_id": run_id})}

    return EventSourceResponse(gen())


@app.get("/api/run/{run_id}/events")
def run_events(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "run not found")
    return RUNS[run_id]


@app.post("/api/upload")
async def upload(files: list[UploadFile] = File(...)):
    payloads = [(f.filename, await f.read()) for f in files]
    result = ingest.ingest(payloads)
    if result["page_count"] == 0:
        raise HTTPException(400, "No readable pages. Upload PDF (or .txt/.md/.csv) documents.")
    return result


@app.get("/api/run_upload/{upload_id}")
async def run_upload(upload_id: str):
    up = ingest.UPLOADS.get(upload_id)
    if not up:
        raise HTTPException(404, "upload not found (re-upload the documents)")
    run_id = uuid.uuid4().hex[:12]
    events: list[dict] = []
    RUNS[run_id] = {"events": events, "memo": None, "decision": None, "upload_id": upload_id}

    async def gen():
        yield {"event": "run_id", "data": json.dumps({"run_id": run_id})}
        for ev in orchestrator_adhoc.run_upload(up):
            events.append(ev)
            if ev["kind"] == "memo":
                RUNS[run_id]["memo"] = ev["payload"]
            yield {"event": "trace", "data": json.dumps(ev)}
            await asyncio.sleep(DEMO_PACE_MS / 1000.0)
        yield {"event": "end", "data": json.dumps({"run_id": run_id})}

    return EventSourceResponse(gen())


@app.get("/api/samples")
def samples():
    d = os.path.join(config.DATA_DIR, "samples")
    files = sorted(os.listdir(d)) if os.path.isdir(d) else []
    return {"files": [{"name": f, "url": f"/samples/{f}"} for f in files if f.endswith(".pdf")]}


CHAT_DB = os.path.join(config.DATA_DIR, "runs.sqlite")


def _chat_db():
    con = sqlite3.connect(CHAT_DB)
    con.execute("CREATE TABLE IF NOT EXISTS chats(run_id TEXT, idx INT, role TEXT, payload TEXT)")
    return con


def _persist_chat(run_id: str, history: list[dict]):
    con = _chat_db()
    con.execute("DELETE FROM chats WHERE run_id = ?", (run_id,))
    con.executemany("INSERT INTO chats VALUES (?,?,?,?)",
                    [(run_id, i, h.get("role", "assistant"), json.dumps(h)) for i, h in enumerate(history)])
    con.commit(); con.close()


@app.get("/api/suggested/{scenario_id}")
def suggested(scenario_id: str):
    return {"questions": chat.SUGGESTED.get(scenario_id, [])}


@app.get("/api/chat/{run_id}")
def chat_history(run_id: str):
    run = RUNS.get(run_id)
    if run and run.get("chat"):
        return {"history": run["chat"]}
    con = _chat_db()
    rows = con.execute("SELECT payload FROM chats WHERE run_id=? ORDER BY idx", (run_id,)).fetchall()
    con.close()
    return {"history": [json.loads(r[0]) for r in rows]}


@app.post("/api/chat/{run_id}")
async def chat_turn(run_id: str, body: dict):
    run = RUNS.get(run_id)
    if not run:
        raise HTTPException(404, "run not found (re-run the scenario)")
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "empty message")
    session = chat.ChatSession(run)
    history = run.setdefault("chat", [])

    async def gen():
        answer = None
        for ev in session.answer(message):
            if ev["kind"] == "chat_answer":
                answer = ev
            yield {"event": "chat", "data": json.dumps(ev)}
            await asyncio.sleep(min(DEMO_PACE_MS, 200) / 1000.0)
        history.append({"role": "user", "text": message})
        history.append({"role": "assistant", **(answer or {"text": "(no answer)", "citations": []})})
        _persist_chat(run_id, history)
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(gen())


@app.post("/api/decision")
async def decision(body: dict):
    run_id = body.get("run_id")
    action = body.get("action")  # approve | escalate | send_back
    note = body.get("note", "")
    if run_id not in RUNS:
        raise HTTPException(404, "run not found")
    RUNS[run_id]["decision"] = {"action": action, "note": note}
    return {"ok": True, "run_id": run_id, "action": action,
            "message": {
                "approve": "Memo approved and filed to the credit file.",
                "escalate": "Escalated to the credit committee with the memo attached.",
                "send_back": "Sent back to the agent with your note for a targeted re-run.",
            }.get(action, "Recorded.")}


# --- static: document page images + built frontend ---------------------------
app.mount("/corpus", StaticFiles(directory=config.CORPUS_DIR), name="corpus")
os.makedirs(ingest.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=ingest.UPLOAD_DIR), name="uploads")
_SAMPLES = os.path.join(config.DATA_DIR, "samples")
if os.path.isdir(_SAMPLES):
    app.mount("/samples", StaticFiles(directory=_SAMPLES), name="samples")

_FRONTEND = os.path.join(config.BACKEND_DIR, "..", "frontend", "dist")
if os.path.isdir(_FRONTEND):
    app.mount("/", StaticFiles(directory=_FRONTEND, html=True), name="frontend")
