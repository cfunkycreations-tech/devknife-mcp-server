"""FunkBot in the terminal.

    python cli.py                 # chat
    python cli.py --learn         # run the recursive learning pass and exit
"""

from __future__ import annotations

import sys

import learn
from agent import FunkBot


def main() -> None:
    if "--learn" in sys.argv:
        print(learn.consolidate())
        return

    bot = FunkBot()
    print(f"FunkBot ready. session={bot.session_id}  mcp={bot.mcp_status}")
    print("ctrl-c or 'exit' to end (learning runs on exit).\n")

    try:
        while True:
            try:
                line = input("you> ").strip()
            except EOFError:
                break
            if not line or line in {"exit", "quit"}:
                break

            def show(kind: str, text: str) -> None:
                if kind == "text":
                    sys.stdout.write(text)
                elif kind == "tool":
                    sys.stdout.write(f"\n  · {text}\n")
                sys.stdout.flush()

            bot.send(line, show)
            print("\n")
    except KeyboardInterrupt:
        pass

    print("\nlearning…")
    print(bot.end_session())


if __name__ == "__main__":
    main()
