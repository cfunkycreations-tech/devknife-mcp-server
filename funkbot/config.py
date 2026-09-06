"""FunkBot configuration.

Offline by default. FunkBot talks to a Qwen model running on this machine
through any OpenAI-compatible server (Ollama, llama.cpp, LM Studio, vLLM).
No API key, no cloud call, no telemetry — every override is an env var.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path(os.getenv("FUNKBOT_DATA", ROOT / "data"))
DATA.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA / "funkbot.db"
SKILLS_DIR = pathlib.Path(os.getenv("FUNKBOT_SKILLS", ROOT / "skills"))
DICTATIONS_DIR = DATA / "dictations"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)
DICTATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ the model

# "local" (default, offline) or "anthropic" (opt-in, requires network + key)
BACKEND = os.getenv("FUNKBOT_BACKEND", "local")

MODEL = os.getenv("FUNKBOT_MODEL", "qwen3:32b")
LLM_BASE_URL = os.getenv("FUNKBOT_BASE_URL", "http://localhost:11434/v1")
LLM_API_KEY = os.getenv("FUNKBOT_API_KEY", "")        # local servers need none
NUM_CTX = int(os.getenv("FUNKBOT_NUM_CTX", "32768"))
TEMPERATURE = float(os.getenv("FUNKBOT_TEMPERATURE", "0.7"))

MAX_TOKENS = int(os.getenv("FUNKBOT_MAX_TOKENS", "8192"))
MAX_TURNS = int(os.getenv("FUNKBOT_MAX_TURNS", "40"))
EFFORT = os.getenv("FUNKBOT_EFFORT", "high")          # cloud backend only

# Smaller local model for subagents; same model by default since it's free.
WORKER_MODEL = os.getenv("FUNKBOT_WORKER_MODEL", MODEL)

# Context budget before old turns get summarized out (no server-side compaction
# exists locally, so FunkBot does it itself).
COMPACT_AT_TOKENS = int(os.getenv("FUNKBOT_COMPACT_AT", str(int(NUM_CTX * 0.7))))

# ------------------------------------------------------------------ learning

LEARN_AFTER_EVERY_SESSION = os.getenv("FUNKBOT_AUTOLEARN", "1") == "1"
MAX_LEARN_DEPTH = int(os.getenv("FUNKBOT_LEARN_DEPTH", "3"))

# ------------------------------------------------------------------ mcp

MCP_CONFIG = pathlib.Path(os.getenv("FUNKBOT_MCP_CONFIG", ROOT / "mcp_servers.json"))

# ------------------------------------------------------------------ identity

IDENTITY = os.getenv(
    "FUNKBOT_IDENTITY",
    "You are FunkBot, cfunky's personal agent, running fully offline on his own "
    "hardware. Nothing you process leaves this machine. You are direct, blunt, and "
    "you never pad an answer. You have tools, skills, MCP servers, persistent "
    "memory, subagents, and the ability to rewrite your own source code.",
)
