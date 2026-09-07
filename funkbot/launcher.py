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
# writes must live somewhere it can actually write.
BUNDLED = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(getattr(sys, "_MEIPASS", __file__)))
BESIDE_EXE = os.path.dirname(sys.executable) if BUNDLED else HERE


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-probe")
        with open(probe, "w") as fh:
            fh.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


def default_data_dir() -> str:
    """Beside the exe when that is writable (portable use); otherwise the
    per-user app data directory — an install under Program Files is read-only,
    and silently failing to save memory there would be worse than moving."""
    beside = os.path.join(BESIDE_EXE, "data")
    if not BUNDLED or _writable(beside):
        return beside
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(root, "FunkBot", "data")
    return os.path.join(os.path.expanduser("~"), ".funkbot", "data")


sys.path.insert(0, HERE)
os.environ.setdefault("FUNKBOT_DATA", default_data_dir())

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
        print(f"{R}✗ no model server found{X}")
        print(f"{D}  Start yours — Bionic, LM Studio, llama.cpp, Ollama, vLLM.{X}")
        print(f"{D}  FunkBot checks the usual ports itself; set FUNKBOT_BASE_URL{X}")
        print(f"{D}  only if yours listens somewhere unusual.{X}")
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

    import llm             # noqa: E402  (after sys.path/env setup)

    if "--cli" in sys.argv:
        ensure_model_server(llm.resolve()[0])
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

    # resolve() discovers the server; 'auto' never reaches the probe.
    model_ok = ensure_model_server(llm.resolve()[0])
    print(f"{D}{llm.health()}{X}")
    print(f"{D}model: {llm.resolved_model()} · data: {os.environ['FUNKBOT_DATA']}{X}")
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
