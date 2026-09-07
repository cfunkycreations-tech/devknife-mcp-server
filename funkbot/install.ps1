# FunkBot one-shot installer.
#
#   powershell -ExecutionPolicy Bypass -c "irm https://raw.githubusercontent.com/cfunkycreations-tech/devknife-mcp-server/main/funkbot/install.ps1 | iex"
#
# Downloads FunkBot, builds FunkBot.exe, and puts it on your Desktop.
# Needs nothing installed beforehand except Python (it offers to install that too).

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Say($msg, $color = "Green") { Write-Host "  $msg" -ForegroundColor $color }
function Die($msg) { Write-Host "`n  X  $msg`n" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Green
Write-Host "   FUNKBOT  |  building your desktop app" -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Green
Write-Host ""

# ---------------------------------------------------------------- python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) {
    Say "Python isn't installed. Installing it..." Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [Environment]::GetEnvironmentVariable("Path", "User")
        $py = Get-Command python -ErrorAction SilentlyContinue
    }
    if (-not $py) {
        Die "Install Python from https://python.org (tick 'Add python.exe to PATH'), then run this again."
    }
}
Say "Python: $($py.Source)"

# ---------------------------------------------------------------- source
$root = Join-Path $env:LOCALAPPDATA "FunkBot"
$src  = Join-Path $root "src"
New-Item -ItemType Directory -Force -Path $root | Out-Null

Say "Downloading FunkBot..."
$zip = Join-Path $env:TEMP "funkbot.zip"
Invoke-WebRequest -UseBasicParsing `
    -Uri "https://github.com/cfunkycreations-tech/devknife-mcp-server/archive/refs/heads/main.zip" `
    -OutFile $zip
if (Test-Path $src) { Remove-Item -Recurse -Force $src }
Expand-Archive -Path $zip -DestinationPath $root -Force
$extracted = Join-Path $root "devknife-mcp-server-main"
Move-Item -Force -Path $extracted -Destination $src
Remove-Item -Force $zip

$funkbot = Join-Path $src "funkbot"
if (-not (Test-Path $funkbot)) { Die "Download looks wrong - $funkbot is missing." }
Set-Location $funkbot

# ---------------------------------------------------------------- build
Say "Installing what it needs (a minute or two)..."
& $py.Source -m pip install --quiet --upgrade pip
& $py.Source -m pip install --quiet -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { Die "Could not install dependencies." }

Say "Checking the code is sound..."
& $py.Source -m pytest -q tests
if ($LASTEXITCODE -ne 0) { Die "Tests failed - not building a broken app." }

Say "Making the icon..."
& $py.Source make_icon.py

Say "Building FunkBot.exe (this is the slow part)..."
& $py.Source -m PyInstaller --noconfirm --clean FunkBot.spec
if ($LASTEXITCODE -ne 0) { Die "Build failed." }

# ---------------------------------------------------------------- desktop
# OneDrive relocates the Desktop, so ask Windows where it actually is.
$desktop = [Environment]::GetFolderPath("Desktop")
if (-not (Test-Path $desktop)) { $desktop = Join-Path $env:USERPROFILE "Desktop" }

$exe = Join-Path $funkbot "dist\FunkBot.exe"
if (-not (Test-Path $exe)) { Die "Build finished but FunkBot.exe is missing." }
Copy-Item -Force $exe (Join-Path $desktop "FunkBot.exe")

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Green
Write-Host "   DONE - FunkBot.exe is on your Desktop." -ForegroundColor Green
Write-Host ""
Write-Host "   Double-click it. Your browser opens and" -ForegroundColor Green
Write-Host "   FunkBot talks to whatever local model you" -ForegroundColor Green
Write-Host "   already have running." -ForegroundColor Green
Write-Host "  ============================================" -ForegroundColor Green
Write-Host ""
