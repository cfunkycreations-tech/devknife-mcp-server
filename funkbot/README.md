# FunkBot

An offline agent runtime. Runs Qwen on your own hardware — nothing leaves the
machine, no API key, no cloud, no filter but your own. Tools, skills, MCP,
subagents, persistent memory, voice in and out, a permission gate, and recursive
self-improvement: it rewrites its own code and learns from its own learning.

## Launch

**Windows — install it:**

Grab `FunkBot-Setup.exe` from the [latest release](../../releases/latest), or from
the artifacts of any run of the
[Windows build workflow](../../actions/workflows/build-windows.yml). It installs
per-user (no admin prompt), adds Start Menu and desktop shortcuts, and can start
FunkBot at sign-in. Memory, skills and dictations live in
`%LOCALAPPDATA%\FunkBot\data`, so upgrading or uninstalling never eats what
FunkBot has learned.

Build it yourself, or want the portable single file instead:

```
build_exe.bat     ->  Desktop\FunkBot.exe          (copied there for you)
                  ->  dist\FunkBot.exe             (portable, data beside the exe)
                  ->  installer\FunkBot-Setup.exe  (when Inno Setup is present)
```

It installs deps, generates the icon, runs the tests, and refuses to build a
broken exe. No build needed at all if you'd rather not — `FunkBot.bat` runs it
straight from source. PyInstaller can't cross-compile, so Windows binaries get
built on Windows; that's what the Actions workflow is for.

Packaged builds can't edit their own source (it lives inside the executable) and
report `PACKAGED` rather than a health status. Run from a checkout for
self-modification.

**Linux / macOS:** `./funkbot.sh` (or `make launch`).

**Manual:**

```bash
ollama serve &
ollama pull qwen3:32b

pip install -r requirements.txt
python launcher.py          # model check + server + browser
python server.py            # just the server, http://localhost:8800
python cli.py               # the terminal
```

Any OpenAI-compatible server works — Ollama, llama.cpp (`--jinja` for tools),
LM Studio, vLLM, KoboldCpp. Point `FUNKBOT_BASE_URL` at it and go.

## Modules

| File | What it does |
|---|---|
| `llm.py` | The backend. Stdlib-only streaming client for `/v1/chat/completions`, Qwen `<think>` parsing, tool-call assembly. Zero dependencies, zero egress. |
| `agent.py` | The loop: streaming, parallel tools, permission gate, hooks, context accounting, self-compaction, session resume. |
| `tools.py` | 24 tools — bash, file r/w/edit, http, memory, skills, subagents, verified self-edit, and 10 self-modification primitives. |
| `safety.py` | Permission policy. Every call is allow / ask / deny before it runs. |
| `hooks.py` | Eight lifecycle events, Python or shell handlers. Block a tool, rewrite its args, redact its output. |
| `subagents.py` | Fan work out to parallel workers with their own context. Presets: researcher, coder, critic. |
| `skills.py` | Markdown playbooks, progressive disclosure. FunkBot writes new ones for itself. |
| `mcp_client.py` | Connects every server in `mcp_servers.json`; also runs FunkBot *as* an MCP server. |
| `memory.py` | SQLite + FTS5: facts, lessons, transcripts, tool history. |
| `learn.py` | The recursive learning engine. |
| `verify.py` | Runs the check suite after any self-edit and rolls it back if it broke. |
| `usage.py` | Token and context telemetry (local runs are free; cloud is priced). |
| `voice.py` | Dictation via local faster-whisper or the browser. |
| `server.py` + `web/` | FastAPI + the HUD: live thinking, tool trace, permission prompts, telemetry, mic, TTS. |
| `launcher.py` | The double-click entry point: brings the model up, boots the server, opens the browser, survives a missing model with a readable message. |
| `make_icon.py` | Generates `FunkBot.ico` in pure Python — no Pillow, no network. |
| `tests/` | 37 tests, no network needed — including a stub model server that exercises the whole agent loop. |

## Recursive learning

Three loops, each feeding the next:

1. **`reflect(session)`** — after every conversation FunkBot reads its own
   transcript and tool log, extracts durable facts and actionable lessons, and
   when a procedure recurs, writes itself a new skill or tool.
2. **`consolidate(depth)`** — the recursive step. It reflects on *its own
   lessons*: merging duplicates, retiring what newer lessons contradict,
   promoting clusters into skills. Output re-enters as input until nothing
   changes or `FUNKBOT_LEARN_DEPTH` (default 3) is hit.
3. **`score_outcome(good)`** — reinforcement. Lessons live during a good run gain
   score, during a bad run lose it. Score orders the system prompt; a lesson that
   keeps losing retires itself.

```
conversation ──▶ reflect ──▶ lessons ──┐
                    │                  │
                    ▼                  ▼
                 skills  ◀── consolidate (recurses on its own output)
                    │                  ▲
                    └──▶ system prompt ─┘
```

## Self-modification that can't brick itself

```
verified_self_edit → snapshot → apply → compileall → imports → pytest
                                            │
                              green ────────┴──────── red
                                │                      │
                          git commit           restore every file,
                                               report what failed
```

`verify.guard()` snapshots every `.py` before the edit and restores them all if
the check suite goes red — including deleting files the edit created. FunkBot
cannot leave itself broken, which is what makes unattended self-improvement safe.
`make check` runs the same gate by hand.

