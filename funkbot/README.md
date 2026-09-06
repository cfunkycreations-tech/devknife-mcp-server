# FunkBot

A full agent runtime: tools, skills, MCP (client *and* server), persistent memory,
voice dictation, a web UI, and recursive self-improvement — it rewrites its own
code and learns from its own learning.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python server.py          # http://localhost:8800
python cli.py             # or terminal
python mcp_client.py      # or expose FunkBot's tools to Claude Desktop over MCP
```

## What's in it

| File | What it does |
|---|---|
| `agent.py` | The loop. Streaming, adaptive thinking, parallel tool calls, prompt caching, server-side compaction for long runs. |
| `tools.py` | 20 built-in tools: bash, file read/write/edit, http, memory, skills, and the 10 self-modification tools. |
| `skills.py` | Markdown playbooks with progressive disclosure — only name+description sit in the prompt; the body loads on demand. FunkBot can `write_skill` new ones for itself. |
| `mcp_client.py` | Connects every server in `mcp_servers.json` (stdio or SSE) and surfaces their tools as `mcp__<server>__<tool>`. Also runs FunkBot *as* an MCP server. |
| `memory.py` | SQLite + FTS5. Facts, lessons, full transcripts, tool-run history. Survives restarts; injected into every system prompt. |
| `learn.py` | The recursive learning engine (below). |
| `selfmod.py` | Read/patch/extend/reload/commit its own source, with path confinement, backups, AST syntax gate, and rollback. |
| `voice.py` | Dictation. Local faster-whisper, or the browser's Web Speech API. Every dictation saved to disk *and* memory. |
| `server.py` + `web/` | FastAPI + a dark chat UI: SSE streaming, live thinking, tool trace, mic button, memory inspector. |

## Recursive learning

Three loops, each feeding the next:

1. **`reflect(session)`** — after every conversation, FunkBot reads its own
   transcript and tool log, then extracts durable facts, actionable lessons, and —
   when a procedure has recurred — writes itself a new skill or a new tool.
2. **`consolidate(depth)`** — the recursive step. FunkBot reflects on *its own
   lessons*: merging duplicates, retiring what's been contradicted, and promoting
   clusters of related lessons into a single skill. Its output re-enters as input,
   recursing until nothing changes or `FUNKBOT_LEARN_DEPTH` (default 3) is hit.
3. **`score_outcome(good)`** — reinforcement. Lessons live during a good run gain
   score, during a bad run lose it. Score orders the system prompt; a lesson that
   keeps losing retires itself.

Every artifact learning produces — lesson, skill, tool — goes through the same
syntax gate, backup, and git commit as any other self-edit. A bad lesson is one
`git revert` away.

```
conversation ──▶ reflect ──▶ lessons ──┐
                    │                  │
                    ▼                  ▼
                 skills  ◀── consolidate (recurses on its own output)
                    │                  ▲
                    └──▶ system prompt ─┘
```

## The avatar

`web/avatar.js` + `web/avatar.css` — a pure SVG/CSS cyborg icon that animates on
every question. No libraries, no image files, scales from 44px to any size.

```js
import { FunkAvatar } from './avatar.js';
const av = new FunkAvatar(document.getElementById('avatar'));
av.state = 'thinking';   // idle | listening | thinking | tool | speaking
av.pulse();              // one-shot flare
```

| State | What it does |
|---|---|
| `idle` | slow ring drift, eye breathing, label STANDBY |
| `listening` | goes red, fast ring, bars ride the mic |
| `thinking` | rings accelerate, eye charges, scan sweep across the face, green halo |
| `tool` | purple takeover, stepped eye flicker, fast bars |
| `speaking` | bars carry the cadence, eye settles |

The chat UI drives it automatically: `pulse()` + `thinking` when you send, `tool`
on each tool call, `speaking` as text streams, `idle` when done, `listening` while
the mic is open. Drop a portrait at `web/funkbot.png` and it fills the ring in
place of the drawn face. `prefers-reduced-motion` stops the motion but keeps the
color and label changes. Open `web/avatar-demo.html` to see every state side by side.

## The mic button

Click to toggle. If the browser has the Web Speech API it transcribes live into
the input box; otherwise it records audio and posts it to `/api/transcribe`, which
runs faster-whisper locally — audio never leaves the machine either way. Both
paths save the dictation to `data/dictations/` and to memory, so *"what did I
dictate Tuesday"* is answerable.

## Config

All env vars, all optional: `FUNKBOT_MODEL` (default `claude-opus-5`),
`FUNKBOT_EFFORT`, `FUNKBOT_MAX_TOKENS`, `FUNKBOT_MAX_TURNS`, `FUNKBOT_DATA`,
`FUNKBOT_SKILLS`, `FUNKBOT_MCP_CONFIG`, `FUNKBOT_AUTOLEARN`, `FUNKBOT_LEARN_DEPTH`,
`FUNKBOT_IDENTITY`.

## Adding an MCP server

```json
{
  "filesystem": {"command": "npx",
                 "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me"]},
  "devknife":   {"url": "https://devknife-mcp.onrender.com/mcp/sse"}
}
```

A server that fails to start is reported and skipped — it never takes the bot down.

## Things to type at FunkBot

```
show me your own source files
add yourself a tool that checks my calendar
that took three tries — record what you should have done instead
consolidate your lessons and tell me what you merged
give yourself a --verbose flag that logs every tool call, then restart
what have you learned about me
```

## Safety rails

- Self-edits confined to FunkBot's own directory; path escapes raise.
- `.bak.<timestamp>` before every write; `rollback()` restores the newest.
- `ast.parse` gate — broken Python is rejected, never written.
- Per-change git commits; learning depth capped; failing lessons auto-retire.

Worth adding on your side: run your test suite after each self-edit and auto-rollback
on failure, and put `restart_self` behind an owner check.
