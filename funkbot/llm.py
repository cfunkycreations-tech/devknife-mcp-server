"""The model backend. Local and offline by default — nothing leaves the machine.

Speaks the OpenAI-compatible `/v1/chat/completions` API that every local runtime
exposes, so it works unchanged against:

    Ollama       http://localhost:11434/v1     (FUNKBOT_MODEL=qwen3:32b)
    llama.cpp    http://localhost:8080/v1      (llama-server --jinja for tools)
    LM Studio    http://localhost:1234/v1
    vLLM         http://localhost:8000/v1
    text-gen-webui, KoboldCpp, anything else OpenAI-shaped

Zero dependencies — stdlib urllib, including SSE streaming. No API key is sent
unless you set one. Qwen's `<think>` blocks are parsed out into a separate
channel so reasoning streams to the UI without polluting the transcript.

An optional cloud backend exists (FUNKBOT_BACKEND=anthropic) but nothing selects
it for you: offline is the default and the fallback.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterable

from config import (BACKEND, LLM_BASE_URL, LLM_API_KEY, MAX_TOKENS, MODEL,
                    NUM_CTX, TEMPERATURE)

THINK_RE = re.compile(r"<think>(.*?)</think>", re.S)
OPEN_THINK_RE = re.compile(r"<think>(.*)$", re.S)


@dataclass
class Reply:
    text: str = ""
    thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)   # {id, name, args}
    usage: dict = field(default_factory=dict)
    stop_reason: str = "end_turn"


class LocalError(RuntimeError):
    """The local model server is unreachable or refused the request."""


# --------------------------------------------------------------------- helpers

def _post(path: str, payload: dict, stream: bool):
    url = LLM_BASE_URL.rstrip("/") + path
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=None if stream else 600)
    except urllib.error.URLError as e:
        raise LocalError(
            f"cannot reach the local model at {url} ({e}). "
            f"Start it first — e.g. `ollama serve` then `ollama run {MODEL}`."
        ) from e


def _sse_lines(response) -> Iterable[dict]:
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _to_openai_tools(specs: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": s["name"], "description": s["description"],
        "parameters": s["input_schema"]}} for s in specs]


def _split_thinking(text: str) -> tuple[str, str]:
    """Pull Qwen's <think>…</think> out of the visible answer."""
    thinking = "\n".join(THINK_RE.findall(text))
    clean = THINK_RE.sub("", text)
    if "<think>" in clean:                      # unterminated block
        m = OPEN_THINK_RE.search(clean)
        if m:
            thinking += "\n" + m.group(1)
            clean = clean[:m.start()]
    return clean.strip(), thinking.strip()


# --------------------------------------------------------------------- local