## Permissions

Every tool call is classified before it executes. Deny always wins; between allow
and ask the more specific pattern wins, so a blanket `bash:*` ask still lets
`bash:git status*` through.

```json
{
  "deny":  ["bash:*rm -rf /*", "read_file:*/.ssh/id_*"],
  "ask":   ["bash:*", "write_file:*"],
  "allow": ["bash:git *", "read_file:*", "spawn_agent:*"]
}
```

Put that in `policy.json`. Destructive shell patterns (`rm -rf /`, `mkfs`, fork
bombs, `curl | sh`) are hard-blocked regardless — that's about protecting your
disk, not policing what you ask. In the web UI an "ask" pops a prompt; in the CLI
it prompts the terminal; unattended (`FUNKBOT_UNATTENDED=deny`) it refuses, so a
headless bot can't quietly escalate. `--yes` auto-approves when you want it to
just go.

## Hooks

```python
from hooks import on

@on("pre_tool")
def no_pushes_after_midnight(ctx):
    if ctx["tool"] == "bash" and "git push" in ctx["args"].get("command", ""):
        return {"block": "not at this hour"}

@on("post_tool")
def redact(ctx):
    return {"result": ctx["result"].replace(os.environ["SECRET"], "***")}
```

Events: `session_start`, `pre_turn`, `pre_tool`, `post_tool`, `post_turn`,
`session_end`, `self_modified`, `lesson_learned`. Executables in
`hooks.d/<event>/` work too — JSON on stdin, JSON on stdout.

## Subagents

```
spawn_agent("find every place we parse dates", preset="researcher")
spawn_swarm('["audit auth", "audit uploads", "audit the cron jobs"]', preset="critic")
```

Each worker gets its own context window and a restricted tool set, and returns
only its conclusion — so a twenty-file investigation costs the main thread one
paragraph instead of twenty files.

## The avatar

`web/avatar.js` + `web/avatar.css` — pure SVG/CSS, no libraries, no image files,
44px to any size. It animates on every question:

| State | What it does |
|---|---|
| `idle` | slow ring drift, eye breathing |
| `listening` | goes red, fast ring, bars ride the mic |
| `thinking` | rings accelerate, eye charges, scan sweep, green halo |
| `tool` | purple takeover, stepped flicker |
| `speaking` | bars carry the cadence |

Three ways to give it your own face:

```bash
python cli.py --avatar ~/Downloads/funkbot.avatar.png     # any path, quotes ok
```

…or drag the image onto the avatar in the running UI, or copy it to
`web/funkbot.png` yourself. Wide shots crop correctly — framing is explicit:

```js
new FunkAvatar(el, { src: 'funkbot.png', frame: { zoom: 2.6, x: 52, y: 27 } });
```

`web/avatar-demo.html` has sliders that print the exact frame values to paste.

## Voice

**In:** the mic button uses the browser's Web Speech API when available, else
records audio and transcribes it with local faster-whisper. Audio never leaves
the machine either way, and every dictation is saved to `data/dictations/` *and*
to memory — so "what did I dictate Tuesday" is answerable.

**Out:** the VOICE button speaks replies aloud through the browser.

## Config

Every setting is an env var, all optional:

| Var | Default | |
|---|---|---|
| `FUNKBOT_MODEL` | `qwen3:32b` | any local model |
| `FUNKBOT_BASE_URL` | `http://localhost:11434/v1` | Ollama, llama.cpp, LM Studio, vLLM |
| `FUNKBOT_BACKEND` | `local` | `anthropic` to opt into cloud |
| `FUNKBOT_NUM_CTX` | `32768` | context window |
| `FUNKBOT_TEMPERATURE` | `0.7` | |
| `FUNKBOT_UNATTENDED` | `deny` | what "ask" means with nobody watching |
| `FUNKBOT_AUTOLEARN` | `1` | reflect after every session |
| `FUNKBOT_LEARN_DEPTH` | `3` | recursion cap on consolidation |
| `FUNKBOT_WORKER_MODEL` | same as main | subagent model |
| `FUNKBOT_IDENTITY` | — | rewrite its personality |

## Commands

```
make run      web UI            make test     the 33 tests
make cli      terminal          make check    full self-verification
make model    pull the model    make learn    force a learning pass
make mcp      serve FunkBot's tools to other agents over MCP

python cli.py --sessions          list past sessions
python cli.py --resume <id>       continue one
python cli.py --status            model, health, totals
python cli.py -p "one shot"       single prompt
python cli.py --yes               auto-approve everything
python cli.py --avatar <path>     install a portrait into the avatar ring
```

`Dockerfile` and `funkbot.service` are included; the service unit runs with
`ProtectSystem=full` and unattended-deny since the thing has shell access.

## Things to type at it

```
show me your own source files
add yourself a tool that reads my clipboard, verify it, and commit
spawn three critics on the auth code and merge their findings
that took you three tries — record what you should have done instead
consolidate your lessons and tell me what you merged
what have you learned about me
```

## Rails

Self-edits confined to FunkBot's own directory; `.bak` before every write;
AST gate rejects broken Python; the full check suite gates every verified edit
with automatic rollback; per-change git commits; permission gate on every tool;
learning depth capped; failing lessons auto-retire.
