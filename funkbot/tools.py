"""FunkBot's built-in tool surface, in Anthropic tool-definition form."""

from __future__ import annotations

import inspect
import json
import pathlib
import subprocess
import textwrap
import urllib.request
from typing import Any, Callable

import memory
import selfmod
import skills

REGISTRY: dict[str, dict] = {}


def tool(name: str, description: str, schema: dict) -> Callable:
    """Register a python callable as a Claude tool."""
    def deco(fn: Callable) -> Callable:
        REGISTRY[name] = {"fn": fn, "spec": {
            "name": name, "description": description, "input_schema": schema}}
        return fn
    return deco


def _s(**props) -> dict:
    required = [k for k, v in props.items() if v.pop("_req", True)]
    return {"type": "object", "properties": props, "required": required,
            "additionalProperties": False}


# --------------------------------------------------------------------- shell / files

@tool("bash", "Run a shell command in FunkBot's working directory. Use for git, "
      "package managers, tests, anything a terminal can do.",
      _s(command={"type": "string", "description": "the command"},
         timeout={"type": "integer", "description": "seconds, default 120", "_req": False}))
def bash(command: str, timeout: int = 120) -> str:
    p = subprocess.run(command, shell=True, capture_output=True, text=True,
                       timeout=timeout, cwd=selfmod.ROOT)
    return f"exit={p.returncode}\n{p.stdout}{p.stderr}"[:40000]


@tool("read_file", "Read any file on disk.",
      _s(path={"type": "string"}, max_bytes={"type": "integer", "_req": False}))
def read_file(path: str, max_bytes: int = 200_000) -> str:
    return pathlib.Path(path).expanduser().read_text(
        encoding="utf-8", errors="replace")[:max_bytes]


@tool("write_file", "Create or overwrite a file on disk.",
      _s(path={"type": "string"}, content={"type": "string"}))
def write_file(path: str, content: str) -> str:
    p = pathlib.Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {p} ({len(content)} bytes)"


@tool("edit_file", "Replace an exact string in a file.",
      _s(path={"type": "string"}, find={"type": "string"}, replace={"type": "string"}))
def edit_file(path: str, find: str, replace: str) -> str:
    p = pathlib.Path(path).expanduser()
    src = p.read_text(encoding="utf-8")
    if find not in src:
        return f"NOT FOUND: {find[:80]!r}"
    p.write_text(src.replace(find, replace, 1), encoding="utf-8")
    return f"patched {p}"


# --------------------------------------------------------------------- web

@tool("http_get", "Fetch a URL and return its body as text.",
      _s(url={"type": "string"}, max_bytes={"type": "integer", "_req": False}))
def http_get(url: str, max_bytes: int = 100_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "FunkBot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(max_bytes).decode("utf-8", errors="replace")


# --------------------------------------------------------------------- memory

@tool("remember", "Store a durable fact about the user or their world. Use this "
      "whenever you learn something worth carrying into future conversations.",
      _s(subject={"type": "string"}, body={"type": "string"},
         kind={"type": "string", "description": "fact|preference|project|person",
               "_req": False}))
def remember(subject: str, body: str, kind: str = "fact") -> str:
    return memory.remember(subject, body, kind)


@tool("recall", "Search FunkBot's memory — past conversations, facts, and lessons.",
      _s(query={"type": "string"}, limit={"type": "integer", "_req": False}))
def recall(query: str, limit: int = 12) -> str:
    hits = memory.recall(query, limit)
    return json.dumps(hits, indent=1) if hits else "no matches"


@tool("record_lesson", "Record a lesson learned from what just happened, so future "
      "runs behave better. Phrase the trigger as a situation, the lesson as an action.",
      _s(trigger={"type": "string"}, lesson={"type": "string"},
         evidence={"type": "string", "_req": False}))
def record_lesson(trigger: str, lesson: str, evidence: str = "") -> str:
    return f"lesson #{memory.add_lesson(trigger, lesson, evidence)} recorded"


# --------------------------------------------------------------------- skills

@tool("load_skill", "Load the full instructions for one of your skills by name.",
      _s(name={"type": "string"}))
def load_skill(name: str) -> str:
    return skills.load(name)


@tool("write_skill", "Write a new skill for yourself — a reusable playbook you will "
      "see listed in every future conversation.",
      _s(name={"type": "string"}, description={"type": "string"},
         body={"type": "string", "description": "markdown instructions"}))
def write_skill(name: str, description: str, body: str) -> str:
    return skills.write_skill(name, description, body)


# --------------------------------------------------------------------- self-modification

for _name, _fn in [
    ("list_own_files", selfmod.list_own_files), ("read_own_code", selfmod.read_own_code),
    ("search_own_code", selfmod.search_own_code), ("patch_own_code", selfmod.patch_own_code),
    ("write_own_file", selfmod.write_own_file), ("add_own_tool", selfmod.add_own_tool),
    ("rollback", selfmod.rollback), ("reload_self", selfmod.reload_self),
    ("commit_self", selfmod.commit_self), ("self_status", selfmod.self_status),
]:
    _sig = inspect.signature(_fn)
    _props = {
        p.name: {"type": "integer" if p.annotation is int else "string"}
        for p in _sig.parameters.values()
    }
    _req = [p.name for p in _sig.parameters.values()
            if p.default is inspect.Parameter.empty]
    REGISTRY[_name] = {"fn": _fn, "spec": {
        "name": _name,
        "description": textwrap.shorten(inspect.getdoc(_fn) or _name, 300),
        "input_schema": {"type": "object", "properties": _props, "required": _req},
    }}


def specs() -> list[dict]:
    return [t["spec"] for t in REGISTRY.values()]


def call(name: str, args: dict) -> Any:
    if name not in REGISTRY:
        return f"unknown tool: {name}"
    return REGISTRY[name]["fn"](**args)
