param(
    [string]$Python = "",
    [switch]$UpdateDeps
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Resolve-PythonLauncher {
    param([string]$PreferredPython)

    if ($PreferredPython) {
        return @{
            Command = $PreferredPython
            Prefix = @()
        }
    }

    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{
                Command = "python"
                Prefix = @()
            }
        }
    } catch {
    }

    try {
        & py -3 --version *> $null
        if ($LASTEXITCODE -eq 0) {
            return @{
                Command = "py"
                Prefix = @("-3")
            }
        }
    } catch {
    }

    throw "Python 3 was not found. Install Python 3 and make either 'python' or 'py -3' available."
}

function Invoke-Python {
    param(
        [hashtable]$Launcher,
        [string[]]$Arguments
    )

    $allArgs = @($Launcher.Prefix) + $Arguments
    & $Launcher.Command @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed: $($Launcher.Command) $($allArgs -join ' ')"
    }
}

$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DepsMarker = Join-Path $VenvDir ".remote_worker_deps_installed"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating Python venv at $VenvDir"
    $Launcher = Resolve-PythonLauncher -PreferredPython $Python
    Invoke-Python -Launcher $Launcher -Arguments @("-m", "venv", $VenvDir)
}

if ($UpdateDeps -or -not (Test-Path $DepsMarker)) {
    Write-Host "Installing remote worker dependencies"
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed"
    }
    & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "dependency installation failed"
    }
    Set-Content -Path $DepsMarker -Value (Get-Date -Format o)
}

Write-Host "Remote worker venv is ready: $Root\.venv"
