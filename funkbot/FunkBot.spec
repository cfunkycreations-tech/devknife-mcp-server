# PyInstaller spec for FunkBot.exe
#
#   pip install pyinstaller
#   pyinstaller FunkBot.spec        ->  dist\FunkBot.exe
#
# One file, no console flicker on start, icon baked in. Everything FunkBot reads
# at runtime (web UI, skills, MCP config, policy) is bundled; everything it
# *writes* goes to data\ next to the .exe, so upgrading is just replacing the exe.

import os

block_cipher = None

datas = [
    ("web", "web"),
    ("skills", "skills"),
    ("mcp_servers.json", "."),
]
if os.path.exists("policy.json"):
    datas.append(("policy.json", "."))

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # uvicorn resolves these by string at runtime, so PyInstaller can't see them
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        # FunkBot's own modules, imported dynamically by the tool registry
        "agent", "cli", "config", "hooks", "learn", "llm", "mcp_client", "memory",
        "safety", "selfmod", "server", "skills", "subagents", "tools", "usage",
        "verify", "voice",
    ],
    excludes=["tkinter", "matplotlib", "numpy", "pytest", "faster_whisper", "torch"],
    hookspath=[],
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FunkBot",
    icon="FunkBot.ico" if os.path.exists("FunkBot.ico") else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # Console stays: it's where permission prompts, the model status and any
    # startup error are visible. Set False only if you want it fully silent.
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
