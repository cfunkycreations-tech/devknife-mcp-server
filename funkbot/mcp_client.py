"""MCP support: FunkBot as an MCP client (uses other servers' tools) and as an
MCP server (exposes its own tools to Claude Desktop, Cursor, etc.).

Client config lives in mcp_servers.json:

    {
      "filesystem": {"command": "npx",
                     "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me"]},
      "devknife":   {"url": "https://devknife-mcp.onrender.com/mcp/sse"}
    }

Every MCP tool is surfaced to the model as `mcp__<server>__<tool>`.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from config import MCP_CONFIG

_LOOP: asyncio.AbstractEventLoop | None = None
_SESSIONS: dict[str, Any] = {}
_TOOLS: dict[str, dict] = {}          # qualified name -> {"server":.., "tool":.., "spec":..}
_STACK: Any = None


def _run(coro):
    """Run a coroutine on FunkBot's dedicated MCP event loop from sync code."""
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()
        threading.Thread(target=_LOOP.run_forever, daemon=True, name="mcp").start()
    return asyncio.run_coroutine_threadsafe(coro, _LOOP).result(timeout=120)


async def _connect_all() -> str:
    from contextlib import AsyncExitStack

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    global _STACK
    if not MCP_CONFIG.exists():
        return "no mcp_servers.json — no MCP servers configured"

    servers = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    _STACK = AsyncExitStack()
    await _STACK.__aenter__()
    report = []

    for name, cfg in servers.items():
        try:
            if "url" in cfg:
                from mcp.client.sse import sse_client
                read, write = await _STACK.enter_async_context(sse_client(cfg["url"]))
            else:
                params = StdioServerParameters(
                    command=cfg["command"], args=cfg.get("args", []),
                    env=cfg.get("env"))
                read, write = await _STACK.enter_async_context(stdio_client(params))
            session = await _STACK.enter_async_context(ClientSession(read, write))
            await session.initialize()
            _SESSIONS[name] = session

            listed = await session.list_tools()
            for t in listed.tools:
                qualified = f"mcp__{name}__{t.name}"
                _TOOLS[qualified] = {
                    "server": name, "tool": t.name,
                    "spec": {"name": qualified,
                             "description": (t.description or t.name)[:900],
                             "input_schema": t.inputSchema or
                             {"type": "object", "properties": {}}},
                }
            report.append(f"{name}: {len(listed.tools)} tools")
        except Exception as e:  # a broken server must not take the bot down
            report.append(f"{name}: FAILED ({type(e).__name__}: {e})")

    return "; ".join(report)


def connect() -> str:
    """Connect every configured MCP server. Safe to call at startup."""
    try:
        return _run(_connect_all())
    except Exception as e:
        return f"MCP unavailable: {type(e).__name__}: {e}"


def specs() -> list[dict]:
    return [t["spec"] for t in _TOOLS.values()]


def is_mcp(name: str) -> bool:
    return name in _TOOLS


def call(name: str, args: dict) -> str:
    entry = _TOOLS[name]

    async def go():
        result = await _SESSIONS[entry["server"]].call_tool(entry["tool"], args)
        parts = []
        for block in result.content:
            parts.append(getattr(block, "text", None) or str(block))
        return "\n".join(parts)

    return _run(go())[:40000]


# ------------------------------------------------------------------ server side

def serve_stdio() -> None:
    """Expose FunkBot's own tools over MCP so other agents can drive it."""
    from mcp.server.fastmcp import FastMCP

    import tools as funk_tools

    mcp = FastMCP("funkbot")
    for name, entry in funk_tools.REGISTRY.items():
        mcp.tool(name=name, description=entry["spec"]["description"])(entry["fn"])
    mcp.run()


if __name__ == "__main__":
    serve_stdio()
