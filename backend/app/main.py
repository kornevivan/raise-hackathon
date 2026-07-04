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

from . import config, corpus, orchestrator, orchestrator_adhoc, ingest

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
    return {"scenarios": corpus.scenarios()}


@app.get("/api/documents")
def documents():
    return {"documents": corpus.load_index()["documents"]}


def _find_scenario(scenario_id: str) -> dict:
    for s in corpus.scenarios():
        if s["id"] == scenario_id:
            return s
    raise HTTPException(404, f"scenario {scenario_id} not found")


@app.get("/api/run/{scenario_id}")
async def run(scenario_id: str):
    sc = _find_scenario(scenario_id)
    run_id = uuid.uuid4().hex[:12]
    events: list[dict] = []
    RUNS[run_id] = {"events": events, "scenario": sc, "memo": None, "decision": None}

    async def gen():
        yield {"event": "run_id", "data": json.dumps({"run_id": run_id})}
        for ev in orchestrator.run_scenario(sc):
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
