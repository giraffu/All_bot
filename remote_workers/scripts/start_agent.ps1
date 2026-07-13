param(
    [string]$EnvFile = "",
    [string]$BaseEnvFile = "",
    [string]$Python = "",
    [switch]$UpdateDeps,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Resolve-EnvPath {
    param([string]$PathValue)

    if (-not $PathValue) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $Root $PathValue
}

function Import-DotEnvFile {
    param(
        [string]$PathValue,
        [bool]$Required = $true
    )

    if (-not $PathValue) {
        return
    }
    if (-not (Test-Path $PathValue)) {
        if ($Required) {
            throw "Env file not found: $PathValue"
        }
        Write-Warning "Optional env file not found, continuing with defaults: $PathValue"
        return
    }

    foreach ($rawLine in Get-Content $PathValue) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

function Set-DefaultEnv {
    param(
        [string]$Name,
        [string]$Value
    )

    if (-not [Environment]::GetEnvironmentVariable($Name, "Process")) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

if (-not $EnvFile) {
    $EnvFile = Join-Path $Root "env\worker_remote_01.agent.env"
} else {
    $EnvFile = Resolve-EnvPath $EnvFile
}

if (-not $BaseEnvFile) {
    $relayCandidate = $EnvFile -replace "\.agent\.env$", ".relay.env"
    if ($relayCandidate -ne $EnvFile -and (Test-Path $relayCandidate)) {
        $BaseEnvFile = $relayCandidate
    }
} else {
    $BaseEnvFile = Resolve-EnvPath $BaseEnvFile
}

$hasAgentEnv = Test-Path $EnvFile
$hasBaseEnv = $BaseEnvFile -and (Test-Path $BaseEnvFile)
if (-not $hasAgentEnv -and -not $hasBaseEnv) {
    throw "No usable env file found. Create env/*.relay.env first, then optionally copy env/*.agent.env.example for ComfyUI overrides."
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

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Venv not found. Run without -SkipInstall to create it automatically."
}

Set-Location $Root
Import-DotEnvFile -PathValue $BaseEnvFile -Required $false
Import-DotEnvFile -PathValue $EnvFile -Required $false

$relayPort = if ($env:LOCAL_RELAY_PORT) { $env:LOCAL_RELAY_PORT } else { "8013" }
$agentId = if ($env:REMOTE_WORKER_ID) { $env:REMOTE_WORKER_ID } else { "worker_remote_01" }

Set-DefaultEnv -Name "AGENT_ID" -Value $agentId
Set-DefaultEnv -Name "MASTER_API_URL" -Value "http://127.0.0.1:$relayPort"
Set-DefaultEnv -Name "UPLOAD_SIDECAR_URL" -Value "http://127.0.0.1:$relayPort"
Set-DefaultEnv -Name "SUPPORTED_TASK_TYPES" -Value "img2img"
Set-DefaultEnv -Name "COMFY_API_URL" -Value "http://127.0.0.1:8111/"
Set-DefaultEnv -Name "COMFY_WS_URL" -Value "ws://127.0.0.1:8111/ws"
Set-DefaultEnv -Name "COMFY_INPUT_DIR" -Value ".\input"
Set-DefaultEnv -Name "COMFY_OUTPUT_DIR" -Value ".\output"
Set-DefaultEnv -Name "MINIO_INPUT_BUCKET" -Value "user-data-prod"
Set-DefaultEnv -Name "MINIO_RESULT_BUCKET" -Value "user-data-prod"
Set-DefaultEnv -Name "MINIO_TEMPLATE_BUCKET" -Value "user-data-prod"
Set-DefaultEnv -Name "MINIO_SECURE" -Value "true"
Set-DefaultEnv -Name "RESULT_SPOOL_DIR" -Value ".\spool\$env:AGENT_ID"
Set-DefaultEnv -Name "PREFETCH_CACHE_DIR" -Value ".\prefetch-cache\$env:AGENT_ID"
Set-DefaultEnv -Name "AGENT_LOG_DIR" -Value ".\logs"
Set-DefaultEnv -Name "PREFETCH_ENABLED" -Value "false"
Set-DefaultEnv -Name "PIPELINE_ENABLED" -Value "false"
Set-DefaultEnv -Name "CANCEL_LOCK_ON_POP" -Value "true"

[Environment]::SetEnvironmentVariable("REMOTE_WORKER_AGENT_ENV_FILE", $EnvFile, "Process")
[Environment]::SetEnvironmentVariable("NO_PROXY", "*", "Process")
[Environment]::SetEnvironmentVariable("no_proxy", "*", "Process")

New-Item -ItemType Directory -Force -Path $env:COMFY_INPUT_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:COMFY_OUTPUT_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:RESULT_SPOOL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:PREFETCH_CACHE_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:AGENT_LOG_DIR | Out-Null

Write-Host "Starting bundled remote comfy agent: $env:AGENT_ID"
Write-Host "Central via relay: $env:MASTER_API_URL"
Write-Host "ComfyUI: $env:COMFY_API_URL"
& $VenvPython (Join-Path $Root "comfy_agent\agent_main.py")
