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

echo  [1/5] installing dependencies...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller
if errorlevel 1 (
    echo  [X] dependency install failed.
    pause
    exit /b 1
)

echo  [2/5] generating icon...
python make_icon.py

echo  [3/5] running the test suite...
python -m pytest -q tests
if errorlevel 1 (
    echo.
    echo  [X] tests failed - not building a broken exe.
    pause
    exit /b 1
)

echo  [4/5] building the exe...
python -m PyInstaller --noconfirm --clean FunkBot.spec
if errorlevel 1 (
    echo  [X] build failed.
    pause
    exit /b 1
)

echo  [5/5] building the installer...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo  [!] installer step failed - the exe above is still good.
    ) else (
        set "MADE_INSTALLER=1"
    )
) else (
    echo  [-] Inno Setup not found - skipping the installer.
    echo      Want FunkBot-Setup.exe? Install it from https://jrsoftware.org/isdl.php
    echo      then run this script again.
)

echo.
echo  ===============================================
echo   Done.
echo.
echo   Portable:   %cd%\dist\FunkBot.exe
if defined MADE_INSTALLER echo   Installer:  %cd%\installer\FunkBot-Setup.exe
echo.
echo   Double-click either one. FunkBot finds your local
echo   model server, boots, and opens the UI. Installed
echo   builds keep data in %%LOCALAPPDATA%%\FunkBot.
echo  ===============================================
echo.
pause
