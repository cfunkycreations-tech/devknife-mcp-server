"""FunkBot configuration. Everything overridable by env var."""

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

MODEL = os.getenv("FUNKBOT_MODEL", "claude-opus-5")
EFFORT = os.getenv("FUNKBOT_EFFORT", "high")
MAX_TOKENS = int(os.getenv("FUNKBOT_MAX_TOKENS", "32000"))
MAX_TURNS = int(os.getenv("FUNKBOT_MAX_TURNS", "40"))

# Recursive learning
LEARN_AFTER_EVERY_SESSION = os.getenv("FUNKBOT_AUTOLEARN", "1") == "1"
MAX_LEARN_DEPTH = int(os.getenv("FUNKBOT_LEARN_DEPTH", "3"))

# MCP servers: JSON file mapping name -> {"command":..,"args":[..]} or {"url":..}
MCP_CONFIG = pathlib.Path(os.getenv("FUNKBOT_MCP_CONFIG", ROOT / "mcp_servers.json"))

IDENTITY = os.getenv(
    "FUNKBOT_IDENTITY",
    "You are FunkBot, cfunky's personal agent. You are direct, concise, and you "
    "never pad answers. You have tools, skills, MCP servers, persistent memory, and "
    "the ability to modify your own source code.",
)
