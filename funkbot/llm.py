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

from config import (BACKEND, DISCOVER_PORTS, LLM_BASE_URL, LLM_API_KEY,
                    MAX_TOKENS, MODEL, NUM_CTX, TEMPERATURE)

THINK_RE = re.compile(r"<think>(.*?)</think>", re.S)
OPEN_THINK_RE = re.compile(r"<think>(.*)$", re.S)

# Resolved once, then reused: (base_url, model).
_RESOLVED: dict[str, str] = {}

# A model whose name says it can't chat.
NOT_CHAT = ("embed", "embedding", "rerank", "whisper", "clip", "tts", "bge-", "nomic")
# Preferred when several will do — tool use and instruction following first.
PREFERRED = ("coder", "instruct", "qwen", "abliterated", "uncensored", "chat")


@dataclass
class Reply:
    text: str = ""
    thinking: str = ""
    tool_calls: list[dict] = field(default_factory=list)   # {id, name, args}
    usage: dict = field(default_factory=dict)
    stop_reason: str = "end_turn"


class LocalError(RuntimeError):
    """The local model server is unreachable or refused the request."""


# --------------------------------------------------------------------- discovery

def _list_models(base_url: str, timeout: float = 2.0) -> list[str]:
    """Model ids a server advertises, or [] if it isn't one."""
    req = urllib.request.Request(base_url.rstrip("/") + "/models")
    if LLM_API_KEY:
        req.add_header("Authorization", f"Bearer {LLM_API_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    except Exception:
        return []


def _pick_model(available: list[str]) -> str:
    """Choose a chat-capable model, favouring instruction-tuned and coder builds."""
    usable = [m for m in available
              if not any(bad in m.lower() for bad in NOT_CHAT)] or available
    return max(usable, key=lambda m: (
        sum(word in m.lower() for word in PREFERRED), len(m)), default="")


def resolve() -> tuple[str, str]:
    """Find the local server and the model to talk to. Cached after the first hit.

    Nothing here needs configuring: with FUNKBOT_BASE_URL unset, the usual local
    ports are probed; with FUNKBOT_MODEL unset — or set to something the server
    doesn't actually serve — a served model is chosen instead of failing.
    """
    # Keyed on the configuration so a changed setting re-resolves instead of
    # serving a stale endpoint.
    key = f"{LLM_BASE_URL}|{MODEL}"
    if _RESOLVED.get("key") == key:
        return _RESOLVED["base_url"], _RESOLVED["model"]
    _RESOLVED.clear()

    candidates = ([LLM_BASE_URL] if LLM_BASE_URL != "auto" else
                  [f"http://localhost:{p}/v1" for p in DISCOVER_PORTS])

    for base in candidates:
        models = _list_models(base)
        if not models:
            continue
        if MODEL != "auto" and MODEL in models:
            chosen = MODEL
        elif MODEL != "auto" and any(MODEL.split(":")[0] in m for m in models):
            chosen = next(m for m in models if MODEL.split(":")[0] in m)
        else:
            chosen = _pick_model(models)
        if chosen:
            _RESOLVED.update(key=key, base_url=base, model=chosen)
            return base, chosen

    # Nothing answered — keep the configured values so the error names them.
    fallback = LLM_BASE_URL if LLM_BASE_URL != "auto" else \
        f"http://localhost:{DISCOVER_PORTS[0]}/v1"
    return fallback, (MODEL if MODEL != "auto" else "")


# --------------------------------------------------------------------- helpers

def _post(path: str, payload: dict, stream: bool):
    url = resolve()[0].rstrip("/") + path
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=None if stream else 600)
    except urllib.error.HTTPError as e:
        # The server answered — it just refused. Show what it actually said.
        try:
            detail = e.read().decode("utf-8", "replace")[:2000]
        except Exception:
            detail = ""
        raise LocalError(
            f"{url} refused the request (HTTP {e.code} {e.reason})."
            + (f"\n{detail}" if detail else "")
        ) from e
    except urllib.error.URLError as e:
        ports = ", ".join(str(p) for p in DISCOVER_PORTS)
        raise LocalError(
            f"no local model server answered at {url} ({e}).\n"
            f"Start yours (LM Studio / Bionic, Ollama, llama.cpp, …) — FunkBot "
            f"checks ports {ports} automatically, or set FUNKBOT_BASE_URL to its "
            f"address ending in /v1."
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


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Normalized messages -> exactly what an OpenAI-compatible server expects.

    FunkBot carries tool calls around as {id, name, args} and tags tool results
    with bookkeeping keys of its own. Sent as-is, a strict server (LM Studio,
    vLLM) rejects the whole request with a 400, so the shape is fixed here — the
    one place that talks the wire protocol.
    """
    wire: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            wire.append({"role": "tool",
                         "tool_call_id": m.get("tool_call_id", ""),
                         "content": m.get("content") or ""})
            continue
        out = {"role": role, "content": m.get("content") or ""}
        calls = m.get("tool_calls")
        if role == "assistant" and calls:
            out["tool_calls"] = [{
                "id": c.get("id") or f"call_{i}",
                "type": "function",
                "function": {
                    "name": c.get("name", ""),
                    # Servers want the arguments as a JSON *string*.
                    "arguments": c["args"] if isinstance(c.get("args"), str)
                    else json.dumps(c.get("args") or {}, default=str),
                },
            } for i, c in enumerate(calls)]
        wire.append(out)
    return wire


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
        "model": resolve()[1],
        "messages": ([{"role": "system", "content": system}] if system else [])
                    + _to_openai_messages(messages),
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
    """What FunkBot found: the server it discovered and the model it will use."""
    if BACKEND == "anthropic":
        return "backend: anthropic (cloud)"

    base, model = resolve()
    names = _list_models(base, timeout=5)
    if not names:
        ports = ", ".join(str(p) for p in DISCOVER_PORTS)
        return (f"offline · UNREACHABLE — nothing answered on ports {ports}. "
                f"Start your model server, or set FUNKBOT_BASE_URL.")
    others = [n for n in names if n != model]
    tail = f" · also loaded: {', '.join(others[:5])}" if others else ""
    return f"offline · {base} · using {model}{tail}"


def resolved_model() -> str:
    """The model actually in use — what the HUD and the CLI report."""
    return resolve()[1] or (MODEL if MODEL != "auto" else "none found")
