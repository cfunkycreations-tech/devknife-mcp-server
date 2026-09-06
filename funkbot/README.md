# FunkBot self-modifying code snippets

`selfmod.py` gives FunkBot the ability to read, patch, extend, reload, and
commit its own source. Copy it into FunkBot's package directory (next to its
main module) — `ROOT` is that directory, and FunkBot cannot write outside it.

## Wiring it up

### Plain function-calling loop / Anthropic SDK tool_runner
```python
from selfmod import SELF_MOD_TOOLS
TOOLS = {f.__name__: f for f in SELF_MOD_TOOLS}   # dispatch by tool name
```

### LangChain
```python
from langchain_core.tools import StructuredTool
from selfmod import SELF_MOD_TOOLS
tools = [StructuredTool.from_function(f) for f in SELF_MOD_TOOLS]
```

### FastMCP / MCP server
```python
from mcp.server.fastmcp import FastMCP
from selfmod import SELF_MOD_TOOLS
mcp = FastMCP("funkbot")
for f in SELF_MOD_TOOLS:
    mcp.tool()(f)
```

### discord.py / any chat bot — an owner-only command
```python
@bot.command()
async def evolve(ctx, *, instruction: str):
    if ctx.author.id != OWNER_ID:
        return
    import selfmod
    plan = await ask_llm(
        f"FunkBot source files: {selfmod.list_own_files()}\n"
        f"Task: {instruction}\n"
        "Reply with exactly one call to patch_own_code/write_own_file/add_own_tool."
    )
    await ctx.send(run_tool(plan))          # your existing tool dispatcher
    await ctx.send(selfmod.commit_self(instruction))
```

## System prompt to add
```
You can modify your own source code. Use list_own_files and read_own_code to
see the exact current text before editing. Make the smallest change that works
via patch_own_code (the `find` string must match the file byte-for-byte). New
capabilities go in add_own_tool. After editing, call commit_self with a short
message, then reload_self for the changed module, or restart_self if you edited
startup code. If anything breaks, call rollback immediately.
```

## Things to type at FunkBot
```
show me your own source files
read your main loop and tell me what's slow about it
add yourself a tool called weather_now that hits wttr.in and returns the text
give yourself a --verbose flag that logs every tool call, then restart
your last change broke you — roll back selfmod.py and tell me what happened
what have you changed about yourself in the last 10 commits
```

## Guardrails already in place
- writes confined to `ROOT`; path escapes raise
- `.bak.<timestamp>` backup before every write
- `ast.parse` syntax gate — bad Python is rejected, never written
- `rollback()` restores the newest backup
- `commit_self()` makes every change `git revert`-able

Worth adding on your side: run FunkBot's test suite after each self-edit and
auto-rollback on failure, and keep `restart_self` behind an owner check.
