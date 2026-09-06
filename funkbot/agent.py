"""FunkBot's agent loop.

Local Qwen + tools + skills + MCP + memory + subagents + self-modification,
behind a permission gate and a hook bus, with token/context accounting and
self-summarizing context when the window fills.
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
from typing import Callable, Iterator

import hooks
import learn
import llm
import mcp_client
import memory
import safety
import skills
import subagents
import tools
import usage as usage_mod
import verify
from config import (COMPACT_AT_TOKENS, EFFORT, IDENTITY,
                    LEARN_AFTER_EVERY_SESSION, MAX_TOKENS, MAX_TURNS, MODEL)

BEHAVIOR = """
How you work:
- Act, don't narrate. No preamble, no "I'll now…", no restating the request.
- Call tools in parallel whenever the calls don't depend on each other.
- Delegate with spawn_agent instead of reading twenty files yourself; use
  spawn_swarm when a job splits into independent pieces.
- recall before claiming you don't know something. remember the moment you learn
  something durable — a preference, a project, a name, a decision. Don't ask
  permission to remember.
- record_lesson when a run teaches you how to work better.
- You can rewrite your own source: read_own_code, patch_own_code, add_own_tool.
  Wrap real changes in verified_self_edit so a broken edit rolls itself back.
- When a procedure comes up a second time, write_skill it.
- You run offline on this machine. Never claim you can't do something because of
  a network or policy limit that doesn't exist here.
