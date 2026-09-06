"""Subagents: fan work out to parallel workers with their own context.

FunkBot delegates a self-contained task to a worker that has its own message
history and a restricted tool set, then gets back only the worker's conclusion —
so a hundred files of reading never lands in the main context.

Workers default to a cheaper model; the researcher/coder presets are what makes
a 20-file investigation cost one paragraph of main-thread context.
"""

from __future__ import annotations

import concurrent.futures
import json

import llm
import memory
import usage as usage_mod
from config import MAX_TOKENS, WORKER_MODEL

PRESETS = {
    "researcher": {
        "tools": ["read_file", "search_own_code", "list_own_files", "http_get", "recall"],
        "effort": "medium",
        "system": "You are a research worker. Investigate exactly what you were asked, "
                  "read widely, and return a dense findings summary with file:line "
                  "citations. No preamble. Never modify anything.",
    },
    "coder": {
        "tools": ["read_file", "write_file", "edit_file", "bash", "search_own_code"],
        "effort": "high",
        "system": "You are an implementation worker. Make the change you were asked for, "
                  "run whatever check proves it works, and report what you changed and "
                  "how you verified it. Keep the diff minimal.",
    },
    "critic": {
        "tools": ["read_file", "search_own_code", "bash"],
        "effort": "high",
        "system": "You are a review worker. Find real defects in what you were given — "
                  "correctness first. For each, give file:line, the failure scenario, "
                  "and the fix. Report nothing rather than padding.",
    },
}


def run_one(task: str, preset: str = "researcher", context: str = "") -> dict:
    """Run a single worker to completion. Returns {'preset','task','result','usage'}."""
    import tools as tool_mod

    cfg = PRESETS.get(preset, PRESETS["researcher"])
    allowed = [s for s in tool_mod.specs() if s["name"] in cfg["tools"]]
    messages = [{"role": "user", "content": (f"{context}\n\n{task}" if context else task)}]
    tally = usage_mod.Usage(model=WORKER_MODEL if WORKER_MODEL != 'auto'
                            else llm.resolved_model())
    text = ""

    for _ in range(12):
        reply = llm.chat(messages, allowed, cfg["system"],
                         effort=cfg["effort"], max_tokens=min(MAX_TOKENS, 8192))
        tally.add(reply.usage)
        messages.append({
            "role": "assistant", "content": reply.text,
            **({"tool_calls": reply.tool_calls} if reply.tool_calls else {}),
        })
        text = reply.text or text

        if not reply.tool_calls:
            break

        for call in reply.tool_calls:
            try:
                out = tool_mod.call(call["name"], call["args"])
            except Exception as e:
                out = f"{type(e).__name__}: {e}"
            tally.tool_calls += 1
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "name": call["name"], "content": str(out)[:40000]})

    return {"preset": preset, "task": task, "result": text,
            "usage": tally.snapshot()}


def fan_out(tasks: list[dict], max_workers: int = 5) -> list[dict]:
    """Run several workers at once. Each task: {'task':..., 'preset':..., 'context':...}"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(run_one, t["task"], t.get("preset", "researcher"),
                               t.get("context", "")) for t in tasks]
        return [f.result() for f in futures]


# ---------------------------------------------------------------- tool surface

def spawn_agent(task: str, preset: str = "researcher", context: str = "") -> str:
    """Delegate one self-contained task to a subagent with its own context window.
    Presets: researcher (read/investigate), coder (implement), critic (review).
    Use this instead of reading 20 files yourself."""
    out = run_one(task, preset, context)
    memory.log_message("subagent", preset, f"{task}\n---\n{out['result'][:4000]}")
    u = out["usage"]
    return (f"[{preset} · {u['tool_calls']} tools · {u['output']} tok · "
            f"{u['elapsed_s']}s]\n{out['result']}")


def spawn_swarm(tasks_json: str, preset: str = "researcher") -> str:
    """Run several subagents in parallel. tasks_json is a JSON array of task strings.
    Use when a job splits cleanly into independent pieces."""
    try:
        tasks = json.loads(tasks_json)
    except json.JSONDecodeError:
        return "tasks_json must be a JSON array of task strings"
    results = fan_out([{"task": t, "preset": preset} for t in tasks])
    return "\n\n".join(
        f"### {r['task'][:80]}\n{r['result']}" for r in results)
