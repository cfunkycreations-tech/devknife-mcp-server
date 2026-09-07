# FunkBot — where things stand

Read this first in a new session. Everything below is on `main`, merged.

## What FunkBot is

Offline agent runtime in `funkbot/`. Runs against cfunky's **local** model server
(Bionic / LM Studio on port 1234, serving
`huihui-qwen3-coder-30b-a3b-instruct-abliterated-i1`). No cloud, no API key.
Auto-detects the server and model — `FUNKBOT_BASE_URL` and `FUNKBOT_MODEL`
default to `auto` and should stay that way.

## Getting it on his machine

One line in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/cfunkycreations-tech/devknife-mcp-server/main/funkbot/install.ps1 | iex"
```

Downloads, builds, drops `FunkBot.exe` on his Desktop. **He needs ~2 GB free
disk** — he was at 302 MB and the build died; the installer now checks first.

## State

- PRs #1–#7 all merged. No open PRs, no watchers, no scheduled check-ins.
- 56 tests pass. `python -m pytest -q tests`.
- GitHub Actions can't build the Windows exe: jobs return in seconds with
  `runner_id: 0` — no Windows runner available to the org. Not a workflow bug;
  ruled out the third-party action. Workflow only runs on main/tags/manual now
  so it stops reddening PRs. Local build is the working path.

## Modules

`llm.py` backend (stdlib only, OpenAI-compatible, parses Qwen `<think>`) ·
`agent.py` loop · `tools.py` 24 tools · `safety.py` allow/ask/deny gate ·
`hooks.py` · `subagents.py` · `memory.py` SQLite+FTS · `learn.py` recursive
learning · `verify.py` self-edit gate · `voice.py` · `server.py` + `web/` HUD ·
`launcher.py` double-click entry · `cli.py`.

## Gotchas already paid for — don't regress these

- Never hardcode `python3`; use `sys.executable`. On Windows `python3` hits the
  Microsoft Store stub and every check fails.
- `/api/status` must not run the test suite. `health()` is quick by default;
  `health(full=True)` is cached. It used to cost 4.5s per 20s poll.
- Packaged (PyInstaller) builds: no source tree. Health reports `PACKAGED`,
  self-editing refuses, data goes to `%LOCALAPPDATA%\FunkBot\data` because the
  install dir is read-only.
- `run_checks` marks child processes (`FUNKBOT_IN_CHECK`) so a self-edit made
  inside a check can't re-enter pytest and hang.
- The HUD status poll must not overwrite fields the chat stream filled.

## How he wants to be talked to

Short. No jargon — say "your model app", not infrastructure terms. Don't explain
why something failed at length; fix it. Don't hand him command templates with
`<placeholders>` — he will paste them literally. Give one exact command.

**Start a new session at ~150k context.** He has limited tokens and has said so
repeatedly.
