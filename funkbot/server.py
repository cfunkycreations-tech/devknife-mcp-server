"""FunkBot web server: chat UI, SSE streaming, dictation, telemetry, approvals.

    pip install -r requirements.txt
    ollama serve &  ollama run qwen3:32b
    python server.py                     # http://localhost:8800

Binds to 127.0.0.1 by default — this thing has shell access, don't expose it.
"""

from __future__ import annotations

import json
import os
import pathlib
import queue
import threading
import uuid

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import learn
import llm
import memory
import safety
import usage as usage_mod
import verify
import voice
from agent import FunkBot
from config import MODEL

HERE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="FunkBot")
BOTS: dict[str, FunkBot] = {}

# Pending permission prompts: id -> {"event": Event, "granted": bool, "payload": {...}}
PENDING: dict[str, dict] = {}
APPROVAL_TIMEOUT = int(os.getenv("FUNKBOT_APPROVAL_TIMEOUT", "180"))


def _approver_for(sink: queue.Queue) -> callable:
    """Ask the browser. Blocks the tool call until the operator answers."""
    def approve(tool: str, args: dict, reason: str) -> bool:
        pid = uuid.uuid4().hex[:8]
        event = threading.Event()
        PENDING[pid] = {"event": event, "granted": False}
        sink.put(("approval", json.dumps(
            {"id": pid, "tool": tool, "args": args, "reason": reason})))
        granted = PENDING[pid]["granted"] if event.wait(APPROVAL_TIMEOUT) else False
        PENDING.pop(pid, None)
        return granted
    return approve


def bot(session_id: str | None, sink: queue.Queue | None = None) -> FunkBot:
    if session_id and session_id in BOTS:
        b = BOTS[session_id]
        if sink is not None:
            b.gate.approver = _approver_for(sink)
        return b
    b = FunkBot(approver=_approver_for(sink) if sink else None)
    BOTS[b.session_id] = b
    return b


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "web" / "index.html")


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    body = await request.json()
    sink: queue.Queue = queue.Queue()
    b = bot(body.get("session_id"), sink)

    def events():
        yield f"data: {json.dumps({'type': 'session', 'id': b.session_id})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'text': json.dumps(b.status())})}\n\n"

        done = threading.Event()
        threading.Thread(
            target=lambda: (b.send(body["message"], lambda k, t: sink.put((k, t))),
                            done.set()),
            daemon=True).start()

        while not done.is_set() or not sink.empty():
            try:
                kind, chunk = sink.get(timeout=0.1)
            except queue.Empty:
                continue
            yield f"data: {json.dumps({'type': kind, 'text': chunk})}\n\n"

        yield f"data: {json.dumps({'type': 'status', 'text': json.dumps(b.status())})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/approve")
async def approve(request: Request) -> JSONResponse:
    body = await request.json()
    entry = PENDING.get(body["id"])
    if not entry:
        return JSONResponse({"error": "expired"}, status_code=404)
    entry["granted"] = bool(body.get("granted"))
    entry["event"].set()
    return JSONResponse({"ok": True})


@app.get("/api/status")
def status(session_id: str | None = None) -> JSONResponse:
    b = BOTS.get(session_id) if session_id else None
    return JSONResponse({
        "backend": llm.health(),
        "model": MODEL,
        "health": verify.health().splitlines()[0],
        "totals": usage_mod.totals(),
        "session": b.status() if b else None,
        "policy": {k: len(v) for k, v in safety.load_policy().items()},
    })


@app.get("/api/sessions")
def sessions() -> JSONResponse:
    with memory.db() as c:
        rows = c.execute(
            "SELECT s.id, s.started_at, s.title,"
            " (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) n"
            " FROM sessions s ORDER BY s.started_at DESC LIMIT 50").fetchall()
    return JSONResponse([dict(r) for r in rows])


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile, save: str = "1") -> JSONResponse:
    raw = await audio.read()
    suffix = pathlib.Path(audio.filename or "clip.webm").suffix or ".webm"
    try:
        text = voice.transcribe(raw, suffix)
    except RuntimeError as e:
        return JSONResponse({"error": str(e)}, status_code=501)
    record = voice.save_dictation(text, raw, suffix) if save == "1" else {"text": text}
    return JSONResponse(record)


@app.post("/api/dictation")
async def save_browser_dictation(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse(voice.save_dictation(body["text"]))


@app.post("/api/avatar")
async def set_avatar(image: UploadFile) -> JSONResponse:
    raw = await image.read()
    if len(raw) > 8_000_000:
        return JSONResponse({"error": "image over 8MB"}, status_code=413)
    (HERE / "web" / "funkbot.png").write_bytes(raw)
    return JSONResponse({"ok": True, "bytes": len(raw)})


@app.get("/api/dictations")
def dictations() -> JSONResponse:
    return JSONResponse(voice.list_dictations())


@app.get("/api/memory")
def memory_dump() -> JSONResponse:
    with memory.db() as c:
        facts = [dict(r) for r in c.execute(
            "SELECT subject, body, kind, ts FROM facts ORDER BY ts DESC LIMIT 200")]
        lessons = [dict(r) for r in c.execute(
            "SELECT id, trigger, lesson, score, depth, retired FROM lessons"
            " ORDER BY score DESC LIMIT 200")]
    return JSONResponse({"facts": facts, "lessons": lessons})


@app.post("/api/learn")
async def run_learning(request: Request) -> JSONResponse:
    body = await request.json()
    sid = body.get("session_id")
    good = body.get("good")
    return JSONResponse({"result": learn.learn(sid, good) if sid else learn.consolidate()})


@app.get("/{path:path}")
def static(path: str) -> FileResponse:
    target = (HERE / "web" / path).resolve()
    if target.is_file() and str(target).startswith(str(HERE / "web")):
        return FileResponse(target)
    return FileResponse(HERE / "web" / "index.html")


if __name__ == "__main__":
    import uvicorn
    print(llm.health())
    uvicorn.run(app, host=os.getenv("FUNKBOT_HOST", "127.0.0.1"),
                port=int(os.getenv("FUNKBOT_PORT", "8800")))
