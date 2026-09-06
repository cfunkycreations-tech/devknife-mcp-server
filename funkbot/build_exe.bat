@echo off
REM Build FunkBot.exe — run this once on Windows, double-click the result forever.
REM
REM   build_exe.bat
REM   -> dist\FunkBot.exe
REM
REM PyInstaller cannot cross-compile: a Windows .exe has to be built on Windows.

setlocal
cd /d "%~dp0"

echo.
echo  ===============================================
echo   FUNKBOT  ^|  building FunkBot.exe
echo  ===============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo  [X] Python not found on PATH.
    echo      Install it from https://python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

echo  [1/4] installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 (
    echo  [X] dependency install failed.
    pause
    exit /b 1
)

echo  [2/4] generating icon...
python make_icon.py

echo  [3/4] running the test suite...
python -m pytest -q tests
if errorlevel 1 (
    echo.
    echo  [X] tests failed - not building a broken exe.
    pause
    exit /b 1
)

echo  [4/4] building...
python -m PyInstaller --noconfirm --clean FunkBot.spec
if errorlevel 1 (
    echo  [X] build failed.
    pause
    exit /b 1
)

echo.
echo  ===============================================
echo   Done:  %cd%\dist\FunkBot.exe
echo.
echo   Double-click it to launch. It starts your local
echo   model if it isn't running, boots the server, and
echo   opens the UI. Data lands in dist\data\.
echo  ===============================================
echo.
pause
