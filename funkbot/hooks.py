"""Hooks: intercept FunkBot's lifecycle without editing its loop.

    from hooks import on

    @on("pre_tool")
    def audit(ctx):
        print(ctx["tool"], ctx["args"])
        # return {"block": "reason"} to stop the call
        # return {"args": {...}} to rewrite the arguments

    @on("post_tool")
    def redact(ctx):
        return {"result": ctx["result"].replace(SECRET, "***")}

Events: session_start, pre_turn, pre_tool, post_tool, post_turn, session_end,
        self_modified, lesson_learned.

Shell hooks work too — drop executables in hooks.d/<event>/, they receive the
context as JSON on stdin and may return JSON on stdout.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from typing import Any, Callable

from config import ROOT

HOOKS_DIR = ROOT / "hooks.d"
_HANDLERS: dict[str, list[Callable]] = defaultdict(list)

EVENTS = ("session_start", "pre_turn", "pre_tool", "post_tool", "post_turn",
          "session_end", "self_modified", "lesson_learned")


def on(event: str) -> Callable:
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}; known: {EVENTS}")

    def deco(fn: Callable) -> Callable:
        _HANDLERS[event].append(fn)
        return fn
    return deco


def _shell_hooks(event: str, ctx: dict) -> list[dict]:
    folder = HOOKS_DIR / event
    if not folder.is_dir():
        return []
    out = []
    for script in sorted(folder.iterdir()):
        if not script.is_file() or not script.stat().st_mode & 0o111:
            continue
        try:
            p = subprocess.run([str(script)], input=json.dumps(ctx, default=str),
                               capture_output=True, text=True, timeout=30)
            if p.stdout.strip():
                out.append(json.loads(p.stdout))
        except Exception:
            continue          # a broken hook never breaks the run
    return out


def fire(event: str, ctx: dict) -> dict:
    """Run every handler for an event; merged dict of their returns."""
    merged: dict[str, Any] = {}
    for fn in _HANDLERS.get(event, []):
        try:
            result = fn(ctx)
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        if isinstance(result, dict):
            merged.update(result)
    for result in _shell_hooks(event, ctx):
        merged.update(result)
    return merged