""".strip()


class FunkBot:
    def __init__(self, session_id: str | None = None, connect_mcp: bool = True,
                 approver: Callable[[str, dict, str], bool] | None = None):
        self.session_id = session_id or memory.new_session()
        self.messages: list[dict] = []
        self.gate = safety.Gate(approver)
        self.usage = usage_mod.Usage(model=MODEL)
        self.mcp_status = mcp_client.connect() if connect_mcp else "mcp disabled"
        self.backend_status = llm.health()
        self.last_blocked: list[str] = []

        if session_id:
            self._resume(session_id)
        hooks.fire("session_start", {"session_id": self.session_id})

    # ---------------------------------------------------------------- resume

    def _resume(self, session_id: str) -> None:
        """Rebuild the conversation from the transcript on disk."""
        with memory.db() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE session_id = ?"
                " AND role IN ('user','assistant') ORDER BY id", (session_id,)).fetchall()
        self.messages = [{"role": r["role"], "content": r["content"]} for r in rows]

    # ---------------------------------------------------------------- prompt

    def system(self) -> str:
        return "\n\n".join(filter(None, [
            IDENTITY, BEHAVIOR, skills.prompt_block(),
            memory.memory_prompt() or "No memory yet.",
        ]))

    def tool_specs(self) -> list[dict]:
        return tools.specs() + mcp_client.specs()

    # ---------------------------------------------------------------- context

    def _approx_tokens(self) -> int:
        chars = sum(len(json.dumps(m, default=str)) for m in self.messages)
        return chars // 3          # ~3 chars/token, good enough to trigger on

    def _compact(self) -> None:
        """Summarize the older half of the conversation to free context."""
        if len(self.messages) < 8:
            return
        cut = len(self.messages) // 2
        older, recent = self.messages[:cut], self.messages[cut:]
        # never split a tool call from its result
        while recent and recent[0].get("role") == "tool":
            older.append(recent.pop(0))

        transcript = "\n".join(
            f"[{m['role']}] {str(m.get('content'))[:2000]}" for m in older)
        summary = llm.chat(
            [{"role": "user", "content":
              f"Summarize this conversation segment. Keep every decision, file "
              f"path, number, and open thread. Drop pleasantries.\n\n{transcript}"}],
            system="You compress transcripts without losing operational detail.",
            max_tokens=2000,
        )
        self.messages = ([{"role": "user",
                           "content": f"[earlier conversation, summarized]\n{summary.text}"}]
                         + recent)

    # ---------------------------------------------------------------- tools

    def _run_tool(self, call: dict) -> dict:
        name, args = call["name"], call["args"]
        started = time.time()

        pre = hooks.fire("pre_tool", {"tool": name, "args": args,
                                      "session_id": self.session_id})
        if pre.get("block"):
            return self._result(call, f"blocked by hook: {pre['block']}", ok=False)
        args = pre.get("args", args)

        permitted, reason = self.gate.check(name, args)
        if not permitted:
            self.last_blocked.append(f"{name}: {reason}")
            return self._result(call, f"PERMISSION DENIED — {reason}", ok=False)

        try:
            if mcp_client.is_mcp(name):
                out = mcp_client.call(name, args)
            else:
                out = tools.call(name, args)
            ok, text = True, out if isinstance(out, str) else json.dumps(out, default=str)
        except Exception as e:
            ok, text = False, f"{type(e).__name__}: {e}"

        post = hooks.fire("post_tool", {"tool": name, "args": args, "result": text,
                                        "ok": ok, "session_id": self.session_id})
        text = post.get("result", text)

        self.usage.tool_calls += 1
        memory.log_tool_run(self.session_id, name, args, ok,
                            int((time.time() - started) * 1000), text[:2000])
        return self._result(call, text, ok)

    @staticmethod
    def _result(call: dict, content: str, ok: bool) -> dict:
        return {"role": "tool", "tool_call_id": call["id"], "name": call["name"],
                "content": content[:40000], "_ok": ok}

    def _run_tools(self, calls: list[dict]) -> list[dict]:
        if len(calls) == 1:
            return [self._run_tool(calls[0])]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(self._run_tool, calls))

    # ---------------------------------------------------------------- loop

    def send(self, user_message: str,
             on_event: Callable[[str, str], None] | None = None) -> str:
        emit = on_event or (lambda kind, text: None)

        turn = hooks.fire("pre_turn", {"message": user_message,
                                       "session_id": self.session_id})
        user_message = turn.get("message", user_message)

        self.messages.append({"role": "user", "content": user_message})
        memory.log_message(self.session_id, "user", user_message)

        final_text = ""
        for _ in range(MAX_TURNS):
            if self._approx_tokens() > COMPACT_AT_TOKENS:
                emit("tool", "· compacting context")
                self._compact()

            try:
                reply = llm.chat(self.messages, self.tool_specs(), self.system(),
                                 emit, EFFORT, MAX_TOKENS)
            except llm.LocalError as e:
                emit("error", str(e))
                return str(e)

            self.usage.add(reply.usage)
            self.messages.append({
                "role": "assistant", "content": reply.text,
                **({"tool_calls": reply.tool_calls} if reply.tool_calls else {}),
            })
            if reply.text:
                final_text = reply.text
                memory.log_message(self.session_id, "assistant", reply.text)

            if not reply.tool_calls:
                break

            for c in reply.tool_calls:
                emit("tool", f"{c['name']}({json.dumps(c['args'], default=str)[:200]})")
            results = self._run_tools(reply.tool_calls)
            memory.log_message(self.session_id, "tool_results",
                               [r["content"][:1500] for r in results])
            self.messages.extend(results)
        else:
            final_text += "\n[hit MAX_TURNS]"

        self.usage.persist(self.session_id)
        hooks.fire("post_turn", {"session_id": self.session_id, "reply": final_text,
                                 "usage": self.usage.snapshot()})
        emit("usage", json.dumps(self.usage.snapshot()))
        return final_text

    def stream(self, user_message: str) -> Iterator[tuple[str, str]]:
        """Generator form for the web UI: yields ('text'|'thinking'|'tool'|…, chunk)."""
        queue: list[tuple[str, str]] = []
        worker = threading.Thread(
            target=self.send, args=(user_message, lambda k, t: queue.append((k, t))),
            daemon=True)
        worker.start()
        while worker.is_alive() or queue:
            if queue:
                yield queue.pop(0)
            else:
                time.sleep(0.01)

    # ---------------------------------------------------------------- status

    def status(self) -> dict:
        return {
            "session": self.session_id,
            "backend": self.backend_status,
            "model": MODEL,
            "mcp": self.mcp_status,
            "tools": len(self.tool_specs()),
            "skills": len(skills.catalog()),
            "context_tokens": self._approx_tokens(),
            "context_limit": COMPACT_AT_TOKENS,
            "usage": self.usage.snapshot(),
            "blocked": self.last_blocked[-5:],
            "lessons": len(memory.active_lessons()),
        }

    # ---------------------------------------------------------------- learning

    def end_session(self, good: bool | None = None) -> str:
        hooks.fire("session_end", {"session_id": self.session_id,
                                   "usage": self.usage.snapshot()})
        self.usage.persist(self.session_id)
        if not LEARN_AFTER_EVERY_SESSION:
            return "autolearn off"
        return learn.learn(self.session_id, good)