def _chat_local(messages: list[dict], tools: list[dict], system: str,
                on_delta: Callable[[str, str], None] | None,
                effort: str, max_tokens: int) -> Reply:
    payload = {
        "model": MODEL,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
        "stream": True,
        "stream_options": {"include_usage": True},
        # Ollama passthrough — ignored by servers that don't know it.
        "options": {"num_ctx": NUM_CTX},
    }
    if tools:
        payload["tools"] = _to_openai_tools(tools)
        payload["tool_choice"] = "auto"

    text_parts: list[str] = []
    think_parts: list[str] = []
    calls: dict[int, dict] = {}
    usage: dict = {}
    finish = "end_turn"
    in_think = False

    with _post("/chat/completions", payload, stream=True) as response:
        for chunk in _sse_lines(response):
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices", []):
                delta = choice.get("delta") or {}
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]

                # Some servers stream reasoning on its own field.
                if delta.get("reasoning_content"):
                    think_parts.append(delta["reasoning_content"])
                    if on_delta:
                        on_delta("thinking", delta["reasoning_content"])

                piece = delta.get("content") or ""
                if piece:
                    # Route <think> spans to the thinking channel as they arrive.
                    while piece:
                        if in_think:
                            end = piece.find("</think>")
                            if end == -1:
                                think_parts.append(piece)
                                if on_delta:
                                    on_delta("thinking", piece)
                                piece = ""
                            else:
                                think_parts.append(piece[:end])
                                if on_delta:
                                    on_delta("thinking", piece[:end])
                                piece, in_think = piece[end + 8:], False
                        else:
                            start = piece.find("<think>")
                            if start == -1:
                                text_parts.append(piece)
                                if on_delta:
                                    on_delta("text", piece)
                                piece = ""
                            else:
                                head = piece[:start]
                                if head:
                                    text_parts.append(head)
                                    if on_delta:
                                        on_delta("text", head)
                                piece, in_think = piece[start + 7:], True

                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = calls.setdefault(idx, {"id": tc.get("id") or f"call_{idx}",
                                                  "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["arguments"] += fn.get("arguments") or ""

    tool_calls = []
    for slot in calls.values():
        try:
            args = json.loads(slot["arguments"] or "{}")
        except json.JSONDecodeError:
            args = {"_raw": slot["arguments"]}
        tool_calls.append({"id": slot["id"], "name": slot["name"], "args": args})

    text = "".join(text_parts)
    thinking = "".join(think_parts)
    if "<think>" in text:                          # non-streaming servers
        text, extra = _split_thinking(text)
        thinking = (thinking + "\n" + extra).strip()

    return Reply(
        text=text.strip(), thinking=thinking.strip(), tool_calls=tool_calls,
        usage={"input_tokens": usage.get("prompt_tokens", 0),
               "output_tokens": usage.get("completion_tokens", 0)},
        stop_reason="tool_use" if tool_calls else finish,
    )


# --------------------------------------------------------------------- cloud (opt-in)

def _chat_anthropic(messages: list[dict], tools: list[dict], system: str,
                    on_delta: Callable[[str, str], None] | None,
                    effort: str, max_tokens: int) -> Reply:
    from anthropic import Anthropic

    client = Anthropic()
    anth_msgs, pending_results = [], []
    for m in messages:                              # normalized -> Anthropic blocks
        if m["role"] == "tool":
            pending_results.append({"type": "tool_result",
                                    "tool_use_id": m["tool_call_id"],
                                    "content": m["content"]})
            continue
        if pending_results:
            anth_msgs.append({"role": "user", "content": pending_results})
            pending_results = []
        if m["role"] == "assistant" and m.get("tool_calls"):
            blocks = ([{"type": "text", "text": m["content"]}] if m.get("content") else [])
            blocks += [{"type": "tool_use", "id": c["id"], "name": c["name"],
                        "input": c["args"]} for c in m["tool_calls"]]
            anth_msgs.append({"role": "assistant", "content": blocks})
        else:
            anth_msgs.append({"role": m["role"], "content": m["content"]})
    if pending_results:
        anth_msgs.append({"role": "user", "content": pending_results})

    with client.messages.stream(
        model=MODEL, max_tokens=max_tokens, system=system,
        tools=[{"name": s["name"], "description": s["description"],
                "input_schema": s["input_schema"]} for s in tools],
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": effort},
        messages=anth_msgs,
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and on_delta:
                d = event.delta
                if d.type == "text_delta":
                    on_delta("text", d.text)
                elif d.type == "thinking_delta":
                    on_delta("thinking", d.thinking)
        msg = stream.get_final_message()

    return Reply(
        text="".join(b.text for b in msg.content if b.type == "text"),
        thinking="".join(getattr(b, "thinking", "") for b in msg.content
                         if b.type == "thinking"),
        tool_calls=[{"id": b.id, "name": b.name, "args": b.input}
                    for b in msg.content if b.type == "tool_use"],
        usage={"input_tokens": msg.usage.input_tokens,
               "output_tokens": msg.usage.output_tokens,
               "cache_read": getattr(msg.usage, "cache_read_input_tokens", 0) or 0},
        stop_reason=msg.stop_reason or "end_turn",
    )


# --------------------------------------------------------------------- entry point

def chat(messages: list[dict], tools: list[dict] | None = None, system: str = "",
         on_delta: Callable[[str, str], None] | None = None,
         effort: str = "high", max_tokens: int = MAX_TOKENS) -> Reply:
    """One model call. Normalized in, normalized out, backend-agnostic."""
    fn = _chat_anthropic if BACKEND == "anthropic" else _chat_local
    return fn(messages, tools or [], system, on_delta, effort, max_tokens)


def health() -> str:
    """Is the local model up, and which ones are loaded?"""
    if BACKEND == "anthropic":
        return "backend: anthropic (cloud)"
    try:
        req = urllib.request.Request(LLM_BASE_URL.rstrip("/") + "/models")
        if LLM_API_KEY:
            req.add_header("Authorization", f"Bearer {LLM_API_KEY}")
        with urllib.request.urlopen(req, timeout=5) as r:
            names = [m["id"] for m in json.load(r).get("data", [])]
        loaded = "loaded: " + ", ".join(names[:8]) if names else "no models loaded"
        mark = "✓" if any(MODEL.split(":")[0] in n for n in names) else "✗ not found"
        return f"offline · {LLM_BASE_URL} · {MODEL} {mark} · {loaded}"
    except Exception as e:
        return f"offline · {LLM_BASE_URL} · UNREACHABLE ({type(e).__name__})"
