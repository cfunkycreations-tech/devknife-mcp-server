"""FunkBot in the terminal.

    python cli.py                    chat
    python cli.py --resume <id>      continue a past session
    python cli.py --sessions         list past sessions
    python cli.py --status           model, health, totals
    python cli.py --learn            run the recursive learning pass
    python cli.py -p "one shot"      single prompt, print, exit
    python cli.py --yes              auto-approve every permission prompt
"""

from __future__ import annotations

import sys

import learn
import llm
import memory
import usage as usage_mod
import verify
from agent import FunkBot

G, P, D, R, X = "\033[38;5;48m", "\033[38;5;141m", "\033[2m", "\033[38;5;203m", "\033[0m"


def terminal_approver(auto_yes: bool):
    def approve(tool: str, args: dict, reason: str) -> bool:
        if auto_yes:
            return True
        print(f"\n{P}┌ PERMISSION{X} {tool}")
        for k, v in args.items():
            print(f"{P}│{X} {k}: {str(v)[:300]}")
        print(f"{P}│{X} {D}{reason}{X}")
        try:
            answer = input(f"{P}└ allow? [y/N/a=always] {X}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in {"y", "yes", "a", "always"}
    return approve


def main() -> None:
    args = sys.argv[1:]

    if "--status" in args:
        print(llm.health())
        print(verify.health())
        print("totals:", usage_mod.totals())
        return

    if "--sessions" in args:
        with memory.db() as c:
            for r in c.execute(
                    "SELECT s.id, s.started_at, s.title,"
                    " (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) n"
                    " FROM sessions s ORDER BY s.started_at DESC LIMIT 25"):
                print(f"{G}{r['id']}{X}  {r['n']:>4} msgs  {r['title'] or ''}")
        return

    if "--learn" in args:
        print(learn.consolidate())
        return

    resume = args[args.index("--resume") + 1] if "--resume" in args else None
    bot = FunkBot(session_id=resume, approver=terminal_approver("--yes" in args))

    if "-p" in args:
        print(bot.send(args[args.index("-p") + 1]))
        return

    print(f"{G}FUNKBOT{X}  {bot.backend_status}")
    print(f"{D}session {bot.session_id} · {len(bot.tool_specs())} tools · "
          f"mcp: {bot.mcp_status}{X}")
    print(f"{D}'exit' to end · /status · /learn · /health{X}\n")

    try:
        while True:
            try:
                line = input(f"{G}you>{X} ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in {"exit", "quit"}:
                break
            if line == "/status":
                print(bot.status()); continue
            if line == "/health":
                print(verify.health()); continue
            if line == "/learn":
                print(learn.learn(bot.session_id)); continue

            def show(kind: str, text: str) -> None:
                if kind == "text":
                    sys.stdout.write(text)
                elif kind == "thinking":
                    sys.stdout.write(f"{D}{text}{X}")
                elif kind == "tool":
                    sys.stdout.write(f"\n{P}  · {text}{X}\n")
                elif kind == "error":
                    sys.stdout.write(f"\n{R}  ! {text}{X}\n")
                sys.stdout.flush()

            bot.send(line, show)
            u = bot.usage.snapshot()
            print(f"\n{D}[{u['output']} tok out · {u['tool_calls']} tools · "
                  f"{u['elapsed_s']}s]{X}\n")
    except KeyboardInterrupt:
        pass

    print(f"\n{D}learning…{X}")
    print(bot.end_session())


if __name__ == "__main__":
    main()
