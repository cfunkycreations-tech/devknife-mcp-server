"""The local-backend contract, tested against a stub OpenAI-compatible server.

No model, no network, no key — this proves the streaming parser, the <think>
splitting, the tool-call assembly, and the agent loop all work offline.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import config          # noqa: E402
import llm             # noqa: E402


def sse(*chunks: dict) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


SCRIPT: list[bytes] = []


class Stub(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        payload = SCRIPT.pop(0) if SCRIPT else sse({"choices": [{"delta": {}}]})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "qwen3:32b"}]}).encode())

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module", autouse=True)
def stub_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    llm.LLM_BASE_URL = config.LLM_BASE_URL = f"http://127.0.0.1:{srv.server_port}/v1"
    yield
    srv.shutdown()


def delta(**d) -> dict:
    return {"choices": [{"delta": d}]}


def test_plain_text_streams_through():
    SCRIPT.append(sse(delta(content="Hello "), delta(content="funk"),
                      {"choices": [{"delta": {}, "finish_reason": "stop"}]}))
    seen = []
    reply = llm.chat([{"role": "user", "content": "hi"}],
                     on_delta=lambda k, t: seen.append((k, t)))
    assert reply.text == "Hello funk"
    assert [t for k, t in seen if k == "text"] == ["Hello ", "funk"]


def test_think_blocks_are_split_out_of_the_answer():
    SCRIPT.append(sse(delta(content="<think>weighing "), delta(content="options</think>"),
                      delta(content="The answer is 4.")))
    channels = {"text": "", "thinking": ""}
    reply = llm.chat([{"role": "user", "content": "2+2"}],
                     on_delta=lambda k, t: channels.__setitem__(k, channels[k] + t))
    assert reply.text == "The answer is 4."
    assert reply.thinking == "weighing options"
    assert "<think>" not in channels["text"]
    assert channels["thinking"] == "weighing options"


def test_think_split_across_one_chunk():
    SCRIPT.append(sse(delta(content="<think>quick</think>done")))
    reply = llm.chat([{"role": "user", "content": "x"}])
    assert (reply.text, reply.thinking) == ("done", "quick")


def test_reasoning_content_field_is_honored():
    SCRIPT.append(sse(delta(reasoning_content="hmm"), delta(content="ok")))
    reply = llm.chat([{"role": "user", "content": "x"}])
    assert reply.thinking == "hmm" and reply.text == "ok"


def test_tool_calls_assemble_from_fragments():
    SCRIPT.append(sse(
        delta(tool_calls=[{"index": 0, "id": "c1",
                           "function": {"name": "ba", "arguments": '{"comm'}}]),
        delta(tool_calls=[{"index": 0, "function": {"name": "sh",
                                                    "arguments": 'and": "ls"}'}}]),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}))
    reply = llm.chat([{"role": "user", "content": "list"}])
    assert reply.stop_reason == "tool_use"
    assert reply.tool_calls == [{"id": "c1", "name": "bash", "args": {"command": "ls"}}]


def test_malformed_tool_arguments_do_not_raise():
    SCRIPT.append(sse(delta(tool_calls=[{"index": 0, "id": "c9",
                                         "function": {"name": "bash",
                                                      "arguments": "{not json"}}])))
    reply = llm.chat([{"role": "user", "content": "x"}])
    assert reply.tool_calls[0]["args"]["_raw"] == "{not json"


def test_usage_is_reported():
    SCRIPT.append(sse(delta(content="hi"),
                      {"choices": [], "usage": {"prompt_tokens": 11,
                                                "completion_tokens": 3}}))
    reply = llm.chat([{"role": "user", "content": "x"}])
    assert reply.usage == {"input_tokens": 11, "output_tokens": 3}


def test_health_reports_the_local_endpoint():
    assert "offline" in llm.health()
    assert "UNREACHABLE" not in llm.health()


def test_unreachable_server_raises_a_useful_error():
    saved = llm.LLM_BASE_URL
    llm.LLM_BASE_URL = "http://127.0.0.1:9/v1"
    try:
        with pytest.raises(llm.LocalError) as e:
            llm.chat([{"role": "user", "content": "x"}])
        assert "no local model server answered" in str(e.value)
        assert "FUNKBOT_BASE_URL" in str(e.value)
    finally:
        llm.LLM_BASE_URL = saved


def test_agent_runs_a_full_tool_loop_offline():
    """Model asks for a tool, gets the result, answers — end to end, no network."""
    import agent

    SCRIPT.append(sse(delta(tool_calls=[{"index": 0, "id": "t1",
                                         "function": {"name": "bash",
                                                      "arguments":
                                                      '{"command": "echo funkbot"}'}}])))
    SCRIPT.append(sse(delta(content="It printed funkbot.")))

    bot = agent.FunkBot(connect_mcp=False, approver=lambda *a: True)
    out = bot.send("run echo")
    assert out == "It printed funkbot."
    assert any(m.get("role") == "tool" and "funkbot" in m["content"]
               for m in bot.messages)
    assert bot.usage.tool_calls == 1


def test_denied_tool_never_executes():
    import agent

    SCRIPT.append(sse(delta(tool_calls=[{"index": 0, "id": "t2",
                                         "function": {"name": "write_file",
                                                      "arguments":
                                                      '{"path": "/tmp/nope.txt",'
                                                      ' "content": "x"}'}}])))
    SCRIPT.append(sse(delta(content="I was blocked.")))

    bot = agent.FunkBot(connect_mcp=False, approver=lambda *a: False)
    bot.send("write a file")
    assert not pathlib.Path("/tmp/nope.txt").exists()
    assert any("PERMISSION DENIED" in m.get("content", "")
               for m in bot.messages if m.get("role") == "tool")
