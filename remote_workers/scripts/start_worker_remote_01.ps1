param(
    [string]$Python = "",
    [switch]$UpdateDeps,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$EnvFile = Join-Path $Root "env\worker_remote_01.relay.env"
$ArgsList = @("-EnvFile", $EnvFile)

if ($Python) {
    $ArgsList += @("-Python", $Python)
}
if ($UpdateDeps) {
    $ArgsList += "-UpdateDeps"
}
if ($SkipInstall) {
    $ArgsList += "-SkipInstall"
}

& (Join-Path $PSScriptRoot "start_relay.ps1") @ArgsList

