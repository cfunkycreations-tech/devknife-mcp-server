@echo off
REM Double-click launcher — no build required.
REM Same behavior as FunkBot.exe: starts the model if needed, boots the server,
REM opens the browser. Use build_exe.bat if you want a real .exe to pin.

setlocal
cd /d "%~dp0"
title FunkBot

where python >nul 2>nul
if errorlevel 1 (
    echo  [X] Python not found on PATH. Install from https://python.org
    pause
    exit /b 1
)

REM First run: pull in the dependencies.
python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo  installing dependencies, one moment...
    python -m pip install --quiet -r requirements.txt
)

python launcher.py %*
pause
