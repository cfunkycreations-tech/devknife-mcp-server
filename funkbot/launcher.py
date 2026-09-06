"""FunkBot launcher — what FunkBot.exe runs.

Double-click behavior: check the model server, start it if it isn't up, wait for
it to answer, boot the web server, open the browser, and stay in the console
showing status. Ctrl-C (or closing the window) shuts everything down.

    python launcher.py              normal launch
    python launcher.py --no-browser don't open a window
    python launcher.py --port 9000  different port
    python launcher.py --cli        terminal chat instead of the web UI
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# Running from a PyInstaller bundle: sources live in _MEIPASS, but data the bot
# writes must live next to the .exe, not in the temp unpack dir.
BUNDLED = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(getattr(sys, "_MEIPASS", __file__)))
BESIDE_EXE = os.path.dirname(sys.executable) if BUNDLED else HERE

sys.path.insert(0, HERE)
os.environ.setdefault("FUNKBOT_DATA", os.path.join(BESIDE_EXE, "data"))

G, P, D, R, X = "\033[38;5;48m", "\033[38;5;141m", "\033[2m", "\033[38;5;203m", "\033[0m"
BANNER = rf"""{G}
   ▄████ █    █ █▄  █ █ ▄▀ ██▄  ▄███▄ ▄████
   █▄▄   █    █ █ ▀▄█ █▀▄  █▄▄█ █   █  █
   █     ▀███▀ █   ▀█ █  ▀▄███▀ ▀███▀  █    {D}offline · local model · your machine{X}
"""


def _arg(flag: str, default: str) -> str:
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _model_up(base_url: str) -> bool:
    try:
        urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_model_server(base_url: str) -> bool:
    """Bring the local model up if it isn't already. Returns True if it's answering."""
    if _model_up(base_url):
        print(f"{G}✓{X} model server already running")
        return True

    ollama = shutil.which("ollama")
    if not ollama:
        print(f"{R}✗ no model server at {base_url}{X}")
        print(f"{D}  Install Ollama from https://ollama.com, then:{X}")
        print(f"{D}    ollama pull {os.getenv('FUNKBOT_MODEL', 'qwen3:32b')}{X}")
        print(f"{D}  Or point FUNKBOT_BASE_URL at llama.cpp / LM Studio / vLLM.{X}")
        return False

    print(f"{D}starting ollama…{X}")
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    subprocess.Popen([ollama, "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **flags)

    for _ in range(40):                      # up to ~20s
        time.sleep(0.5)
        if _model_up(base_url):
            print(f"{G}✓{X} model server up")
            return True
    print(f"{R}✗ ollama did not come up in 20s{X}")
    return False


def main() -> int:
    print(BANNER)

    import config          # noqa: E402  (after sys.path/env setup)
    import llm             # noqa: E402

    if "--cli" in sys.argv:
        ensure_model_server(config.LLM_BASE_URL)
        import cli
        cli.main()
        return 0

    port = int(_arg("--port", os.getenv("FUNKBOT_PORT", "8800")))
    host = os.getenv("FUNKBOT_HOST", "127.0.0.1")

    if _port_open(host, port):
        print(f"{G}FunkBot is already running{X} → http://{host}:{port}")
        if "--no-browser" not in sys.argv:
            webbrowser.open(f"http://{host}:{port}")
        return 0

    model_ok = ensure_model_server(config.LLM_BASE_URL)
    print(f"{D}{llm.health()}{X}")
    print(f"{D}model: {config.MODEL} · data: {os.environ['FUNKBOT_DATA']}{X}")
    if not model_ok:
        print(f"{P}starting anyway — the UI will show MODEL DOWN until it's up{X}")

    import uvicorn

    from server import app

    if "--no-browser" not in sys.argv:
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(f"http://{host}:{port}")),
            daemon=True).start()

    print(f"\n{G}FunkBot ready{X} → http://{host}:{port}   {D}(ctrl-c to stop){X}\n")
    try:
        uvicorn.run(app, host=host, port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    print(f"\n{D}FunkBot stopped.{X}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:                    # a frozen exe must never just vanish
        import traceback

        print(f"\n{R}FunkBot failed to start: {type(e).__name__}: {e}{X}\n")
        traceback.print_exc()
        if BUNDLED and os.name == "nt":
            input("\npress Enter to close…")
        sys.exit(1)
