"""FunkBot's agent loop: Claude + tools + skills + MCP + memory + self-modification.

Streaming, adaptive thinking, prompt caching on the stable prefix, parallel tool
execution, server-side compaction for long runs, and a learning pass when the
session ends.
"""

from __future__ import annotations

import concurrent.futures
import json
import time
from typing import Any, Callable, Iterator

import learn
import mcp_client
import memory
import skills
import tools
from config import (EFFORT, IDENTITY, LEARN_AFTER_EVERY_SESSION, MAX_TOKENS,
                    MAX_TURNS, MODEL)

BEHAVIOR = """
How you work:
- Act, don't narrate. No preamble, no "I'll now…", no restating the request.
- Call tools in parallel whenever the calls don't depend on each other.
- Use recall before claiming you don't know something about the user.
- Use remember the moment you learn something durable — a preference, a project,
  a name, a decision. Do not ask permission to remember.
- Use record_lesson when a run teaches you something about how to work better.
- You can rewrite your own source: read_own_code, patch_own_code, add_own_tool,
  then commit_self and reload_self. Make the smallest change that works, and
  rollback the instant something breaks.
- When a procedure comes up a second time, write_skill it so it is reusable.
""".strip()


class FunkBot:
    def __init__(self, session_id: str | None = None, connect_mcp: bool = True):
        from anthropic import Anthropic

        self.client = Anthropic()
        self.session_id = session_id or memory.new_session()
        self.messages: list[dict] = []
        self.mcp_status = mcp_client.connect() if connect_mcp else "mcp disabled"

    # ---------------------------------------------------------------- prompt

    def system(self) -> list[dict]:
        """Stable prefix first (cached), volatile memory last."""
        stable = "\n\n".join([IDENTITY, BEHAVIOR, skills.prompt_block()]).strip()
        return [
            {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": memory.memory_prompt() or "No memory yet."},
        ]

    def tool_specs(self) -> list[dict]:
        return tools.specs() + mcp_client.specs()

    # ---------------------------------------------------------------- tools

    def _run_tool(self, block: Any) -> dict:
        started = time.time()
        args = block.input if isinstance(block.input, dict) else {}
        try:
            if mcp_client.is_mcp(block.name):
                result = mcp_client.call(block.name, args)
            else:
                result = tools.call(block.name, args)
            ok, text = True, result if isinstance(result, str) else json.dumps(
                result, default=str)
        except Exception as e:
            ok, text = False, f"{type(e).__name__}: {e}"

        memory.log_tool_run(self.session_id, block.name, args, ok,
                            int((time.time() - started) * 1000), text[:2000])
        return {"type": "tool_result", "tool_use_id": block.id,
                "content": text[:60000], "is_error": not ok}

    def _run_tools_parallel(self, blocks: list[Any]) -> list[dict]:
        if len(blocks) == 1:
            return [self._run_tool(blocks[0])]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(self._run_tool, blocks))

    # ---------------------------------------------------------------- loop

    def send(self, user_message: str, on_event: Callable[[str, str], None] | None = None) -> str:
        """One user turn, driven to completion through however many tool calls."""
        emit = on_event or (lambda kind, text: None)
        self.messages.append({"role": "user", "content": user_message})
        memory.log_message(self.session_id, "user", user_message)

        final_text = ""
        for _ in range(MAX_TURNS):
            with self.client.beta.messages.stream(
                betas=["compact-2026-01-12"],
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=self.system(),
                tools=self.tool_specs(),
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT},
                context_management={"edits": [{"type": "compact_20260112"}]},
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta":
                        d = event.delta
                        if d.type == "text_delta":
                            emit("text", d.text)
                        elif d.type == "thinking_delta":
                            emit("thinking", d.thinking)
                response = stream.get_final_message()

            # Append the FULL content — compaction blocks must survive.
            self.messages.append({"role": "assistant", "content": response.content})
            text = "".join(b.text for b in response.content if b.type == "text")
            if text:
                final_text = text
                memory.log_message(self.session_id, "assistant", text)

            if response.stop_reason == "refusal":
                return f"[refused: {getattr(response.stop_details, 'category', 'unknown')}]"

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return final_text

            for b in tool_uses:
                emit("tool", f"{b.name}({json.dumps(b.input, default=str)[:200]})")
            results = self._run_tools_parallel(tool_uses)
            memory.log_message(self.session_id, "tool_results",
                               [r["content"][:1500] for r in results])
            # All results in ONE user message, or Claude stops calling in parallel.
            self.messages.append({"role": "user", "content": results})

        return final_text + "\n[hit MAX_TURNS]"

    def stream(self, user_message: str) -> Iterator[tuple[str, str]]:
        """Generator form for the web UI: yields ('text'|'thinking'|'tool', chunk)."""
        queue: list[tuple[str, str]] = []
        done: list[str] = []

        def collect(kind: str, text: str) -> None:
            queue.append((kind, text))

        import threading
        worker = threading.Thread(
            target=lambda: done.append(self.send(user_message, collect)), daemon=True)
        worker.start()
        while worker.is_alive() or queue:
            if queue:
                yield queue.pop(0)
            else:
                time.sleep(0.01)

    # ---------------------------------------------------------------- learning

    def end_session(self, good: bool | None = None) -> str:
        """Close the session and run the recursive learning pass."""
        if not LEARN_AFTER_EVERY_SESSION:
            return "autolearn off"
        return learn.learn(self.session_id, good)
