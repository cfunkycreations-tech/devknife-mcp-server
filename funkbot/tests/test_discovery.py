"""Server discovery and model selection — no config, no placeholders.

Uses the real model list Bionic/LM Studio reported, so the choice is tested
against actual data rather than an invented one.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import llm  # noqa: E402

BIONIC_MODELS = [
    "huihui-qwen3-coder-30b-a3b-instruct-abliterated-i1",
    "qwen3-4b-instruct-2507",
    "text-embedding-nomic-embed-text-v1.5",
    "mistral-7b-instruct-v0.1",
    "llama-3-8b-lexi-uncensored",
    "solar-10.7b-instruct-v1.0-uncensored",
    "guanaco-13b-uncensored@q4_k_m",
    "guanaco-13b-uncensored@q5_k_s",
]


def make_server(models: list[str]):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(
                {"data": [{"id": m} for m in models], "object": "list"}).encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.fixture(autouse=True)
def clear_cache():
    llm._RESOLVED.clear()
    yield
    llm._RESOLVED.clear()


# ------------------------------------------------------------------ selection

def test_picks_the_coder_model_from_a_real_bionic_list():
    assert llm._pick_model(BIONIC_MODELS) == \
        "huihui-qwen3-coder-30b-a3b-instruct-abliterated-i1"


def test_never_picks_an_embedding_model():
    assert llm._pick_model(["text-embedding-nomic-embed-text-v1.5",
                            "mistral-7b-instruct-v0.1"]) == "mistral-7b-instruct-v0.1"


def test_falls_back_to_whatever_exists_when_all_look_unusable():
    assert llm._pick_model(["text-embedding-ada-002"]) == "text-embedding-ada-002"


def test_empty_list_yields_nothing():
    assert llm._pick_model([]) == ""


# ------------------------------------------------------------------ discovery

def test_discovers_a_server_on_an_unconfigured_port(monkeypatch):
    srv = make_server(BIONIC_MODELS)
    port = srv.server_port
    monkeypatch.setattr(llm, "LLM_BASE_URL", "auto")
    monkeypatch.setattr(llm, "MODEL", "auto")
    monkeypatch.setattr(llm, "DISCOVER_PORTS", [9, port])   # 9 is dead on purpose

    base, model = llm.resolve()
    assert base == f"http://localhost:{port}/v1"
    assert model == "huihui-qwen3-coder-30b-a3b-instruct-abliterated-i1"
    srv.shutdown()


def test_a_configured_model_that_is_not_served_falls_back_to_one_that_is(monkeypatch):
    """The failure the user hit: FUNKBOT_MODEL=qwen3:32b against LM Studio."""
    srv = make_server(BIONIC_MODELS)
    monkeypatch.setattr(llm, "LLM_BASE_URL", f"http://localhost:{srv.server_port}/v1")
    monkeypatch.setattr(llm, "MODEL", "qwen3:32b")

    _, model = llm.resolve()
    assert model in BIONIC_MODELS
    assert "qwen3" in model          # honors the intent, uses a real id
    srv.shutdown()


def test_an_exact_configured_model_is_respected(monkeypatch):
    srv = make_server(BIONIC_MODELS)
    monkeypatch.setattr(llm, "LLM_BASE_URL", f"http://localhost:{srv.server_port}/v1")
    monkeypatch.setattr(llm, "MODEL", "llama-3-8b-lexi-uncensored")

    assert llm.resolve()[1] == "llama-3-8b-lexi-uncensored"
    srv.shutdown()


def test_health_names_the_server_and_the_chosen_model(monkeypatch):
    srv = make_server(BIONIC_MODELS)
    monkeypatch.setattr(llm, "LLM_BASE_URL", f"http://localhost:{srv.server_port}/v1")
    monkeypatch.setattr(llm, "MODEL", "auto")

    report = llm.health()
    assert "using huihui-qwen3-coder-30b" in report
    assert "also loaded" in report
    srv.shutdown()


def test_health_says_what_to_do_when_nothing_is_listening(monkeypatch):
    monkeypatch.setattr(llm, "LLM_BASE_URL", "auto")
    monkeypatch.setattr(llm, "DISCOVER_PORTS", [9])
    assert "UNREACHABLE" in llm.health()
    assert "FUNKBOT_BASE_URL" in llm.health()
