# tools/install.ps1 - one-click setup for people who don't use Python.
# Run it through install.bat (double-click). It:
#   1. finds Python 3.10-3.13, or installs Python 3.12 for this user with winget
#   2. creates .venv and installs requirements.txt (about 300 MB to download)
#   3. creates the Desktop / Start-menu shortcuts and starts AirMouse
# Running it again is safe: it only adds what is missing.

$ErrorActionPreference = "Continue"
$App = Split-Path -Parent $PSScriptRoot
Set-Location $App
$Supported = @("3.10", "3.11", "3.12", "3.13")

function Say($text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Fail($text) {
    Write-Host ""
    Write-Host $text -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

function Python-Version($exe) {
    try { return (& $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null | Select-Object -First 1) } catch { return $null }
}

function Find-Python {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($v in "3.12", "3.13", "3.11", "3.10") {
            try {
                $exe = & py "-$v" -c "import sys; print(sys.executable)" 2>$null | Select-Object -First 1
                if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
            } catch {}
        }
    }
    foreach ($v in "312", "313", "311", "310") {
        $exe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe"
        if (Test-Path $exe) { return $exe }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    # The "python" in WindowsApps only opens the Microsoft Store
    if ($cmd -and $cmd.Source -notlike "*WindowsApps*" -and ($Supported -contains (Python-Version $cmd.Source))) {
        return $cmd.Source
    }
    return $null
}

Write-Host "AirMouse setup" -ForegroundColor White
Write-Host "Folder: $App"

$venvPython = Join-Path $App ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Say "Looking for Python"
    $python = Find-Python
    if (-not $python) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Say "Installing Python 3.12 (only for this user)"
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            $python = Find-Python
        }
    }
    if (-not $python) {
        Start-Process "https://www.python.org/downloads/windows/"
        Fail "Python 3.12 is needed. Install it from the page that just opened (tick 'Add python.exe to PATH'), then run install.bat again."
    }
    Write-Host "Using $python"
    Say "Creating the private Python environment (.venv)"
    & $python -m venv .venv
    if (-not (Test-Path $venvPython)) { Fail "Could not create .venv with $python" }
}

# mediapipe needs the Microsoft Visual C++ runtime (most PCs already have it)
if (-not (Test-Path (Join-Path $env:WINDIR "System32\msvcp140.dll"))) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "Installing the Microsoft Visual C++ runtime (Windows may ask for permission)"
        winget install -e --id Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host "If AirMouse fails to start, install the Microsoft Visual C++ Redistributable (x64)." -ForegroundColor Yellow
    }
}

Say "Installing AirMouse's libraries (the first time downloads about 300 MB)"
& $venvPython -m pip install --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "Installing the libraries failed. Check the internet connection and run install.bat again." }

Say "Creating the AirMouse shortcuts (Desktop and Start menu)"
& $venvPython tools\create_shortcuts.py

Say "Starting AirMouse - a setup guide opens in your browser"
Start-Process -FilePath (Join-Path $App ".venv\Scripts\pythonw.exe") -ArgumentList "`"$App\main.py`"" -WorkingDirectory $App
Write-Host ""
Write-Host "Done. Next time, open AirMouse from the Desktop or the Start menu." -ForegroundColor Green
Start-Sleep -Seconds 6
