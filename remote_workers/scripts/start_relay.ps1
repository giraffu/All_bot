param(
    [string]$EnvFile = "",
    [string]$Python = "",
    [switch]$UpdateDeps,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

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

if (-not $EnvFile) {
    $EnvFile = Join-Path $Root "env\worker_remote_01.relay.env"
} elseif (-not [System.IO.Path]::IsPathRooted($EnvFile)) {
    $EnvFile = Join-Path $Root $EnvFile
}

if (-not (Test-Path $EnvFile)) {
    throw "Env file not found: $EnvFile. Copy env/*.example to a real .env file first."
}

$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$DepsMarker = Join-Path $VenvDir ".remote_worker_deps_installed"

if (-not $SkipInstall) {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating Python venv at $VenvDir"
        $Launcher = Resolve-PythonLauncher -PreferredPython $Python
        Invoke-Python -Launcher $Launcher -Arguments @("-m", "venv", $VenvDir)
    }

    if ($UpdateDeps -or -not (Test-Path $DepsMarker)) {
        Write-Host "Installing remote worker relay dependencies"
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
}

if (-not (Test-Path $VenvPython)) {
    throw "Venv not found. Run without -SkipInstall to create it automatically."
}

Set-Location $Root

foreach ($rawLine in Get-Content $EnvFile) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
        continue
    }
    $parts = $line.Split("=", 2)
    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    [Environment]::SetEnvironmentVariable($key, $value, "Process")
}

[Environment]::SetEnvironmentVariable("REMOTE_WORKER_ENV_FILE", $EnvFile, "Process")
$spool = if ($env:RESULT_SPOOL_DIR) { $env:RESULT_SPOOL_DIR } else { ".\spool" }
New-Item -ItemType Directory -Force -Path $spool | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "logs") | Out-Null

Write-Host "Starting remote worker relay with env: $EnvFile"
& $VenvPython -m remote_relay.relay_main
