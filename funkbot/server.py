"""FunkBot web server: chat UI, SSE streaming, dictation endpoints.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...
    python server.py            # http://localhost:8800
"""

from __future__ import annotations

import json
import pathlib

from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import learn
import memory
import voice
from agent import FunkBot

HERE = pathlib.Path(__file__).resolve().parent
app = FastAPI(title="FunkBot")
BOTS: dict[str, FunkBot] = {}


def bot(session_id: str | None) -> FunkBot:
    if session_id and session_id in BOTS:
        return BOTS[session_id]
    b = FunkBot()
    BOTS[b.session_id] = b
    return b


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HERE / "web" / "index.html")


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    body = await request.json()
    b = bot(body.get("session_id"))

    def events():
        yield f"data: {json.dumps({'type': 'session', 'id': b.session_id})}\n\n"
        for kind, chunk in b.stream(body["message"]):
            yield f"data: {json.dumps({'type': kind, 'text': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


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
    """The browser already transcribed it (Web Speech API) — just persist it."""
    body = await request.json()
    return JSONResponse(voice.save_dictation(body["text"]))


@app.post("/api/avatar")
async def set_avatar(image: UploadFile) -> JSONResponse:
    """Drop a portrait into the avatar ring. Saved as web/funkbot.png."""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8800)
