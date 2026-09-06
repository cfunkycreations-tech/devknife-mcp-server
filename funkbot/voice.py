"""Dictation: audio in, text out, every dictation saved.

Transcription backends, tried in order:
  1. faster-whisper running locally  (pip install faster-whisper) — no network
  2. openai-whisper                  (pip install openai-whisper)
  3. the browser's own Web Speech API — the UI sends text instead of audio

Every dictation is written to data/dictations/ as a .wav + .txt pair and stored
in memory, so "what did I dictate on Tuesday" is answerable.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import uuid

import memory
from config import DICTATIONS_DIR

_MODEL = None


def _whisper():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    try:
        from faster_whisper import WhisperModel
        _MODEL = ("faster", WhisperModel("base.en", device="cpu", compute_type="int8"))
    except ImportError:
        try:
            import whisper
            _MODEL = ("openai", whisper.load_model("base.en"))
        except ImportError:
            _MODEL = ("none", None)
    return _MODEL


def transcribe(audio_bytes: bytes, suffix: str = ".webm") -> str:
    kind, model = _whisper()
    if kind == "none":
        raise RuntimeError(
            "no local transcription backend — pip install faster-whisper, "
            "or let the browser transcribe with the Web Speech API")

    tmp = DICTATIONS_DIR / f"tmp-{uuid.uuid4().hex}{suffix}"
    tmp.write_bytes(audio_bytes)
    try:
        if kind == "faster":
            segments, _ = model.transcribe(str(tmp), beam_size=5)
            return " ".join(s.text.strip() for s in segments).strip()
        return model.transcribe(str(tmp))["text"].strip()
    finally:
        tmp.unlink(missing_ok=True)


def save_dictation(text: str, audio_bytes: bytes | None = None,
                   suffix: str = ".webm") -> dict:
    """Persist a dictation to disk and to memory. Returns its record."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = DICTATIONS_DIR / f"{stamp}-{uuid.uuid4().hex[:6]}"
    base.with_suffix(".txt").write_text(text, encoding="utf-8")
    if audio_bytes:
        pathlib.Path(str(base) + suffix).write_bytes(audio_bytes)
    memory.remember(f"dictation {stamp}", text, kind="dictation", source="voice")
    return {"id": base.name, "text": text, "path": str(base.with_suffix(".txt"))}


def list_dictations(limit: int = 50) -> list[dict]:
    files = sorted(DICTATIONS_DIR.glob("*.txt"), reverse=True)[:limit]
    return [{"id": f.stem, "text": f.read_text(encoding="utf-8")} for f in files]
