#!/usr/bin/env bash
# Same launcher for Linux and macOS: starts the model if needed, boots the
# server, opens the browser. chmod +x funkbot.sh and double-click or run it.
set -e
cd "$(dirname "$0")"

python3 -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "installing dependencies…"
    python3 -m pip install --quiet -r requirements.txt
}

exec python3 launcher.py "$@"
