param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

& $Python -m venv .venv
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -r requirements.txt

Write-Host "Remote worker relay venv is ready: $Root\.venv"

