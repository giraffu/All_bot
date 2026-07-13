param(
    [string]$Python = "",
    [switch]$UpdateDeps,
    [switch]$SkipInstall,
    [switch]$RelayOnly,
    [switch]$AgentOnly
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RelayEnvFile = Join-Path $Root "env\worker_remote_01.relay.env"
$AgentEnvFile = Join-Path $Root "env\worker_remote_01.agent.env"

if ($RelayOnly -and $AgentOnly) {
    throw "-RelayOnly and -AgentOnly cannot be used together."
}

if (-not $SkipInstall) {
    $installArgs = @()
    if ($Python) {
        $installArgs += @("-Python", $Python)
    }
    if ($UpdateDeps) {
        $installArgs += "-UpdateDeps"
    }
    & (Join-Path $PSScriptRoot "install_venv.ps1") @installArgs
}

$commonArgs = @()
if ($Python) {
    $commonArgs += @("-Python", $Python)
}
$commonArgs += "-SkipInstall"

if ($RelayOnly) {
    & (Join-Path $PSScriptRoot "start_relay.ps1") @commonArgs -EnvFile $RelayEnvFile
    exit $LASTEXITCODE
}

if ($AgentOnly) {
    & (Join-Path $PSScriptRoot "start_agent.ps1") @commonArgs -EnvFile $AgentEnvFile -BaseEnvFile $RelayEnvFile
    exit $LASTEXITCODE
}

$relayArgs = @(
    "-ExecutionPolicy",
    "Bypass",
    "-NoExit",
    "-File",
    (Join-Path $PSScriptRoot "start_relay.ps1"),
    "-EnvFile",
    $RelayEnvFile,
    "-SkipInstall"
)

Write-Host "Starting worker_remote_01 relay in a new PowerShell window..."
Start-Process -FilePath "powershell.exe" -ArgumentList $relayArgs
Start-Sleep -Seconds 3

Write-Host "Starting worker_remote_01 bundled agent in this window..."
& (Join-Path $PSScriptRoot "start_agent.ps1") @commonArgs -EnvFile $AgentEnvFile -BaseEnvFile $RelayEnvFile
