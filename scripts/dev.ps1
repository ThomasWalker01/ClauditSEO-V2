# One-command bootstrap: venv, deps, migrations, demo data, dashboard build, serve.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 [-NoServe]
param([switch]$NoServe)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --quiet -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

& .\.venv\Scripts\python.exe -m clauditseo migrate
if ($LASTEXITCODE -ne 0) { throw "migrate failed" }
& .\.venv\Scripts\python.exe -m clauditseo seed
if ($LASTEXITCODE -ne 0) { throw "seed failed" }

Push-Location dashboard
if (-not (Test-Path "node_modules")) {
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Pop-Location; throw "npm install failed" }
}
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "dashboard build failed" }
Pop-Location

if ($NoServe) {
    Write-Host "Bootstrap complete (serve skipped)."
} else {
    & .\.venv\Scripts\python.exe -m clauditseo serve
}
